"""Static build from reviewed public sources and curated project summaries."""
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
from native_demo import fetch_reviewed_bundle, verify_bundle

ROOT=Path(__file__).resolve().parents[1]
BASE='/portfolio-site/'
CANONICAL_URL='https://oleksiimamchuralx.github.io/portfolio-site/'
CACHE_NOTICE='GENERATED SNAPSHOT / CACHE; NOT AUTHORITATIVE. Offline preview only; live builds resolve protected main through portfolio_registry.json.'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')

def registry():
    """The reviewed registry is the sole project admission list, not discovery."""
    value=read(ROOT/'portfolio_registry.json')
    if (set(value)!={'schema_version','canonical_url','projects'}
            or type(value['schema_version']) is not int or value['schema_version']!=1
            or value['canonical_url']!=CANONICAL_URL
            or not isinstance(value['projects'],dict) or not value['projects']):
        raise Blocked('REGISTRY_SCHEMA')
    repos=set()
    for key,item in value['projects'].items():
        if (not re.fullmatch('[a-z][a-z0-9-]*',key) or not isinstance(item,dict)
                or set(item)!={'repository','tracking','fallback_commit'}
                or item['tracking']!='protected-main'
                or not isinstance(item['repository'],str)
                or not re.fullmatch(r'OleksiiMamchurAlx/[A-Za-z0-9_-]+',item['repository'])
                or not isinstance(item['fallback_commit'],str)
                or not re.fullmatch('[0-9a-f]{40}',item['fallback_commit'])
                or item['repository'] in repos):
            raise Blocked('REGISTRY_ENTRY')
        repos.add(item['repository'])
    return value

def project_repos():
    return {key:item['repository'] for key,item in registry()['projects'].items()}

def related_work():
    """Read editorial summaries only; never connect to a private project source."""
    value=read(ROOT/'content/related_work.json')
    if (set(value)!={'schema_version','reviewed_at','notice','projects'}
            or value['schema_version']!=1 or not isinstance(value['projects'],list)):
        raise Blocked('RELATED_WORK_SCHEMA')
    ids=set()
    for item in value['projects']:
        if (not isinstance(item,dict)
                or set(item)!={'id','title','track','state','summary','boundary'}
                or not all(isinstance(v,str) and v.strip() for v in item.values())
                or not re.fullmatch('[a-z][a-z0-9-]*',item['id'])
                or item['id'] in ids):
            raise Blocked('RELATED_WORK_ENTRY')
        ids.add(item['id'])
    scan('related_work.json',canonical(value))
    return value


def graphics_case():
    """Reviewed derived evidence, separate from the two public project metrics."""
    value=read(ROOT/'content/cases/graphics-validation.json')
    required={'schema_version','id','title','reviewed_at','summary','ownership','method',
              'profiles','comparison','verification','source_records','limits',
              'hiring_relevance','public_evidence_status'}
    if (set(value)!=required or type(value['schema_version']) is not int
            or value['schema_version']!=1 or value['id']!='graphics-configuration-validation'):
        raise Blocked('GRAPHICS_CASE_SCHEMA')
    for key in ('title','reviewed_at','summary','ownership','public_evidence_status'):
        if not isinstance(value[key],str) or not value[key].strip():
            raise Blocked('GRAPHICS_CASE_TEXT')
    for key in ('method','limits','hiring_relevance'):
        if (not isinstance(value[key],list) or not value[key]
                or not all(isinstance(x,str) and x.strip() for x in value[key])):
            raise Blocked('GRAPHICS_CASE_TEXT')
    if (not isinstance(value['profiles'],list) or len(value['profiles'])!=3
            or {p.get('id') for p in value['profiles']}!={'baseline','variant','diagnostic'}):
        raise Blocked('GRAPHICS_CASE_PROFILES')
    for p in value['profiles']:
        if (set(p)!={'id','label','sha256'} or not isinstance(p['label'],str)
                or not re.fullmatch('[0-9a-f]{64}',p['sha256'])):
            raise Blocked('GRAPHICS_CASE_PROFILES')
    if not isinstance(value['source_records'],list) or not value['source_records']:
        raise Blocked('GRAPHICS_CASE_SOURCES')
    for source in value['source_records']:
        if (set(source)!={'label','sha256'} or not isinstance(source['label'],str)
                or not re.fullmatch('[0-9a-f]{64}',source['sha256'])):
            raise Blocked('GRAPHICS_CASE_SOURCES')
    c=value['comparison']; v=value['verification']
    if set(c)!={'changed','unchanged','diagnostic_changed','diagnostic_unchanged','scope'}:
        raise Blocked('GRAPHICS_CASE_COMPARISON')
    counts={'receipt_members_matched','receipt_members_expected','package_members_matched',
            'package_members_expected','archive_members_matched','archive_members_expected',
            'historical_function_tests','historical_installer_cases','historical_installer_shells'}
    if set(v)!=counts|{'observed_at','scope','historical_function_tests_rerun'}:
        raise Blocked('GRAPHICS_CASE_VERIFICATION')
    if (any(type(c[k]) is not int or c[k]<0 for k in set(c)-{'scope'})
            or any(type(v[k]) is not int or v[k]<0 for k in counts)
            or v['historical_function_tests_rerun'] is not False):
        raise Blocked('GRAPHICS_CASE_COUNTS')
    if any(v[f'{group}_members_matched']>v[f'{group}_members_expected']
           for group in ('receipt','package','archive')):
        raise Blocked('GRAPHICS_CASE_COUNTS')
    scan('content/cases/graphics-validation.json',canonical(value))
    return value

