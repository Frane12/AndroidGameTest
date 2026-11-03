#!/usr/bin/env python3
"""DRNAS R22 strict prospective native SAT audit and formula-level PAR-2 analysis.

Prohibit aggregate results if ANY of 16 same-runner complete native shards is
missing, any C/Python clause-use rule differs, any malformed SAT answer,
earlier SHA collision, pre-intervention divergent trace or partial attempt.
"""
from __future__ import annotations
import csv,hashlib,json,math,random,statistics
from collections import defaultdict
from pathlib import Path
import r22_native_benchmark as b

DOWNLOAD=Path("r21-download")
OUT=Path("drnas-r21-results/aggregate")
MODES=b.MODES
PRIMARY="r22_chain50"
FOLDS=("random3_development","random3_test","community3_development","community3_test")
def fail(reason):raise RuntimeError("R22_BLIND_AUDIT_FAIL "+reason)
def sha(p):return b.sha(p)
def csvread(p):
 with p.open(newline="") as f:return list(csv.DictReader(f))
def csvwrite(p,rows):
 with p.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def jsonwrite(p,ob):p.write_text(json.dumps(ob,indent=2,sort_keys=True)+"\n")
def quantile(values,q):
 arr=sorted(values);j=(len(arr)-1)*q;i=int(j)
 return arr[i]*(1-(j-i))+arr[min(i+1,len(arr)-1)]*(j-i)
def bootstrap(records,mode,seed):
 rng=random.Random(seed);by=defaultdict(list)
 for x in records:by[x["n"]].append(x)
 boots=[]
 for _ in range(4000):
  sampled=[rng.choice(z) for _,z in sorted(by.items()) for j in range(len(z))]
  baseline=sum(x["monitor"] for x in sampled)
  treated=sum(x[mode] for x in sampled)
  boots.append(100*(baseline-treated)/baseline)
 return [quantile(boots,.025),quantile(boots,.975)]
def rank_correlation(xs,ys):
 if len(xs)<4:return None
 def rank(z):
  order=sorted(range(len(z)),key=lambda i:z[i])
  out=[0.]*len(z)
  a=0
  while a<len(z):
   q=a+1
   while q<len(z) and z[order[a]]==z[order[q]]:q+=1
   for i in range(a,q):out[order[i]]=(a+q-1)/2
   a=q
  return out
 xx,yy=rank(xs),rank(ys)
 xavg=statistics.mean(xx);yavg=statistics.mean(yy)
 sx=sum((v-xavg)**2 for v in xx);sy=sum((v-yavg)**2 for v in yy)
 return sum((a-xavg)*(v-yavg) for a,v in zip(xx,yy))/math.sqrt(sx*sy) if sx*sy>0 else None

