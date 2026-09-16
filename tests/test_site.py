import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import importlib.util
spec=importlib.util.spec_from_file_location('portfolio_site',Path(__file__).resolve().parents[1]/'tools/site.py')
site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
from publication_guard import Blocked,scan

class SiteTests(unittest.TestCase):
    def setUp(self):
        self.records=[site.read(site.ROOT/'content/projects'/f'{k}.json') for k in site.REPOS]
    def test_valid_schema(self):
        for r in self.records: site.validate_record(r)
    def test_unreviewed_claim(self):
        bad=copy.deepcopy(self.records[0]);bad['project']['skills_demonstrated'].append('Unverified expert')
        with self.assertRaises(Blocked): site.validate_record(bad)
    def test_private_source(self):
        bad=copy.deepcopy(self.records[0]);bad['source_repository']='private/control'
        with self.assertRaises(Blocked): site.validate_record(bad)
    def test_build_and_links(self):
        with tempfile.TemporaryDirectory() as d:
            receipt=site.render(self.records,Path(d))
            self.assertEqual(len(list(Path(d).rglob('index.html'))),8)
            site.check_links(Path(d))
            self.assertEqual(receipt['sources']['router']['verified_at'],self.records[0]['project']['verification']['verified_at'])
    def test_failed_build_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);site.render(self.records,out);old=(out/'index.html').read_bytes()
            bad=copy.deepcopy(self.records);bad[0]['project']['title']='New unsupported claim'
            with self.assertRaises(Blocked): site.render(bad,out)
            self.assertEqual((out/'index.html').read_bytes(),old)
    def test_content_hash_stable_across_builds(self):
        with tempfile.TemporaryDirectory() as d:
            a=site.render(self.records,Path(d)/'a');b=site.render(self.records,Path(d)/'b')
            self.assertEqual(a['content_hash'],b['content_hash'])
    def test_secret_block(self):
        with self.assertRaises(Blocked): scan('fixture.txt',('gh'+'p_'+'x'*30).encode())
    def test_pii_block(self):
        with self.assertRaises(Blocked): scan('fixture.txt',('private'+'@'+'example.com').encode())
    def test_private_path_block(self):
        with self.assertRaises(Blocked): scan('fixture.txt',('C'+':'+chr(92)+'Users'+chr(92)+'Fixture').encode())
    def test_external_host_denied(self):
        with self.assertRaises(Blocked): site.fetch('https://example.org/private')
    def test_boolean_test_count_rejected(self):
        bad=copy.deepcopy(self.records[0]);bad['project']['verification']['tests_passed']=True
        with self.assertRaises(Blocked): site.validate_record(bad)

    def reconciliation_fixture(self, destination):
        receipt=site.render(self.records,destination,'a'*40)
        live={p.relative_to(destination).as_posix():p.read_bytes() for p in destination.rglob('*') if p.is_file()}
        return receipt,live

    def test_identical_live_output_is_noop_even_with_new_build_time(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); receipt,live=self.reconciliation_fixture(out)
            receipt['built_at']='new build, not new verification'
            self.assertFalse(site.needs_deployment(out,receipt,live.__getitem__))

    def test_site_code_change_cannot_be_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); receipt,live=self.reconciliation_fixture(out)
            receipt['site_commit']='b'*40
            self.assertTrue(site.needs_deployment(out,receipt,live.__getitem__))

    def test_missed_source_update_requires_deploy(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); receipt,live=self.reconciliation_fixture(out)
            receipt['sources']['router']['commit']='b'*40
            self.assertTrue(site.needs_deployment(out,receipt,live.__getitem__))

    def test_broken_page_or_css_not_mistaken_for_noop(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); receipt,live=self.reconciliation_fixture(out)
            for name in ('style.css','qa/index.html','content.json'):
                corrupted=dict(live); corrupted[name]=b'broken'
                self.assertTrue(site.needs_deployment(out,receipt,corrupted.__getitem__))

    def test_unavailable_live_site_requires_deploy(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); receipt,_=self.reconciliation_fixture(out)
            def unavailable(name): raise OSError('unavailable')
            self.assertTrue(site.needs_deployment(out,receipt,unavailable))

if __name__=='__main__': unittest.main()
