#!/usr/bin/env python3
"""REAL600 comparison using the frozen, previously audited CORE2 runner."""
import argparse, collections, importlib.util, json, os, platform, sys, time
from pathlib import Path

ROOT=Path.cwd(); DATA=ROOT/'real600_inputs'; OUT=ROOT/'real600_results'
spec=importlib.util.spec_from_file_location('core2_benchmark',ROOT/'research/unified_core2/benchmark.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
b.DATA=DATA; b.OUT=OUT; b.CAP=10; b.REPS=1; b.SHARDS=30
b.P=dict(b.P,cap_s=10,repetitions=1,shards=30,target_sources=600,
         availability_amendment='Source-only availability gate: exactly 600 or stop.',
         selection_seed='DRNAS-REAL600-20261115',memory_limit_bytes=4294967296,
         proof_limit_bytes=268435456)
manifest_hash=b.sha(DATA/'manifest.json')
def sources():
    m=json.loads((DATA/'manifest.json').read_text()); assert m['target']==600 and m['selected']==600
    assert len(m['sources'])==600 and len({s['sha256'] for s in m['sources']})==600
    result=[]
    for i,s in enumerate(m['sources']):
        assert s['id']==i and b.sha(ROOT/s['path'])==s['sha256']
        old=s.get('original',{}); fam=old.get('family',old.get('normalized_name_family'))
        result.append(dict(s,id=i,file_id=s.get('original_url',str(i)),family=fam or s['origin'],catalog_label='unknown'))
    return {'sources':result}
def prepare():
    b.affinity(); src=sources()['sources']; bins=b.pinned()
    cpu=next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),None)
    p={'target':600,'source_manifest_sha256':manifest_hash,'binary_sha256':bins,'arms':b.ARMS,'cap_e2e_s':b.CAP,'repetitions':b.REPS,'shards':b.SHARDS,'commit':os.getenv('GITHUB_SHA'),'kernel':platform.release(),'cpu_model':cpu,'selection':'source-only; retrospective, historical overlap','checker_in_e2e':True,'one_logical_cpu':True,'primary':'structural and standard checked certificates','strict':'MODEL/DRAT/FRAT only'}
    b.save(OUT/'protocol.json',p)
    print('REAL600_READY '+json.dumps({'sources':len(src),'attempts':len(src)*len(b.ARMS)*b.REPS}),flush=True)
def restore():
    b.affinity(); p=json.loads((OUT/'protocol.json').read_text())
    assert p['source_manifest_sha256']==b.sha(DATA/'manifest.json')==manifest_hash
    assert p['binary_sha256']==b.pinned()
    return sources()['sources'],p
b.frozen_sources=sources; b.prepare=prepare; b.restore=restore
# The inherited runner includes SAT model validation in E2E but reports its
# checker duration as zero. Record it separately without changing E2E scoring.
old_model=b.model_ok; old_trial=b.trial; model_time=0.0
def timed_model(*args):
    global model_time
    start=time.perf_counter()
    try: return old_model(*args)
    finally: model_time=time.perf_counter()-start
def trial(*args):
    global model_time
    model_time=0.0; row=old_trial(*args)
    if row['certificate_kind']=='MODEL': row['checker_s']=round(model_time,6)
    return row
b.model_ok=timed_model; b.trial=trial
def report():
    b.report()
    rows=[]
    for i in range(b.SHARDS):
        rows.extend(json.loads(x) for x in (OUT/f'shard-{i}'/'trials.jsonl').read_text().splitlines())
    m=json.loads((DATA/'manifest.json').read_text()); origin={s['id']:s['origin'] for s in m['sources']}
    groups={}
    for group in sorted(set(origin.values())):
        for arm in b.ARMS:
            rr=[r for r in rows if origin[r['id']]==group and r['arm']==arm]
            groups[f'{group} / {arm}']={'attempts':len(rr),'solved':sum(x['accepted'] for x in rr),'sat':sum(x['status']=='SAT_VERIFIED' for x in rr),'unsat':sum(x['status']=='UNSAT_VERIFIED' for x in rr),'par2_sum_s':round(sum(x['PAR2_s'] for x in rr),3),'strict_par2_sum_s':round(sum(x['PAR2_strict_s'] for x in rr),3)}
    b.save(OUT/'by_origin.json',groups)
    print('REAL600_BY_ORIGIN '+json.dumps(groups,sort_keys=True),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['prepare','shard','report']); p.add_argument('--index',type=int); a=p.parse_args()
    if a.action=='prepare': prepare()
    elif a.action=='shard': b.shard(a.index)
    else: report()
