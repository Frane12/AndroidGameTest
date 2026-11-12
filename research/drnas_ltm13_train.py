"""Direct native control: E2E profile training, frozen choice, online UCB and fallback.
Synthetic SAT only; telemetry explains heuristic choices, not proof of causation.
"""
import collections, hashlib, json, os, pathlib, random, re, statistics, sys, time
import drnas_ltm12_fast600 as G
B,L=G.B,G.L
ROOT=pathlib.Path('ltm13_direct')
FIXED=tuple('FIXED'+str(i) for i in range(4))
TEST=('LTM13_ONLINE','LTM13_TRAINED','FIXED0','LTM9_FAST','Kissat','CaDiCaL','CryptoMiniSat')

def collect():
    # Disjoint seeds and sizes, no outcome filtering. Keep known SAT witnesses.
    old=G.generate
    def generate(family,seed):
        # Compose independent blocks to offer three size tiers, preserving witnesses.
        blocks=1+(seed%3)*3;parts=[];models=[];offset=0
        for b in range(blocks):
            raw,witness=old(family,seed+9000000+b*700000)
            lines=raw.splitlines();n=int(lines[0].split()[2])
            for line in lines[1:]:
                lits=[int(x) for x in line.split() if x!='0']
                parts.append([v+offset if v>0 else v-offset for v in lits])
            models.extend(v+offset if v>0 else v-offset for v in map(int,witness.split()[1:]) if v)
            offset+=n
        return ('p cnf %d %d\n'%(offset,len(parts))+''.join(' '.join(map(str,c))+' 0\n' for c in parts),
                'v '+' '.join(map(str,models))+' 0\n')
    G.generate=generate
    return G.collect(ROOT)

def trial(arm,s,seed,trained=0):
    os.environ.pop('DRNAS_LTM13_DIRECT',None);os.environ.pop('DRNAS_LTM13_FIXED',None)
    if arm.startswith(('LTM13','FIXED')):
        os.environ['DRNAS_LTM13_DIRECT']='1'
        if arm!='LTM13_ONLINE':os.environ['DRNAS_LTM13_FIXED']=str(trained if arm=='LTM13_TRAINED' else int(arm[-1]))
    captured=[];original=B.subprocess.run
    def capture(*args,**kw):
        p=original(*args,**kw);captured.append(p.stdout or '');return p
    B.subprocess.run=capture
    try:r=L.run_checked(arm,s,seed,1.)
    finally:B.subprocess.run=original
    if r['status'].startswith('UNSAT'):raise RuntimeError('UNSAT contradicts generator witness')
    lines=[x for text in captured for x in text.splitlines() if 'LTM13_WINDOW' in x or 'LTM8_LEARNING' in x]
    r.update(telemetry=lines,family=s['family'],fallback=any('fallback-low-reward' in x for x in lines))
    return r

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});L.setup_source()
    old=B.command
    def command(arm,path,seed,cap):
        if arm.startswith(('LTM13','FIXED')):
            return ['mre_atlas23/bin/drnas_ltm13',str(path),'--mode','LTM8_FAST','--time',str(max(.1,cap-.3)),'--seed',str(seed),'--policy','1.0,0.85']
        return old(arm,path,seed,cap)
    B.command=command;sources=collect();train=[];val=[]
    with (ROOT/'training.jsonl').open('w') as fd:
        for s in sources:
            if s['split']=='holdout':continue
            rows=[]
            for rep,seed in enumerate((17,29)):
                shift=(s['id']+rep)%4
                for arm in FIXED[shift:]+FIXED[:shift]:
                    r=trial(arm,s,seed);r['rep']=rep;rows.append(r);fd.write(json.dumps(r)+'\n');fd.flush()
            (train if s['split']=='train' else val).extend(rows)
            if (s['id']+1)%60==0:L.emit('LTM13_TRAIN_PROGRESS',dict(sources=s['id']+1,split=s['split'],totals=B.metrics(train if s['split']=='train' else val,1,FIXED)))
    # One globally learned profile. Validation can reject, never choose an alternative.
    costs={a:sum(r['PAR2_verified_s'] for r in train if r['arm']==a) for a in FIXED}
    candidate=min(FIXED,key=lambda a:costs[a]); vc={a:sum(r['PAR2_verified_s'] for r in val if r['arm']==a) for a in FIXED}
    accepted=candidate!='FIXED0' and vc[candidate]<vc['FIXED0']*.98
    chosen=int(candidate[-1]) if accepted else 0
    memory=dict(candidate=candidate,chosen=chosen,accepted=accepted,train_cost=costs,validation_cost=vc,
                holdout_used_for_fit=False,reward='verified E2E PAR2',online_reward='LBD/work surrogate; not proof of speed')
    (ROOT/'memory.json').write_text(json.dumps(memory,indent=2));L.emit('LTM13_POLICY',memory)
    chosen=json.loads((ROOT/'memory.json').read_text())['chosen'];rows=[]
    with (ROOT/'holdout.jsonl').open('w') as fd:
        for s in sources:
            if s['split']!='holdout':continue
            for rep,seed in enumerate((17,29,43)):
                shift=(s['id']+rep)%len(TEST)
                paired=[]
                for arm in TEST[shift:]+TEST[:shift]:
                    r=trial(arm,s,seed,chosen);r.update(rep=rep,shard=(s['id']-480)//30)
                    rows.append(r);paired.append(r);fd.write(json.dumps(r)+'\n');fd.flush()
                best=min(paired,key=lambda r:r['PAR2_verified_s'])
                L.emit('LTM13_DECISION_AUDIT',dict(id=s['id'],rep=rep,best=best['arm'],
                    controllers=[dict(arm=r['arm'],PAR2=r['PAR2_verified_s'],regret_s=r['PAR2_verified_s']-best['PAR2_verified_s'],
                                      fallback=r['fallback'],telemetry=r['telemetry']) for r in paired if r['arm'].startswith('LTM13')]))
            if (s['id']+1)%30==0:L.emit('LTM13_PROGRESS',B.metrics(rows,1,TEST))
    B.check_contradictions(rows)
    report=dict(memory=memory,totals=B.metrics(rows,1,TEST),shards={str(i):B.metrics([r for r in rows if r['shard']==i],1,TEST) for i in range(4)},
                fallback_trials=sum(r['fallback'] for r in rows),synthetic=True,source_count=600,train=360,validation=120,holdout=120,
                one_CPU=True,holdout_repetitions=3,warning='disjoint instances, shared generators; block composition does not guarantee harder search')
    (ROOT/'report.json').write_text(json.dumps(report,indent=2));L.emit('LTM13_FINAL',report)

if __name__=='__main__':main()
