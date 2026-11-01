#!/usr/bin/env python3
import argparse,csv,json,statistics,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tseitin-replay'))
from jerk_r9_analysis import paired_stats
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
allrows=[];formulas=[];groups=[];hashes=set();gains=defaultdict(list)
for cat in ('random3','graphcolor','xor','external_satlib'):
 folder=a.input/cat;rows=list(csv.DictReader((folder/'measurements.csv').open()));manifest=json.loads((folder/'manifest.json').read_text())
 assert len(rows)==225 and len(manifest['cases'])==25
 assert not any(r['error'] for r in rows)
 h={c['formula_sha256'] for c in manifest['cases']};assert len(h)==25 and not h.intersection(hashes);hashes.update(h)
 assert len({(r['formula'],r['mode'],r['repeat']) for r in rows})==225
 for name in sorted({r['formula'] for r in rows}):
  rs=[r for r in rows if r['formula']==name];m={mode:statistics.median(float(r['par2_s']) for r in rs if r['mode']==mode) for mode in ('monitor','stable_v1531','selector')}
  assert len(rs)==9 and len({r['status'] for r in rs if r['status'] in ('SAT','UNSAT')})<=1
  row={'category':cat,'formula':name,**m}
  for base in ('monitor','stable_v1531'):
   gain=100*(m[base]-m['selector'])/m[base];row['gain_pct_vs_'+base]=gain;gains[base].append(gain)
  formulas.append(row)
 for mode in ('monitor','stable_v1531','selector'):
  rs=[r for r in rows if r['mode']==mode];groups.append({'category':cat,'mode':mode,'solved':sum(r['status'] in ('SAT','UNSAT') for r in rs),'timeouts':sum(r['status']=='TIMEOUT' for r in rs),'par2_sum':sum(float(r['par2_s']) for r in rs)})
 allrows.extend(rows)
report={'attempts':len(allrows),'formulas':len(hashes),'groups':groups,'effects':{b:paired_stats(v,20261102+i) for i,(b,v) in enumerate(gains.items())},'totals':{m:sum(float(r['par2_s']) for r in allrows if r['mode']==m) for m in ('monitor','stable_v1531','selector')},'limitation':'same family holdout; short formulas and runtime overhead matter; independent UNSAT proofs not collected for Kissat'}
for fn,rs in [('measurements.csv',allrows),('formula_effects.csv',formulas)]:
 with (a.out/fn).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rs[0]);w.writeheader();w.writerows(rs)
(a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
