import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('candidate_site', ROOT / 'tools' / 'site.py')
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)
from native_demo import fetch_reviewed_bundle, verify_bundle
from publication_guard import Blocked


class ReviewedDemoTests(unittest.TestCase):
    def setUp(self):
        self.files = {
            'web/README.md': b'# Small checked demo\n',
            'web/index.html': b'<!doctype html><a href="./README.md">Reproduce</a>',
        }
        self.policy = copy.deepcopy(site.read(ROOT / 'policies/router.json'))
        self.policy['approved_web_demo'] = {
            'entry': 'web/index.html', 'files': sorted(self.files)}
        self.policy['allowed_files'] += sorted(self.files)
        self.policy['reviewed_hashes'].update({name: hashlib.sha256(data).hexdigest()
                                                for name, data in self.files.items()})
        self.records = [site.read_cache(key) for key in site.project_repos()]
        self.router = next(r for r in self.records if r['project']['project_id'] == 'router')

    def test_public_bundle_must_match_reviewed_hashes_and_paths(self):
        self.assertEqual(2, verify_bundle(self.policy, self.files)['file_count'])
        damaged = dict(self.files, **{'web/index.html': b'unreviewed output'})
        with self.assertRaisesRegex(Blocked, 'WEB_DEMO_HASH_MISMATCH'):
            verify_bundle(self.policy, damaged)
        extra = dict(self.files, **{'web/private.txt': b'unreviewed'})
        with self.assertRaisesRegex(Blocked, 'WEB_DEMO_UNREVIEWED_BUNDLE'):
            verify_bundle(self.policy, extra)

    def test_fetch_uses_exact_public_source_commit_and_built_card_links_to_it(self):
        observed = []
        def fetcher(url):
            observed.append(url)
            return self.files[url.rsplit('/', 2)[-2] + '/' + url.rsplit('/', 1)[-1]]
        bundle = fetch_reviewed_bundle(self.router, self.policy, fetcher)
        self.assertEqual(self.files, bundle)
        self.assertTrue(all('/' + self.router['source_commit'] + '/web/' in url for url in observed))

        original_read = site.read
        def reviewed_read(path):
            return self.policy if path == ROOT / 'policies/router.json' else original_read(path)
        with tempfile.TemporaryDirectory() as directory, patch.object(site, 'read', side_effect=reviewed_read):
            destination = Path(directory)
            receipt = site.render(self.records, destination, demo_assets=bundle)
            self.assertEqual(bundle['web/index.html'], (destination / 'router-demo/index.html').read_bytes())
            self.assertEqual(2, receipt['reviewed_demo']['file_count'])
            html = (destination / 'index.html').read_text(encoding='utf-8')
            self.assertIn('/portfolio-site/router-demo/', html)
            self.assertIn(self.router['source_commit'] + '/web/README.md', html)

    def test_unreviewed_policy_cannot_enable_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(Blocked, 'WEB_DEMO_UNREVIEWED_BUNDLE'):
                site.render(self.records, Path(directory), demo_assets=self.files)

    def test_stale_demo_files_cannot_survive_a_new_build(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'router-demo'
            old.mkdir()
            (old / 'unreviewed.html').write_text('stale')
            with self.assertRaisesRegex(Blocked, 'STALE_DEMO_OUTPUT'):
                site.render(self.records, Path(directory))

    def test_reviewed_demo_noop_requires_served_asset_bytes_to_match(self):
        original_read = site.read
        def reviewed_read(path):
            return self.policy if path == ROOT / 'policies/router.json' else original_read(path)
        with tempfile.TemporaryDirectory() as directory, patch.object(site, 'read', side_effect=reviewed_read):
            destination = Path(directory)
            receipt = site.render(self.records, destination, 'a' * 40, self.files)
            live = {p.relative_to(destination).as_posix(): p.read_bytes()
                    for p in destination.rglob('*') if p.is_file()}
            same_content_new_build = dict(receipt, built_at='later build time')
            self.assertFalse(site.needs_deployment(destination, same_content_new_build, live.__getitem__))
            live['router-demo/index.html'] = b'corrupt or stale'
            self.assertTrue(site.needs_deployment(destination, same_content_new_build, live.__getitem__))


if __name__ == '__main__':
    unittest.main()