def read_cache(project):
    if project not in project_repos(): raise Blocked('SOURCE_REPO_DENIED')
    value=read(ROOT/'content/projects'/f'{project}.json')
    if value.pop('$comment',None)!=CACHE_NOTICE: raise Blocked('CACHE_NOTICE_REQUIRED')
    validate_record(value)
    if value['project']['project_id']!=project: raise Blocked('CACHE_PROJECT_MISMATCH')
    return value

def resolve_records(sync=False,freeze=False):
    if freeze and not sync: raise Blocked('FREEZE_REQUIRES_SYNC')
    # An upstream error propagates. Never fall back to cache on a live sync failure.
    return [snapshot(key,refresh=not freeze) if sync else read_cache(key)
            for key in project_repos()]

def validate_build_mode(sync,freeze,reconcile):
    if reconcile and (not sync or freeze): raise Blocked('LIVE_SYNC_REQUIRED')

def fetch(url):
    if not url.startswith(('https://api.github.com/repos/OleksiiMamchurAlx/','https://raw.githubusercontent.com/OleksiiMamchurAlx/')):
        raise Blocked('SOURCE_HOST_DENIED')
    with urlopen(Request(url,headers={'User-Agent':'portfolio-public-sync','Accept':'application/vnd.github+json'}),timeout=30) as response:
        value=response.read(1_000_001)
    if len(value)>1_000_000:
        raise Blocked('SOURCE_SIZE')
    return value

def snapshot(project,refresh=False):
    admitted=registry()['projects']
    if project not in admitted: raise Blocked('SOURCE_REPO_DENIED')
    config=admitted[project]
    repo=config['repository']
    sha=config['fallback_commit']
    if refresh:
        metadata=json.loads(fetch('https://api.github.com/repos/'+repo))
        if metadata.get('private') is not False or metadata.get('full_name')!=repo:
            raise Blocked('PRIVATE_SOURCE_DENIED')
        branch=json.loads(fetch('https://api.github.com/repos/'+repo+'/branches/main'))
        if branch.get('name')!='main' or branch.get('protected') is not True:
            raise Blocked('PROTECTED_MAIN_REQUIRED')
        # Resolve once; all tree/blob reads and the receipt use this exact observed SHA.
        sha=branch['commit']['sha']
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
    if set(record)-{'research'}!={'content_schema_version','source_repository','source_commit','manifest_sha256','project'} or type(record['content_schema_version']) is not int or record['content_schema_version']!=1:
        raise Blocked('SITE_SCHEMA')
    p=record['project']; project=p['project_id']
    repos=project_repos()
    if project not in repos or record['source_repository']!=repos[project]:
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

