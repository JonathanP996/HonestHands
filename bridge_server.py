"""Localhost server the browser extension talks to. Never touches the internet.
The extension sends {text, site, url}; we return {verdict, reason, rule, quote, active}.
All intelligence stays here in the app — the extension only reports and obeys."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 7673
HOST = '127.0.0.1'


class _Handler(BaseHTTPRequestHandler):
    app = None  # set by start()

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        # Only the known AI sites may call us; still, localhost-only + CORS for browser fetch.
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send({}, 204)

    def do_GET(self):
        # Health/status: is the guard live right now (app running + session on)?
        if self.path == '/status':
            if _Handler.app:
                _Handler.app.note_extension_ping()
            active = _Handler.app.extension_active() if _Handler.app else False
            self._send({'ok': True, 'active': active})
        else:
            self._send({'ok': True})

    def do_POST(self):
        if self.path != '/check':
            self._send({'error': 'unknown endpoint'}, 404)
            return
        try:
            n = int(self.headers.get('Content-Length') or 0)
            data = json.loads(self.rfile.read(n).decode() or '{}')
        except Exception:
            self._send({'error': 'bad request'}, 400)
            return
        app = _Handler.app
        if app is not None:
            app.note_extension_ping()
        if app is None or not app.extension_active():
            # App off or no session -> the extension must do NOTHING.
            self._send({'active': False, 'verdict': 'allow'})
            return
        try:
            result = app.extension_check(data.get('text', ''), data.get('site', ''), data.get('url', ''))
            result['active'] = True
            self._send(result)
        except Exception as e:
            # Fail safe: on an internal error, allow (never freeze the user's browser).
            self._send({'active': True, 'verdict': 'allow', 'error': str(e)})

    def log_message(self, *a):
        pass  # silence default logging


def start(app):
    _Handler.app = app
    srv = ThreadingHTTPServer((HOST, PORT), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv
