import http.client
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from review_server import make_server


class ReviewServerTests(unittest.TestCase):
    def test_review_routes_are_read_only_and_snapshot_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<h1>Reviewed</h1>', encoding='utf-8')
            (root / 'private.db').write_bytes(b'not public')
            server = make_server(root, 0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                def request(method, path, body=None):
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                    connection.request(method, path, body=body)
                    response = connection.getresponse()
                    result = response.status, dict(response.getheaders()), response.read()
                    connection.close()
                    return result

                self.assertEqual(request('GET', '/portfolio-site/')[2], b'<h1>Reviewed</h1>')
                self.assertEqual(request('HEAD', '/portfolio-site/')[2], b'')
                self.assertEqual(request('POST', '/portfolio-site/', b'upload')[0], 405)
                self.assertEqual(request('GET', '/portfolio-site/private.db')[0], 404)
                self.assertEqual(request('GET', '/portfolio-site/%2e%2e/private.db')[0], 404)
                (root / 'index.html').write_text('<h1>Changed</h1>', encoding='utf-8')
                self.assertEqual(request('GET', '/portfolio-site/')[2], b'<h1>Reviewed</h1>')
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)