def load():
 protocol=b.cfg();oldhashes=b.history()
 raw=[];traces={};manifests=[];sources=[]
 for category in b.SHARDS:
  folder=DOWNLOAD/("r21-"+category)
  files=[folder/z for z in ("measurements.csv","traces.jsonl","manifest.json")]
  if not all(p.is_file() for p in files):fail("missing shard "+category)
  rows=csvread(files[0])
  events=[json.loads(x) for x in files[1].read_text().splitlines()]
  manifest=json.loads(files[2].read_text())
  if len(rows)!=240 or len(events)!=240 or len(manifest["cases"])!=10:
   fail("incomplete 240 native attempts "+category)
  if (manifest["protocol"]!=protocol["protocol"] or
      manifest["category"]!=category or
      list(manifest["modes"])!=list(MODES) or
      manifest["repeats"]!=3 or manifest["cap_seconds"]!=12 or
      manifest["historic_count"]!=3054 or
      manifest["protocol_sha256"]!=sha(b.PROTOCOL) or
      manifest["historic_sha256"]!=hashlib.sha256(
        "\n".join(sorted(oldhashes)).encode()).hexdigest() or
      manifest["cpu_affinity"]!=[manifest["cpu_core"]] or
      manifest["kissat_pin"]!=protocol["history"]["pinned_kissat_commit"] or
      manifest["v1531_blob"]!=protocol["history"]["frozen_v1531_blob"]):
   fail("source/CPU/protocol/hash mismatch "+category)
  cases={x["formula"]:x for x in manifest["cases"]}
  if len(cases)!=10 or len({x["formula_sha256"] for x in cases.values()})!=10:
   fail("duplicate cases "+category)
  for x in rows:
   case=cases.get(x["formula"])
   if (not case or x["formula_sha256"]!=case["formula_sha256"] or
       x["seed"]!=str(case["metadata"]["seed"]) or
       x["runner"]!=manifest["runner"] or x["category"]!=category or
       x["r22_protocol_sha256"]!=sha(b.PROTOCOL) or
       x["error"] or x["r22_error"] or x["r16_decision_error"]):
    fail("invalid witness, seed, formula SHA, native R22 gate parity")
   if x["status"] not in ("SAT","UNSAT","TIMEOUT"):fail("invalid solver status")
   if x["status"]=="SAT" and x["sat_model_checked"]!="True":
    fail("SAT assignment not checked")
   if x["status"]=="TIMEOUT":
    if abs(float(x["par2_s"])-24.)>1e-5:fail("PAR2 timeout penalty")
   elif abs(float(x["par2_s"])-float(x["wall_s"]))>1e-5:
    fail("PAR2 elapsed time mismatch")
  for x in events:
   key=(x["category"],x["formula"],str(x["repeat"]),x["mode"])
   if key in traces:fail("duplicate trace")
   traces[key]=x
  raw.extend(rows)
  manifests.append(manifest)
  sources.append({
   "category":category,"source_commit":manifest["source_commit"],
   "runner":manifest["runner"],"cpu_core":manifest["cpu_core"],
   "measurements_sha256":sha(files[0]),
   "traces_sha256":sha(files[1]),"manifest_sha256":sha(files[2]),
   "binary_sha256":manifest["binaries"]})
 if len(raw)!=3840 or len(traces)!=3840:fail("3840 native attempts required")
 identities={r["formula_sha256"] for r in raw}
 if len(identities)!=160 or identities&oldhashes:fail("new formula SHA not disjoint")
 paired=defaultdict(dict)
 for x in raw:
  key=(x["category"],x["formula"],x["repeat"])
  if x["mode"] in paired[key]:fail("duplicate mode/repeat")
  paired[key][x["mode"]]=x
 if len(paired)!=480:fail("480 exact native paired groups")
 for key,group in paired.items():
  if set(group)!=set(MODES):fail("missing strategy in paired formula/repeat")
  if len({z["runner"] for z in group.values()})!=1:fail("not same runner")
  if len({z["formula_sha256"] for z in group.values()})!=1:fail("different formula hashes")
  truth={x["status"] for x in group.values() if x["status"] in ("SAT","UNSAT")}
  if len(truth)>1:fail("SAT/UNSAT contradiction")
  mon={int(p["conflict"]):p for p in traces[(*key,"monitor")]["points"]
       if int(p["conflict"])<=1024}
  for arm in ("r11_2048_50","r16_live50","r21_inverse50")+b.LOCAL:
   got={int(p["conflict"]):p for p in traces[(*key,arm)]["points"]
        if int(p["conflict"])<=1024}
   if set(mon)!=set(got):fail("pre1024 checkpoint list changed "+arm)
   for cp in mon:
    if any(mon[cp].get(z)!=got[cp].get(z)
       for z in ("restarts","decisions","propagations","learned","glue","stable")):
     fail("preintervention telemetry differs "+arm)
  for arm in b.LOCAL:
   rr=group[arm];trace=traces[(*key,arm)]
   cp=trace.get("r22_native_checkpoints",[])
   event=trace.get("r22_native_event",{})
   if bool(event)!=(bool(rr["r22_native_decision"])):fail("native event differs CSV")
   if event:
    times=[int(z["conflict"]) for z in cp]
    if len(cp)!=3 or not (256<=times[0]<512 and
       512<=times[1]<1024 and 1024<=times[2]<2048):
     fail("R22 three native time checkpoints missing")
    d0=int(cp[1]["antecedent"])-int(cp[0]["antecedent"])
    d1=int(cp[2]["antecedent"])-int(cp[1]["antecedent"])
    o0=int(cp[1]["mature_low_antecedent"])-int(cp[0]["mature_low_antecedent"])
    o1=int(cp[2]["mature_low_antecedent"])-int(cp[1]["mature_low_antecedent"])
    q0=o0/(d0+1.);q1=o1/(d1+1.)
    stale=(q1<.105 or (q1<.14 and q1<1.8*q0))
    selection=int(b.prior.r20.r16.previous.r14.size_from_category(key[0])>=220
       and (stale if arm=="r22_chain50" else not stale))
    if (event.get("selected")!=str(selection) or
        event.get("weak")!=str(int(stale)) or
        rr["r22_python_selected"]!=str(selection) or
        abs(float(rr["r22_share_prev"])-q0)>2e-5 or
        abs(float(rr["r22_share_recent"])-q1)>2e-5):
     fail("R22 independent C/Python mature low-LBD conflict antecedent mismatch")
    if rr["switch_at"] and (selection!=1 or int(rr["switch_at"])<2048 or
        int(rr["restart_after"])!=50 or rr["learned_before"]!=rr["learned_after"]):
     fail("invalid native clause or restart modification")
 return raw,traces,manifests,sources

