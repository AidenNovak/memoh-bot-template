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
