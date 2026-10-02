"""Dependency-free WebSocket transport for Memoh's native web chat endpoint."""
import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import time
import uuid
from urllib.parse import urlsplit


class ChatSocket:
    def __init__(self, client, bot_id):
        url = urlsplit(client.base_url)
        self.sock = socket.create_connection((url.hostname, url.port or (443 if url.scheme == 'https' else 80)), timeout=15)
        if url.scheme == 'https':
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=url.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        path = url.path.rstrip('/') + '/bots/' + bot_id + '/web/ws'
        request = ('GET ' + path + ' HTTP/1.1\r\nHost: ' + url.netloc + '\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                   'Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + key + '\r\nAuthorization: Bearer ' + client.token + '\r\n\r\n')
        self.sock.sendall(request.encode())
        self.buffer = b''
        while b'\r\n\r\n' not in self.buffer:
            self.buffer += self.sock.recv(4096)
        header, self.buffer = self.buffer.split(b'\r\n\r\n', 1)
        accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if b' 101 ' not in header or accept.lower() not in header.lower():
            self.sock.close()
            raise RuntimeError('Memoh WebSocket handshake failed')
        self.sock.settimeout(.25)

    def send(self, value, opcode=1):
        raw = json.dumps(value, ensure_ascii=False).encode() if opcode == 1 else value
        length = len(raw)
        header = bytes([0x80 | opcode, 0x80 | (length if length < 126 else 126 if length < 65536 else 127)])
        if length >= 126:
            header += struct.pack('!H' if length < 65536 else '!Q', length)
        mask = os.urandom(4)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(raw)))

    def receive(self):
        # Preserve incomplete frames across timeouts and answer server keepalives.
        while True:
            if len(self.buffer) >= 2:
                opcode = self.buffer[0] & 15
                length = self.buffer[1] & 127
                offset = 2
                if length in (126, 127):
                    count = 2 if length == 126 else 8
                    if len(self.buffer) < offset + count:
                        length = None
                    else:
                        length = int.from_bytes(self.buffer[offset:offset+count], 'big')
                        offset += count
                if length is not None and len(self.buffer) >= offset + length:
                    payload, self.buffer = self.buffer[offset:offset+length], self.buffer[offset+length:]
                    if opcode == 9:
                        self.send(payload, 10)
                        continue
                    if opcode == 8:
                        raise RuntimeError('Memoh closed the chat connection')
                    if opcode == 1:
                        return json.loads(payload)
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError('Memoh closed the chat connection')
            self.buffer += chunk

    def close(self):
        try:
            self.send(b'', 8)
        finally:
            self.sock.close()


def answer(client, bot_id, text, expected):
    started = time.monotonic()
    sessions = client.request('GET', '/bots/' + bot_id + '/sessions').get('items', [])
    session_id = sessions[0]['id'] if sessions else ''
    ws = ChatSocket(client, bot_id)
    try:
        if session_id:
            ws.send({'type': 'runtime_subscribe', 'session_id': session_id})
        ws.send({'type': 'message', 'session_id': session_id, 'invocation_id': str(uuid.uuid4()), 'text': text})
        deadline = time.monotonic() + 180
        next_read = 0
        while time.monotonic() < deadline:
            try:
                event = ws.receive()
                if event.get('session_id'):
                    session_id = event['session_id']
                if event.get('type') in ['error', 'run_rejected']:
                    raise RuntimeError('Memoh chat error: ' + str((event.get('feedback') or {}).get('code', event.get('code', 'stream_error'))))
            except socket.timeout:
                pass
            if time.monotonic() >= next_read:
                next_read = time.monotonic() + .5
                if not session_id:
                    sessions = client.request('GET', '/bots/' + bot_id + '/sessions').get('items', [])
                    session_id = sessions[0]['id'] if sessions else ''
                if not session_id:
                    continue
                history = client.request('GET', '/bots/' + bot_id + '/messages?session_id=' + session_id + '&limit=100')['items']
                turns = [t for t in history if t.get('role') == 'assistant']
                if len(turns) >= expected:
                    latest = max(turns, key=lambda t: t.get('turn_position', t.get('timestamp', '')))
                    content = latest.get('text') or '\n'.join(m.get('content', '') for m in latest.get('messages', []) if m.get('type') == 'text')
                    if content:
                        return content, round(time.monotonic() - started, 2)
        raise RuntimeError('No persisted assistant answer within 180 seconds')
    finally:
        ws.close()



def turn_text(turn):
    """Read only persisted public text, excluding reasoning and tool payloads."""
    return turn.get('text') or '\n'.join(m.get('content', '') for m in turn.get('messages', []) if m.get('type') == 'text')