def summarize():
 raw,traces,manifests,refs=load()
 grouped=defaultdict(lambda:defaultdict(list))
 for row in raw:grouped[(row["category"],row["formula"])][row["mode"]].append(row)
 formula_records=[];action_records=[];paired_records=[]
 for (cat,name),arms in sorted(grouped.items()):
  if any(len(arms[m])!=3 for m in MODES):fail("per-formula repeats missing")
  monitor=arms["monitor"][0]
  times={m:sum(float(x["par2_s"]) for x in arms[m]) for m in MODES}
  row=dict(formula=name,formula_sha256=monitor["formula_sha256"],
   seed=monitor["seed"],fold=monitor["fold"],family=manifests[b.SHARDS.index(cat)]["family"],
   n=b.prior.r20.r16.previous.r14.size_from_category(cat),
   **times)
  for m in b.LOCAL:
   row[m+"_selected"]=sum(x["r22_python_selected"]=="1" for x in arms[m])
   row[m+"_switched"]=sum(bool(x["switch_at"]) for x in arms[m])
   avail=[x for x in arms[m] if x["r22_share_prev"]!=""]
   row[m+"_share_prev"]=statistics.median(float(x["r22_share_prev"]) for x in avail) if avail else ""
   row[m+"_share_recent"]=statistics.median(float(x["r22_share_recent"]) for x in avail) if avail else ""
   for x in arms[m]:
    action_records.append({
     "fold":row["fold"],"formula":name,"formula_sha256":row["formula_sha256"],
     "repeat":x["repeat"],"mode":m,
     "native_decision":x["r22_native_decision"],"C_Python_selected":x["r22_python_selected"],
     "actual_switch":x["switch_at"],"mature_low_prev":x["r22_mature_low_prev"],
     "mature_low_recent":x["r22_mature_low_recent"],
     "antecedent_prev":x["r22_antecedent_prev"],"antecedent_recent":x["r22_antecedent_recent"],
     "share_prev":x["r22_share_prev"],"share_recent":x["r22_share_recent"]})
  formula_records.append(row)
  for arm in MODES:
   if arm=="monitor":continue
   paired_records.append({
    "formula":name,"sha256":row["formula_sha256"],"fold":row["fold"],
    "n":row["n"],"strategy":arm,
    "monitor_PAR2_s":times["monitor"],"treatment_PAR2_s":times[arm],
    "speedup":times["monitor"]/times[arm],
    "gain_gt2x":times["monitor"]>2*times[arm],
    "regression_gt2x":times[arm]>2*times["monitor"]})
 if len(formula_records)!=160 or len(paired_records)!=1120 or len(action_records)!=960:
  fail("incorrect aggregation size")
 folds={}
 for i,fold in enumerate(FOLDS):
  items=[x for x in formula_records if x["fold"]==fold]
  if len(items)!=(60 if fold.startswith("random3") else 20):fail("fold incorrect")
  mon=sum(z["monitor"] for z in items)
  stats={}
  for j,arm in enumerate(MODES):
   values=[p for p in paired_records if p["fold"]==fold and p["strategy"]==arm]
   total=sum(x[arm] for x in items)
   stats[arm]={
    "PAR2_seconds":round(total,6),
    "gain_vs_monitor_percent":100*(mon-total)/mon,
    "stratified_formula_bootstrap95_gain_percent":bootstrap(items,arm,212121+i*100+j) if arm!="monitor" else [0,0],
    "wins_over_2x":sum(v["gain_gt2x"] for v in values),
    "regressions_over_2x":sum(v["regression_gt2x"] for v in values),
    "selected_attempts":sum(x[arm+"_selected"] for x in items) if arm in b.LOCAL else None,
    "actual_policy_changes":sum(x[arm+"_switched"] for x in items) if arm in b.LOCAL else None,
    "missed_forced_over_2x":sum(x[arm+"_selected"]==0 and
       x["monitor"]>2*x["r11_2048_50"] for x in items) if arm in b.LOCAL else None}
  eligible=[x for x in items if x["r22_chain50_share_prev"]!=""]
  ratios=[float(x["r22_chain50_share_recent"])-float(x["r22_chain50_share_prev"]) for x in eligible]
  forcing=[math.log(x["monitor"]/x["r11_2048_50"]) for x in eligible]
  folds[fold]={
   "formula_count":len(items),"eligible_to_1024":len(eligible),
   "mature_low_LBD_reason_share_change_spearman_vs_forced_gain":rank_correlation(ratios,forcing),
   "strategies":stats}
 OUT.mkdir(parents=True,exist_ok=True)
 report={
  "protocol":b.cfg()["protocol"],"attempts":3840,"formulas":160,"shards":16,
  "repeats":3,"modes":list(MODES),"protocol_sha256":sha(b.PROTOCOL),
  "historical_CNF_SHA_overlap":0,"preintervention_telemetry_mismatches":0,
  "C_Python_gate_mismatches":0,"source_artifacts":refs,"folds":folds,
  "limitations":[
    "Only redundant learned nonbinary clauses (>2 literals) have tracked age and LBD; binary clauses excluded",
    "Direct implication reason includes immediate first-UIP assertion, not only later reuse",
    "Clause birth timestamps stored in clause struct, so all same-binary controls share header-size overhead",
    "R22 signals describe measured reasons, not causal proof of future search efficiency",
    "Synthetic random3/community3, not official SAT Competition benchmark",
    "SAT assignment witnesses checked; UNSAT no independently verified certificates",
    "Original Kissat and stable V15.3.1 are separately compiled references"] }
 jsonwrite(OUT/"results.json",report)
 csvwrite(OUT/"formula_features.csv",formula_records)
 csvwrite(OUT/"paired.csv",paired_records)
 csvwrite(OUT/"native_decisions.csv",action_records)
 text=["# DRNAS R22 prospective native SAT","",
  "R22 real native frozen clause-age/LBD/implication-role gate; NOT off-policy.",
  "Same-binary comparisons; 160 fresh SHA-exclusive synthetic CNFs, 3840 true runs.",
  "| Fold | Strategy | PAR2 s | Gain % | 95% formula bootstrap CI | Switches | >2x regressions |",
  "|---|---|---:|---:|---|---:|---:|"]
 for fold in FOLDS:
  for mode,st in folds[fold]["strategies"].items():
   text.append(f"| {fold} | {mode} | {st['PAR2_seconds']:.6f} | "+
       f"{st['gain_vs_monitor_percent']:+.3f}% | "+
       f"{st['stratified_formula_bootstrap95_gain_percent']} | "+
       f"{st['actual_policy_changes']} | {st['regressions_over_2x']} |")
 text.extend(["","Formula-level inference is exploratory; no causal law or official world record.",
  "UNSAT result certificates NOT independently verified."])
 (OUT/"README.md").write_text("\n".join(text)+"\n")
 print("R22_3840_NATIVE_SOLVES_SUCCESSFULLY_AUDITED",
       json.dumps({"primary":folds["random3_test"],"community":folds["community3_test"]},sort_keys=True),flush=True)
if __name__=="__main__":summarize()
