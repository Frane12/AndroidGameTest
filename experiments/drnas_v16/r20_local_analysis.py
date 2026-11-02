#!/usr/bin/env python3
"""R20 independently audited prospective native benchmark; no replay.

Require all 16 raw shards, all 3360 real SAT executions, 480 groups of 7
on same core/runner with exact formula SHA and conflict-prefix equality.
C/Python local reuse decision parity is also checked for each R20 run.
"""
import csv,hashlib,json,math,random,statistics
from collections import defaultdict,Counter
from pathlib import Path
import r20_local_benchmark as b

DOWNLOAD=Path("r20-download")
OUT=Path("drnas-r20-results/aggregate")
FOLDS=("random3_development","random3_test","community3_development","community3_test")
def sha(p):return b.sha(p)
def fail(s):raise RuntimeError("R20_STRICT_NATIVE_AUDIT_FAIL "+s)
def writejson(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+"\n")
def writecsv(p,rows):
 if not rows:return
 with p.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def quantile(arr,p):
 z=sorted(arr);v=p*(len(z)-1);k=int(v)
 return z[k]*(1-(v-k))+z[min(k+1,len(z)-1)]*(v-k)
def bootstrap(rows,mode,seed):
 rng=random.Random(seed);strata=defaultdict(list)
 for r in rows:strata[r["n"]].append(r)
 draws=[]
 for _ in range(4000):
  sample=[rng.choice(s) for n,s in sorted(strata.items()) for i in range(len(s))]
  mon=sum(x["monitor"] for x in sample)
  arm=sum(x[mode] for x in sample)
  draws.append(100*(mon-arm)/mon)
 return [quantile(draws,.025),quantile(draws,.975)]
def spearman(x,y):
 if len(x)<4:return None
 def rank(arr):
  idx=sorted(range(len(arr)),key=lambda i:arr[i]);r=[0.]*len(arr)
  a=0
  while a<len(arr):
   z=a+1
   while z<len(arr) and arr[idx[z]]==arr[idx[a]]:z+=1
   v=(a+z-1)/2
   for j in range(a,z):r[idx[j]]=v
   a=z
  return r
 xx,yy=rank(x),rank(y)
 mx=statistics.mean(xx);my=statistics.mean(yy)
 a=sum((u-mx)**2 for u in xx);c=sum((u-my)**2 for u in yy)
 return sum((u-mx)*(v-my) for u,v in zip(xx,yy))/math.sqrt(a*c) if a*c>0 else None

