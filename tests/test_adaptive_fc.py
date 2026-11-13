#!/usr/bin/env python3
"""Exact small-oracle tests and first-conflict policy invariants, not speed tuning."""
from pathlib import Path
import hashlib, itertools, json, random, subprocess, sys, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
import gate_real36 as B

BIN='build/drnas-adaptive-fc'

def solve(path,mode,seconds=2):
    p=subprocess.run([BIN,str(path),'--mode',mode,'--time',str(seconds),'--stats'],
                     capture_output=True,text=True,timeout=seconds+1)
    if p.returncode not in (0,10,20):raise AssertionError(p.stderr[-500:])
    found=[s for s in p.stderr.splitlines() if s.startswith('X3_STATS ')]
    assert len(found)==1
    return p,json.loads(found[0].split(' ',1)[1])

def check_gate(stats):
    assert stats['fc_probes_before_conflict']==0
    assert stats['fc_first_probe_conflicts']==-1 or stats['fc_first_probe_conflicts']>=1
    assert stats['fc_first_backdoor_conflicts']==-1 or stats['fc_first_backdoor_conflicts']>=1
    if stats['conflicts']==0:
        assert stats['depth_probes']==stats['backdoor_checks']==0

def main():
    rng=random.Random(130011)
    sat_count=unsat_count=probes=prefix_checks=0
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'case.cnf'
        for idx in range(100):
            n=6+idx%5
            clauses=[tuple(v*(1 if rng.getrandbits(1) else -1) for v in rng.sample(range(1,n+1),3))
                     for _ in range(3*n+idx%31)]
            if idx%20==0:clauses.extend([(1,),(-1,)])
            truth=any(all(any(bits[abs(x)-1]==(x>0) for x in c) for c in clauses)
                      for bits in itertools.product((False,True),repeat=n))
            sat_count+=truth;unsat_count+=not truth
            path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
            res={}
            for mode in ('core','x3','x3_fc'):
                p,stats=solve(path,mode)
                assert p.returncode==(10 if truth else 20),(idx,mode,p.returncode)
                if truth:assert B.verify_sat(p.stdout,n,clauses),(idx,mode)
                res[mode]=stats
            check_gate(res['x3_fc']);probes+=res['x3_fc']['depth_probes']
            for key in ('fc_prefix_decisions','fc_prefix_hash','fc_first_literal','fc_first_conflict_decision'):
                assert res['core'][key]==res['x3_fc'][key],(idx,key,res)
            prefix_checks+=1
        # Pigeonhole 7 into 6 is UNSAT. This is a mechanism smoke, not a benchmark.
        n=42
        clauses=[tuple(p*6+h+1 for h in range(6)) for p in range(7)]
        clauses += [(-(p*6+h+1),-(q*6+h+1)) for h in range(6) for p in range(7) for q in range(p+1,7)]
        path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
        p,stats=solve(path,'x3_fc',5)
        assert p.returncode==20
        check_gate(stats)
        probes+=stats['depth_probes']
        assert probes>0,'The gate never enabled post-conflict probing'
    # Read-only check on each diagnostic original, no parameter selection.
    original_prefix=[]
    for src in json.loads(Path('real3_frozen/manifest.json').read_text()):
        assert hashlib.sha256(Path(src['path']).read_bytes()).hexdigest()==src['sha256']
        a,sa=solve(src['path'],'core',0.2)
        b,sb=solve(src['path'],'x3_fc',0.2)
        check_gate(sb)
        # First prefix is comparable only once both hit a real conflict or SAT.
        if (sa['fc_first_conflict_decision']>=0 and sb['fc_first_conflict_decision']>=0) or (a.returncode==10 and b.returncode==10):
            assert (sa['fc_prefix_decisions'],sa['fc_prefix_hash'])==(sb['fc_prefix_decisions'],sb['fc_prefix_hash'])
        if b.returncode==10:
            n,c=B.parse_cnf(Path(src['path']).read_bytes());assert B.verify_sat(b.stdout,n,c)
        original_prefix.append({'sha256':src['sha256'],'core_rc':a.returncode,'fc_rc':b.returncode,
            'core_prefix':sa['fc_prefix_hash'],'fc_prefix':sb['fc_prefix_hash'],
            'fc_first_probe_conflicts':sb['fc_first_probe_conflicts']})
    assert sat_count and unsat_count
    report={'status':'PASS','small_oracle_cases':100,'small_oracle_runs':300,
            'SAT_cases':sat_count,'UNSAT_cases':unsat_count,'matched_core_prefixes':prefix_checks,
            'post_conflict_probes_observed':probes,'original_prefix_checks':original_prefix}
    Path('build/adaptive_fc_test.json').write_text(json.dumps(report,indent=2)+'\n')
    print('ADAPTIVE_FC_TEST_PASS '+json.dumps(report,sort_keys=True))

if __name__=='__main__':main()
