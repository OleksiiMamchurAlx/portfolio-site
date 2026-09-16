"""Public GitHub-only static build. No private account credentials are read."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen
from publication_guard import Blocked, canonical, digest, scan, validate

ROOT=Path(__file__).resolve().parents[1]
BASE='/portfolio-site/'
REPOS={'router':'OleksiiMamchurAlx/adaptive-ai-router-demo','graphics':'OleksiiMamchurAlx/graphics-installer-validation'}

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')

def fetch(url):
    if not url.startswith(('https://api.github.com/repos/OleksiiMamchurAlx/','https://raw.githubusercontent.com/OleksiiMamchurAlx/')):
        raise Blocked('SOURCE_HOST_DENIED')
    with urlopen(Request(url,headers={'User-Agent':'portfolio-public-sync','Accept':'application/vnd.github+json'}),timeout=30) as response:
        value=response.read(1_000_001)
    if len(value)>1_000_000:
        raise Blocked('SOURCE_SIZE')
    return value

def snapshot(project,refresh=False):
    config=read(ROOT/'content/sources.json')[project]
    repo=config['repository']
    if repo!=REPOS[project]:
        raise Blocked('SOURCE_REPO_DENIED')
    sha=config['accepted_commit']
    if refresh:
        metadata=json.loads(fetch('https://api.github.com/repos/'+repo))
        if metadata['private']:
            raise Blocked('PRIVATE_SOURCE_DENIED')
        sha=json.loads(fetch('https://api.github.com/repos/'+repo+'/git/ref/heads/main'))['object']['sha']
    if not re.fullmatch('[0-9a-f]{40}',sha):
        raise Blocked('INVALID_SOURCE_SHA')
    policy=read(ROOT/'policies'/f'{project}.json')
    tree=json.loads(fetch('https://api.github.com/repos/'+repo+'/git/trees/'+sha+'?recursive=1'))
    blobs={x['path']:x for x in tree['tree'] if x['type']!='tree'}
    if tree.get('truncated') or set(blobs)!=set(policy['allowed_files']) or any(x['mode']!='100644' for x in blobs.values()):
        raise Blocked('UNREVIEWED_REMOTE_TREE')
    with tempfile.TemporaryDirectory(prefix='public-site-') as directory:
        dest=Path(directory)
        for name in policy['allowed_files']:
            value=fetch('https://raw.githubusercontent.com/'+repo+'/'+sha+'/'+name)
            if hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()!=blobs[name]['sha']:
                raise Blocked('REMOTE_BLOB_MISMATCH')
            target=dest/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(value)
        if read(dest/'publication-policy.json')!=policy:
            raise Blocked('POLICY_REVIEW_REQUIRED')
        validate(dest,policy)
        data=read(dest/'project.json'); manifest=digest((dest/'PUBLICATION_MANIFEST.json').read_bytes())
        research=read(dest/'projects/future-unreal-automation-rd.json') if 'approved_research' in policy else None
    record={'content_schema_version':1,'source_repository':repo,'source_commit':sha,
            'manifest_sha256':manifest,'project':data}
    if research is not None: record['research']=research
    validate_record(record)
    return record

def validate_record(record):
    if set(record)-{'research'}!={'content_schema_version','source_repository','source_commit','manifest_sha256','project'} or record['content_schema_version']!=1:
        raise Blocked('SITE_SCHEMA')
    p=record['project']; project=p['project_id']
    if project not in REPOS or record['source_repository']!=REPOS[project]:
        raise Blocked('SITE_SOURCE')
    from publication_guard import validate_project
    validate_project(p,read(ROOT/'policies'/f'{project}.json')['approved_project'])
    if 'research' in record:
        approved=read(ROOT/'policies'/f'{project}.json').get('approved_research')
        if project!='router' or not approved or canonical(record['research'])!=canonical(approved):
            raise Blocked('UNREVIEWED_RESEARCH')
    for name,length in [('source_commit',40),('manifest_sha256',64)]:
        if not re.fullmatch('[0-9a-f]{'+str(length)+'}',record[name]):
            raise Blocked('SITE_PROVENANCE')
    scan('record.json',canonical(record))

def render(records, destination, site_commit='local-preview'):
    for record in records: validate_record(record)
    profile=read(ROOT/'content/profile.json'); experience=read(ROOT/'content/experience.json')
    e=lambda x:html.escape(str(x),quote=True)
    nav=[('','Overview'),('reliability/','Reliability'),('qa/','QA'),('systems/','Systems'),('graphics/','Graphics R&D'),('evidence/','Evidence'),('about/','About'),('contact/','Contact')]
    links=''.join(f'<a href="{BASE}{p}">{e(n)}</a>' for p,n in nav)
    def card(r):
        p=r['project']; v=p['verification']; repo='https://github.com/'+r['source_repository']
        return f'''<article class="project"><div class="eyebrow">{e(' / '.join(p['category']))}</div>
<h2><a href="{repo}">{e(p['title'])}</a></h2><p>{e(' · '.join(p['technology']))}</p>
<p class="metric"><strong>{v['tests_passed']}</strong> passing public-code tests</p>
<ul>{''.join('<li>'+e(s)+'</li>' for s in p['skills_demonstrated'])}</ul>
<details><summary>Evidence, ownership & limits</summary><p>Project owner; AI-assisted implementation, testing and documentation.</p>
<p>Verification scope: {e(v['scope'])}. Last tested: <time>{e(v['verified_at'])}</time>.</p>
<p><a href="{repo}/tree/{r['source_commit']}">Exact published revision</a> · <a href="{repo}/blob/{r['source_commit']}/PUBLICATION_MANIFEST.json">File manifest</a></p>
<ul>{''.join('<li>'+e(s)+'</li>' for s in p['limitations'])}</ul></details></article>'''
    all_cards=''.join(card(r) for r in records)
    def research_section():
        sections=[]
        for r in records:
            if 'research' not in r: continue
            item=r['research']; repo='https://github.com/'+r['source_repository']
            proof=repo+'/blob/'+r['source_commit']+'/'+item['evidence_links'][0]
            sections.append(f'<section class="note" aria-labelledby="future-rd"><h2 id="future-rd">Future Automation R&amp;D</h2><h3>{e(item["title"])}</h3><p><strong>{e(item["status"])}</strong></p><p>{e(item["summary"])}</p><p>{e(item["role"])}</p><p><a href="{e(proof)}">Planning evidence and method</a> · Summary updated {e(item["updated_at"])}</p><details><summary>Scope, AI use and limitations</summary><p>{e(item["ai_disclosure"])}</p><ul>'+''.join('<li>'+e(s)+'</li>' for s in item['limitations'])+'</ul></details></section>')
        return ''.join(sections)
    overview=f'<section class="hero"><p class="eyebrow">{e(profile["location"])}</p><h1>Reliable work.<br>Visible evidence.</h1><p class="lead">{e(profile["headline"])}</p><p>{e(profile["summary"])}</p><a class="cta" href="{BASE}evidence/">Explore the evidence</a></section><section class="projects">{all_cards}</section>'
    pages={'':('Engineering portfolio',overview)}
    for lens in read(ROOT/'content/skills.json')['lenses']:
        cards=''.join(card(r) for r in records if set(r['project']['category'])&set(lens['tags']))
        extra='<p>Prior professional support background is separate from controlled project evidence.</p>' if lens['id']=='systems' else ''
        research=research_section() if lens['id'] in {'reliability','qa'} else ''
        pages[lens['id']]=(lens['title'],f'<h1>{e(lens["title"])}</h1>{extra}<section class="projects">{cards}</section>{research}')
    pages['evidence']=('Evidence & Methods','<h1>Every number has a source.</h1><p>Public test results, immutable source revisions and explicit limitations. Build time is not test time. Synthetic graphics data is not a live-game benchmark.</p>'+all_cards+'<h2>Method</h2><p>Reviewed source → tests → exact manifest → public GitHub → validated site content. The website never reads private control repositories or local databases.</p>')
    pages['about']=('About & Experience',f'<h1>{e(profile["name"])}</h1><p>{e(profile["summary"])}</p><h2>Professional background</h2><ul>'+''.join('<li>'+e(x)+'</li>' for x in experience['areas'])+f'</ul><p class="note">{e(experience["provenance"])}</p><h2>How I use AI</h2><p>{e(profile["ai_disclosure"])}</p><h2>Currently developing</h2><ul>'+''.join('<li>'+e(x)+'</li>' for x in experience['developing'])+'</ul>')
    pages['contact']=('Contact',f'<h1>Start with the work.</h1><p>Explore the projects, methods and source code on my GitHub profile.</p><a class="cta" href="{e(profile["github"])}">Oleksii Mamchur on GitHub</a>')
    destination.mkdir(parents=True,exist_ok=True)
    css=(ROOT/'assets/style.css').read_text(encoding='utf-8')
    (destination/'style.css').write_text(css,encoding='utf-8')
    for slug,(title,body) in pages.items():
        target=destination/slug/'index.html'; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} — Oleksii Mamchur</title><meta name="description" content="Evidence-driven automation, QA and systems diagnostics portfolio."><link rel="stylesheet" href="{BASE}style.css"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%2315243c'/%3E%3Ctext x='5' y='23' fill='white' font-size='21'%3EOM%3C/text%3E%3C/svg%3E"></head><body><a class="skip" href="#main">Skip to content</a><header><a class="brand" href="{BASE}">OM<span>Oleksii Mamchur</span></a><nav aria-label="Main navigation">{links}</nav></header><main id="main">{body}</main><footer>Independent projects. AI-assisted engineering. Evidence before claims.<br><a href="{BASE}receipt.json">Build and source receipt</a></footer></body></html>''',encoding='utf-8')
    content_hash=digest(canonical(records))
    receipt={'schema':1,'site_commit':site_commit,'sources':{r['project']['project_id']:{'commit':r['source_commit'],'manifest_sha256':r['manifest_sha256'],'verified_at':r['project']['verification']['verified_at']} for r in records},'content_hash':content_hash,'built_at':datetime.now(timezone.utc).isoformat()}
    write(destination/'receipt.json',receipt)
    write(destination/'content.json',records)
    (destination/'.nojekyll').touch()
    check_links(destination)
    return receipt

def check_links(root):
    for p in root.rglob('*.html'):
        for link in re.findall(r'href="([^"]+)"',p.read_text(encoding='utf-8')):
            if link.startswith(('https://','data:','#')): continue
            if not link.startswith(BASE): raise Blocked('LINK_OUTSIDE_SITE')
            target=root/link[len(BASE):]
            if target.is_dir(): target=target/'index.html'
            if not target.is_file(): raise Blocked('BROKEN_SITE_LINK')

def fetch_live(name):
    # Fixed public origin, never a user-controlled URL or a private repository.
    url='https://oleksiimamchuralx.github.io/portfolio-site/'+name
    with urlopen(Request(url,headers={'Cache-Control':'no-cache','User-Agent':'portfolio-reconciliation'}),timeout=15) as response:
        data=response.read(1_000_001)
    if len(data)>1_000_000: raise ValueError('LIVE_SIZE_LIMIT')
    return data

def needs_deployment(destination, receipt, fetcher=fetch_live):
    """Skip only if provenance AND every served artifact already match the build."""
    if not re.fullmatch('[0-9a-f]{40}',receipt['site_commit']):
        return True
    try:
        live=json.loads(fetcher('receipt.json'))
        if set(live)!=set(receipt): return True
        if {k:v for k,v in live.items() if k!='built_at'}!={k:v for k,v in receipt.items() if k!='built_at'}:
            return True
        for path in destination.rglob('*'):
            if path.is_file() and path.name not in {'receipt.json','.nojekyll'}:
                if fetcher(path.relative_to(destination).as_posix())!=path.read_bytes(): return True
        return False
    except (OSError,ValueError,KeyError):
        # Unavailable/stale/broken live output cannot suppress a verified deployment.
        return True

def main():
    p=argparse.ArgumentParser(); p.add_argument('--sync',action='store_true'); p.add_argument('--freeze',action='store_true'); p.add_argument('--output',default='dist'); p.add_argument('--reconcile',action='store_true')
    args=p.parse_args()
    if args.sync:
        records=[snapshot(k,refresh=not args.freeze) for k in REPOS]
        # Only the generated public schema enters content; remote code is not executed.
        for record in records: validate_record(record)
        for record in records: write(ROOT/'content/projects'/f'{record["project"]["project_id"]}.json',record)
    else:
        records=[read(ROOT/'content/projects'/f'{k}.json') for k in REPOS]
    destination=ROOT/args.output
    receipt=render(records,destination,os.environ.get('GITHUB_SHA','local-preview'))
    deploy=needs_deployment(destination,receipt) if args.reconcile else True
    if args.reconcile and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as output:
            output.write('deploy_required='+str(deploy).lower()+'\n')
    print(json.dumps({'reconciliation':'DEPLOY_REQUIRED' if deploy else 'VERIFIED_NO_OP','receipt':receipt}))

if __name__=='__main__': main()
