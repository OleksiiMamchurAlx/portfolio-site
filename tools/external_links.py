"""Bounded, anonymous HTTP checks for approved rendered links; no arbitrary web crawl."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from publication_guard import Blocked


def allowed_url(url):
    if not isinstance(url,str) or re.search(r'[\s\\%]',url):
        raise Blocked('EXTERNAL_URL_DENIED')
    parsed=urlsplit(url)
    if (parsed.scheme!='https' or parsed.netloc not in {'github.com','oleksiimamchuralx.github.io'}
            or parsed.query or not re.fullmatch(r'/[A-Za-z0-9_./-]*',parsed.path)
            or '//' in parsed.path or any(x in {'.','..'} for x in parsed.path.split('/'))):
        raise Blocked('EXTERNAL_URL_DENIED')
    if parsed.netloc=='github.com':
        prefix='/OleksiiMamchurAlx'
        if parsed.path!=prefix and not parsed.path.startswith(prefix+'/'):
            raise Blocked('EXTERNAL_URL_DENIED')
    elif not parsed.path.startswith('/portfolio-site/'):
        raise Blocked('EXTERNAL_URL_DENIED')
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))


class ApprovedRedirects(HTTPRedirectHandler):
    max_redirections=3
    max_repeats=2

    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # Check before following, not after sending an unintended request.
        return super().redirect_request(req,fp,code,msg,headers,allowed_url(newurl))


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls=set()

    def handle_starttag(self,tag,attrs):
        # A new page's canonical URL cannot return 200 until this build is deployed.
        if tag=='link' and any(k=='rel' and 'canonical' in v.split() for k,v in attrs if v):
            return
        for key,value in attrs:
            if key!='href' or not value or value.startswith(('data:','#')): continue
            if urlsplit(value).scheme or value.startswith('//'):
                self.urls.add(allowed_url(value))


def collect(root):
    parser=Links()
    pages=list(Path(root).rglob('*.html'))
    if not pages: raise Blocked('EXTERNAL_NO_PAGES')
    for page in pages: parser.feed(page.read_text(encoding='utf-8'))
    if not parser.urls or len(parser.urls)>64: raise Blocked('EXTERNAL_LINK_COUNT')
    return sorted(parser.urls)


def probe(url,opener=None,sleeper=time.sleep):
    url=allowed_url(url)
    opener=opener or build_opener(ApprovedRedirects())
    for attempt in range(3):
        try:
            request=Request(url,headers={'User-Agent':'portfolio-link-check','Accept':'text/html'})
            with opener.open(request,timeout=10) as response:
                final=allowed_url(response.geturl())
                if response.status!=200: raise Blocked('EXTERNAL_HTTP_STATUS')
                response.read(1)  # Status/reachability check, not content ingestion.
                return {'url':url,'final_url':final,'status':response.status}
        except HTTPError as error:
            if error.code!=429 and not 500<=error.code<=599:
                raise Blocked('EXTERNAL_HTTP_FAILURE') from None
        except (URLError,TimeoutError,OSError):
            pass
        if attempt<2: sleeper(attempt+1)
    raise Blocked('EXTERNAL_TRANSPORT_UNAVAILABLE')


def verify(root):
    results=[probe(url) for url in collect(root)]
    return {'status':'PASS','checked':len(results),'scope':'anonymous HTTP 200; allowlisted redirects only','links':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('dist'))
    args=parser.parse_args()
    try:
        print(json.dumps(verify(args.root),sort_keys=True))
    except Blocked as error:
        print(json.dumps({'status':'BLOCKED','reason':str(error)}))
        raise SystemExit(1)
