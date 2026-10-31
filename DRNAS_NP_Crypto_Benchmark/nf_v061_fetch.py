#!/usr/bin/env python3
"""Original SATLIB 160/160 split for NeuroFlow v0.6.1.

Train: v0.6 formerly held-out SATLIB formulas (legitimately now training data).
Test: a NEW deterministic, SHA-disjoint selection excluding all v0.2–v0.6
source files. No test content is used for policy training or threshold selection.
"""
import csv,hashlib,io,random,tarfile
from pathlib import Path
from fetch_satlib import BASE,SOURCES,fetch
from drnas_np_lab import read_dimacs

def make(root='.'):
    base=Path(root);out={}
    folders={mode:base/('nf061_'+mode+'_satlib') for mode in ('train','holdout')}
    for phase,d in folders.items():d.mkdir(exist_ok=True);out[phase]=[]
    seen=set()
    for group,(family,archive,expected) in enumerate(SOURCES):
        url=BASE+'/'+archive;raw=fetch(url)
        archive_hash=hashlib.sha256(raw).hexdigest()
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as ar:
            names=sorted((m for m in ar.getmembers() if m.isfile() and m.name.endswith('.cnf')
                     and m.size<3000000),key=lambda m:m.name)
            original=[(m.name,ar.extractfile(m).read()) for m in names]
        hashes=[hashlib.sha256(b).hexdigest() for _,b in original]
        first=random.Random(20261031+701*group).sample(range(len(original)),20)
        banned={hashes[j] for j in first}
        next04=[j for j in range(len(original)) if hashes[j] not in banned]
        old04=random.Random(2026110107+111*group).sample(next04,20)
        banned.update(hashes[j] for j in old04)
        next05=[j for j in range(len(original)) if j not in set(first)|set(old04)]
        old05=random.Random(2026110617+197*group).sample(next05,20)
        banned.update(hashes[j] for j in old05)
        next06=[j for j in range(len(original)) if hashes[j] not in banned]
        old06=random.Random(2026121119+311*group).sample(next06,20)
        banned.update(hashes[j] for j in old06)
        next061=[j for j in range(len(original)) if hashes[j] not in banned]
        if len(next061)<20:raise ValueError('Insufficient untouched SATLIB examples for '+family)
        fresh=random.Random(2027021507+457*group).sample(next061,20)
        assert not ({hashes[j] for j in fresh}&banned)
        for phase,indices in (('train',old06),('holdout',fresh)):
            for j in indices:
                name,original_bytes=original[j];sha=hashes[j]
                assert sha not in seen,(phase,family,name)
                seen.add(sha)
                cid=f'{phase}_{len(out[phase])+1:04d}';dest=folders[phase]/(cid+'.cnf')
                dest.write_bytes(original_bytes)
                n,clauses=read_dimacs(dest)
                # Normalize format, not truth value: both solvers see same CNF.
                dest.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(
                    ' '.join(map(str,c))+' 0\n' for c in clauses))
                assert read_dimacs(dest)==(n,clauses)
                out[phase].append(dict(case_id=cid,family=family,n=n,m=len(clauses),
                    expected=expected,original_name=name,original_sha256=sha,
                    archive_sha256=archive_hash,source_url=url,
                    canonical_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
        print(f'{family}: trained=20 (v06), NEVER-SEEN=20 (v061)',flush=True)
    assert len(out['train'])==len(out['holdout'])==160
    assert {v['original_sha256'] for v in out['train']}.isdisjoint(
           v['original_sha256'] for v in out['holdout'])
    for phase,d in folders.items():
        with (d/'manifest.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(out[phase][0]))
            writer.writeheader();writer.writerows(out[phase])
    print('PASS 160 independent previously UNUSED SATLIB formula SHA256',flush=True)
if __name__=='__main__':make()
