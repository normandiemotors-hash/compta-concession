"""Requetes/reponses et routeur, uniquement avec la bibliotheque standard."""
import html
import re
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, quote, urlparse


class Request:
    def __init__(self, handler):
        self.handler = handler
        self.method = handler.command
        parsed = urlparse(handler.path)
        self.path = parsed.path
        self.query = parse_qs(parsed.query)
        self.headers = handler.headers
        self.cookies = {}
        raw = handler.headers.get("Cookie")
        if raw:
            jar = SimpleCookie()
            try:
                jar.load(raw)
                self.cookies = {k: m.value for k, m in jar.items()}
            except Exception:
                self.cookies = {}
        self._body = None
        self.session = None
        self.user = None

    @property
    def body(self):
        if self._body is None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            self._body = self.handler.rfile.read(length) if length > 0 else b""
        return self._body

    @property
    def form(self):
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("application/x-www-form-urlencoded"):
            parsed = parse_qs(self.body.decode("utf-8", "replace"), keep_blank_values=True)
            return {k: v[0] for k, v in parsed.items()}
        return {}

    def q(self, name, default=""):
        vals = self.query.get(name)
        return vals[0] if vals else default


class Response:
    def __init__(self, body="", status=200, content_type="text/html; charset=utf-8", headers=None):
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.status = status
        self.content_type = content_type
        self.headers = dict(headers or {})


def redirect(location, msg=None, ok=None):
    if msg:
        sep = "&" if "?" in location else "?"
        location += f"{sep}msg={quote(msg)}"
        if ok is not None:
            location += f"&ok={1 if ok else 0}"
    return Response("", 303, headers={"Location": location})


def esc(value):
    return html.escape("" if value is None else str(value))


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, pattern, handler, auth="login"):
        regex = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")
        self.routes.append((method, regex, handler, auth))

    def match(self, method, path):
        for m, regex, handler, auth in self.routes:
            if m != method:
                continue
            mt = regex.match(path)
            if mt:
                return handler, auth, mt.groupdict()
        return None
