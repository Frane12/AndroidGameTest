#!/usr/bin/env python3
"""Independent checks of inference, AUC, split isolation, pruning and durable storage."""
import argparse,copy,gzip,json,os,sqlite3,subprocess,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'research'))
import drnas_x47_long as L
import drnas_x47 as X
import x47_long_models as M

def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--models',type=Path,required=True);a=p.parse_args()
    rows=[json.loads(s) for s in (a.inputs/'collect-0/pairs.jsonl').read_text().splitlines()]
    model=json.loads((a.models/'frozen_model.json').read_text())
    expected=[X.choose(model,r['features']) for r in rows]
    assert M.decisions(model,rows).tolist()==expected
    for r in rows:
        if r['features'] is not None:
            assert abs(M.scores(model,M.matrix(model,[r]))[0]-X.predict(model,r['features'])[0])<1e-12
    for threshold in (0.,.1,1e9):
        mm={**model,'threshold':threshold}
        assert M.decisions(mm,rows).tolist()==[X.choose(mm,r['features']) for r in rows]
    clone=copy.deepcopy(model);clone['weights']*=5
    reduced,events,features=M.prune(clone,rows,True)
    assert 2<=len(reduced['weights'])<=64 and features<=set(range(24))
    assert all(e['after']<=e['before'] for e in events if e['reason']=='no_validation_work_loss')
    rng=np.random.default_rng(47)
    for _ in range(100):
        y=rng.integers(0,2,70).astype(bool);score=rng.integers(-3,4,70)
        pos=score[y];neg=score[~y]
        oracle=np.mean((pos[:,None]>neg).astype(float)+.5*(pos[:,None]==neg))
        assert abs(L.auc(y,score)-oracle)<1e-12
    assert L.auc([],[]) is None and L.auc([True],[0.]) is None
    parents={s:{f for split,_,_,fs in L.REGIMES if s==split for f in fs} for s in ('train','validation','holdout')}
    assert not parents['train']&parents['validation'] and not (parents['train']|parents['validation'])&parents['holdout']
    manifest=L.rows_manifest(1000,'unit-disjoint');assert len(manifest)==30000
    for split,shards in (('train',8),('validation',8),('holdout',6)):
        ids={m['id'] for m in manifest if m['split']==split}
        parts=[{i for i in ids if i%shards==shard} for shard in range(shards)]
        assert sum(map(len,parts))==len(ids) and set.union(*parts)==ids
    # Publish to a temporary bare Git remote: genuinely survive loss of working files.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);remote=root/'remote.git';store=root/'checkout';out=root/'out';out.mkdir()
        def git(*args):return subprocess.run(['git',*map(str,args)],check=True,capture_output=True,text=True)
        git('init','--bare',remote);git('clone',remote,store)
        db=L.open_memory(out/'memory.sqlite');db.execute("INSERT INTO meta VALUES('test','durable')")
        previous=os.environ.get('X47_MEMORY_STORE');os.environ['X47_MEMORY_STORE']=str(store)
        try:L.publish(SimpleNamespace(out=out,namespace='unit'),db,model,'unit-roundtrip')
        finally:
            if previous is None:os.environ.pop('X47_MEMORY_STORE')
            else:os.environ['X47_MEMORY_STORE']=previous
        db.close();restored=root/'restored';git('clone','--branch',L.DATA_BRANCH,remote,restored)
        raw=gzip.decompress((restored/'research/memory/x47/memory.sqlite.gz').read_bytes())
        recovered=root/'recovered.sqlite';recovered.write_bytes(raw)
        check=sqlite3.connect(recovered);assert check.execute("SELECT value FROM meta WHERE key='test'").fetchone()==('durable',);check.close()
    db=sqlite3.connect(a.models/'memory.sqlite')
    assert db.execute("SELECT count(*) FROM experiences WHERE split='holdout'").fetchone()[0]==0
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
    print('X47LONG_TEST_PASS inference=AUC=split_isolation=pruning=durable_git_roundtrip=OK')

if __name__=='__main__':main()
