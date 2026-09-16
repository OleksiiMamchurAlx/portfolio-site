"""Compare the deployed receipt to the exact built artifact, not just HTTP 200."""
import argparse
import json
from pathlib import Path
import time
from urllib.request import urlopen

def verify(url, expected):
    if not url.startswith('https://oleksiimamchuralx.github.io/portfolio-site'):
        raise ValueError('UNEXPECTED_PAGES_ORIGIN')
    with urlopen(url.rstrip('/')+'/receipt.json',timeout=15) as r: actual=json.load(r)
    if actual!=expected: raise ValueError('DEPLOY_RECEIPT_MISMATCH')
    with urlopen(url.rstrip('/')+'/',timeout=15) as r: page=r.read(200000).decode()
    if 'Oleksii Mamchur' not in page or 'Reliable work.' not in page: raise ValueError('SITE_SMOKE_FAILED')
    return {'status':'PASS','live_url':url,'receipt':actual}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--receipt',default='dist/receipt.json');a=p.parse_args()
    expected=json.loads(Path(a.receipt).read_text(encoding='utf-8'))
    for attempt in range(12):
        try:
            print(json.dumps(verify(a.url,expected)));break
        except Exception:
            if attempt==11: raise
            time.sleep(5)
