#!/usr/bin/env python3
"""Get original SATLIB CNFs, with SHA-disjoint test after previous v0.2/v0.4 studies."""
import csv,hashlib,io,random,tarfile
from pathlib import Path
from fetch_satlib import SOURCES,BASE,fetch
from drnas_np_lab import read_dimacs

def build(root='.'):
    root=Path(root);train=root/'nf05_train_satlib';held=root/'nf05_holdout_satlib'
    train.mkdir(parents=True,exist_ok=True);held.mkdir(parents=True,exist_ok=True)
    train_rows=[];held_rows=[];used=set()
    for i,(family,path,expected) in enumerate(SOURCES):
        url=BASE+'/'+path;raw=fetch(url)
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as ar:
            members=sorted((m for m in ar.getmembers() if m.isfile() and m.name.lower().endswith('.cnf') and m.size<3000000),key=lambda m:m.name)
            files=[(m.name,ar.extractfile(m).read()) for m in members]
        hashes=[hashlib.sha256(data).hexdigest() for name,data in files]
        # Reconstruct original v0.2 selection and v0.4 previously unseen selection.
        old_indices=random.Random(20261031+701*i).sample(range(len(files)),20)
        previous_pool=[j for j in range(len(files)) if hashes[j] not in {hashes[k] for k in old_indices}]
        previous_v04=random.Random(2026110107+111*i).sample(previous_pool,20)
        banned=set(old_indices)|set(previous_v04)
        available=[j for j in range(len(files)) if j not in banned and hashes[j] not in set(hashes[k] for k in banned)]
        fresh=random.Random(2026110617+197*i).sample(available,20)
        assert not set(fresh)&banned
        for selected,directory,rows,prefix in ((old_indices,train,train_rows,'train'),(fresh,held,held_rows,'held')):
            for j in selected:
                original_name,original=files[j];h=hashes[j]
                assert h not in used,(family,original_name)
                used.add(h)
                cid=f'{prefix}_{len(rows)+1:04}'
                target=directory/(cid+'.cnf')
                target.write_bytes(original)
                n,clauses=read_dimacs(target)
                # Same equivalent canonical DIMACS for both programs.
                target.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
                assert read_dimacs(target)==(n,clauses)
                rows.append(dict(case_id=cid,family=family,n=n,m=len(clauses),expected=expected,
                    original_name=original_name,original_sha256=h,canonical_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    source_url=url))
        print(f'{family}: 20 train + 20 NEW heldout; excluded 20 prior v04',flush=True)
    assert len(train_rows)==len(held_rows)==160
    assert set(r['original_sha256'] for r in train_rows).isdisjoint(r['original_sha256'] for r in held_rows)
    for directory,rows in ((train,train_rows),(held,held_rows)):
        with (directory/'manifest.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('PASS: 160 fresh SHA-disjoint external holdout instances',flush=True)
if __name__=='__main__':build()
