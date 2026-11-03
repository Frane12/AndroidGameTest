#!/usr/bin/env python3
"""Validate R24b shadow instrumentation against R24, not a speed benchmark."""
import json, os, subprocess
from pathlib import Path

out=Path('drnas-r24-pilot'); out.mkdir(exist_ok=True)
labels=out/'planted_communities.txt'; renamed=out/'planted_communities_renamed.txt'
labels.write_text(''.join(f'{i} {(i-1)//55+1}\n' for i in range(1,221)))
renamed.write_text(''.join(f'{i} {5-((i-1)//55+1)}\n' for i in range(1,221)))
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
rows=[]
for number in (1,3,5,6):
    cnf=out/'cnf'/f'r24_community3_development_{number:02}.cnf'
    runs=[]
    for binary,group in [('kissat-clean/build/kissat',None),('kissat-r24b/build/kissat',labels),
                         ('kissat-r24b/build/kissat',renamed)]:
        env=os.environ.copy();env.update(DRNAS_V177_MODE='r5_monitor',DRNAS_R13_N='220',
                 DRNAS_R12_DEGREE_CV='0.28',DRNAS_R16_GINI='0.16',DRNAS_R16_POLARITY='0.22')
        if group:env['DRNAS_R24_COMMUNITIES']=str(group)
        p=subprocess.run([binary,str(cnf)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,env=env,timeout=4)
        if p.returncode not in (10,20):raise RuntimeError(f'solver failed: {p.returncode}')
        a=[line for line in p.stdout.splitlines() if line.startswith('c R24_TRACE ')]
        b=[line for line in p.stdout.splitlines() if line.startswith('c R24B_TRACE ')]
        runs.append((p.returncode,a,b))
    if runs[0][0]!=runs[1][0] or runs[1][0]!=runs[2][0]:raise RuntimeError('status mismatch')
    if runs[0][1]!=runs[1][1] or runs[1][1]!=runs[2][1]:raise RuntimeError('R24 trace drift')
    if runs[1][2]!=runs[2][2]:raise RuntimeError('community name permutation changed crossings')
    if not runs[1][2]:raise RuntimeError('no graph checkpoint')
    for line in runs[1][2]:
        d={k:int(v) for k,v in (x.split('=',1) for x in line.split()[2:])}
        if d['errors'] or d['cross']+d['unknown']>d['edges'] or d['max_depth']<1:
            raise RuntimeError(f'invalid R24b telemetry {d}')
    rows.append({'formula':cnf.name,'status':runs[0][0],'graph_traces':runs[1][2]})
    print('R24B_VALIDATED',json.dumps(rows[-1]),flush=True)
(out/'r24b_validation.json').write_text(json.dumps(rows,indent=2))
