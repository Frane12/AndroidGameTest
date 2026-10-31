#!/usr/bin/env python3
"""Predeclare completely unseen SAT/UNSAT Byt-Wyze files for v1.0 holdout.
Exclude all 16 originals used in v0.6.3–v0.9 and all 20 used in v0.9.1.
Pinned upstream bytes and deterministic selection; never outcome-based pick.
"""
import csv,hashlib,random
from pathlib import Path
from drnas_np_lab import read_dimacs
from nf_v063_external_fetch import get_bytes,json_url
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'nf100_holdout'
PREV=ROOT/'nf091_holdout/manifest.csv'
PREV63=ROOT/'nf063_external/manifest.csv'
REPO='Byt-wyze-technology/sat-instances-library'
SHA='0a150d63fb86d0eb344d65c6b2cf94be24bbfd11'
SEED=202611010042

def build():
    with PREV.open(encoding='utf-8') as f:old20=list(csv.DictReader(f))
    with PREV63.open(encoding='utf-8') as f:old60=list(csv.DictReader(f))
    ban={r['source_path'] for r in old20}
    ban|={r['path'] for r in old60 if r['source_group']=='BytWyze'}
    assert len(ban)==36, len(ban)
    items=json_url(f'https://api.github.com/repos/{REPO}/contents/instances?ref={SHA}')
    selection=[]
    for i,label in enumerate(('sat-','unsat-')):
        options=sorted((r for r in items if r['type']=='file'
          and r['name'].startswith(label) and r['name'].endswith('.cnf')
          and 500<=r['size']<=40000 and r['path'] not in ban),key=lambda r:r['name'])
        assert len(options)>=10,(label,len(options))
        selection.extend(sorted(random.Random(SEED+770*i).sample(options,10),key=lambda r:r['name']))
    BASE.mkdir(parents=True,exist_ok=True)
    records=[]
    for i,item in enumerate(selection,1):
        url=f'https://raw.githubusercontent.com/{REPO}/{SHA}/{item["path"]}'
        raw=get_bytes(url,limit=300000)
        original_hash=hashlib.sha256(raw).hexdigest()
        path=BASE/(f'new_{i:03d}.cnf')
        path.write_bytes(raw)
        n,cls=read_dimacs(path)
        assert cls
        path.write_text(f'p cnf {n} {len(cls)}\n'+''.join(
          ' '.join(map(str,c))+' 0\n' for c in cls),encoding='ascii')
        assert read_dimacs(path)==(n,cls)
        records.append(dict(id=path.stem,label=item['name'].split('-')[0],
          original_path=item['path'],source_url=url,upstream_sha=SHA,
          original_sha256=original_hash,
          normalized_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),n=n,m=len(cls)))
    with (BASE/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    print('PASS: 20 previously unused BYT-WYZE formula files; excluded',len(ban),'prior files',flush=True)

if __name__=='__main__':build()
