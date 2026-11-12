#!/usr/bin/env python3
import hashlib,json,os,pathlib,sqlite3,subprocess,tempfile
from drnas_r28_context_memory import Memory,SCHEMA,solve
from drnas_r28_native_check import parse_dimacs,verify
from drnas_r28_native_selftest import write

def main():
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td);db=root/'m.sqlite';m=Memory(db)
        sha='a'*64;m.register(sha,'train')
        telemetry='c R28_CONTEXT_DELTA key=32 phase=0 arm=2 n=30 sum=18\nc R28_CONTEXT_DELTA key=32 phase=1 arm=1 n=12 sum=6\n'
        assert not m.learn(sha,'UNKNOWN',False,telemetry,1)['updated'];assert m.info()['cells']==0
        assert m.learn(sha,'SAT_VERIFIED',True,telemetry,.1)['updated'];first=m.digest()
        assert not m.learn(sha,'SAT_VERIFIED',True,telemetry,.1)['updated'];assert m.digest()==first
        assert m.info()['cells']==2
        m.register('b'*64,'eval')
        for h,role in [('b'*64,'train'),(sha,'eval')]:
            try:m.register(h,role)
            except ValueError:pass
            else:raise AssertionError('split leak')
        m.register('c'*64,'train');before=m.digest()
        try:m.learn('c'*64,'SAT_VERIFIED',True,telemetry.replace('sum=18','sum=nan'),.1)
        except ValueError:pass
        # A malformed telemetry line must not silently mark a formula as trained.
        else:raise AssertionError('malformed telemetry accepted')
        assert m.digest()==before
        for h in ('d'*64,'e'*64):
            m.register(h,'train');m.learn(h,'SAT_VERIFIED',True,telemetry,.1)
        first=m.digest()
        snapshot=pathlib.Path(m.snapshot());assert snapshot.stat().st_size<65536
        m.advance();m.backup(root/'backup.sqlite');m.close()
        m=Memory(db);assert m.digest()==first and m.generation()==1
        copy=Memory(root/'backup.sqlite');assert copy.digest()==first;copy.close()
        # Verify transfer actually changes the FIRST native decision profile.
        p=root/'source.cnf';write(p,180,[[i,i%180+1,(i+1)%180+1] for i in range(1,181)]*5)
        # This source's exact structural key is 32; no answer is inferred from it.
        r,out=solve(m,p,'eval',1,warm=True)
        assert r['verified'],out
        assert 'R28_CONTEXT_START arm=2 key=32' in out,out
        r2,cold=solve(m,p,'eval',1,warm=False)
        assert r2['verified'];assert 'R28_CONTEXT_START arm=0 key=32' in cold,cold
        assert m.digest()==first
        # Reject an unsupported snapshot schema and fall back to cold parameters.
        bad=root/'bad.txt';bad.write_text('WRONG_SCHEMA\n32 0 3 8 0.99\n')
        env=dict(os.environ,DRNAS_CONTEXT_SNAPSHOT=str(bad),DRNAS_LTM8_MEMORY='')
        q=subprocess.run(['mre_r28_context/drnas_r28_context',str(p),'--time','1','--profile','direct'],env=env,capture_output=True,text=True,timeout=2)
        assert 'accepted=0' in q.stdout and 'R28_CONTEXT_START arm=0' in q.stdout
        assert verify(parse_dimacs(p),q.stdout,q.returncode)[1]
        # The R153 unit bridge still certifies original-CNF XOR contradiction.
        write(p,2,[[1,-2],[-1,2],[1],[-2]])
        r,out=solve(m,p,'eval',1);assert r['status']=='UNSAT_GF2_VERIFIED'
        assert 'route=exact_gf2' in out
        m.close()
    print('R28_CONTEXT_SELFTEST_PASS persistence=true dedup=true heldout_isolation=true weak_prior_changes_initial_arm=true invalid_schema_cold_fallback=true r153_unit_certificate=true',flush=True)
if __name__=='__main__':main()
