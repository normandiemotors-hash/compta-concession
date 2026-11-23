"""Serveur HTTP (stdlib) : dispatch, sessions, CSRF, en-tetes de securite."""
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import db, security, web

STATIC_FILES = {
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/static/logo.png": ("logo.png", "image/png"),
}

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"


class Context:
    def __init__(self, db_path, static_dir):
        self.db_path = db_path
        self.static_dir = static_dir
        self.router = web.Router()


def make_context(db_path, static_dir):
    return Context(db_path, static_dir)


def make_handler(ctx):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ComptaConcession/1.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def _send(self, resp):
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(resp.body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            for k, v in resp.headers.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD" and resp.body:
                self.wfile.write(resp.body)

        def _serve_static(self, req):
            entry = STATIC_FILES.get(req.path)
            if not entry:
                return web.Response("", 404, "text/plain; charset=utf-8")
            filename, ctype = entry
            path = os.path.join(ctx.static_dir, filename)
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                return web.Response("", 404, "text/plain; charset=utf-8")
            return web.Response(data, 200, ctype)

        def _handle(self):
            req = web.Request(self)
            try:
                if req.path in STATIC_FILES:
                    return self._send(self._serve_static(req))
                if req.path == "/favicon.ico":
                    return self._send(web.Response("", 204, "text/plain; charset=utf-8"))
                route = ctx.router.match(req.method, req.path)
                if route is None:
                    return self._send(web.Response("<h1>404 - page introuvable</h1>", 404))
                handler, auth, params = route
                conn = db.connect(ctx.db_path)
                try:
                    session = security.get_session(conn, req.cookies.get("session"))
                    if session:
                        req.session = session
                        req.user = session
                    if auth != "public":
                        if req.user is None:
                            return self._send(web.redirect("/login", "Veuillez vous connecter."))
                        if auth == "admin" and req.user["role"] != "admin":
                            return self._send(web.Response("<h1>403 - reserve aux administrateurs</h1>", 403))
                        if req.method == "POST" and not security.csrf_ok(req):
                            return self._send(web.Response("<h1>403 - jeton CSRF invalide</h1>", 403))
                    resp = handler(req, ctx, conn, **params)
                finally:
                    conn.close()
            except Exception:
                traceback.print_exc()
                resp = web.Response("<h1>500 - erreur interne (voir la console)</h1>", 500)
            self._send(resp)

    return Handler


def run(ctx, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(ctx))
    return httpd