class ChatConversation:
    """Keep one explicit session and wait for a matching completed invocation."""
    def __init__(self, client, bot_id):
        self.client, self.bot_id = client, bot_id
        if client.request('GET', '/bots/' + bot_id + '/sessions').get('items'):
            raise ValueError('Multiturn evaluation requires a new disposable Bot')
        self.ws = ChatSocket(client, bot_id)
        self.session_id = ''
        self.subscribed = False
        self.receipts = []

    def send(self, text):
        started = time.monotonic()
        invocation = str(uuid.uuid4())
        expected = len(self.receipts) + 1
        run_id, status = '', ''
        self.ws.send({'type': 'message', 'session_id': self.session_id,
                      'invocation_id': invocation, 'text': text})
        deadline, next_read, next_session_read = time.monotonic() + 180, 0, 0
        while time.monotonic() < deadline:
            try:
                event = self.ws.receive()
                received_session = event.get('session_id')
                if received_session:
                    if self.session_id and received_session != self.session_id:
                        raise RuntimeError('Conversation unexpectedly changed session')
                    self.session_id = received_session
                if event.get('type') in ['error', 'run_rejected']:
                    raise RuntimeError('Memoh rejected this chat turn')
                for payload in [event.get('snapshot') or {}, event.get('delta') or {}]:
                    view = payload.get('current_run_view') or {}
                    if view.get('invocation_id') == invocation:
                        run_id, status = view.get('run_id', ''), view.get('status', '')
                    patch = payload.get('run') or {}
                    if run_id and patch.get('run_id') == run_id and patch.get('status'):
                        status = patch['status']
                if status in ['failed', 'aborted', 'lost']:
                    raise RuntimeError('Native runtime ended without a completed reply: ' + status)
            except socket.timeout:
                pass
            if not self.session_id and time.monotonic() >= next_session_read:
                next_session_read = time.monotonic() + .5
                sessions = self.client.request('GET', '/bots/' + self.bot_id + '/sessions')['items']
                if len(sessions) > 1:
                    raise RuntimeError('A new evaluation Bot unexpectedly has multiple sessions')
                if sessions:
                    self.session_id = sessions[0]['id']
            if self.session_id and not self.subscribed:
                self.ws.send({'type': 'runtime_subscribe', 'session_id': self.session_id})
                self.subscribed = True
            if status == 'completed' and self.session_id and time.monotonic() >= next_read:
                next_read = time.monotonic() + .4
                history = self.history()
                users = sorted([t for t in history if t.get('role') == 'user'], key=lambda t: t['turn_position'])
                assistants = sorted([t for t in history if t.get('role') == 'assistant'], key=lambda t: t['turn_position'])
                if len(users) != expected or len(assistants) != expected:
                    continue
                user, assistant = users[-1], assistants[-1]
                content = turn_text(assistant)
                if turn_text(user) != text or user['turn_id'] != assistant['turn_id']:
                    raise RuntimeError('Persisted reply does not match the submitted turn')
                if not content:
                    continue
                receipt = {'turn': expected, 'user': text, 'assistant': content,
                           'seconds': round(time.monotonic() - started, 2), 'characters': len(content),
                           'session_sha256': hashlib.sha256(self.session_id.encode()).hexdigest(),
                           'user_sha256': hashlib.sha256(text.encode()).hexdigest(),
                           'assistant_sha256': hashlib.sha256(content.encode()).hexdigest(),
                           'turn_position': user['turn_position'], 'persisted_user_turns': len(users),
                           'persisted_assistant_turns': len(assistants), 'runtime_completed': True}
                self.receipts.append(receipt)
                return receipt
        raise RuntimeError('No completed, matching persisted reply within 180 seconds')

    def history(self):
        return self.client.request('GET', '/bots/' + self.bot_id + '/messages?session_id=' + self.session_id + '&limit=100')['items']

    def verify(self):
        history = self.history()
        users = sorted([t for t in history if t.get('role') == 'user'], key=lambda t: t['turn_position'])
        assistants = sorted([t for t in history if t.get('role') == 'assistant'], key=lambda t: t['turn_position'])
        if len(users) != len(self.receipts) or len(assistants) != len(self.receipts):
            raise RuntimeError('Unexpected extra or missing persisted chat turns')
        for user, assistant, receipt in zip(users, assistants, self.receipts):
            if turn_text(user) != receipt['user'] or turn_text(assistant) != receipt['assistant']:
                raise RuntimeError('Final persisted chat differs from recorded replies')
        sessions = self.client.request('GET', '/bots/' + self.bot_id + '/sessions')['items']
        if len(sessions) != 1 or sessions[0]['id'] != self.session_id:
            raise RuntimeError('Expected exactly one unchanged chat session')
        return True

    def close(self):
        self.ws.close()