def load():
 c=b.cfg();historic=b.history()
 traces={};raw=[];sources=[];manifests=[]
 for shard in b.SHARDS:
  folder=DOWNLOAD/("r20-"+shard)
  a,bt,m=[folder/z for z in ("measurements.csv","traces.jsonl","manifest.json")]
  if not (a.is_file() and bt.is_file() and m.is_file()):
   fail("missing full raw 210-run shard "+shard)
  with a.open(newline="") as f:rr=list(csv.DictReader(f))
  tt=[json.loads(x) for x in bt.read_text().splitlines()]
  meta=json.loads(m.read_text())
  if len(rr)!=210 or len(tt)!=210 or len(meta["cases"])!=10:
   fail("incomplete real native shard "+shard)
  if (meta["category"]!=shard or meta["protocol"]!=c["protocol"] or
     list(meta["modes"])!=list(b.MODES) or meta["repeats"]!=3 or
     meta["cap_seconds"]!=12 or meta["historic_count"]!=2734 or
     meta["protocol_sha256"]!=sha(b.PROTOCOL) or
     meta["cpu_affinity"]!=[meta["cpu_core"]] or
     meta["kissat_pin"]!=b.r16.PIN or
     meta["v1531_blob"]!=b.r16.STABLE_PIN or
     meta["historic_sha256"]!=hashlib.sha256(
       "\n".join(sorted(historic)).encode()).hexdigest()):
   fail("source/protocol/CPU/seed/SHA drift "+shard)
  cases={x["formula"]:x for x in meta["cases"]}
  if len(cases)!=10 or len({x["formula_sha256"] for x in meta["cases"]})!=10:
   fail("duplicate formula in manifest")
  for x in rr:
   case=cases.get(x["formula"])
   if not case or x["formula_sha256"]!=case["formula_sha256"] or (
      x["seed"]!=str(case["metadata"]["seed"]) or x["runner"]!=meta["runner"]
      or x["category"]!=shard or x["r20_protocol_sha256"]!=sha(b.PROTOCOL)
      or x["error"] or x["r16_decision_error"] or x["r20_error"]):
    fail("incorrect native row, seed, SHA or parity")
   if x["status"] not in ("SAT","UNSAT","TIMEOUT"):fail("invalid solver status")
   if x["status"]=="SAT" and x["sat_model_checked"]!="True":
    fail("SAT model not independently checked")
   if x["status"]=="TIMEOUT":
    if abs(float(x["par2_s"])-24)>1e-6:fail("PAR2 timeout penalty missing")
   elif abs(float(x["par2_s"])-float(x["wall_s"]))>1e-5:
    fail("PAR2 not actual elapsed seconds")
  for t in tt:
   key=(t["category"],t["formula"],str(t["repeat"]),t["mode"])
   if key in traces:fail("duplicate trace across shards")
   traces[key]=t
  raw.extend(rr)
  manifests.append(meta)
  sources.append({
   "shard":shard,"source_commit":meta["source_commit"],
   "runner":meta["runner"],"cpu_core":meta["cpu_core"],
   "manifest_sha256":sha(m),"measurement_sha256":sha(a),
   "trace_sha256":sha(bt),"binaries_sha256":meta["executables"]})
 if len(raw)!=3360 or len(traces)!=3360:
  fail("R20 incomplete 3360 native attempts")
 hashes={x["formula_sha256"] for x in raw}
 if len(hashes)!=160 or hashes&historic:fail("R20 SHA overlap or duplicate CNF")
 paired=defaultdict(dict)
 for x in raw:
  key=(x["category"],x["formula"],x["repeat"])
  if x["mode"] in paired[key]:fail("duplicate mode/attempt")
  paired[key][x["mode"]]=x
 if len(paired)!=480:fail("R20 expected 160*3 groups")
 for key,p in paired.items():
  if set(p)!=set(b.MODES):fail("missing paired arm")
  if len({x["runner"] for x in p.values()})!=1:
   fail("not same runner")
  if len({x["formula_sha256"] for x in p.values()})!=1:
   fail("not same exact CNF")
  ss={x["status"] for x in p.values() if x["status"] in ("SAT","UNSAT")}
  if len(ss)>1:fail("SAT/UNSAT contradictory answers")
  ref={int(t["conflict"]):t for t in traces[(*key,"monitor")]["points"] if int(t["conflict"])<=1024}
  for arm in ("r11_2048_50","r16_live50","r20_local50","r20_inverse50"):
   test={int(t["conflict"]):t for t in traces[(*key,arm)]["points"] if int(t["conflict"])<=1024}
   if set(test)!=set(ref):fail("preintervention 1024 checkpoint sequence changed "+arm)
   for cp in ref:
    if any(ref[cp].get(f)!=test[cp].get(f)
        for f in ("restarts","decisions","propagations","learned","glue","stable")):
     fail("preintervention state mismatch "+arm)
  for arm in b.LOCAL:
   row=p[arm];trace=traces[(*key,arm)]
   event=trace.get("r20_native_event",{})
   cp=trace.get("r20_native_local_checkpoints",[])
   if bool(event)!=(row["r20_native_decision"]!=""):
    fail("R20 recorded event and raw trace do not match")
   if event:
    times=[int(z["conflict"]) for z in cp]
   if len(cp)!=3 or not (256<=times[0]<512 and
       512<=times[1]<1024 and 1024<=times[2]<2048):
     fail("R20 missing or misordered local-use landmark timestamps")
    if event.get("selected")!=row["r20_python_selected"]:
     fail("R20 native vs independent Python gate mismatch")
    if bool(row["switch_at"]) and row["r20_python_selected"]!="1":
     fail("R20 unsolicited native restart")
 return raw,traces,manifests,sources

