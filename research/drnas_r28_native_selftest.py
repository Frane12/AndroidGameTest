#!/usr/bin/env python3
import itertools,os,pathlib,random,subprocess,tempfile,time
from drnas_r28_native_check import parse_dimacs,verify,check_gf2
BIN='mre_r28_native/drnas_r28_native'
def write(p,n,cs):p.write_text(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
def truth(n,cs):return any(all(any(bool(bits[abs(v)-1])==(v>0) for v in c) for c in cs) for bits in itertools.product((0,1),repeat=n))
def run(p,profile,extra=()):
    env=dict(os.environ,DRNAS_LTM8_MEMORY='')
    return subprocess.run([BIN,str(p),'--time','1','--profile',profile,*extra],capture_output=True,text=True,env=env,timeout=3)
def main():
    rng=random.Random(20261112);checks=0;rejected=0
    cases=[(2,[[1,-2],[-1,2]],True),(2,[[1,-2],[-1,2],[1],[-2]],False),
           (3,[[1,2],[-2,3],[-3]],True),(1,[[]],False),
           (2,[[1,-2],[-1,2],[1,2]],True)]
    for _ in range(90):
        n=rng.randrange(2,9);cs=[]
        for j in range(rng.randrange(1,35)):
            vs=rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))
            cs.append([v if rng.getrandbits(1) else -v for v in vs])
        cases.append((n,cs,truth(n,cs)))
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/'original.cnf'
        for n,cs,sat in cases:
            write(p,n,cs);source=parse_dimacs(p)
            for profile in ('fast','direct','fixed0'):
                r=run(p,profile);status,valid=verify(source,r.stdout,r.returncode)
                assert r.returncode==(10 if sat else 20),(n,cs,profile,r.stdout,r.stderr)
                if sat:assert valid and status=='SAT_VERIFIED'
                checks+=1
        write(p,2,[[1,-2],[-1,2],[1],[-2]])
        r=run(p,'fast');assert verify(parse_dimacs(p),r.stdout,r.returncode)==('UNSAT_GF2_VERIFIED',True)
        # Remove a required source clause; stale contradiction must be rejected.
        write(p,2,[[1,-2],[-1,2],[1]])
        try:check_gf2(parse_dimacs(p),r.stdout)
        except ValueError:rejected+=1
        else:raise AssertionError('forged source proof accepted')
        # Mixed consistent XOR must use the native fallback and verify the ORIGINAL model.
        write(p,3,[[1,-2],[-1,2],[1,2,3]])
        r=run(p,'direct');assert 'route=native_learning' in r.stdout
        assert verify(parse_dimacs(p),r.stdout,r.returncode)==('SAT_VERIFIED',True)
        # Disable the exact route to exercise native logic on the same XOR input.
        r=run(p,'fast',('--gf2-ms','0'));assert r.returncode==10
        # Counting proof is independently checked, even after variable renaming.
        cs=[[1,2],[3,4],[5,6],[-1,-3],[-1,-5],[-3,-5],[-2,-4],[-2,-6],[-4,-6]]
        write(p,6,cs);r=run(p,'fast');assert verify(parse_dimacs(p),r.stdout,r.returncode)==('UNSAT_PHP_VERIFIED',True)
        # Whole-process budget includes parsing/detection; it cannot leak into a new solver budget.
        write(p,500,[[rng.choice((-1,1))*v for v in rng.sample(range(1,501),3)] for _ in range(3000)])
        begin=time.perf_counter()
        r=subprocess.run([BIN,str(p),'--time','0.005','--profile','direct'],capture_output=True,text=True,timeout=1)
        assert time.perf_counter()-begin<.5
    print('R28_NATIVE_SELFTEST_PASS',dict(bruteforce_cases=len(cases),profile_checks=checks,forged_proofs_rejected=rejected,native_fallback=True,php_verified=True,outer_deadline=True),flush=True)
if __name__=='__main__':main()
