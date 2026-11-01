#!/usr/bin/env python3
"""Read-only falsification test for finite-difference conflict jerk; never alters SAT solver."""
import argparse,csv,collections,json,math,random,statistics
from pathlib import Path
def finite(x):
 try:
  v=float(x);return v if math.isfinite(v) else None
 except (ValueError,TypeError):return None
def rank(x):
 order=sorted(range(len(x)),key=lambda i:x[i]);out=[0.]*len(x);i=0
 while i<len(x):
  j=i+1
  while j<len(x) and x[order[j]]==x[order[i]]:j+=1
  for k in range(i,j):out[order[k]]=(i+j-1)/2
  i=j
 return out
def rho(x,y):
 if len(x)<8:return None
 a,b=rank(x),rank(y);ma=statistics.mean(a);mb=statistics.mean(b)
 den=math.sqrt(sum((v-ma)**2 for v in a)*sum((v-mb)**2 for v in b))
 return sum((v-ma)*(w-mb) for v,w in zip(a,b))/den if den else None
def main():
 p=argparse.ArgumentParser();p.add_argument('--telemetry',required=True);p.add_argument('--paired',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 groups=collections.defaultdict(list)
 for r in csv.DictReader(open(a.telemetry)):
  key=tuple(r.get(k,'') for k in ('dataset','case_name','solver','repeat'))
  groups[key].append(r)
 gains=collections.defaultdict(list)
 for r in csv.DictReader(open(a.paired)):
  v=finite(r.get('gain_percent'))
  if v is not None:gains[(r['dataset'],r['case_name'],r['solver'])].append(v)
 rows=[]
 for (d,c,s,rep),events in groups.items():
  events.sort(key=lambda r:int(r['event']))
  # Require at least five equally spaced observations in CONFLICT-count domain.
  x=[finite(r.get('conflicts')) for r in events]
  t=[finite(r.get('elapsed_seconds')) for r in events]
  l=[finite(r.get('avg_lbd')) for r in events]
  if len(x)<5 or None in x or None in t:continue
  dt=[t[i]-t[i-1] for i in range(1,len(t))]
  if min(dt)<=0 or max(dt)/min(dt)>1.1:continue
  j=[x[i]-3*x[i-1]+3*x[i-2]-x[i-3] for i in range(3,len(x))]
  gain=gains.get((d,c,s))
  if not gain:continue
  rows.append(dict(dataset=d,case_name=c,solver=s,repeat=rep,jerk_abs_mean=statistics.mean(map(abs,j)),jerk_signed_mean=statistics.mean(j),lbd_change=(l[-1]-l[0] if None not in l else ''),gain_percent=statistics.median(gain)))
 fields=['dataset','case_name','solver','repeat','jerk_abs_mean','jerk_signed_mean','lbd_change','gain_percent']
 with (out/'jerk_features.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 # Aggregate per formula to avoid treating repeated runs as independent.
 by=collections.defaultdict(list)
 for r in rows:by[(r['dataset'],r['case_name'],r['solver'])].append(r)
 aggregate=[(statistics.median(v['jerk_abs_mean'] for v in rs),statistics.median(v['gain_percent'] for v in rs)) for rs in by.values()]
 corr=rho([x for x,y in aggregate],[y for x,y in aggregate]) if aggregate else None
 report={'usable_telemetry_runs':len(rows),'independent_formula_solver_pairs':len(aggregate),'spearman_jerk_vs_gain':corr,'hypothesis_supported':None,'warning':'Exploratory association only; no causal law or validated predictive gate. Unequal telemetry intervals excluded. Do not change solver.'}
 (out/'jerk_report.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
