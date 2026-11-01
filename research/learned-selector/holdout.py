#!/usr/bin/env python3
import argparse,csv,hashlib,json,types
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tseitin-replay'))
from jerk_r8_holdout import fresh_satlib_cases, known_formula_hashes, replace_once

ap=argparse.ArgumentParser();ap.add_argument('--runner',type=Path,required=True);ap.add_argument('--category',required=True);ap.add_argument('--registry',type=Path,required=True);ap.add_argument('--prior',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
seen=known_formula_hashes(a.registry)
for version in ('r8','r9'):
 manifests=list((a.prior/version).rglob('manifest.json'))
 if len(manifests)!=4:raise RuntimeError('Need all four previous shards for '+version)
 for f in manifests:
  cases=json.loads(f.read_text())['cases']
  if len(cases)!=25:raise RuntimeError('Incomplete historical hash registry')
  seen.update(c['formula_sha256'] for c in cases)
s=a.runner.read_text()
for old,new in [(610000,910000),(620000,920000),(630000,930000)]:s=replace_once(s,f'seed={old}+i',f'seed={new}+i')
assert s.count('for i in range(10):')==3
s=s.replace('for i in range(10):','for i in range(25):')
s=replace_once(s,'if len(cases)!=10 or len({c["formula_sha256"] for c in cases})!=10:','if len(cases)!=25 or len({c["formula_sha256"] for c in cases})!=25:')
s=replace_once(s,'if len(rows)!=120:','if len(rows)!=len(cases)*REPEATS*len(MODES):')
s=replace_once(s,'    else:\n        env["DRNAS_V177_MODE"]={','    elif mode=="selector":\n        env["DRNAS_V177_MODE"]="r5_monitor"\n        command=["/tmp/drnas-selector",str(PATCHED),str(STABLE),str(ORIGINAL),str(case["path"].resolve())]\n    else:\n        env["DRNAS_V177_MODE"]={')
s=replace_once(s,'"R5_EARLY","DRNAS_V177_SWITCH","DRNAS_V177_FINAL"','"R5_EARLY","DRNAS_V177_SWITCH","DRNAS_V177_FINAL","DRNAS_SELECTOR"')
s=replace_once(s,'repeat=rep,mode=mode,points=traces,early=early,gate=gate,','repeat=rep,mode=mode,points=traces,early=early,gate=gate,selection=labels.get("DRNAS_SELECTOR",{}),')
r=types.ModuleType('frozen_holdout');r.__file__=str(a.runner);exec(compile(s,str(a.runner),'exec'),r.__dict__)
r.MODES=('monitor','stable_v1531','selector');r.REPEATS=3;r.CAP=8;r.OUT=a.out
r.ORIGINAL=Path('/tmp/kissat-r9-original/build/kissat');r.PATCHED=Path('/tmp/kissat-r9-patched/build/kissat');r.STABLE=Path('/tmp/drnas-r9-v1531')
base_get=r.get_cases
def get_cases(category,out):
 cases=fresh_satlib_cases(r,out,seen) if category=='external_satlib' else base_get(category,out)
 if any(c['formula_sha256'] in seen for c in cases):raise RuntimeError('Historical formula leakage')
 return cases
r.get_cases=get_cases
base_run=r.run_one
def run_one(case,rep,mode,runner):
 row,trace=base_run(case,rep,mode,runner)
 if mode=='selector':
  expected='stable_v1531' if len(case['clauses'])/case['n']<=3.2039999961853027 else 'monitor'
  if trace['selection'].get('route')!=expected:raise RuntimeError('Selector route mismatch')
 return row,trace
r.run_one=run_one
a.out.mkdir(parents=True,exist_ok=True)
protocol={'name':'Frozen learned selector independent holdout','training_run':41353826120,'threshold':3.2039999961853027,'seed_bases':[910000,920000,930000],'excluded_hash_count':len(seen),'excluded_hashes_sha256':hashlib.sha256('\n'.join(sorted(seen)).encode()).hexdigest(),'rule_source_sha256':hashlib.sha256(Path('research/learned-selector/selector.cpp').read_bytes()).hexdigest(),'measure':'end-to-end wall time includes selector startup and header parsing','modes':r.MODES,'formulas':100,'repeats':3,'cap_seconds':8,'validation':'known answers, native certificates where emitted, SAT witness where emitted, cross-route status consistency; no independent Kissat UNSAT proofs'}
(a.out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
r.run_shard(a.category)
