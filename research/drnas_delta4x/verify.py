#!/usr/bin/env python3
"""Independent proof checks. No status, source name or expected answer reaches recognition."""
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(ROOT/'tests'))
import drnas_x55_cpu_real36 as B
from test_drnas_deltacoop2 import bcp,check_rup
from test_drnas_deltacoop3 import validate_lemma

BASE=[[1,-2,3],[2,-3],[-1,-3],[-1,-2,5],[1,-5],[2,-5],[-1,2,4],[1,-4],[-2,-4]]
def canon(c): return tuple(sorted(set(c)))
def validate_alias(e,source):
    a,b,c=canon(e['parent_a']),canon(e['parent_b']),canon(e['forward'])
    pivot=e['pivot'];rev=canon(e['reverse']);g=e['guard'];x=e['a'];y=e['b']
    assert a in source and b in source and rev in source,('PARENT_NOT_ORIGINAL',e)
    assert pivot in a and -pivot in b,('INVALID_PIVOT',e)
    assert canon([l for l in a if l!=pivot]+[l for l in b if l!=-pivot])==c
    assert len(c)==3 and not any(-l in c for l in c)
    assert x>0 and y>0 and x!=y and canon([-x,y,g])==c
    assert rev==canon([x,-y]),('REVERSE_NOT_EQUIVALENCE',e)
    assert bcp([a,b],[-l for l in c]) is None,('NOT_RUP',e)
    return c not in source

def events(stderr,tag):
    return [json.loads(l.split(' ',1)[1]) for l in stderr.splitlines() if l.startswith(tag+' ')]
def validate_events(stderr,clauses):
    source={canon(c) for c in clauses};aliases=events(stderr,'DELTA4X_ALIAS')
    novel=sum(validate_alias(e,source) for e in aliases)
    for e in events(stderr,'DELTA3_LEMMA'):validate_lemma(e,source)
    installed={canon(e['forward']) for e in aliases}
    causal=events(stderr,'DELTA4X_CAUSAL')
    for e in causal:
        c=canon(e['clause']);lit=e['literal']
        assert c in installed and lit in c
        assert canon(e['antecedents_false'])==canon(l for l in c if l!=lit)
    st=events(stderr,'DELTA4X_STATS')
    assert len(st)==1,'MISSING_OR_DUPLICATE_X_TELEMETRY'
    st=st[0]
    assert st['installed']==len(aliases),'QUEUED_CONFUSED_WITH_INSTALLED'
    assert len(causal)<=st['actual_enqueues']
    if st['mode']==1:assert not aliases and st['installed']==0 and st['actual_enqueues']==0
    return st,novel,len(causal)

def oracle(cs):
    used=sorted({abs(l) for c in cs for l in c})
    assert len(used)<=10
    for bits in itertools.product((False,True),repeat=len(used)):
        v=dict(zip(used,bits))
        if all(any(v[abs(l)]==(l>0) for l in c) for c in cs):return True
    return False

def text(n,cs):return f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs)

def fixtures():
    rows=[('core',5,BASE+[[-3],[-4]]),('downstream',7,BASE+[[-3],[-4],[-5,6],[-6,7]]),
          ('unguarded',5,BASE),('one_guard',5,BASE+[[-3]]),
          ('missing_reverse',5,[[-1,-2,5],[-1,2,4],[-4]]),
          ('linear',5,[[-1,2],[1,-2],[-2,5],[2,-5],[-3],[-4]]),
          ('unsat',5,BASE+[[-3],[-4],[1],[-5]]),('empty_clause',2,[[]])]
    for seed in range(12):
        r=random.Random(4400+seed);v=list(range(1,6));r.shuffle(v)
        cs=[[(1 if l>0 else -1)*v[abs(l)-1] for l in c] for c in BASE+[[-3],[-4]]]
        r.shuffle(cs);rows.append((f'renamed_{seed}',5,cs))
    # Same logical motif above the OLD hidden 4096-variable boundary.
    cs=[[(1 if l>0 else -1)*(abs(l)+5000) for l in c] for c in BASE+[[-3],[-4]]]
    rows.append(('shifted_5005',5005,cs))
    for seed in range(32):
        r=random.Random(440400+seed);n=6+seed%3;cs=[]
        for _ in range(12+seed%25):
            vs=r.sample(range(1,n+1),r.randint(1,3))
            cs.append([v if r.randrange(2) else -v for v in vs])
        rows.append((f'random_{seed}',n,cs))
    return rows

def run_suite(binary,compact=False):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[];cases=fixtures()
    if compact:cases=cases[:8]+[cases[20]]
    root=Path('delta4x_audit');root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for name,n,cs in cases:
            src=td/'source.cnf';src.write_text(text(n,cs));expected=10 if oracle(cs) else 20
            for mode in ('d4','d4x-shadow','d4x'):
                proof=td/'proof.drat';proof.unlink(missing_ok=True)
                cmd=[str(Path(binary).resolve()),str(src),'--mode','core','--time','1.8','--stats',
                     '--x5-no-minimize','--coop4','gate','--coop4-eager','--coop5','off',
                     '--delta2',mode,'--proof',str(proof)]
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
                assert p.returncode==expected,('ORACLE_MISMATCH',name,mode,p.returncode,p.stderr[-1500:])
                if p.returncode==10:assert B.check_sat(p.stdout,cs,n),('INVALID_SAT',name,mode)
                else:
                    q=subprocess.run(['build/drat-trim',str(src),str(proof)],capture_output=True,text=True,timeout=20)
                    assert q.returncode==0 and 's VERIFIED' in q.stdout,('INVALID_UNSAT',name,mode,q.stdout[-500:])
                assert proof.exists();check_rup(cs,proof)
                st,new,causal=validate_events(p.stderr,cs)
                if name=='shifted_5005':assert st['math_enabled'] and st['d4_originals']>0,'HIDDEN_SIZE_DISABLE'
                row={'case':name,'mode':mode,'verified':True,'status':'SAT' if expected==10 else 'UNSAT',
                     'installed':st['installed'],'new_original_clauses':new,'actual_enqueues':st['actual_enqueues'],
                     'guarded_candidates':st['guarded_candidates'],'math_enabled':st['math_enabled']}
                rows.append(row)
                (root/f'{"ubsan-" if compact else ""}{name}-{mode}.stderr').write_text(p.stderr)
    report={'status':'PASS','trials':len(rows),'distinct_fixtures':len(cases),
            'oracle_and_original_proofs_checked':True,'all_aliases_original_rup_checked':True,
            'high_dimension_enabled':True,'installed':sum(r['installed'] for r in rows if r['mode']=='d4x'),
            'actual_enqueues':sum(r['actual_enqueues'] for r in rows if r['mode']=='d4x'),
            'causal_fixture_count':sum(r['actual_enqueues']>0 for r in rows if r['mode']=='d4x'),
            'synthetic_not_independent_families':True,'speed_claim':False,'ubsan':compact}
    # Hard gate: an installed clause and an ACTUAL CDCL reason must exist.
    assert report['installed']>0 and report['actual_enqueues']>0,('NO_CAUSAL_INTEGRATION',report)
    suffix='ubsan' if compact else 'preflight'
    (root/f'{suffix}.json').write_text(json.dumps({'report':report,'trials':rows},indent=2)+'\n')
    print('DELTA4X_PREFLIGHT_PASS',json.dumps(report,sort_keys=True),flush=True)
    return report

if __name__=='__main__':
    compact='--ubsan' in sys.argv
    run_suite('build/drnas-delta4x-ubsan' if compact else 'build/drnas-delta4x',compact)
