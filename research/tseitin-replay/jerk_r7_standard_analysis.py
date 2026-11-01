#!/usr/bin/env python3
"""Analyze newly executed R7 timed R6 benchmark (not replay).
All features from MONITOR checkpoints <=2048 conflicts, before forced restart.
No learned threshold or unsupported universal law claim.
"""
import argparse,csv,hashlib,json,math,os,statistics,random
from pathlib import Path
from collections import defaultdict,Counter

MODES=('stable_v1531','monitor','forced_restart25','r5_frozen_gate')
CATS=('random3','graphcolor','xor','external_satlib')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rho(a,b):
 if len(a)<6:return None
 def ranks(a):
  order=sorted(range(len(a)),key=lambda i:a[i]);out=[0.0]*len(a);i=0
  while i<len(order):
   j=i+1
   while j<len(order) and a[order[i]]==a[order[j]]:j+=1
   for k in range(i,j):out[order[k]]=(i+j-1)/2
   i=j
  return out
 x,y=ranks(a),ranks(b);mx=statistics.mean(x);my=statistics.mean(y)
 den=sum((z-mx)**2 for z in x)*sum((z-my)**2 for z in y)
 return sum((v-mx)*(w-my) for v,w in zip(x,y))/math.sqrt(den) if den else None
def interpolate(t,x,value):
 if value<=t[0]:return x[0]
 if value>=t[-1]:return x[-1]
 for i in range(1,len(t)):
  if t[i]>=value:
   return x[i-1]+(x[i]-x[i-1])*(value-t[i-1])/(t[i]-t[i-1])
 raise AssertionError
