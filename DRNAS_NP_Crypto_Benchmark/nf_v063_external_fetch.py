#!/usr/bin/env python3
"""NeuroFlow 0.6.3 — fetch fixed-seed existing CNFs from TWO independent publishers.

Publisher A: Tractables/cnfs (LGSynth89, ISCAS85, ISCAS89 and feature-models).
Publisher B: Byt-wyze-technology/sat-instances-library (separate authored SAT set).
File candidates are fixed BEFORE any SAT solver is used. Git commit immutable.
No DRNAS synthetic formulas, no SATLIB, and no post-result cherry-picking.
"""
import csv,hashlib,json,lzma,random,time,urllib.request
from pathlib import Path
from drnas_np_lab import read_dimacs

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'nf063_external'
GROUPS=[
 dict(group='LGSynth89',repo='Tractables/cnfs',folder='LGSynth89',ext='.cnf',minimum=400,maximum=60000,count=12,kind='logic-synthesis circuits'),
 dict(group='ISCAS85',repo='Tractables/cnfs',folder='iscas85b',ext='.cnf',minimum=500,maximum=120000,count=8,kind='combinational hardware'),
 dict(group='ISCAS89',repo='Tractables/cnfs',folder='iscas89',ext='.cnf',minimum=400,maximum=50000,count=12,kind='sequential hardware'),
 dict(group='FeatureModels',repo='Tractables/cnfs',folder='feature-models',ext='.cnf.xz',minimum=150,maximum=16000,count=12,kind='software feature models (SAT abstraction of counting CNF)'),
 dict(group='BytWyze',repo='Byt-wyze-technology/sat-instances-library',folder='instances',ext='.cnf',minimum=500,maximum=40000,count=16,kind='third-party generated SAT benchmarks'),
]

def get_bytes(url,limit=5000000):
    error=None
    for attempt in range(4):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'DRNAS-NP-Lab-external-research','Accept':'application/vnd.github+json'})
            with urllib.request.urlopen(req,timeout=35) as f:
                content=f.read(limit+1)
                if len(content)>limit:raise ValueError('file too large: '+url)
                return content
        except Exception as exc:
            error=exc;time.sleep(1.5*(attempt+1))
    raise RuntimeError(f'Failed fetching {url}: {error}')

def json_url(url):
    return json.loads(get_bytes(url,limit=2500000))

def build():
    OUT.mkdir(exist_ok=True);records=[];refs={}
    repos=sorted(set(g['repo'] for g in GROUPS))
    for repo in repos:
        d=json_url(f'https://api.github.com/repos/{repo}/commits/HEAD')
        refs[repo]=d['sha']
        print('SOURCE PIN',repo,refs[repo],flush=True)
    for i,g in enumerate(GROUPS):
        repo=g['repo'];sha=refs[repo]
        directory=json_url(f"https://api.github.com/repos/{repo}/contents/{g['folder']}?ref={sha}")
        options=sorted([v for v in directory if v['type']=='file'
            and v['name'].endswith(g['ext'])
            and g['minimum']<=v['size']<=g['maximum']],key=lambda v:v['name'])
        if len(options)<g['count']:raise AssertionError('Insufficient source candidates '+g['group'])
        selection=sorted(random.Random(20261031+i*991).sample(options,g['count']),key=lambda v:v['name'])
        for item in selection:
            path=item['path']
            url=f'https://raw.githubusercontent.com/{repo}/{sha}/{path}'
            raw=get_bytes(url,limit=2000000)
            raw_sha=hashlib.sha256(raw).hexdigest()
            try:
                content=lzma.decompress(raw) if path.endswith('.xz') else raw
                if len(content)>3500000:raise ValueError('decompressed size > 3.5 MiB')
                dest=OUT/(f"external_{len(records)+1:03d}.cnf")
                dest.write_bytes(content)
                n,clauses=read_dimacs(dest)
                if not clauses:raise ValueError('no clauses')
                canon=(f'c canonical CNF from {repo}/{path} (source preserved by hash)\n'
                      +f'p cnf {n} {len(clauses)}\n'
                      +''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
                dest.write_text(canon,encoding='utf-8')
                assert read_dimacs(dest)==(n,clauses)
                status='READY';detail=''
            except Exception as exc:
                status='PARSE_ERROR';detail=str(exc)[:200]
                if 'dest' in locals():dest.unlink(missing_ok=True)
            record=dict(case_id=f'external_{len(records)+1:03d}',source_group=g['group'],
              source_type=g['kind'],publisher=repo,repo_commit_sha=sha,path=path,
              source_url=url,source_sha256=raw_sha,source_size=len(raw),
              canonical_sha256=hashlib.sha256(dest.read_bytes()).hexdigest() if status=='READY' else '',
              variables=n if status=='READY' else '',clauses=len(clauses) if status=='READY' else '',
              fetch_status=status,detail=detail)
            records.append(record)
        print('SELECTED',g['group'],g['count'],'valid',sum(x['fetch_status']=='READY' for x in records if x['source_group']==g['group']),flush=True)
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    (OUT/'source_revisions.json').write_text(json.dumps(refs,indent=2))
    assert len(records)==sum(x['count'] for x in GROUPS)==60
    print('CORPUS',len(records),'sources; parsed=',sum(r['fetch_status']=='READY' for r in records),flush=True)

if __name__=='__main__':build()
