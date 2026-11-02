#!/usr/bin/env python3
"""R21 new true clause-age/LBD/reason-role prospective native SAT experiment.

Each case uses native same-binary monitor/forced50/R16/R20/R21 local/R21
inverse and separate upstream Kissat plus frozen V15.3.1, 3 real repetitions.
R21's 64-bit clause-birth metadata persists in arena relocations. True direct
implication reasons are recorded in assign.c; 1-UIP antecedents in deduce.c.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random
from pathlib import Path
import r20_local_benchmark as r20

ROOT=Path("experiments/drnas_v16")
PROTOCOL=ROOT/"r21_frozen_protocol.json"
R20_FORMULAS=ROOT/"r20-results/current/formula_features.csv"
OUT=Path("drnas-r21-results")
MODES=("monitor","r11_2048_50","r16_live50","r20_local50",
       "r21_mature_low50","r21_inverse50","original_kissat","stable_v1531")
LOCAL=("r21_mature_low50","r21_inverse50")
SHARDS=r20.SHARDS
FIELDS=r20.FIELDS+("r21_native_decision","r21_python_selected",
  "r21_python_signal","r21_direct_prev","r21_direct_recent",
  "r21_mature_low_prev","r21_mature_low_recent","r21_share_prev",
  "r21_share_recent","r21_trace_checkpoints","r21_protocol_sha256",
  "r21_error")
REPEAT=3
CAP=12
# Maintain R16 and R20 parsers before appending R21's two own tags.
PREV_PARSE=r20.parse_r20
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cfg():
 c=json.loads(PROTOCOL.read_text())
 if (c["protocol"]!="DRNAS-R21-clause-signature-age-lbd-implication-role-frozen-20261102-v2"
     or c["dataset"]["modes"]!=list(MODES)
     or c["dataset"]["expected_native_executions"]!=3840
     or c["dataset"]["seed_base"]!=2121210000
     or c["history"]["pinned_kissat_commit"]!=r20.r16.PIN
     or c["history"]["frozen_v1531_blob"]!=r20.r16.STABLE_PIN
     or c["frozen_gate"]["low_lbd_max"]!=4
     or c["frozen_gate"]["mature_age_conflicts"]!=256
     or c["frozen_gate"]["min_prior_lowLBD_mature_reason_share"]!=.08
     or c["frozen_gate"]["max_recent_to_prior_share_ratio"]!=.85):
  raise RuntimeError("R21 PROTOCOL OR NATIVE GATE PIN DRIFT")
 return c
def history():
 c=cfg()
 prev=r20.history()
 if len(prev)!=2734:raise RuntimeError("R21 R20 HISTORY MISSING")
 if r20.r19.git_blob(R20_FORMULAS)!=c["history"]["r20_formula_features_git_blob"]:
  raise RuntimeError("R21 R20 ARCHIVED FORMULA BLOB DRIFT")
 with R20_FORMULAS.open(newline="") as f:
  newly={x["formula_sha256"] for x in csv.DictReader(f)}
 if len(newly)!=160 or newly&prev:
  raise RuntimeError("R21 R20 HISTORICAL FORMULA SHA NOT DISTINCT")
 used=prev|newly
 if len(used)!=2894:raise RuntimeError("R21 HISTORIC FORMULA COUNT NOT 2894")
 return used
def make_cases(category,folder,used):
 c=cfg()
 n=r20.r16.previous.r14.size_from_category(category)
 family=r20.r16.previous.r14.family_from_category(category)
 fold="development" if "_development" in category else "test"
 part=int(category[-1]);result=[]
 for j in range(10):
  seed=(c["dataset"]["seed_base"]+n*10000+(1000 if fold=="test" else 0)
     +part*10+j+(20000 if family=="community3" else 0))
  rng=random.Random(seed);clauses=[]
  for _ in range(round(4.23*n)):
   if family=="community3" and rng.random()<.65:
    start=rng.randrange(4)*(n//4)+1
    vs=rng.sample(range(start,start+n//4),3)
   else:vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  fs=r20.r16.previous.r14.r11.features(clauses,n)
  case=r20.r16.previous.r14.r11.base.emit_cnf(
    folder,f"r21_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
    n,clauses,"UNKNOWN","generated_prospective",
    "R21 true clause age/LBD/implication-role blind test, not official",
    "r21-true-clause-birth-lbd-role-gate-frozen",
    {"seed":seed,"fold":fold,"family":family,
     "features":fs,"community_probability":.65 if family=="community3" else 0.})
  if case["formula_sha256"] in used:
   raise RuntimeError("R21 HASH COLLISION EARLIER CORPUS")
  case["category"]=category
  result.append(case)
 if len({x["formula_sha256"] for x in result})!=10:
  raise RuntimeError("R21 DUPLICATE NEW CASE IN SHARD")
 return result
def parse(output):
 points,labels=PREV_PARSE(output)
 checkpoints=[];decisions=[]
 for line in output.splitlines():
  if line.startswith("c R21_TRACE "):
   out={}
   for token in line.split()[2:]:
    if "=" in token:
     key,v=token.split("=",1);out[key]=v
   checkpoints.append(out)
  elif line.startswith("c R21_DECISION "):
   out={}
   for token in line.split()[2:]:
    if "=" in token:
     key,v=token.split("=",1);out[key]=v
   decisions.append(out)
 if len(checkpoints)>3 or len(decisions)>1:
  raise RuntimeError("R21 DUPLICATE TRACE OR DECISION")
 early=labels.setdefault("DRNAS_V177_EARLY",{})
 early["r21_checkpoint"]=checkpoints
 early["r21_decision"]=decisions[0] if decisions else {}
 return points,labels
r20.r16.previous.r14.r11.base.extract_tags=parse

def actual_run(case,rep,mode,runner):
 if mode not in LOCAL:
  row,trace=r20.run_one(case,rep,mode,runner)
  event={};values={}
 else:
  features=case["metadata"]["features"]
  names={"DRNAS_R16_GINI":features["degree_gini"],
         "DRNAS_R16_POLARITY":features["polarity_imbalance"]}
  old={k:os.environ.get(k) for k in names}
  try:
   for k,v in names.items():os.environ[k]=format(v,".17g")
   row,trace=r20.r16.previous.r14.run_one(case,rep,mode,runner)
  finally:
   for k,v in old.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
  row["fold"]=r20.r16.previous.r14.fold_from_category(case["category"])
  row["r16_protocol_sha256"]=sha(r20.r16.CONFIG)
  row["r16_model_sha256"]=sha(r20.r16.MODEL)
  early=trace.get("early",{})
  inherited=early.get("r16_event",{})
  event=early.get("r21_decision",{})
  checkpoints=early.get("r21_checkpoint",[])
  row.update(r16_native_conflict=inherited.get("conflict",""),
      r16_native_ready=inherited.get("complete",""),
      r16_native_score=inherited.get("score",""),
      r16_python_score="",r16_selected=inherited.get("selected",""),
      r16_expected_target=inherited.get("target",""),
      r16_threshold=inherited.get("threshold",""),
      r16_model=inherited.get("model",""),r16_decision_error="")
  values={}
  if event:
   times=[int(q["conflict"]) for q in checkpoints]
   if not(len(times)==3 and 256<=times[0]<512 and
          512<=times[1]<1024 and 1024<=times[2]<2048):
    row["error"]="R21 NOT 3 ORDERED ACTUAL CHECKPOINTS 256/512/1024"
   else:
    a,b,d=checkpoints
    v=lambda name,p,q:int(q[name])-int(p[name])
    direct0=v("direct",a,b);direct1=v("direct",b,d)
    oldlow0=v("oldlow",a,b);oldlow1=v("oldlow",b,d)
    share0=oldlow0/(1.+direct0);share1=oldlow1/(1.+direct1)
    signal=share0>=.08 and share1<.85*share0
    selected=(case["n"]>=220 and
      (signal if mode=="r21_mature_low50" else not signal))
    vals={
      "direct_prev":direct0,"direct_recent":direct1,
      "mature_low_prev":oldlow0,"mature_low_recent":oldlow1,
      "share_prev":share0,"share_recent":share1}
    mismatch=[k for k,v in vals.items()
      if not math.isfinite(float(event.get(k,"nan"))) or
      abs(float(event.get(k,"nan"))-v)>2e-5]
    expected="2048" if selected else "0"
    if (mismatch or event.get("selected")!=str(int(selected)) or
        event.get("signal")!=str(int(signal)) or
        event.get("target")!=expected or
        event.get("complete")!="1" or
        event.get("model")!=("maturelow" if mode=="r21_mature_low50" else "inverse") or
        int(event.get("n","-1"))!=case["n"] or
        inherited.get("selected")!=str(int(selected)) or
        inherited.get("target")!=expected):
     row["error"]="R21 NATIVE/PYTHON AGE_LBD_REASON GATE MISMATCH "+str(mismatch)
    if row["switch_at"] and (not selected or int(row["switch_at"])<2048
        or int(row["restart_after"])!=50 or
        row["learned_before"]!=row["learned_after"]):
     row["error"]="R21 ILLEGAL SWITCH OR LEARNED CLAUSE RESET"
    values={
      "r21_python_selected":int(selected),"r21_python_signal":int(signal),
      "r21_direct_prev":direct0,"r21_direct_recent":direct1,
      "r21_mature_low_prev":oldlow0,"r21_mature_low_recent":oldlow1,
      "r21_share_prev":share0,"r21_share_recent":share1}
  elif row["switch_at"]:
   row["error"]="R21 SWITCH WITHOUT LIVE GATE"
  if event and not inherited:
   row["error"]="R21 MISSING SAME-PREFIX R16 DECISION"
  trace["r21_native_event"]=event
  trace["r21_native_checkpoints"]=checkpoints
 row.update(r21_native_decision=json.dumps(event,sort_keys=True) if event else "",
   r21_trace_checkpoints=len(trace.get("early",{}).get("r21_checkpoint",[])) if mode in LOCAL else "",
   r21_protocol_sha256=sha(PROTOCOL),
   r21_error=row.get("error",""),**values)
 return row,trace

def write_rows(p,rows):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  w.writeheader();w.writerows(rows)

def run_shard(category):
 cfg();used=history()
 core=r20.r16.previous.r14.r11.set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 cases=make_cases(category,folder,used)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / core "+str(core)+" / "+platform.processor()
 manifest={
  "protocol":cfg()["protocol"],"category":category,
  "source_commit":os.environ.get("GITHUB_SHA","local"),
  "fold":r20.r16.previous.r14.fold_from_category(category),
  "family":r20.r16.previous.r14.family_from_category(category),
  "modes":MODES,"repeats":REPEAT,"cap_seconds":CAP,
  "runner":runner,"cpu_core":core,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "kissat_pin":r20.r16.PIN,"v1531_blob":r20.r16.STABLE_PIN,
  "protocol_sha256":sha(PROTOCOL),"historic_count":len(used),
  "historic_sha256":hashlib.sha256("\n".join(sorted(used)).encode()).hexdigest(),
  "binaries":{
    "same_binary_monitor_forced_R16_R20_R21":sha(r20.r16.previous.r14.r11.base.PATCHED),
    "original":sha(r20.r16.previous.r14.r11.base.ORIGINAL),
    "v1531":sha(r20.r16.previous.r14.r11.base.STABLE)},
  "cases":[{k:(str(v) if isinstance(v,Path) else v)
     for k,v in case.items() if k!="clauses"} for case in cases],
  "limits":"Real native in-process measurement; generated 3SAT not official; UNSAT uncertified."}
 (folder/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
 rows=[];traces=[]
 for case in cases:
  for rep in range(REPEAT):
   order=list(MODES)
   random.Random(212121+int(case["formula_sha256"][:12],16)+rep).shuffle(order)
   for mode in order:
    row,trace=actual_run(case,rep,mode,runner)
    rows.append(row);traces.append(trace)
    write_rows(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:
     f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R21_NATIVE",category,case["formula"],rep,mode,row["status"],
      "PAR2",row["par2_s"],"selected",row.get("r21_python_selected",""),
      "switch",row["switch_at"],flush=True)
    if row["error"]:
     (folder/"error.json").write_text(json.dumps(row,indent=2,sort_keys=True)+"\n")
     raise RuntimeError("R21 REAL SAT INVALID "+str(row["error"]))
  solved={x["status"] for x in rows if x["formula"]==case["formula"]
           and x["status"] in ("SAT","UNSAT")}
  if len(solved)>1:raise RuntimeError("R21 SAT/UNSAT DISAGREEMENT")
 if len(rows)!=240 or len(traces)!=240:
  raise RuntimeError("R21 NATIVE SHARD INCOMPLETE 240")
 write_rows(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in traces))
 print("R21_COMPLETE_REAL_NATIVE_SHARD",category,240,flush=True)

def smoke():
 from tempfile import TemporaryDirectory
 with TemporaryDirectory() as d:
  for case in make_cases("n240_development0",Path(d),history()):
   for mode in LOCAL:
    row,trace=actual_run(case,0,mode,"R21 smoke")
    if row["error"] or row["status"] not in ("SAT","UNSAT"):
     raise RuntimeError("R21 HARD SAT SMOKE INVALID "+str(row))
    if row["r21_native_decision"]:
     print("R21_AGE_LBD_DIRECT_IMPLICATION_GATE_PARITY_PASS",
       case["formula"],mode,row["r21_share_prev"],row["r21_share_recent"],flush=True)
     return
 raise RuntimeError("R21 NO COMPLETE NATIVE 1024 COUNTER WINDOW ON SMOKE")
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--category",choices=SHARDS);p.add_argument("--smoke",action="store_true")
 a=p.parse_args()
 if a.smoke:smoke()
 elif a.category:run_shard(a.category)
 else:p.error("Need --smoke or --category")
