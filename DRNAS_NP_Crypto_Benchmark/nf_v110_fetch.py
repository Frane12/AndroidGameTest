#!/usr/bin/env python3
"""Previously unused heldout from two third-party publishing entities.

Fixed, predeclared sample: 15 SAT + 15 UNSAT Byt-Wyze independent synthetic
formulas; 4 each from three hardware CNF benchmark families in Tractables.
Exclude original filenames from all 100 previously studied external examples.
All selection is BEFORE solving, blinded to performance or SAT status
(other than Byt-Wyze's self-reported filename family for balanced sampling).
"""
import csv,hashlib,random
from pathlib import Path
from nf_v063_external_fetch import json_url,get_bytes
from drnas_np_lab import read_dimacs
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'nf110_holdout'
BYT='Byt-wyze-technology/sat-instances-library'
B_SHA='0a150d63fb86d0eb344d65c6b2cf94be24bbfd11'
TRACT='Tractables/cnfs'
T_SHA='de4731f68e5a5bb6629269b3be1d19b44e812763'
SEED=202611031100
GROUPS=[('LGSynth89','LGSynth89',4),('ISCAS85','iscas85b',4),
        ('ISCAS89','iscas89',4)]

def load_previous():
    with (ROOT/'nf063_external/manifest.csv').open(encoding='utf8') as f:ext=list(csv.DictReader(f))
    with (ROOT/'nf091_holdout/manifest.csv').open(encoding='utf8') as f:prior91=list(csv.DictReader(f))
    with (ROOT/'nf100_holdout/manifest.csv').open(encoding='utf8') as f:prior100=list(csv.DictReader(f))
    assert len(ext)==60 and len(prior91)==20 and len(prior100)==20
    old={row['publisher']+'/'+row['path'] for row in ext}
    old.update(BYT+'/'+row['source_path'] for row in prior91)
    old.update(BYT+'/'+row['original_path'] for row in prior100)
    assert len(old)==100,len(old)
    return old

def main():
    old=load_previous()
    items=json_url(f'https://api.github.com/repos/{BYT}/contents/instances?ref={B_SHA}')
    selected=[]
    for cat,subseed in [('sat-',0),('unsat-',1)]:
        candidates=sorted([r for r in items if r['type']=='file'
          and r['name'].startswith(cat) and r['name'].endswith('.cnf')
          and 500<=r['size']<=125000 and BYT+'/'+r['path'] not in old],
          key=lambda x:x['name'])
        assert len(candidates)>=15,(cat,len(candidates))
        pick=random.Random(SEED+subseed).sample(candidates,15)
        selected.extend([(BYT,B_SHA,'BytWyze_'+cat[:-1],r) for r in pick])
    for i,(group,folder,size) in enumerate(GROUPS):
        items=json_url(f'https://api.github.com/repos/{TRACT}/contents/{folder}?ref={T_SHA}')
        candidates=sorted([r for r in items if r['type']=='file' and
           r['name'].endswith('.cnf') and 500<=r['size']<=100000 and
           TRACT+'/'+r['path'] not in old],key=lambda x:x['name'])
        assert len(candidates)>=size,(group,len(candidates))
        pick=random.Random(SEED+100+i).sample(candidates,size)
        selected.extend([(TRACT,T_SHA,group,r) for r in pick])
    assert len(selected)==42
    OUT.mkdir(exist_ok=True)
    rows=[];original_hashes=set()
    for i,(repo,commit,group,item) in enumerate(selected,1):
        url=f'https://raw.githubusercontent.com/{repo}/{commit}/{item["path"]}'
        raw=get_bytes(url,limit=1500000)
        raw_sha=hashlib.sha256(raw).hexdigest()
        assert raw_sha not in original_hashes
        original_hashes.add(raw_sha)
        dst=OUT/(f'holdout_{i:03d}.cnf')
        dst.write_bytes(raw)
        n,cnf=read_dimacs(dst)
        assert cnf
        dst.write_text(f'p cnf {n} {len(cnf)}\n'+
             ''.join(' '.join(map(str,c))+' 0\n' for c in cnf),encoding='ascii')
        assert read_dimacs(dst)==(n,cnf)
        rows.append(dict(id=dst.stem,source_group=group,publisher=repo,
           upstream_commit=commit,source_name=item['name'],source_path=item['path'],
           original_sha256=raw_sha,canonical_sha256=hashlib.sha256(dst.read_bytes()).hexdigest(),
           n=n,m=len(cnf),source_url=url))
    assert all(r['publisher']+'/'+r['source_path'] not in old for r in rows)
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('PASS: 42 previously unused external CNF originals: 30 Byt-Wyze + 12 hardware',flush=True)
    for group in sorted({r['source_group'] for r in rows}):
        print(group,sum(r['source_group']==group for r in rows),flush=True)

if __name__=='__main__':main()
