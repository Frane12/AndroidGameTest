#!/usr/bin/env python3
"""New SHA-disjoint original SATLIB holdout after studies v0.2–v0.6.1.

If a small original archive has exhausted unseen instances, omit that whole
family consistently from BOTH splits; do not reuse previously tested examples.
"""
import csv,hashlib,io,random,tarfile
from pathlib import Path
from fetch_satlib import SOURCES,BASE,fetch
from drnas_np_lab import read_dimacs

def download(root='.'):
    root=Path(root);folders={x:root/('nf062_'+x+'_satlib') for x in ('train','holdout')}
    for d in folders.values():d.mkdir(parents=True,exist_ok=True)
    rows={'train':[],'holdout':[]};skipped=[]
    for g,(family,path,expected) in enumerate(SOURCES):
        url=BASE+'/'+path;raw=fetch(url)
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
            members=sorted((m for m in tar.getmembers() if m.isfile()
                 and m.name.endswith('.cnf') and m.size<3_000_000),key=lambda m:m.name)
            files=[(m.name,tar.extractfile(m).read()) for m in members]
        hashes=[hashlib.sha256(data).hexdigest() for _,data in files]
        first=random.Random(20261031+701*g).sample(range(len(files)),20)
        blocked={hashes[j] for j in first}
        prior04=[j for j in range(len(files)) if hashes[j] not in blocked]
        old04=random.Random(2026110107+111*g).sample(prior04,20)
        blocked.update(hashes[j] for j in old04)
        prior05=[j for j in range(len(files)) if j not in set(first)|set(old04)]
        old05=random.Random(2026110617+197*g).sample(prior05,20)
        blocked.update(hashes[j] for j in old05)
        prior06=[j for j in range(len(files)) if hashes[j] not in blocked]
        old06=random.Random(2026121119+311*g).sample(prior06,20)
        blocked.update(hashes[j] for j in old06)
        prior061=[j for j in range(len(files)) if hashes[j] not in blocked]
        old061=random.Random(2027021507+457*g).sample(prior061,20)
        blocked.update(hashes[j] for j in old061)
        eligible=[j for j in range(len(files)) if hashes[j] not in blocked]
        if len(eligible)<20:
            skipped.append(family)
            print(f'SKIP exhausted archive {family}: only {len(eligible)} unused files',flush=True)
            continue
        fresh=random.Random(2027041117+613*g).sample(eligible,20)
        assert not {hashes[j] for j in fresh}&blocked
        for phase,selected in (('train',old061),('holdout',fresh)):
            for j in selected:
                filename,orig=files[j];h=hashes[j]
                assert h not in {r['original_sha256'] for r in rows['train']+rows['holdout']}
                cid=f'{phase}_{len(rows[phase])+1:04d}'
                path_out=folders[phase]/(cid+'.cnf')
                path_out.write_bytes(orig)
                n,clauses=read_dimacs(path_out)
                path_out.write_text(f'p cnf {n} {len(clauses)}\n'+
                      ''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
                assert read_dimacs(path_out)==(n,clauses)
                rows[phase].append(dict(case_id=cid,family=family,expected=expected,
                    n=n,m=len(clauses),source_url=url,original_name=filename,
                    original_sha256=h,canonical_sha256=hashlib.sha256(path_out.read_bytes()).hexdigest()))
        print(f'{family}: trained 20 prior v061; 20 NEW heldout',flush=True)
    assert len(rows['train'])==len(rows['holdout'])>=120
    for phase in ('train','holdout'):
        with (folders[phase]/'manifest.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[phase][0]))
            writer.writeheader();writer.writerows(rows[phase])
    print('FRESH HELDOUT:',len(rows['holdout']),'SHA-unique independent originals; skipped:',skipped,flush=True)
if __name__=='__main__':download()
