"""Loopback-only preview matching the Pages subdirectory."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

class Preview(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(Path(__file__).resolve().parents[1]/'dist'),**kwargs)
    def translate_path(self,path):
        if path.startswith('/portfolio-site/'):
            path=path[len('/portfolio-site'):]
        return super().translate_path(path)

if __name__=='__main__':
    print('Preview: http://127.0.0.1:8786/portfolio-site/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8786),Preview).serve_forever()
