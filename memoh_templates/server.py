"""Loopback-only preset picker and API proxy, using Python's standard library."""
import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .api import Client
from .apply import apply_template
from .bundle import bundle
from .catalog import ROOT, load


def serve(port=8765, open_browser=False):
    state = {"client": None}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def local_request(self):
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in hosts:
                return False
            origin = self.headers.get("Origin")
            return not origin or origin in {"http://" + h for h in hosts}

        def send(self, status, data, content_type="application/json; charset=utf-8", filename=None):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.local_request():
                return self.send(403, {"error": "只允许本机请求"})
            path = urlsplit(self.path).path
            static = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8"), "/catalog.json": ("catalog.json", "application/json; charset=utf-8")}
            try:
                if path in static:
                    name, content_type = static[path]
                    return self.send(200, (ROOT / "web" / name).read_bytes(), content_type)
                if re.fullmatch(r'/assets/avatars/[a-z0-9-]+\.jpg', path):
                    return self.send(200, (ROOT / path.lstrip('/')).read_bytes(), 'image/jpeg')
                if path.startswith("/api/template/"):
                    return self.send(200, load(path.rsplit("/", 1)[1]))
                if path.startswith("/download/"):
                    slug = path.rsplit("/", 1)[1]
                    return self.send(200, bundle(load(slug)), "application/zip", slug + ".memoh.zip")
                if path == "/api/bots":
                    if state["client"] is None:
                        return self.send(401, {"error": "请先连接 Memoh"})
                    return self.send(200, state["client"].request("GET", "/bots"))
                return self.send(404, {"error": "找不到页面"})
            except (ValueError, RuntimeError) as exc:
                return self.send(400, {"error": str(exc)})

        def do_POST(self):
            if not self.local_request() or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(403, {"error": "只允许本机 JSON 请求"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError("请求大小不正确")
                data = json.loads(self.rfile.read(length))
                if not lock.acquire(blocking=False):
                    return self.send(409, {"error": "正在处理另一个操作，请稍候"})
                try:
                    if self.path == "/api/connect":
                        client = Client(data["url"], data.get("token", ""))
                        if not client.token:
                            client.login(data.get("username", "admin"), data["password"])
                        bots = client.request("GET", "/bots")
                        state["client"] = client
                        return self.send(200, bots)
                    if self.path == "/api/apply":
                        if state["client"] is None:
                            raise ValueError("请先连接 Memoh")
                        result = apply_template(state["client"], load(data["template"]), data["bot_id"],
                                                data.get("parameters"), data.get("settings"), ROOT / ".backups", data.get("dry_run", False),data.get('customization'))
                        return self.send(200, result)
                    if self.path == "/api/export":
                        item = load(data["template"])
                        return self.send(200, bundle(item, data.get("parameters"), data.get("settings"),data.get('customization')), "application/zip", item["id"] + ".memoh.zip")
                    return self.send(404, {"error": "找不到操作"})
                finally:
                    lock.release()
            except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                return self.send(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"模板选择页：http://127.0.0.1:{port}（退出 Ctrl+C）", flush=True)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
