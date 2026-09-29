"""Allowlist-first source manifest; synthetic test secrets are assembled at runtime."""
import argparse
import json
from pathlib import Path
import subprocess
from publication_guard import scan,digest,Blocked

ROOT=Path(__file__).resolve().parents[1]
ALLOW={'.gitattributes','.gitignore','AGENTS.md','README.md','PUBLICATION_MANIFEST.json',
       'assets/style.css','content/profile.json','content/experience.json','content/skills.json','content/related_work.json','content/cases/graphics-validation.json','portfolio_registry.json','SOURCE_OF_TRUTH.md',
       'content/projects/router.json','content/projects/graphics.json','policies/router.json','policies/graphics.json',
       'schemas/content.schema.json','schemas/registry.schema.json','tools/publication_guard.py','tools/site.py','tools/check.py','tools/preview.py','tools/review_server.py',
       'tools/external_links.py','tools/native_demo.py','tests/test_authority.py','tests/test_external_links.py','tests/test_native_demo_integration.py',
       'tools/smoke.py','tests/test_site.py','tests/test_review_server.py','.github/workflows/ci.yml','.github/workflows/pages.yml','.github/workflows/rollback.yml'}

def files():
    found={}
    for p in ROOT.rglob('*'):
        rel=p.relative_to(ROOT)
        if any(x in {'.git','__pycache__','dist','.sites-runtime','.snapshot-cache'} for x in rel.parts): continue
        if p.is_symlink(): raise Blocked('SYMLINK')
        if p.is_file():
            name=rel.as_posix()
            if name not in ALLOW: raise Blocked('FILE_NOT_ALLOWLISTED')
            scan(name,p.read_bytes()); found[name]=p.read_bytes()
    return found

def run(refresh=False):
    found=files()
    if set(found)-{'PUBLICATION_MANIFEST.json'}!=ALLOW-{'PUBLICATION_MANIFEST.json'}: raise Blocked('MISSING_FILES')
    entries=[{'path':n,'sha256':digest(b),'size_bytes':len(b),'source_artifact':'REVIEWED-PUBLIC-SITE',
        'sanitization_status':'SCAN_PASS','verification_status':'SOURCE_REVIEWED',
        'claim_category':'EXISTING_VERIFIED_PORTFOLIO','rights_note':'Owner-authored AI-assisted code; existing project rights retained'}
        for n,b in sorted(found.items()) if n!='PUBLICATION_MANIFEST.json']
    manifest={'schema':1,'excludes_self':True,'files':entries}
    if refresh:
        (ROOT/'PUBLICATION_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    elif json.loads(found['PUBLICATION_MANIFEST.json'])!=manifest: raise Blocked('MANIFEST_MISMATCH')
    return {'status':'PASS','files':len(ALLOW),'license_boundary':'Original site; no binaries or upstream graphics code'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');a=p.parse_args()
    print(json.dumps(run(a.refresh)))
