#!/usr/bin/env python3
"""LTM12 routing pilot with MATH14 on frozen LTM9, no LTM13 controller.

Fresh synthetic instances, shared generators: not evidence of broad blind
generalization. SAT witnesses are checked on the ORIGINAL CNF. Uncertified
UNSAT never earns reward; any UNSAT contradicts these planted SAT sources.
"""
import hashlib
import itertools
import json
import os
import pathlib
import random
import sys
import tempfile
import time
from unittest.mock import patch
import drnas_ltm12_fast600 as G

L, B, F = G.L, G.B, G.F
ROOT = pathlib.Path('ltm12_math14')
CAP = 1.0
ARMS = L.SCREEN_ARMS + ('MATH14',)
TEST = ('LTM12_NATIVE', 'LTM12_HYBRID') + ARMS
FAMILIES = ('binary', 'three_sparse', 'three_dense', 'mixed', 'wide', 'xor_pairs')
ORIGINAL_RUN = L.run_checked


def run_checked(arm, source, seed, cap):
    telemetry = []
    if arm == 'MATH14':
        def command(alias, path, solver_seed, budget):
            assert alias == 'LTM9_FAST'
            return ['mre_atlas23/bin/drnas_math14', str(path), '--mode', 'LTM8_FAST',
                    '--time', str(max(.1, budget-.30)), '--seed', str(solver_seed),
                    '--policy', '1.0,0.85']
        original_subprocess = B.subprocess.run
        def capture(*args, **kwargs):
            result = original_subprocess(*args, **kwargs)
            telemetry.extend(line for line in result.stdout.splitlines()
                             if line.startswith('c MATH14 '))
            return result
        # MATH14 is compiled from the same certificate-emitting LTM9 source.
        # Reuse its independent ORIGINAL-CNF PHP checker; relabel the row.
        with patch.object(B, 'command', command), patch.object(B.subprocess, 'run', capture):
            row = ORIGINAL_RUN('LTM9_FAST', source, seed, cap)
        row['arm'] = arm
    else:
        row = ORIGINAL_RUN(arm, source, seed, cap)
    if row['status'].startswith('UNSAT'):
        raise RuntimeError('UNSAT contradicts independently checked planted SAT witness')
    row.update(family=source['family'], math14_telemetry=telemetry)
    return row


def generate(family, seed):
    if family != 'xor_pairs':
        return G.generate(family, seed)
    rng = random.Random(seed)
    n = rng.randrange(70, 111)
    model = {v:bool(rng.getrandbits(1)) for v in range(1,n+1)}
    clauses = set()
    # Connected overlapping XOR pairs, deliberately within MATH14's 256-row cap.
    # This targeted family is reported separately, never disguised as random CNF.
    for _ in range(70):
        a,b,c,d = rng.sample(range(1,n+1),4)
        for triple in ((a,b,c),(a,b,d)):
            rhs = sum(model[v] for v in triple)%2
            for bits in itertools.product((False,True), repeat=3):
                if sum(bits)%2 != rhs:
                    clauses.add(tuple(sorted((-v if bit else v for v,bit in zip(triple,bits)),key=abs)))
    cs = sorted(clauses); rng.shuffle(cs)
    return (f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs),
            'v '+' '.join(str(v if model[v] else -v) for v in model)+' 0\n')


def collect(root):
    (root/'cases').mkdir(parents=True)
    sources = []
    for split,count,offset in [('train',15,41000000),('validation',5,42000000),('holdout',10,43000000)]:
        group=[]
        for family_id,family in enumerate(FAMILIES):
            for index in range(count):
                seed=offset+family_id*10000+index
                raw,witness=generate(family,seed)
                sha=hashlib.sha256(raw.encode()).hexdigest()
                path=root/'cases'/f'{sha}.cnf'; path.write_text(raw)
                assert B.sat_witness_valid(path,B.nvars(path),witness)
                group.append(dict(path=str(path),sha256=sha,split=split,family=family,generator_seed=seed))
        random.Random(offset).shuffle(group);sources.extend(group)
    assert len(sources)==len({s['sha256'] for s in sources})==180
    for index,source in enumerate(sources):source['id']=index
    (root/'manifest.json').write_text(json.dumps(dict(sources=sources,synthetic=True,
        all_SAT=True,instance_disjoint=True,family_disjoint=False,
        blind_generalization_claim=False,targeted_family='xor_pairs',
        math14_source_commit='b9c90b7d84782a54a42fd91513ba5f12eca665ac'),indent=2))
    return sources