def render(records, destination, site_commit='local-preview', demo_assets=None):
    for record in records: validate_record(record)
    if len(records)!=len(project_repos()) or {r['project']['project_id'] for r in records}!=set(project_repos()):
        raise Blocked('INCOMPLETE_OR_DUPLICATE_SOURCES')
    demo_provenance = None
    if demo_assets is not None:
        router = next(r for r in records if r['project']['project_id'] == 'router')
        demo_provenance = verify_bundle(read(ROOT/'policies/router.json'), demo_assets)
        demo_provenance['source_commit'] = router['source_commit']
    profile=read(ROOT/'content/profile.json'); experience=read(ROOT/'content/experience.json')
    skills=read(ROOT/'content/skills.json')
    curated=related_work()
    graphics=graphics_case()
    e=lambda x:html.escape(str(x),quote=True)
    nav=[('','Overview'),('projects/','All Projects'),('reliability/','Reliability'),('qa/','QA'),('systems/','Systems'),('graphics/','Graphics R&D'),('evidence/','Evidence'),('about/','About'),('contact/','Contact')]
    links=''.join(f'<a href="{BASE}{p}">{e(n)}</a>' for p,n in nav)
    def card(r):
        p=r['project']; v=p['verification']; repo='https://github.com/'+r['source_repository']
        demo_links = ''
        if p['project_id'] == 'router' and demo_provenance is not None:
            exact = repo + '/blob/' + r['source_commit'] + '/'
            demo_links = f'''<p><a href="{BASE}router-demo/">Try bounded demo</a> ·
<a href="{exact}web/index.html">View source</a> ·
<a href="{exact}web/README.md">Reproduce</a> ·
<a href="{exact}PUBLICATION_MANIFEST.json">Evidence</a> ·
<a href="{BASE}router-demo/#limits">Limits</a></p>'''
        if p['project_id']=='graphics':
            demo_links=f'<p><a href="{BASE}cases/graphics-configuration-validation/">Read the configuration validation case</a></p>'
        return f'''<article class="project"><div class="eyebrow">{e(' / '.join(p['category']))}</div>
<h2><a href="{repo}">{e(p['title'])}</a></h2><p>{e(' · '.join(p['technology']))}</p>
<p class="metric"><strong>{v['tests_passed']}</strong> passing public-code tests</p>
<ul>{''.join('<li>'+e(s)+'</li>' for s in p['skills_demonstrated'])}</ul>
<details><summary>Evidence, ownership & limits</summary><p>Project owner; AI-assisted implementation, testing and documentation.</p>
<p>Verification scope: {e(v['scope'])}. Last tested: <time>{e(v['verified_at'])}</time>.</p>
<p><a href="{repo}/tree/{r['source_commit']}">Exact published revision</a> · <a href="{repo}/blob/{r['source_commit']}/PUBLICATION_MANIFEST.json">File manifest</a></p>
<ul>{''.join('<li>'+e(s)+'</li>' for s in p['limitations'])}</ul></details>{demo_links}</article>'''
    all_cards=''.join(card(r) for r in records)
    def research_section():
        sections=[]
        for r in records:
            if 'research' not in r: continue
            item=r['research']; repo='https://github.com/'+r['source_repository']
            proof=repo+'/blob/'+r['source_commit']+'/'+item['evidence_links'][0]
            sections.append(f'<section class="note" aria-labelledby="future-rd"><h2 id="future-rd">Future Automation R&amp;D</h2><h3>{e(item["title"])}</h3><p><strong>{e(item["status"])}</strong></p><p>{e(item["summary"])}</p><p>{e(item["role"])}</p><p><a href="{e(proof)}">Planning evidence and method</a> · Summary updated {e(item["updated_at"])}</p><details><summary>Scope, AI use and limitations</summary><p>{e(item["ai_disclosure"])}</p><ul>'+''.join('<li>'+e(s)+'</li>' for s in item['limitations'])+'</ul></details></section>')
        return ''.join(sections)
    overview=f'<section class="hero"><p class="eyebrow">{e(profile["location"])}</p><h1>Test the change.<br>Explain the result.</h1><p class="lead">{e(profile["headline"])}</p><p>{e(profile["summary"])}</p><a class="cta" href="{BASE}qa/">Explore QA evidence</a> <a class="cta secondary" href="{BASE}systems/">Explore systems experience</a></section><h2>Public source and demos</h2><section class="projects">{all_cards}</section><p><a href="{BASE}projects/">See all projects, local prototypes and research with their current status</a></p>'
    pages={'':('Engineering portfolio',overview)}
    case_link=f'<p><a href="{BASE}cases/graphics-configuration-validation/">Read the saved-profile validation case</a></p>'
    curated_cards=''.join(f'''<article class="project"><p class="eyebrow">{e(p['track'])}</p>
<h2>{e(p['title'])}</h2><p class="project-status">{e(p['state'])}</p>
<p>{e(p['summary'])}</p><details><summary>Scope and limits</summary><p>{e(p['boundary'])}</p></details>{case_link if p['id']=='stalker-fardetail' else ''}</article>'''
        for p in curated['projects'])
    pages['projects']=('All projects',f'''<h1>Projects and research</h1>
<p>Public source and live demonstrations appear first. Local and private work is summarized below with its review status; no private code or operational data is included.</p>
<h2>Public source and demos</h2><section class="projects">{all_cards}</section>
<h2>Local projects and research</h2><p class="note">{e(curated['notice'])} Reviewed {e(curated['reviewed_at'])}.</p>
<section class="projects">{curated_cards}</section>''')
    for lens in skills['lenses']:
        cards=''.join(card(r) for r in records if set(r['project']['category'])&set(lens['tags']))
        extra=('<p>Prior professional support work includes Windows endpoints, connected devices, local networks and technical documentation. Independent validation projects below show the same habits of fault isolation and checking results.</p>'
               f'<p><a href="{BASE}about/">Read the professional background</a></p>') if lens['id']=='systems' else ''
        research=research_section() if lens['id'] in {'reliability','qa'} else ''
        pages[lens['id']]=(lens['title'],f'<h1>{e(lens["title"])}</h1>{extra}<section class="projects">{cards}</section>{research}')
    pages['evidence']=('Evidence & Methods','<h1>Every number has a source.</h1><p>Public test results, immutable source revisions and explicit limitations. Build time is not test time. Synthetic graphics data is not a live-game benchmark.</p>'+all_cards+'<h2>Method</h2><p>Reviewed source → tests → exact manifest → public GitHub → validated site content. The website never reads private control repositories or local databases.</p>')
    pages['about']=('About & Experience',f'<h1>{e(profile["name"])}</h1><p>{e(profile["summary"])}</p><h2>QA and IT support</h2><p>I am interested in software QA and validation opportunities, alongside IT Support and Service Desk roles. My software testing examples are independent projects; my prior professional experience is in technical support and diagnostics.</p><h2>Professional background</h2><ul>'+''.join('<li>'+e(x)+'</li>' for x in experience['areas'])+f'</ul><p class="note">{e(experience["provenance"])}</p><h2>How I use AI</h2><p>{e(profile["ai_disclosure"])}</p><h2>Currently developing</h2><ul>'+''.join('<li>'+e(x)+'</li>' for x in experience['developing'])+f'</ul><p><a href="{BASE}contact/">Discuss an opportunity</a></p>')
    pages['contact']=('Contact',f'<h1>Let’s discuss the work.</h1><p>I am interested in QA, validation and IT support opportunities. Start with my GitHub profile to review the public projects, methods and source evidence.</p><a class="cta" href="{e(profile["github"])}">Oleksii Mamchur on GitHub</a><p><a href="{BASE}cases/graphics-configuration-validation/">Explore a validation case</a> · <a href="{BASE}about/">Read my background</a></p>')
    c=graphics['comparison']; v=graphics['verification']
    items=lambda rows:'<ul>'+''.join('<li>'+e(x)+'</li>' for x in rows)+'</ul>'
    rows=''.join(f'<tr><th scope="row">{e(p["label"])}</th><td><code>{e(p["sha256"])}</code></td></tr>' for p in graphics['profiles'])
    source_rows=''.join(f'<li>{e(s["label"])}: <code>{e(s["sha256"])}</code></li>' for s in graphics['source_records'])
    case_body=f'''<p class="eyebrow">QA case study · Windows configuration</p><h1>{e(graphics['title'])}</h1>
<p class="lead">{e(graphics['summary'])}</p><p>{e(graphics['ownership'])}</p>
<h2>Question and method</h2><p>What changed between the saved profiles, and what evidence is needed before claiming an improvement?</p>{items(graphics['method'])}
<h2>Saved-profile comparison</h2><p><strong>{c['changed']} changed</strong> and <strong>{c['unchanged']} unchanged</strong> settings between Beta 1.4 Normal.ini and Beta 1.5 Normal.ini. The Beta 1.5 Normal/Split diagnostic pair differs in {c['diagnostic_changed']} settings, with {c['diagnostic_unchanged']} unchanged.</p><p class="note">{e(c['scope'])}</p>
<div class="table-wrap"><table><caption>SHA-256 of the saved inputs</caption><thead><tr><th>Profile</th><th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>What was checked</h2><p>Audit observed {e(v['observed_at'])}.</p><ul><li>Saved evidence receipt: {v['receipt_members_matched']}/{v['receipt_members_expected']} file hashes matched.</li><li>Package manifest: {v['package_members_matched']}/{v['package_members_expected']} members matched; archive content: {v['archive_members_matched']}/{v['archive_members_expected']} matched.</li><li>Preserved FunctionPlan/comparison log: {v['historical_function_tests']} tests passed in the earlier run; not rerun in this audit.</li><li>Separate historical installer records: {v['historical_installer_cases']} scenarios in {v['historical_installer_shells']} PowerShell environments, not {v['historical_function_tests']} installer scenarios.</li></ul><p class="note">{e(v['scope'])}</p>
<h2>What this demonstrates</h2>{items(graphics['hiring_relevance'])}
<h2>Scope and open questions</h2>{items(graphics['limits'])}
<details><summary>Source-record fingerprints</summary><p>{e(graphics['public_evidence_status'])}</p><ul>{source_rows}</ul></details>
<p><a href="{BASE}cases/graphics-configuration-validation/evidence.json">Read the sanitized evidence summary (JSON)</a> · <a href="{BASE}graphics/">Public graphics utility and test evidence</a> · <a href="{BASE}projects/">All projects</a></p>'''
    pages['cases/graphics-configuration-validation']=(graphics['title'],case_body)
    if (destination/'router-demo').exists():
        raise Blocked('STALE_DEMO_OUTPUT')
    destination.mkdir(parents=True,exist_ok=True)
    write(destination/'cases/graphics-configuration-validation/evidence.json',graphics)
    if demo_assets is not None:
        for name, data in demo_assets.items():
            target = destination / 'router-demo' / name.removeprefix('web/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    css=(ROOT/'assets/style.css').read_text(encoding='utf-8')
    (destination/'style.css').write_text(css,encoding='utf-8')
    for slug,(title,body) in pages.items():
        target=destination/slug/'index.html'; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(f'''<!doctype html><html lang="en"><head><link rel="canonical" href="{CANONICAL_URL}{slug+'/' if slug else ''}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} — Oleksii Mamchur</title><meta name="description" content="Evidence-driven automation, QA and systems diagnostics portfolio."><link rel="stylesheet" href="{BASE}style.css"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%2315243c'/%3E%3Ctext x='5' y='23' fill='white' font-size='21'%3EOM%3C/text%3E%3C/svg%3E"></head><body><a class="skip" href="#main">Skip to content</a><header><a class="brand" href="{BASE}">OM<span>Oleksii Mamchur</span></a><nav aria-label="Main navigation">{links}</nav></header><main id="main">{body}</main><footer>Independent projects. AI-assisted engineering. Evidence before claims.<br><a href="{BASE}receipt.json">Build and source receipt</a></footer></body></html>''',encoding='utf-8')
    content_hash=digest(canonical({'public_records':records,'curated_projects':curated,
                                   'profile':profile,'experience':experience,'skills':skills,
                                   'graphics_case':graphics}))
    receipt={'schema':1,'site_commit':site_commit,'sources':{r['project']['project_id']:{'commit':r['source_commit'],'manifest_sha256':r['manifest_sha256'],'verified_at':r['project']['verification']['verified_at']} for r in records},'content_hash':content_hash,'curated_projects_sha256':digest(canonical(curated)),'built_at':datetime.now(timezone.utc).isoformat()}
    receipt['graphics_case_sha256']=digest(canonical(graphics))
    if demo_provenance is not None:
        receipt['reviewed_demo'] = demo_provenance
    write(destination/'receipt.json',receipt)
    write(destination/'content.json',records)
    (destination/'.nojekyll').touch()
    check_links(destination)
    return receipt

def check_links(root):
    for p in root.rglob('*.html'):
        for link in re.findall(r'href="([^"]+)"',p.read_text(encoding='utf-8')):
            if link.startswith(('https://','data:','#')): continue
            if link.startswith(BASE):
                target=root/link[len(BASE):].split('#',1)[0]
            elif p.is_relative_to(root/'router-demo') and link.startswith('./'):
                target=p.parent/link[2:].split('#',1)[0]
            else:
                raise Blocked('LINK_OUTSIDE_SITE')
            if not target.resolve().is_relative_to(root.resolve()): raise Blocked('LINK_OUTSIDE_SITE')
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
    validate_build_mode(args.sync,args.freeze,args.reconcile)
    records=resolve_records(args.sync,args.freeze)
    if args.sync:
        # Only the generated public schema enters content; remote code is not executed.
        for record in records: validate_record(record)
        for record in records: write(ROOT/'content/projects'/f'{record["project"]["project_id"]}.json',{'$comment':CACHE_NOTICE,**record})
    destination=ROOT/args.output
    demo_assets = None
    if args.sync and not args.freeze:
        router = next(r for r in records if r['project']['project_id'] == 'router')
        demo_assets = fetch_reviewed_bundle(router,read(ROOT/'policies/router.json'),fetch)
    receipt=render(records,destination,os.environ.get('GITHUB_SHA','local-preview'),demo_assets)
    deploy=needs_deployment(destination,receipt) if args.reconcile else True
    if args.reconcile and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as output:
            output.write('deploy_required='+str(deploy).lower()+'\n')
    print(json.dumps({'reconciliation':'DEPLOY_REQUIRED' if deploy else 'VERIFIED_NO_OP','receipt':receipt}))

if __name__=='__main__': main()
