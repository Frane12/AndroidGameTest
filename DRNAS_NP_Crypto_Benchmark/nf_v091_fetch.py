#!/usr/bin/env python3
"""Blind additional Byt-Wyze SAT benchmark holdout for frozen native phase() policy.

Preselect 10 SAT and 10 UNSAT CNFs deterministically before solving, excluding
ALL 16 instances tested by DRNAS v0.6.3—v0.9. Provenance is pinned by the
upstream repository Git commit SHA + original source bytes' SHA256.
"""
import csv,hashlib,random
from pathlib import Path
from nf_v063_external_fetch import get_bytes,json_url
from drnas_np_lab import read_dimacs
ROOT=Path(__file__).resolve().parent
OLD=ROOT/'nf063_external'/'manifest.csv'
OUT=ROOT/'nf091_holdout'
UPSTREAM='Byt-wyze-technology/sat-instances-library'
COMMIT='0a150d63fb86d0eb344d65c6b2cf94be24bbfd11'
SEED=2026110419

def fetch():
    if not OLD.exists():raise RuntimeError('Need pinned prior 60-CNF manifest')
    with OLD.open(encoding='utf-8') as f:
        prior=list(csv.DictReader(f))
    seen={r['path'] for r in prior if r['source_group']=='BytWyze'}
    assert len(seen)==16
    listing=json_url(f'https://api.github.com/repos/{UPSTREAM}/contents/instances?ref={COMMIT}')
    choose=[]
    for prefix in ('sat-','unsat-'):
        eligible=sorted((e for e in listing if e['type']=='file' and
            e['name'].startswith(prefix) and e['name'].endswith('.cnf')
            and 500 <= e['size'] <=40000
            and e['path'] not in seen),key=lambda e:e['name'])
        assert len(eligible)>=10,(prefix,len(eligible))
        selected=random.Random(SEED+(0 if prefix=='sat-' else 500)).sample(eligible,10)
        choose.extend(sorted(selected,key=lambda e:e['name']))
    OUT.mkdir(exist_ok=True)
    records=[]
    for i,item in enumerate(choose,1):
        url=f"https://raw.githubusercontent.com/{UPSTREAM}/{COMMIT}/{item['path']}"
        raw=get_bytes(url,limit=300000)
        fingerprint=hashlib.sha256(raw).hexdigest()
        path=OUT/(f"independent_{i:03d}.cnf")
        path.write_bytes(raw)
        n,clauses=read_dimacs(path)
        if not clauses:raise ValueError('empty CNF clauses after normalize '+url)
        path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(
          ' '.join(map(str,c))+' 0\n' for c in clauses),encoding='ascii')
        assert read_dimacs(path)==(n,clauses)
        records.append(dict(id=path.stem,group='sat' if item['name'].startswith('sat-') else 'unsat',
          source_name=item['name'],source_path=item['path'],
          source_commit=COMMIT,source_sha256=fingerprint,
          canonical_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
          n=n,m=len(clauses),url=url))
    assert len(records)==20 and not {r['source_path'] for r in records}&seen
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    print('BLIND HOLDOUT:',len(records),'new-by-source CNFs, 10 sat labelled, 10 unsat labelled;',flush=True)
    print('UPSTREAM PIN:',COMMIT,flush=True)

if __name__=='__main__':fetch()
