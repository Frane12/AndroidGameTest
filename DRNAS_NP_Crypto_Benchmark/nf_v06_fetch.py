#!/usr/bin/env python3
"""Fresh SATLIB train and heldout; exclude earlier selections by original SHA256."""
import csv,hashlib,io,random,tarfile
from pathlib import Path
from drnas_np_lab import read_dimacs
from fetch_satlib import SOURCES,BASE,fetch

def build(root='.'):
    root=Path(root);out={}
    folders={p:root/('nf06_'+p+'_satlib') for p in ('train','holdout')}
    for p,d in folders.items():d.mkdir(parents=True,exist_ok=True);out[p]=[]
    seen=set()
    for group,(family,archive,expected) in enumerate(SOURCES):
        url=BASE+'/'+archive;payload=fetch(url)
        archive_sha=hashlib.sha256(payload).hexdigest()
        with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as tar:
            members=sorted((m for m in tar.getmembers()
                if m.isfile() and m.name.endswith('.cnf') and m.size<3000000),key=lambda x:x.name)
            originals=[(m.name,tar.extractfile(m).read()) for m in members]
        hashes=[hashlib.sha256(b).hexdigest() for _,b in originals]
        # Match v0.2, v0.4 and v0.5 deterministic selections.
        first=random.Random(20261031+701*group).sample(range(len(originals)),20)
        banned={hashes[j] for j in first}
        candidates04=[j for j in range(len(originals)) if hashes[j] not in banned]
        prev04=random.Random(2026110107+111*group).sample(candidates04,20)
        banned.update(hashes[j] for j in prev04)
        candidates05=[j for j in range(len(originals)) if j not in set(first)|set(prev04)]
        prev05=random.Random(2026110617+197*group).sample(candidates05,20)
        banned.update(hashes[j] for j in prev05)
        candidates06=[j for j in range(len(originals)) if hashes[j] not in banned]
        if len(candidates06)<20:raise RuntimeError(f'Not enough untested {family} sources')
        fresh=random.Random(2026121119+311*group).sample(candidates06,20)
        for phase,indices in (('train',first),('holdout',fresh)):
            for j in indices:
                original_name,raw=originals[j];h=hashes[j]
                assert h not in seen
                seen.add(h)
                cid=f'{phase}_{len(out[phase])+1:04}'
                dest=folders[phase]/f'{cid}.cnf'
                dest.write_bytes(raw)
                n,clauses=read_dimacs(dest)
                dest.write_text(f'p cnf {n} {len(clauses)}\n'
                    +''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
                assert read_dimacs(dest)==(n,clauses)
                out[phase].append(dict(case_id=cid,family=family,expected=expected,n=n,m=len(clauses),
                    original_sha256=h,original_name=original_name,
                    canonical_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                    archive_sha256=archive_sha,source_url=url))
        print(f'{family}: 20 train, 20 fresh heldout, 60 previously seen excluded',flush=True)
    for phase in ('train','holdout'):
        rs=out[phase];assert len(rs)==160
        with (folders[phase]/'manifest.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rs[0]));writer.writeheader();writer.writerows(rs)
    assert {r['original_sha256'] for r in out['train']}.isdisjoint({r['original_sha256'] for r in out['holdout']})
    print('PASS 160 SHA-disjoint fresh SATLIB holdouts',flush=True)
if __name__=='__main__':build()
