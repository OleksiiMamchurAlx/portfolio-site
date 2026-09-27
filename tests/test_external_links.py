import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError,URLError
from urllib.request import Request
from test_site import site
from publication_guard import Blocked
import external_links as links


class ExternalLinkTests(unittest.TestCase):
    url='https://github.com/OleksiiMamchurAlx/adaptive-ai-router-demo'

    def response(self,url=None,status=200):
        response=Mock()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        response.status=status
        response.geturl.return_value=url or self.url
        return response

    def test_allowlist_accepts_owner_and_canonical_pages(self):
        for url in [self.url,'https://github.com/OleksiiMamchurAlx','https://oleksiimamchuralx.github.io/portfolio-site/qa/#future-rd']:
            self.assertEqual(links.allowed_url(url),url.split('#')[0])

    def test_urls_cannot_escape_allowlist(self):
        denied=['http://github.com/OleksiiMamchurAlx','https://github.com/another-owner/project',
                'https://github.com/OleksiiMamchurAlx-evil/project',
                'https://github.com:443/OleksiiMamchurAlx/project','https://github.com/OleksiiMamchurAlx/../other',
                'https://github.com/OleksiiMamchurAlx/%2e%2e/other','https://github.com/OleksiiMamchurAlx//other',
                'https://oleksiimamchuralx.github.io/portfolio-site-other/',
                self.url+'?redirect=external','https://example.org/', '//github.com/OleksiiMamchurAlx']
        for url in denied:
            with self.subTest(url=url),self.assertRaises(Blocked): links.allowed_url(url)

    def test_denied_redirect_blocked_before_follow(self):
        handler=links.ApprovedRedirects()
        with self.assertRaises(Blocked):
            handler.redirect_request(Request(self.url),None,302,'redirect',{},'https://example.org/')

    def test_anonymous_get_status_and_small_read(self):
        opener=Mock(); response=self.response();opener.open.return_value=response
        self.assertEqual(links.probe(self.url,opener)['status'],200)
        request=opener.open.call_args.args[0]
        self.assertFalse(request.has_header('Authorization'))
        response.read.assert_called_once_with(1)

    def test_wrong_final_host_is_not_success(self):
        opener=Mock();opener.open.return_value=self.response('https://example.org/')
        with self.assertRaises(Blocked): links.probe(self.url,opener)

    def test_http_404_not_success_or_retried(self):
        opener=Mock();opener.open.side_effect=HTTPError(self.url,404,'missing',{},io.BytesIO())
        with self.assertRaises(Blocked): links.probe(self.url,opener)
        self.assertEqual(opener.open.call_count,1)

    def test_transient_retry_is_bounded_and_can_recover(self):
        opener=Mock();opener.open.side_effect=[URLError('fixture'),self.response()]
        sleeper=Mock()
        self.assertEqual(links.probe(self.url,opener,sleeper)['status'],200)
        self.assertEqual(opener.open.call_count,2)
        sleeper.assert_called_once_with(1)

    def test_exhausted_retries_fail_closed(self):
        opener=Mock();opener.open.side_effect=URLError('fixture')
        with self.assertRaises(Blocked): links.probe(self.url,opener,Mock())
        self.assertEqual(opener.open.call_count,3)

    def test_rendered_links_deduplicated_and_internal_checker_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);site.render([site.read_cache(k) for k in site.project_repos()],root)
            site.check_links(root)
            urls=links.collect(root)
            self.assertEqual(len(urls),len(set(urls)))
            self.assertIn(self.url,urls)
            self.assertIn(self.url+'/blob/'+site.read_cache('router')['source_commit']+'/docs/FUTURE_RD_METHOD.md',urls)

    def test_new_page_canonical_url_is_not_probed_before_deployment(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'index.html').write_text(
                '<link rel="canonical" href="https://oleksiimamchuralx.github.io/portfolio-site/projects/">'
                f'<a href="{self.url}">Source</a>', encoding='utf-8')
            self.assertEqual(links.collect(directory), [self.url])

    def test_unapproved_rendered_link_prevents_any_probe(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(links,'probe') as probe:
            (Path(directory)/'index.html').write_text('<a href="https://example.org/">fixture</a>')
            with self.assertRaises(Blocked): links.verify(Path(directory))
            probe.assert_not_called()


if __name__=='__main__': unittest.main()
