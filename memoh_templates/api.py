"""Memoh HTTP client. Credentials stay in memory, never in logs or backups."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler


class APIError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, base_url, token="", timeout=120):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API 地址必须是 http(s) URL，不能包含凭据、查询或片段")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.opener = build_opener(NoRedirect)

    def request(self, method, path, data=None):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if data is not None:
            headers["Content-Type"] = "application/json"
        raw = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        req = Request(self.base_url + path, data=raw, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                content = response.read()
                return json.loads(content) if content else {}
        except HTTPError as exc:
            # Server errors can echo supplied credentials. Never print their bodies.
            raise APIError(exc.code, f"Memoh {method} {path.split('?')[0]} 返回 HTTP {exc.code}") from None
        except (URLError, TimeoutError) as exc:
            raise APIError(0, "无法连接 Memoh，或请求超时；写请求结果可能未知，请先检查目标 Bot") from None

    def login(self, username, password):
        result = self.request("POST", "/auth/login", {"username": username, "password": password})
        self.token = result["access_token"]

    def contract(self):
        for path in ("/api/swagger.json", "/swagger.json", "/swagger/doc.json"):
            try:
                result = self.request("GET", path)
                if "paths" in result and "definitions" in result:
                    return result
            except APIError as exc:
                if exc.status not in (404, 405):
                    raise
        raise APIError(404, "实例没有可读取的 OpenAPI 文档，请使用当前 Memoh 上游版本")
