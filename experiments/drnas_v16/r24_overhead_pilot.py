#!/usr/bin/env python3
"""Paired instrumentation-overhead check on R24 development formulas only."""
import json, os, random, statistics
from pathlib import Path
import r24_live_pilot as pilot

os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
sources={'r22':'kissat-r22/build/kissat', 'r24':'kissat-clean/build/kissat'}
sources={k:str(Path(v).resolve()) for k,v in sources.items()}
rows=[]
rng=random.Random(242405)
for family in ('random3','community3'):
    for i in range(4):
        path,clauses,sha,seed=pilot.make_case(family,'development',i)
        for rep in range(2):
            order=list(sources);rng.shuffle(order)
            for name in order:
                result=pilot.run(sources[name],path,clauses,family,'development',rep,'monitor')
                result['instrumentation']=name
                rows.append(result)
                print('OVERHEAD',path.name,rep,name,result['seconds'],flush=True)
        statuses={x['status'] for x in rows if x['formula']==path.name} - {'TIMEOUT'}
        if len(statuses)>1:raise RuntimeError('Instrumentation changed SAT/UNSAT status')
pairs=[]
for name in sorted({x['formula'] for x in rows}):
    pairs.append({kind:statistics.median(x['par2'] for x in rows if x['formula']==name and x['instrumentation']==kind)
                  for kind in sources})
base=sum(p['r22'] for p in pairs); instrumented=sum(p['r24'] for p in pairs)
report={'formulas':len(pairs),'r22_sum_medians':base,'r24_sum_medians':instrumented,
        'overhead_pct':100*(instrumented-base)/base,'pairs':pairs,
        'timeouts':sum(r['status']=='TIMEOUT' for r in rows)}
Path('drnas-r24-pilot/overhead.json').write_text(json.dumps({'report':report,'rows':rows},indent=2))
print('OVERHEAD_SUMMARY',json.dumps(report),flush=True)
