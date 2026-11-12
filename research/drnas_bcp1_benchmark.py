#!/usr/bin/env python3
"""Paired retrospective gap test: identical R153, policy and full-process limits."""
import argparse,collections,hashlib,json,lzma,os,pathlib,random,statistics
import drnas_r28_native_benchmark as B
P=pathlib.Path
ROOT=P('bcp1_results')
ARMS=['BASE','BLOCKER','CIRCULAR','Kissat','CaDiCaL','CryptoMiniSat']
OLD_COMMAND=B.command
def command(arm,p,cap,seed):
    if arm in ARMS[:3]:
        exe='mre_r28_native/drnas_r28_native' if arm=='BASE' else 'mre_bcp1/'+arm
        return [exe,p,'--time',str(cap),'--seed',str(seed),'--profile','fast']
    return OLD_COMMAND(arm,p,cap,seed)
B.command=command;B.ROOT=ROOT
def collect():
    from remotezip import RemoteZip
    plan=json.loads(P('research/drnas_bcp1_sources.json').read_text())
    (ROOT/'cases').mkdir(exist_ok=True)
    cases=[]
    with RemoteZip(plan['archive'],timeout=120) as z:
        for c in plan['sources']:
            raw=lzma.decompress(z.read(c['source_file']))
            assert hashlib.sha256(raw).hexdigest()==c['sha256'],('original source mismatch',c)
            p=ROOT/'cases'/(str(c['id'])+'_'+c['sha256'][:12]+'.cnf');p.write_bytes(raw)
            cases.append(dict(c,path=str(p),cohort=c['family'],dataset='official2024_retrospective'))
            B.emit('BCP1_SOURCE',cases[-1])
    assert len(cases)==12 and len({c['sha256'] for c in cases})==12
    return cases
def aggregate(rows):
    result={}
    for arm in sorted({r['arm'] for r in rows}):
        rs=[r for r in rows if r['arm']==arm]
        result[arm]={k:sum(r[k] for r in rs) for k in ('e2e_s','PAR2_verified_s','PAR2_reported_s','verified','reported_solved')}
        result[arm].update(trials=len(rs),unique_verified=len({r['sha256'] for r in rs if r['verified']}),
                           timeouts=sum(r['status']=='TIMEOUT' for r in rs))
    return result
def report(rows,complete=False):
    stages={stage:aggregate([r for r in rows if r['stage']==stage]) for stage in sorted({r['stage'] for r in rows})}
    real=[r for r in rows if r['stage']=='real12']
    matched=collections.defaultdict(dict)
    for r in real:matched[(r['sha256'],r['rep'])][r['arm']]=r
    comparisons={}
    for arm in ('BLOCKER','CIRCULAR'):
        pairs=[(d[arm],d['BASE']) for d in matched.values() if arm in d and 'BASE' in d]
        a=sum(x['PAR2_verified_s'] for x,y in pairs);b=sum(y['PAR2_verified_s'] for x,y in pairs)
        comparisons[arm]=dict(paired=len(pairs),baseline_over_candidate_PAR2=b/a if a else None,
            verified_gains=sum(x['verified'] and not y['verified'] for x,y in pairs),
            verified_losses=sum(y['verified'] and not x['verified'] for x,y in pairs),
            common_solved_median_speedup=statistics.median([y['e2e_s']/x['e2e_s'] for x,y in pairs if x['verified'] and y['verified']]) if any(x['verified'] and y['verified'] for x,y in pairs) else None)
    per_source={}
    for sha in sorted({r['sha256'] for r in real}):
        rs=[r for r in real if r['sha256']==sha]
        per_source[sha]=dict(id=rs[0]['id'],family=rs[0]['cohort'],arms=aggregate(rs))
    out=dict(complete=complete,trials=len(rows),stages=stages,paired_vs_base=comparisons,
       shards={str(s):aggregate([r for r in real if r['shard']==s]) for s in sorted({r['shard'] for r in real})},
       per_source=per_source,one_logical_CPU=True,main_repetitions=3,real_cap_s=8,
       verification='original SAT witnesses; source GF2/PHP certificates; general UNSAT unverified scores kept separate',
       promotion='NONE. Retrospective targeted test. Require independent unseen family holdout, >=30% lower verified PAR2 versus best reference, no loss of verified coverage.',
       paired_unit='source SHA and repeat; repetitions are not independent formulas')
    (ROOT/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
    return out
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--local-smoke',action='store_true');a=ap.parse_args()
    ROOT.mkdir(exist_ok=True);cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    real=[] if a.local_smoke else collect();synthetic=B.controls()
    (ROOT/'sources.json').write_text(json.dumps(real+synthetic,indent=2)+'\n')
    arms=ARMS[:3] if a.local_smoke else ARMS
    stages=[('controls',synthetic,1.0 if a.local_smoke else 2.0)]
    if real:stages=[('real12',real,8.)]+stages
    reps=2 if a.local_smoke else 3
    B.emit('BCP1_PLAN',dict(cpu=cpu,arms=arms,repetitions=reps,stages=[(s,len(cs),cap) for s,cs,cap in stages],expected_trials=sum(len(cs)*len(arms)*reps for s,cs,cap in stages)))
    rows=[];claims=collections.defaultdict(set)
    with (ROOT/'results.jsonl').open('w') as fd:
        for stage,cs,cap in stages:
            for index,c in enumerate(cs):
                for rep in range(reps):
                    order=list(arms);random.Random(c['sha256']+str(rep)).shuffle(order)
                    for arm in order:
                        r=B.trial(c,arm,stage,rep,cap);r['shard']=index//4 if stage=='real12' else -1
                        rows.append(r)
                        if r['reported_solved']:claims[c['sha256']].add('UNSAT' if r['status'].startswith('UNSAT') else 'SAT')
                        assert len(claims[c['sha256']])<=1,('contradiction',c['id'],arm)
                        fd.write(json.dumps(r)+'\n');fd.flush();B.emit('BCP1_TRIAL',r)
                report(rows);B.emit('BCP1_PROGRESS',dict(stage=stage,completed=index+1,trials=len(rows)))
    result=report(rows,True);B.emit('BCP1_FINAL',dict(stages=result['stages'],paired_vs_base=result['paired_vs_base']))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('## BCP1: original SAT2024 targeted gaps, retrospective\n\nOne logical CPU, serial arms, 3 repeats, 8s full-process cap.\n\n|Arm|Verified solved|Reported solved|Verified PAR2 s|Reported PAR2 s|\n|---|---:|---:|---:|---:|\n')
            for arm,m in result['stages'].get('real12',{}).items():f.write(f"|{arm}|{m['verified']}/{m['trials']}|{m['reported_solved']}|{m['PAR2_verified_s']:.4f}|{m['PAR2_reported_s']:.4f}|\n")
if __name__=='__main__':main()
