#!/usr/bin/env python3
"""Collect 4 frozen X4.2 shards; offline validation then one holdout scoring.
No holdout sample may enter training or parameter/model selection.
Model predictions are retrospective future-time estimates, not causal branching rewards.
"""
from __future__ import annotations
import argparse, collections, json, math, pathlib, statistics, sys, hashlib
from typing import NamedTuple

FEATURES=['nvars','log_clauses','assigned_fraction','depth_fraction',
          'open_long_fraction','open_binary_fraction','open_unit_fraction',
          'conflict_per_decision','learnt_per_decision','elapsed_log_ms']


def get_features(row):
 a=row['before'];n=max(1,row['nvars']);ns=max(1,a['sampled_total'])
 return [math.log1p(n),math.log1p(row['nclauses']),
         a['assigned']/n,a['level']/n,a['sample_unresolved_long']/ns,
         a['sample_open_binary']/ns,a['sample_open_unit']/ns,
         a['conflicts']/(1+a['decisions']),a['learnt']/(1+a['decisions']),
         math.log1p(max(0,a['elapsed_s'])*1000)]


def predict_models(training,other):
 med=statistics.median(y for x,y in training)
 med_model=lambda x:med
 scales=[];centers=[]
 for j in range(len(FEATURES)):
  vals=sorted(x[j] for x,y in training)
  q1=vals[len(vals)//4];q3=vals[(len(vals)*3)//4]
  centers.append(statistics.median(vals));scales.append(max(.03,q3-q1))
 trainnorm=[([(v-c)/sc for v,c,sc in zip(x,centers,scales)],y) for x,y in training]
 def knn(x):
  z=[(v-c)/sc for v,c,sc in zip(x,centers,scales)]
  near=sorted((sum((a-b)**2 for a,b in zip(z,w)),y) for w,y in trainnorm)[:9]
  return max(0,math.expm1(statistics.median(math.log1p(v*1000) for _,v in near))/1000)
 # Fixed, regularized linear regression on log(1+future_time_ms).
 # 10-dimensional Gaussian solve, trained ONLY on training examples.
 def solve(matrix,target):
  m=len(target)
  mat=[list(matrix[i])+[target[i]] for i in range(m)]
  for c in range(m):
   best=max(range(c,m),key=lambda i:abs(mat[i][c]))
   if abs(mat[best][c])<1e-12:return [0]*m
   mat[c],mat[best]=mat[best],mat[c]
   v=mat[c][c]
   for j in range(c,m+1):mat[c][j]/=v
   for i in range(m):
    if i==c:continue
    fact=mat[i][c]
    for j in range(c,m+1):mat[i][j]-=fact*mat[c][j]
  return [mat[i][-1] for i in range(m)]
 p=len(FEATURES)+1;mat=[[0.0]*p for _ in range(p)];tar=[0.0]*p
 for x,y in trainnorm:
  z=[1.0]+x;label=math.log1p(1000*y)
  for i in range(p):
   tar[i]+=z[i]*label
   for j in range(p):mat[i][j]+=z[i]*z[j]
 for i in range(1,p):mat[i][i]+=8.0
 coef=solve(mat,tar)
 def ridge(x):
  z=[1.0]+[(v-c)/sc for v,c,sc in zip(x,centers,scales)]
  y=sum(a*b for a,b in zip(z,coef))
  return max(0, math.expm1(min(20,max(-10,y)))/1000)
 predictions={'median':med_model,'knn9':knn,'ridge_log':ridge}
 metrics={}
 for name,fn in predictions.items():
  errors=[abs(fn(x)-y)*1000 for x,y in other]
  squares=[(fn(x)-y)**2 * 1e6 for x,y in other]
  metrics[name]=dict(MAE_ms=round(statistics.mean(errors),4),RMSE_ms=round(math.sqrt(statistics.mean(squares)),4)) if errors else dict(n=0)
 return metrics


def main():
 p=argparse.ArgumentParser();p.add_argument('--artifact-dir',default='x42_downloads')
 p.add_argument('--out',default='x42_aggregate');args=p.parse_args()
 root=pathlib.Path(args.artifact_dir);out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
 alltrials=[];allrows=[];reports=[]
 for shard in range(4):
  folder=root/f'x42-shard-{shard}'
  if not (folder/'report.json').exists():raise RuntimeError(f'missing shard {shard}')
  report=json.loads((folder/'report.json').read_text());reports.append(report)
  if report['shard']!=shard or report['shards']!=4 or report['sources']!=250:raise RuntimeError('shard wrong size')
  for l in (folder/'trials.jsonl').read_text().splitlines():alltrials.append(json.loads(l))
  for l in (folder/'transitions.jsonl').read_text().splitlines():allrows.append(json.loads(l))
 sha={r['manifest_sha256'] for r in reports}
 if len(sha)!=1 or len(alltrials)!=1000:raise RuntimeError('manifest mismatch / missing sources')
 ids=[x['sha256'] for x in alltrials]
 if len(set(ids))!=1000:raise RuntimeError('duplicate source hash')
 family_splits=collections.defaultdict(set)
 for t in alltrials:family_splits[t['family']].add(t['split'])
 if any(len(splits)!=1 for splits in family_splits.values()):raise RuntimeError('family leakage')
 expected={'train':600,'validation':200,'holdout':200}
 split_counts=collections.Counter(x['split'] for x in alltrials)
 if dict(split_counts)!=expected:raise RuntimeError('bad split '+str(split_counts))
 label_count=0; earliest={}; rows_by_sha=collections.Counter()
 status_by_sha={r['sha256']:r['status'] for r in alltrials}
 for row in allrows:
  sha=row['sha256']; rows_by_sha[sha]+=1
  if sha not in status_by_sha:raise RuntimeError('unexpected trace source')
  if row['label_remaining_wall_s'] is None:continue
  label=row['label_remaining_wall_s']
  if row['result']!='SAT_VERIFIED' or status_by_sha[sha]!='SAT_VERIFIED' or not isinstance(label,(float,int)) or label<0 or not math.isfinite(label):
   raise RuntimeError('invalid future-work label')
  label_count+=1
  if sha not in earliest or row['before']['decisions']<earliest[sha]['before']['decisions']:earliest[sha]=row
 samples=collections.defaultdict(list)
 for row in earliest.values():samples[row['split']].append((get_features(row),row['label_remaining_wall_s']))
 if len(samples['train'])<20: evaluation={'status':'not_enough_verified_train_sources','n_train':len(samples['train'])}
 else:
  # Fixed estimators: fit on train once, evaluate on validation and untouched holdout.
  evaluation=dict(status='diagnostic_only_no_policy',training_instances=len(samples['train']),
    validation_instances=len(samples['validation']),holdout_instances=len(samples['holdout']),
    validation=predict_models(samples['train'],samples['validation']),
    holdout=predict_models(samples['train'],samples['holdout']),
    note='No claim of causal value; holdout has not been used for training or tuning; model trained on completed SAT only.')
 summary={}
 for sp,n in expected.items():
  data=[t for t in alltrials if t['split']==sp]
  completed=[x for x in data if x['status']=='SAT_VERIFIED']
  vals=[t['e2e_s'] for t in completed]
  summary[sp]=dict(total=n,completed=len(completed),censored=n-len(completed),
      target_band_50ms_3s=sum(.05<=x<3 for x in vals),
      under_50ms=sum(x<.05 for x in vals),
      PAR2_s=round(sum(x['PAR2_verified_s'] for x in data),4),
      solved_wall_median_s=round(statistics.median(vals),4) if vals else None,
      solved_wall_p90_s=round(sorted(vals)[int((len(vals)-1)*.9)],4) if vals else None,
      family_names=sorted({t['family'] for t in data}))
 result=dict(status='COMPLETE',total_sources=1000,source_kind='GENERATED_NOT_OFFICIAL',
    manifest_sha256=next(iter(sha)),sha_unique_count=len(set(ids)),
    transition_rows=len(allrows),future_label_rows=label_count,
    independent_labeled_formulas=len(earliest),
    splits=summary,offline_cost_model=evaluation,
    limits='Generator-defined planted SAT CNFs, not 1000 authentic competition originals. Incomplete runs censored. One sample per solved CNF in offline model. No learned live branching, no general distance-to-solution or causal step reward.')
 (out/'report.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
 with (out/'all_trials.jsonl').open('w') as f:
  for row in alltrials:f.write(json.dumps(row,sort_keys=True)+'\n')
 print('X42_FINAL '+json.dumps(result,sort_keys=True),flush=True)

if __name__=='__main__':main()