def main():
 raw,traces,manifests,sources=load()
 OUT.mkdir(parents=True,exist_ok=True)
 groups=defaultdict(lambda:defaultdict(list))
 for x in raw:groups[(x["category"],x["formula"])][x["mode"]].append(x)
 cases=[];pair_records=[];actions=[]
 for (shard,formula),arms in sorted(groups.items()):
  if any(len(arms[mode])!=3 for mode in b.MODES):fail("missing 3 repeated measurements")
  first=arms["monitor"][0]
  summed={arm:sum(float(z["par2_s"]) for z in arms[arm]) for arm in b.MODES}
  row={
   "shard":shard,"formula":formula,"formula_sha256":first["formula_sha256"],
   "fold":first["fold"],"n":b.r16.previous.r14.size_from_category(shard),
   "seed":first["seed"],**summed}
  for arm in b.LOCAL:
   row[arm+"_selected"]=sum(x["r20_python_selected"]=="1" for x in arms[arm])
   row[arm+"_switched"]=sum(bool(x["switch_at"]) for x in arms[arm])
   has=[x for x in arms[arm] if x["r20_reuse_prev"]!=""]
   row[arm+"_reuse_prev"]=statistics.median(float(x["r20_reuse_prev"]) for x in has) if has else ""
   row[arm+"_reuse_recent"]=statistics.median(float(x["r20_reuse_recent"]) for x in has) if has else ""
   for x in arms[arm]:
    actions.append({
     "fold":first["fold"],"formula":formula,"repeat":x["repeat"],"arm":arm,
     "native_event":x["r20_native_decision"],
     "recomputed_stagnating":x["r20_python_stagnating"],
     "selected":x["r20_python_selected"],"actual_switch_at":x["switch_at"],
     "reuse_prev":x["r20_reuse_prev"],"reuse_recent":x["r20_reuse_recent"],
     "prop_prev":x["r20_prop_prev"],"prop_recent":x["r20_prop_recent"],
     "glue_prev":x["r20_glue_prev"],"glue_recent":x["r20_glue_recent"]})
  cases.append(row)
  for arm in b.MODES:
   if arm=="monitor":continue
   pair_records.append({
     "formula":formula,"fold":first["fold"],"n":row["n"],
     "formula_sha256":first["formula_sha256"],"mode":arm,
     "monitor_PAR2_s":summed["monitor"],"treatment_PAR2_s":summed[arm],
     "gain_pct":100*(summed["monitor"]-summed[arm])/summed["monitor"],
     "speedup":summed["monitor"]/summed[arm],
     "gain_gt2x":summed["monitor"]>2*summed[arm],
     "regression_gt2x":summed[arm]>2*summed["monitor"],
     "actual_switches":sum(bool(x["switch_at"]) for x in arms[arm])})
 if len(cases)!=160 or len(pair_records)!=960 or len(actions)!=960:
  fail("aggregated number of formulas/actions wrong")
 folds={}
 for k,fold in enumerate(FOLDS):
  sub=[x for x in cases if x["fold"]==fold]
  if len(sub)!=(60 if fold.startswith("random3") else 20):
   fail("wrong formula count in fold")
  ref=sum(x["monitor"] for x in sub)
  metrics={}
  for i,arm in enumerate(b.MODES):
   total=sum(x[arm] for x in sub)
   paired=[p for p in pair_records if p["fold"]==fold and p["mode"]==arm]
   metrics[arm]={
    "PAR2_s":round(total,6),"gain_vs_monitor_pct":100*(ref-total)/ref,
    "formula_stratified_bootstrap_95_pct":bootstrap(sub,arm,202020+k*100+i) if arm!="monitor" else [0,0],
    "wins_gt2x":sum(p["gain_gt2x"] for p in paired),
    "regressions_gt2x":sum(p["regression_gt2x"] for p in paired),
    "selected_attempts":sum(x[arm+"_selected"] for x in sub) if arm in b.LOCAL else None,
    "real_restarts_switched":sum(x[arm+"_switched"] for x in sub) if arm in b.LOCAL else None,
    "missed_forced_gt2x":sum((x[arm+"_selected"]==0) and x["monitor"]>2*x["r11_2048_50"] for x in sub) if arm in b.LOCAL else None}
  full=[x for x in sub if x["r20_local50_reuse_prev"]!=""]
  local_drop=[x["r20_local50_reuse_recent"]/max(.001,x["r20_local50_reuse_prev"]) for x in full]
  label=[math.log(x["monitor"]/x["r11_2048_50"]) for x in full]
  folds[fold]={
   "formulas":len(sub),"local_reuse_signal_observed":len(full),
   "reuse_ratio_vs_forced50_log_gain_spearman":spearman(local_drop,label) if len(full)>3 else None,
   "strategies":metrics}
 report={
  "protocol":b.cfg()["protocol"],"kind":"R20_TRUE_NATIVE_LOCAL_CLAUSE_REUSE_GATE_PROSPECTIVE",
  "attempts":3360,"formulas":160,"repeats":3,"modes":list(b.MODES),
  "protocol_sha256":sha(b.PROTOCOL),"historical_hash_overlap":0,
  "preintervention_prefix_mismatch":0,"native_python_gate_mismatches":0,
  "source_artifacts":sources,"manifests":manifests,"folds":folds,
  "cautions":[
   "Kissat clauses_used counts redundant reason clause use, not proven causal usefulness",
   "Frozen local gate, no threshold retuning on any R20 outcome",
   "Random3/Community3 generated CNFs, NOT official SAT Competition benchmarks",
   "SAT models checked, UNSAT independent proof certificates absent",
   "V15.3.1 separate executable; same binary paired monitor/force50/R16/R20",
   "All aggregate bootstraps stratified by formula size and sample formula, not correlated repeats"]}
 writejson(OUT/"results.json",report)
 writecsv(OUT/"formula_features.csv",cases)
 writecsv(OUT/"paired.csv",pair_records)
 writecsv(OUT/"native_local_decisions.csv",actions)
 lines=["# DRNAS R20 — real native local learned-clause usefulness test","",
  "Native in-process R20 local gate and inverse control; no off-policy replay.",
  "All 160 CNFs SHA-disjoint from earlier experiments; 3 repeats each.",
  "",
  "| Fold | Strategy | PAR2 (s) | Δ vs monitor | 95% formula bootstrap CI | Selected | >2x regressions |",
  "|---|---|---:|---:|---|---:|---:|"]
 for fold in FOLDS:
  for arm in b.MODES:
   x=folds[fold]["strategies"][arm]
   lines.append(f"| {fold} | {arm} | {x['PAR2_s']:.6f} | {x['gain_vs_monitor_pct']:+.3f}% | "+
    f"{x['formula_stratified_bootstrap_95_pct']} | {x['selected_attempts']} | {x['regressions_gt2x']} |")
 lines.extend(["","The clause-reuse count is observational, not a proof of causal solver dynamics.",
  "Primary claim requires a new random3_test benefit with formula-bootstrap CI >0.",
  "UNSAT certificates were NOT independently verified."])
 (OUT/"README.md").write_text("\n".join(lines)+"\n")
 print("R20_FULL_NATIVE_BLIND_ANALYSIS_COMPLETE",json.dumps({
  "attempts":3360,"primary":folds["random3_test"],
  "community_transfer":folds["community3_test"]},sort_keys=True),flush=True)
if __name__=="__main__":main()
