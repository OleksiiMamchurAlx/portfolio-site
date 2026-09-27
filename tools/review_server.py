"""Serve one immutable public build for browser review on loopback only.

Browsers must receive page assets to display a site. This server cannot prevent a
visitor from saving those assets, but it accepts no uploads or server-side writes.
"""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

from publication_guard import Blocked, scan

ROOT = Path(__file__).resolve().parents[1]
BASE = '/portfolio-site/'
ALLOWED_EXTENSIONS = {'.html', '.css', '.js', '.json', '.py', '.md'}
MAX_FILE_BYTES = 1_000_000
MAX_BUILD_BYTES = 5_000_000


def load_public_build(root):
    root = root.resolve(strict=True)
    assets = {}
    total = 0
    for path in root.rglob('*'):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise Blocked('REVIEW_SYMLINK')
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise Blocked('REVIEW_FILE_SIZE')
        scan(rel, data)
        assets[rel] = data
        total += len(data)
    if total > MAX_BUILD_BYTES or 'index.html' not in assets:
        raise Blocked('REVIEW_BUILD_INVALID')
    return assets


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = 'PortfolioReview'
    sys_version = ''

    def __init__(self, *args, assets, **kwargs):
        self.assets = assets
        super().__init__(*args, **kwargs)

    def _asset(self):
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment or not parsed.path.startswith(BASE):
            return None
        rel = parsed.path[len(BASE):]
        if not rel or rel.endswith('/'):
            rel += 'index.html'
        if ('%' in rel or '\\' in rel or '\x00' in rel
                or any(not part or part in {'.', '..'} or part.startswith('.')
                       for part in rel.split('/'))):
            return None
        return rel if rel in self.assets else None

    def _serve(self, send_body):
        name = self._asset()
        if name is None:
            self.send_error(404, 'Not found')
            return
        body = self.assets[name]
        content_type = mimetypes.guess_type(name)[0] or 'text/plain'
        if name.endswith(('.html', '.css', '.js', '.json', '.py', '.md')):
            content_type += '; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def do_GET(self):
        self._serve(True)

    def do_HEAD(self):
        self._serve(False)

    def _deny_method(self):
        self.send_response(405)
        self.send_header('Allow', 'GET, HEAD')
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = _deny_method

    def send_response(self, code, message=None):
        self.response_code = code
        return super().send_response(code, message)

    def log_message(self, format, *args):
        # Do not copy paths or query strings into logs.
        print(f'{self.client_address[0]} {self.command} {getattr(self, "response_code", "pending")}', flush=True)


def make_server(root=ROOT / 'dist', port=8786):
    assets = load_public_build(Path(root))
    server = ThreadingHTTPServer(('127.0.0.1', port), partial(ReviewHandler, assets=assets))
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT / 'dist')
    parser.add_argument('--port', type=int, default=8786)
    args = parser.parse_args()
    with make_server(args.root, args.port) as server:
        print(f'Review only: http://127.0.0.1:{server.server_port}{BASE}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
