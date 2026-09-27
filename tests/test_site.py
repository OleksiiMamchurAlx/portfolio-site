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
        self.records=[site.read_cache(k) for k in site.project_repos()]
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
            self.assertEqual(len(list(Path(d).rglob('index.html'))),9)
            site.check_links(Path(d))
            self.assertEqual(receipt['sources']['router']['verified_at'],self.records[0]['project']['verification']['verified_at'])
            projects=(Path(d)/'projects/index.html').read_text(encoding='utf-8')
            self.assertIn('AIQ / Portfolio Publisher',projects)
            self.assertIn('Computational engineering research',projects)
            self.assertNotIn('private/control',projects)
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

    def with_research(self):
        records=copy.deepcopy(self.records)
        records[0]['research']=site.read(site.ROOT/'policies/router.json')['approved_research']
        return records

    def test_future_rd_only_on_secondary_lenses(self):
        with tempfile.TemporaryDirectory() as d:
            records=self.with_research();out=Path(d);site.render(records,out)
            for lens in ('reliability','qa'):
                page=(out/lens/'index.html').read_text(encoding='utf-8')
                self.assertIn('Future Automation R&amp;D',page)
                self.assertIn('Research / architecture planning',page)
            self.assertNotIn('Future Automation', (out/'index.html').read_text())

    def test_raw_chat_private_ids_and_unreviewed_research_blocked(self):
        for field,value in [('messages',[{'role':'user','content':'private fixture'}]),('run_id','fixture'),('summary','A shipped commercial game'),('schema_version',True)]:
            records=self.with_research();records[0]['research'][field]=value
            with self.assertRaises(Blocked): site.validate_record(records[0])

    def test_research_cannot_import_private_source(self):
        records=self.with_research();records[0]['research']['evidence_links']=['private/control']
        with self.assertRaises(Blocked): site.validate_record(records[0])

    def test_research_changes_content_hash_and_keeps_noop(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);without=copy.deepcopy(self.records);without[0].pop('research',None)
            old=site.render(without,out,'a'*40)
            new=site.render(self.with_research(),out,'a'*40)
            self.assertNotEqual(old['content_hash'],new['content_hash'])
            live={p.relative_to(out).as_posix():p.read_bytes() for p in out.rglob('*') if p.is_file()}
            self.assertFalse(site.needs_deployment(out,new,live.__getitem__))

if __name__=='__main__': unittest.main()
