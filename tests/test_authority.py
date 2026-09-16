"""Offline contract tests; source-resolution fixtures do not claim real executions."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_site import site
from publication_guard import Blocked,canonical


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.records=[site.read_cache(k) for k in site.project_repos()]

    def source_fixture(self,sha='f'*40,protected=True,private=False):
        repo=site.project_repos()['router']
        policy=site.read(site.ROOT/'policies/router.json')
        files={name:b'fixture' for name in policy['allowed_files']}
        files['publication-policy.json']=canonical(policy)
        files['project.json']=canonical(self.records[0]['project'])
        files['projects/future-unreal-automation-rd.json']=canonical(policy['approved_research'])
        tree={'truncated':False,'tree':[{'path':name,'type':'blob','mode':'100644',
              'sha':hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()}
              for name,body in files.items()]}
        def fetch(url):
            if url=='https://api.github.com/repos/'+repo:
                return canonical({'private':private,'full_name':repo})
            if url=='https://api.github.com/repos/'+repo+'/branches/main':
                return canonical({'name':'main','protected':protected,'commit':{'sha':sha}})
            if url=='https://api.github.com/repos/'+repo+'/git/trees/'+sha+'?recursive=1':
                return canonical(tree)
            prefix='https://raw.githubusercontent.com/'+repo+'/'+sha+'/'
            if url.startswith(prefix): return files[url[len(prefix):]]
            self.fail('Unexpected or unpinned source request')
        return fetch

    def test_registry_is_single_admission_list(self):
        value=site.registry()
        self.assertEqual(site.project_repos(),{k:v['repository'] for k,v in value['projects'].items()})
        schema=site.read(site.ROOT/'schemas/registry.schema.json')
        self.assertEqual(set(schema['required']),set(value))
        for config in value['projects'].values():
            self.assertEqual(set(schema['properties']['projects']['additionalProperties']['required']),set(config))
        self.assertFalse((site.ROOT/'content/sources.json').exists())

    def test_registry_rejects_malformed_or_duplicate_entries(self):
        original=site.registry()
        values=[]
        for key,val in [('tracking','arbitrary-branch'),('fallback_commit','latest'),('repository','another-owner/project')]:
            bad=copy.deepcopy(original);bad['projects']['router'][key]=val;values.append(bad)
        bad=copy.deepcopy(original);bad['schema_version']=True;values.append(bad)
        bad=copy.deepcopy(original);bad['projects']['graphics']['repository']=bad['projects']['router']['repository'];values.append(bad)
        for bad in values:
            with self.subTest(value=bad),patch.object(site,'read',return_value=bad):
                with self.assertRaises(Blocked): site.registry()

    def test_unregistered_repo_rejected_before_network(self):
        with patch.object(site,'fetch') as fetch:
            with self.assertRaises(Blocked): site.snapshot('new-repository',refresh=True)
            fetch.assert_not_called()
        bad=copy.deepcopy(self.records[0]);bad['source_repository']='OleksiiMamchurAlx/new-repository'
        with self.assertRaises(Blocked): site.validate_record(bad)

    def test_fetched_protected_main_pins_all_reads_and_receipt(self):
        # Only manifest validation is stubbed: these bytes test resolution, not evidence validity.
        with patch.object(site,'fetch',side_effect=self.source_fixture()) as fetch,patch.object(site,'validate') as gate:
            current=site.snapshot('router',refresh=True)
            gate.assert_called_once()
            branches=[x for x in fetch.call_args_list if x.args[0].endswith('/branches/main')]
            self.assertEqual(len(branches),1)
        self.assertEqual(current['source_commit'],'f'*40)
        self.assertNotEqual(current['source_commit'],site.registry()['projects']['router']['fallback_commit'])
        with tempfile.TemporaryDirectory() as directory:
            records=[current,self.records[1]]
            receipt=site.render(records,Path(directory),'a'*40)
            for record in records:
                self.assertEqual(receipt['sources'][record['project']['project_id']]['commit'],record['source_commit'])
            self.assertEqual(json.loads((Path(directory)/'content.json').read_text())[0]['source_commit'],'f'*40)

    def test_unprotected_or_private_source_fails_before_tree(self):
        for kwargs in [{'protected':False},{'protected':1},{'private':True},{'private':None}]:
            with self.subTest(kwargs=kwargs),patch.object(site,'fetch',side_effect=self.source_fixture(**kwargs)) as fetch:
                with self.assertRaises(Blocked): site.snapshot('router',refresh=True)
                self.assertFalse(any('/git/trees/' in x.args[0] for x in fetch.call_args_list))

    def test_stale_cache_never_overrides_fresh_sync(self):
        stale=site.read_cache('router')
        with patch.object(site,'fetch',side_effect=self.source_fixture()),patch.object(site,'validate'):
            current=site.snapshot('router',refresh=True)
        self.assertNotEqual(stale['source_commit'],current['source_commit'])
        with patch.object(site,'snapshot',side_effect=[current,self.records[1]]),patch.object(site,'read_cache') as cache:
            self.assertEqual(site.resolve_records(sync=True)[0]['source_commit'],'f'*40)
            cache.assert_not_called()

    def test_live_failure_does_not_fall_back(self):
        with patch.object(site,'snapshot',side_effect=OSError('fixture unavailable')),patch.object(site,'read_cache') as cache:
            with self.assertRaises(OSError): site.resolve_records(sync=True)
            cache.assert_not_called()

    def test_frozen_mode_is_explicit_and_not_live_reconciliation(self):
        sha=site.registry()['projects']['router']['fallback_commit']
        with patch.object(site,'fetch',side_effect=self.source_fixture(sha)) as fetch,patch.object(site,'validate'):
            self.assertEqual(site.snapshot('router',refresh=False)['source_commit'],sha)
            self.assertFalse(any(x.args[0].endswith('/branches/main') for x in fetch.call_args_list))
        for sync,freeze in [(False,False),(True,True),(False,True)]:
            with self.assertRaises(Blocked): site.validate_build_mode(sync,freeze,True)
        site.validate_build_mode(True,False,True)

    def test_cache_marker_required_and_never_published(self):
        for key in site.project_repos():
            self.assertEqual(site.read(site.ROOT/'content/projects'/f'{key}.json')['$comment'],site.CACHE_NOTICE)
            self.assertNotIn('$comment',site.read_cache(key))
        original_read=site.read
        def missing_marker(path):
            value=original_read(path)
            if path.parent.name=='projects': value.pop('$comment',None)
            return value
        with patch.object(site,'read',side_effect=missing_marker):
            with self.assertRaises(Blocked): site.read_cache('router')

    def test_duplicate_or_missing_sources_cannot_forge_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            for bad in [self.records[:1],[self.records[0],self.records[0]]]:
                with self.assertRaises(Blocked): site.render(bad,Path(directory))

    def test_future_rd_remains_off_other_lenses(self):
        with tempfile.TemporaryDirectory() as directory:
            site.render(self.records,Path(directory))
            for slug in ['', 'systems','graphics','about','contact']:
                self.assertNotIn('Future Automation', (Path(directory)/slug/'index.html').read_text(encoding='utf-8'))


if __name__=='__main__': unittest.main()