def main():
    if '--selftest' in sys.argv:
        with tempfile.TemporaryDirectory() as td: collect(pathlib.Path(td))
        L.selftest()
        print('LTM12_MATH14_SELFTEST_PASS 180 original-CNF planted witnesses')
        return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    L.setup_source(); L.run_checked=run_checked
    sources=collect(ROOT); pairs={'train':[], 'validation':[]}; screen=[]
    with (ROOT/'screen.jsonl').open('w') as fd:
        for source in sources:
            if source['split']=='holdout':continue
            start=time.monotonic();feature=F.extract(source['path'])
            feature['feature_extract_s']=time.monotonic()-start
            paired={};shift=source['id']%len(ARMS)
            for arm in ARMS[shift:]+ARMS[:shift]:
                row=run_checked(arm,source,17,CAP);paired[arm]=row;screen.append(row)
                fd.write(json.dumps(row)+'\n');fd.flush()
            pairs[source['split']].append((feature,paired))
            if (source['id']+1)%15==0:L.emit('LTM12_MATH14_SCREEN',dict(sources=source['id']+1))
    B.check_contradictions(screen)
    models={mode:L.fit(pairs['train'],pairs['validation'],mode,
                       win_margin=.002,min_gain=.05,extra_arms=('MATH14',))
            for mode in ('NATIVE','HYBRID')}
    memory=dict(models=models,holdout_used_for_fit=False,
        train_sha256=[s['sha256'] for s in sources if s['split']=='train'],
        validation_sha256=[s['sha256'] for s in sources if s['split']=='validation'])
    (ROOT/'memory.json').write_text(json.dumps(memory,indent=2))
    models=json.loads((ROOT/'memory.json').read_text())['models']
    L.emit('LTM12_MATH14_POLICY',models);rows=[]
    with (ROOT/'holdout.jsonl').open('w') as fd:
        for source in sources:
            if source['split']!='holdout':continue
            for rep,seed in enumerate((17,29,43)):
                shift=(source['id']+rep)%len(TEST)
                for arm in TEST[shift:]+TEST[:shift]:
                    row=(G.routed(arm.split('_',1)[1],models,source,seed)
                         if arm.startswith('LTM12_') else run_checked(arm,source,seed,CAP))
                    row.update(rep=rep,shard=(source['id']-120)//15)
                    rows.append(row);fd.write(json.dumps(row)+'\n');fd.flush()
            if (source['id']+1)%15==0:L.emit('LTM12_MATH14_HOLDOUT',B.metrics(rows,CAP,TEST))
    B.check_contradictions(rows)
    totals=B.metrics(rows,CAP,TEST)
    refs=('Kissat','CaDiCaL','CryptoMiniSat')
    best=min(refs,key=lambda a:totals[a]['PAR2_verified_s'])
    regressions={}
    for arm in ('LTM12_NATIVE','LTM12_HYBRID','MATH14'):
        paired={(r['id'],r['seed']):r for r in rows if r['arm']==best}
        regressions[arm]=sum(r['PAR2_verified_s']>paired[r['id'],r['seed']]['PAR2_verified_s']*1.1+.002
                            for r in rows if r['arm']==arm)
    report=dict(synthetic=True,all_SAT=True,source_count=180,train=90,validation=30,
        holdout=60,repetitions=3,one_logical_CPU=True,policy=models,totals=totals,
        best_reference=best,success_criterion_met=False,
        limitation='Shared synthetic generators, targeted XOR-pair family; no global blind or general UNSAT claim',
        speedup_vs_best={a:totals[best]['PAR2_verified_s']/max(1e-9,totals[a]['PAR2_verified_s'])
                        for a in ('LTM12_NATIVE','LTM12_HYBRID','MATH14')},
        regression_trials_vs_best=regressions,
        families={f:B.metrics([r for r in rows if r['family']==f],CAP,TEST) for f in FAMILIES},
        shards={str(i):B.metrics([r for r in rows if r['shard']==i],CAP,TEST) for i in range(4)})
    (ROOT/'report.json').write_text(json.dumps(report,indent=2))
    L.emit('LTM12_MATH14_FINAL',report)


if __name__=='__main__':main()