def feature(points):
 eligible=[]
 for p in points:
  try: c=int(p['conflict']);t=int(p['wall_ns'])
  except (KeyError,ValueError,TypeError):continue
  if c<=2048: eligible.append((t,c))
 eligible=sorted(set(eligible))
 if len(eligible)<7:return None,'insufficient_prefix_checkpoints'
 t=[v[0] for v in eligible];c=[v[1] for v in eligible]
 if any(t[i]<=t[i-1] or c[i]<=c[i-1] for i in range(1,len(t))):
  return None,'non_monotonic_time_or_conflicts'
 duration=(t[-1]-t[0])*1e-9
 if duration<=0:return None,'zero_duration'
 samples=[interpolate(t,c,t[0]+(t[-1]-t[0])*i/10) for i in range(11)]
 third=[samples[i]-3*samples[i-1]+3*samples[i-2]-samples[i-3] for i in range(3,len(samples))]
 denom=max(1.0,samples[-1]-samples[0])
 return dict(jerk_abs_norm=statistics.mean(map(abs,third))/den,
             jerk_signed_norm=statistics.mean(third)/den,
             prefix_duration_s=duration,prefix_checkpoints=len(eligible),
             prefix_first_conflict=c[0],prefix_last_conflict=c[-1]),None
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
 out=args.out;out.mkdir(parents=True,exist_ok=True)
 rows=[];traces={};sources=[]
 for category in CATS:
  folder=args.input/category
  csvpath=folder/'measurements.csv';trpath=folder/'traces.jsonl';mf=folder/'manifest.json'
  if not all(p.is_file() for p in (csvpath,trpath,mf)):raise SystemExit('Missing complete benchmark shard: '+category)
  rr=list(csv.DictReader(csvpath.open()))
  tt=[json.loads(z) for z in trpath.read_text().splitlines() if z.strip()]
  meta=json.loads(mf.read_text())
  if len(rr)!=120 or len(tt)!=120:raise SystemExit('Incorrect shard size '+category)
  if meta['category']!=category or meta['stable_blob']!='d280a2ffa28d72aec183323bbea40544d676112d':
   raise SystemExit('Unfrozen stable V15.3.1: '+category)
  if meta['kissat_pin']!='8af8e56f174b778aef3aa45af9f739b2a5f492c2':raise SystemExit('Unpinned Kissat')
  if len(meta['cases'])!=10:raise SystemExit('Expected 10 CNFs')
  if any(r.get('error') for r in rr):raise SystemExit('A measured run recorded error')
  rows+=rr
  for t in tt:
   key=(t['category'],t['formula'],str(t['repeat']),t['mode'])
   if key in traces:raise SystemExit('Duplicate trace '+str(key))
   traces[key]=t
  sources.append(dict(category=category,measurements_sha256=sha(csvpath),
     traces_sha256=sha(trpath),manifest_sha256=sha(mf),runner=meta['runner'],
     source_commit=meta['source_commit'],executables=meta['executables']))
 if len(rows)!=480:raise SystemExit('480 fresh attempts required')
 ix={}
 for r in rows:
  key=(r['category'],r['formula'],str(r['repeat']),r['mode'])
  if key in ix:raise SystemExit('Duplicate attempt')
  ix[key]=r
 if len(ix)!=480 or len(traces)!=480:raise SystemExit('Incomplete raw source evidence')
 pairs=[];skips=Counter();feats=[]
 for cat in CATS:
  formulas=sorted({r['formula'] for r in rows if r['category']==cat})
  if len(formulas)!=10:raise SystemExit('Expected 10 distinct formulas '+cat)
  for formula in formulas:
   for rep in range(3):
    allrows={mode:ix.get((cat,formula,str(rep),mode)) for mode in MODES}
    if any(x is None for x in allrows.values()):raise SystemExit('Missing matched comparison')
    if len({r['runner'] for r in allrows.values()})!=1:raise SystemExit('Cross-runner pair')
    if len({r['formula_sha256'] for r in allrows.values()})!=1:raise SystemExit('Formula SHA mismatch')
    statuses={r['status'] for r in allrows.values() if r['status'] in ('SAT','UNSAT')}
    if len(statuses)>1:raise SystemExit('SAT/UNSAT disagreement')
    trace=traces[(cat,formula,str(rep),'monitor')]
    f,reason=feature(trace.get('points',[]))
    if reason:skips[reason]+=1
    for treatment in ('stable_v1531','forced_restart25','r5_frozen_gate'):
     m=allrows['monitor'];v=allrows[treatment]
     base=float(m['par2_s']);target=float(v['par2_s'])
     if base<0 or target<0:raise SystemExit('Negative PAR2')
     rec=dict(category=cat,formula=formula,formula_sha256=m['formula_sha256'],repeat=rep,
       treatment=treatment,monitor_par2=base,treatment_par2=target,
       speedup=base/target if target else None,
       gain_pct=100*(base-target)/base if base else None,
       monitor_status=m['status'],treatment_status=v['status'],
       usable_jerk=int(f is not None),
       jerk_abs_norm=(f or {}).get('jerk_abs_norm',''),
       jerk_signed_norm=(f or {}).get('jerk_signed_norm',''),
       prefix_checkpoints=(f or {}).get('prefix_checkpoints',''),
       prefix_duration_s=(f or {}).get('prefix_duration_s',''))
     pairs.append(rec)
    if f:feats.append(dict(category=cat,formula=formula,repeat=rep,**f))
 with (out/'jerk_pairs.csv').open('w',newline='') as h:
  fields=list(pairs[0]);w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(pairs)
 if feats:
  with (out/'jerk_features.csv').open('w',newline='') as h:
   fields=list(feats[0]);w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(feats)
 else:(out/'jerk_features.csv').write_text('category,formula,repeat,jerk_abs_norm,jerk_signed_norm,prefix_duration_s,prefix_checkpoints\n')
 # Aggregate repeats before Spearman; don't pretend 3 repeats are independent instances.
 associations={}
 for mode in ('forced_restart25','r5_frozen_gate'):
  for category in ('all',)+CATS:
   relevant=[r for r in pairs if r['treatment']==mode and r['usable_jerk'] and (category=='all' or r['category']==category)]
   by=defaultdict(list)
   for r in relevant:by[(r['category'],r['formula'])].append(r)
   xs=[statistics.median(v['jerk_abs_norm'] for v in rr) for rr in by.values()]
   ys=[statistics.median(v['gain_pct'] for v in rr) for rr in by.values() if all(v['gain_pct'] is not None for v in rr)]
   correlation=rho(xs,ys) if len(xs)==len(ys) else None
   associations[mode+'/'+category]=dict(formulas=len(xs),spearman=correlation)
 group=[]
 for cat in CATS:
  for mode in MODES:
   sub=[r for r in rows if r['category']==cat and r['mode']==mode]
   group.append(dict(category=cat,mode=mode,attempts=len(sub),
     solved=sum(r['status'] in ('SAT','UNSAT') for r in sub),
     timeouts=sum(r['status']=='TIMEOUT' for r in sub),
     sum_par2=round(sum(float(r['par2_s']) for r in sub),8)))
 report=dict(measurements=len(rows),unique_formulas=40,paired_comparisons=len(pairs),
  monitor_trials_with_jerk=len(feats),monitor_trials_total=120,
  skipped=dict(skips),associations=associations,groups=group,sources=sources,
  caution='Pre-2048 passive observables on previously studied R6 families; exploratory correlations only, no causal proof, no unseen/official record. Active Jerk gate NOT tested.')
 (out/'jerk_standard_report.json').write_text(json.dumps(report,indent=2)+'\n')
 try:
  import matplotlib
  matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  for mode in ('forced_restart25','r5_frozen_gate'):
   fig,ax=plt.subplots(figsize=(8,5))
   for cat in CATS:
    rr=[r for r in pairs if r['category']==cat and r['treatment']==mode and r['usable_jerk']]
    if rr:ax.scatter([r['jerk_abs_norm'] for r in rr],[r['gain_pct'] for r in rr],label=cat,alpha=.65)
   ax.axhline(0,color='black',ls='--',lw=0.8);ax.set(xlabel='Pre-intervention normalized jerk magnitude',ylabel='PAR-2 gain vs monitor (%)',title='Exploratory timed jerk association')
   if ax.has_data():ax.legend()
   fig.tight_layout();fig.savefig(out/('scatter_jerk_'+mode+'.png'),dpi=160);plt.close(fig)
 except ImportError:pass
 print(json.dumps({'measurements':len(rows),'usable_trials':len(feats),'associations':associations},indent=2))
if __name__=='__main__':main()
