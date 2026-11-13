#!/usr/bin/env python3
"""X4.3 source-only training, holdout isolation, deterministic 3000 design."""
from __future__ import annotations
import copy, json, math, pathlib, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'research'))
import drnas_x43_two_cycle as X
import drnas_x42_1000 as G


def mock_trials():
 result=[]
 for i in range(3000):
  if i<1800:split='train'
  elif i<2400:split='validation'
  else:split='holdout'
  x=[math.log1p(220+i%70),math.log1p(900+i%200),4.2+(i%8)*.1,
     .03*(i%4),.4+(i%13)*.016,.2+(i%7)*.04,
     .05+(i%5)*.002,1.7+(i%10)*.1,.2+(i%9)*.007,
     .06+(i%3)*.03,.02*(i%2),0.]
  core=.05+(i%100)*.007
  adapt=core*(.7 if i%5<2 else 1.35)
  result.append(dict(sha256=f'{i:064x}',formula_id=str(i),split=split,
                     features=x,arms={X.ARM_CORE:{'status':'SAT_VERIFIED','PAR2_s':core},
                                      X.ARM_ADAPT:{'status':'SAT_VERIFIED','PAR2_s':adapt}}))
 return result


def main():
 assert len(X.FEATURES)==12
 assert set(G.FAMILIES)==set(f for fs in G.SPLITS.values() for f in fs)
 with tempfile.TemporaryDirectory() as d:
  root=pathlib.Path(d)
  seeds={}
  for family in G.FAMILIES:
   source=G.gen_source(family,0,root)
   assert source['source_kind']=='GENERATED_NOT_OFFICIAL'
   features=X.extract_features(source['path'],source['nvars'],source['nclauses'])
   assert len(features)==12 and all(math.isfinite(v) for v in features)
   assert source['sha256'] not in seeds
   seeds[source['sha256']]=1
  assert len(seeds)==10
  # Verify native startup and SAT witness on an actual generated instance.
  source=G.gen_source('planted_uniform',1,root)
  if X.X41.is_file() and X.X3.is_file():
   for arm in ('X41_CORE','X3_ADAPTIVE','X41_TRACE'):
    run,trace=X.checked_run(source,arm,.3,root/'trace')
    assert run['status'] in ('SAT_VERIFIED','UNKNOWN')
    if arm=='X41_TRACE':assert trace['trace_rows']>0
  sample=mock_trials()
  model=X.train_model(sample,'frozen-test-manifest')
  model2=X.train_model([copy.deepcopy(r) for r in sample], 'frozen-test-manifest')
  assert model==model2
  assert model['train_count']==1800 and model['validation_count']==600
  assert model['holdout_count']==600
  assert model['uses_source_sha'] is False
  altered=copy.deepcopy(sample)
  for r in altered[2400:]:
   r['arms'][X.ARM_ADAPT]['PAR2_s']=10**9
  # HOLDOUT labels must not influence any learned parameter or threshold.
  assert X.train_model(altered,'frozen-test-manifest')==model
  for r in sample[::257]:
   assert X.choose_arm(model,r['features']) in (X.ARM_CORE,X.ARM_ADAPT)
  assert X.choose_arm(model,sample[0]['features'],policy='always_core')==X.ARM_CORE
  assert X.choose_arm(model,sample[0]['features'],policy='always_adaptive')==X.ARM_ADAPT
  assert set(model['policy'].split(':')[:1]) <= {'always_core','always_adaptive','threshold'}
  print('X43_TEST_PASS',json.dumps(dict(sources=3000,sha_distinct_sample=10,
          train=1800,validation=600,holdout=600,
          holdout_leakage=False,policy=model['policy'],native_smoke=True)))

if __name__=='__main__':main()