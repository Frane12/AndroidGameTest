#!/usr/bin/env python3
"""DRNAS R20 real native SAT measurement, learned-redundant-clause reuse gate.

R20 local / inverse are actual in-process restartint50 policies.
Measures 160 fresh formulas x 3 repeats x 7 strategies = 3360 true solves.
C counters at conflicts 256/512/1024 are independently recomputed by Python,
with paired same-core monitor/force50/R16/vanilla-Kissat/V15.3.1 references.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random
from pathlib import Path
import r16_live_benchmark as r16
import r19_trajectory_benchmark as r19

ROOT=Path("experiments/drnas_v16")
PROTOCOL=ROOT/"r20_frozen_protocol.json"
OUT=Path("drnas-r20-results")
MODES=("monitor","r11_2048_50","r16_live50","r20_local50",
       "r20_inverse50","original_kissat","stable_v1531")
LOCAL=("r20_local50","r20_inverse50")
REPEATS=3
CAP=12
SHARDS=r16.SHARDS
FIELDS=r16.FIELDS+("r20_native_decision","r20_python_selected",
 "r20_python_stagnating","r20_used_prev","r20_used_recent",
 "r20_reuse_prev","r20_reuse_recent","r20_prop_prev",
 "r20_prop_recent","r20_glue_prev","r20_glue_recent",
 "r20_native_checkpoint_count","r20_protocol_sha256","r20_error")
R19_CSV=ROOT/"r19-results/current/predictions.csv"
R19_GIT_BLOB="2e960455a5f722b0373e33925d2fdea3a37fe588"
BASE_PARSE=r16.parse_r16
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def cfg():
 c=json.loads(PROTOCOL.read_text())
 if (c["protocol"]!="DRNAS-R20-local-clause-reuse-prospective-20261102-v1"
    or c["dataset"]["modes"]!=list(MODES) or
    c["dataset"]["attempts"]!=3360 or c["dataset"]["seed_base"]!=2020200000
    or c["source_kissat"]!=r16.PIN
    or c["source_v1531"]!=r16.STABLE_PIN):
  raise RuntimeError("R20 FROZEN MODE/SEED/PROTOCOL/PIN MISMATCH")
 return c
def history():
 known=r19.history()
 if len(known)!=2574:raise RuntimeError("R20 HISTORIC HASH BASE BROKEN")
 if r19.git_blob(R19_CSV)!=R19_GIT_BLOB:
  raise RuntimeError("R20 R19 FINAL PREDICTIONS FILE BLOB CHANGED")
 with R19_CSV.open(newline="") as f:
  recent={x["formula_sha256"] for x in csv.DictReader(f)}
 if len(recent)!=160 or recent&known:
  raise RuntimeError("R20 R19 FORMULA HISTORICAL DUPLICATE")
 combined=known|recent
 if len(combined)!=2734:raise RuntimeError("R20 PREVIOUS FORMULA COUNT INCORRECT")
 return combined
def make_cases(category,folder,used):
 c=cfg()
 n=r16.previous.r14.size_from_category(category)
 family=r16.previous.r14.family_from_category(category)
 fold="development" if "_development" in category else "test"
 part=int(category[-1]);result=[]
 for j in range(10):
  seed=c["dataset"]["seed_base"]+n*10000+(1000 if fold=="test" else 0)+part*10+j+(20000 if family=="community3" else 0)
  rng=random.Random(seed)
  clauses=[]
  for _ in range(round(4.23*n)):
   if family=="community3" and rng.random()<.65:
    start=rng.randrange(4)*(n//4)+1
    vs=rng.sample(range(start,start+n//4),3)
   else:vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  fs=r16.previous.r14.r11.features(clauses,n)
  case=r16.previous.r14.r11.base.emit_cnf(folder,
    f"r20_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
    n,clauses,"UNKNOWN","generated_prospective",
    "R20 local learned clause reuse intervention, synthetic nonofficial",
    "r20-frozen-clause-reuse-gate-v1",
    {"seed":seed,"fold":fold,"family":family,"features":fs,
     "community_probability":.65 if family=="community3" else 0.})
  if case["formula_sha256"] in used:
   raise RuntimeError("R20 HISTORICAL SHA DUPLICATE")
  case["category"]=category
  result.append(case)
 if len({c["formula_sha256"] for c in result})!=10:
  raise RuntimeError("R20 DUPLICATED CNF IN SHARD")
 return result
def parse_r20(output):
 points,labels=BASE_PARSE(output)
 cp=[];decision=[]
 for line in output.splitlines():
  if line.startswith("c R20_TRACE "):
   entry={}
   for z in line.split()[2:]:
    if "=" in z:
     key,value=z.split("=",1);entry[key]=value
   cp.append(entry)
  elif line.startswith("c R20_DECISION "):
   entry={}
   for z in line.split()[2:]:
    if "=" in z:
     key,value=z.split("=",1);entry[key]=value
   decision.append(entry)
 if len(decision)>1 or len(cp)>3:
  raise RuntimeError("R20 MULTIPLE DECISION OR EXTRA CHECKPOINTS")
 early=labels.setdefault("DRNAS_V177_EARLY",{})
 early["r20_trace"]=cp
 early["r20_decision"]=decision[0] if decision else {}
 return points,labels

r16.previous.r14.r11.base.extract_tags=parse_r20
def run_one(case,rep,mode,runner):
 if mode not in LOCAL:
  row,trace=r16.run_one(case,rep,mode,runner)
  event={}
  extra={}
 else:
  envs={"DRNAS_R16_GINI":case["metadata"]["features"]["degree_gini"],
        "DRNAS_R16_POLARITY":case["metadata"]["features"]["polarity_imbalance"]}
  prev={k:os.environ.get(k) for k in envs}
  try:
   for k,v in envs.items():os.environ[k]=format(v,".17g")
   # Bypass r16.run_one because it intentionally rejects R16 telemetry
   # emitted by newly named experimental modes. Audit independently below.
   row,trace=r16.previous.r14.run_one(case,rep,mode,runner)
  finally:
   for k,v in prev.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
  row["fold"]=r16.previous.r14.fold_from_category(case["category"])
  row["r16_protocol_sha256"]=r16.sha(r16.CONFIG)
  row["r16_model_sha256"]=r16.sha(r16.MODEL)
  early=trace.get("early",{})
  native=early.get("r16_event",{})
  cp=early.get("r20_trace",[])
  event=early.get("r20_decision",{})
  row.update(r16_native_conflict=native.get("conflict",""),
    r16_native_ready=native.get("complete",""),
    r16_native_score=native.get("score",""),
    r16_python_score="",r16_selected=native.get("selected",""),
    r16_expected_target=native.get("target",""),
    r16_threshold=native.get("threshold",""),
    r16_model=native.get("model",""),r16_decision_error="")
  extra={}
  if event:
   observed=[int(x["conflict"]) for x in cp]
   if (len(cp)!=3 or not (256<=observed[0]<512 and
       512<=observed[1]<1024 and 1024<=observed[2]<2048)):
    row["error"]="R20 MISSING OR MISORDERED LOCAL CLAUSE UTILITY LANDMARKS"
   else:
    a,b,d=cp
    u0=int(b["used"])-int(a["used"])
    u1=int(d["used"])-int(b["used"])
    l0=int(b["learned"])-int(a["learned"])
    l1=int(d["learned"])-int(b["learned"])
    use0=u0/(l0+1.)
    use1=u1/(l1+1.)
    p0=(int(b["props"])-int(a["props"]))/(int(b["conflict"])-int(a["conflict"]))
    p1=(int(d["props"])-int(b["props"]))/(int(d["conflict"])-int(b["conflict"]))
    g0=float(b["glue"])
    g1=float(d["glue"])
    stale=(use0>=.05 and use1<.85*use0 and (p1<.95*p0 or g1>1.05*g0))
    chosen=(case["n"]>=220 and (stale if mode=="r20_local50" else not stale))
    expected="2048" if chosen else "0"
    values={"used_prev":u0,"used_recent":u1,"learned_prev":l0,
      "learned_recent":l1,"reuse_prev":use0,"reuse_recent":use1,
      "prop_prev":p0,"prop_recent":p1,"glue_prev":g0,
      "glue_recent":g1}
    mismatch=[]
    for key,value in values.items():
     if abs(float(event.get(key,"NaN"))-float(value))>2e-5:
      mismatch.append(key)
    if (mismatch or native.get("selected")!=str(int(chosen)) or
        native.get("target")!=expected or
        event.get("selected")!=str(int(chosen)) or
        event.get("target")!=expected or
        event.get("stagnating")!=str(int(stale)) or
        event.get("model")!=("local" if mode=="r20_local50" else "inverse") or
        int(event.get("conflict","-1"))<1024 or
        int(event.get("n","-1"))!=case["n"]):
     row["error"]="R20 NATIVE/PYTHON LOCAL CLAUSE UTILITY DISAGREEMENT "+str(mismatch)
    extra={"r20_python_selected":int(chosen),
      "r20_python_stagnating":int(stale),
      "r20_used_prev":u0,"r20_used_recent":u1,
      "r20_reuse_prev":use0,"r20_reuse_recent":use1,
      "r20_prop_prev":p0,"r20_prop_recent":p1,
      "r20_glue_prev":g0,"r20_glue_recent":g1}
    if row["switch_at"] and (not chosen or int(row["switch_at"])<2048 or
       int(row["restart_after"])!=50 or
       row["learned_before"]!=row["learned_after"]):
     row["error"]="R20 UNAUTHORIZED RESTART / CLAUSE DATABASE RESET"
  elif cp:
   if len(cp)>3:row["error"]="R20 EARLY USE TRACE MALFORMED"
  if event and not native:
   row["error"]="R20 MISSING SHARED R16 1024 DECISION"
  if not event and row["switch_at"]:
   row["error"]="R20 RESTART SWITCH WITHOUT 1024 EVENT"
  if row["r16_decision_error"]:
   row["error"]=row["r16_decision_error"]
  trace["r20_native_event"]=event
  trace["r20_native_local_checkpoints"]=cp
 row.update(r20_native_decision=json.dumps(event,sort_keys=True) if event else "",
  r20_python_selected=extra.get("r20_python_selected",""),
  r20_python_stagnating=extra.get("r20_python_stagnating",""),
  r20_used_prev=extra.get("r20_used_prev",""),
  r20_used_recent=extra.get("r20_used_recent",""),
  r20_reuse_prev=extra.get("r20_reuse_prev",""),
  r20_reuse_recent=extra.get("r20_reuse_recent",""),
  r20_prop_prev=extra.get("r20_prop_prev",""),
  r20_prop_recent=extra.get("r20_prop_recent",""),
  r20_glue_prev=extra.get("r20_glue_prev",""),
  r20_glue_recent=extra.get("r20_glue_recent",""),
  r20_native_checkpoint_count=len(trace.get("early",{}).get("r20_trace",[])) if mode in LOCAL else "",
  r20_protocol_sha256=sha(PROTOCOL),r20_error=row.get("error",""))
 return row,trace

def writecsv(p,rows):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  w.writeheader();w.writerows(rows)

def shard(category):
 c=cfg()
 cpu=r16.previous.r14.r11.set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 used=history()
 cases=make_cases(category,folder,used)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / core "+str(cpu)+" / "+platform.processor()
 manifest={
  "protocol":c["protocol"],"category":category,
  "source_commit":os.environ.get("GITHUB_SHA","local"),
  "fold":r16.previous.r14.fold_from_category(category),
  "family":r16.previous.r14.family_from_category(category),
  "modes":MODES,"repeats":REPEATS,"cap_seconds":CAP,
  "runner":runner,"cpu_core":cpu,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "kissat_pin":r16.PIN,"v1531_blob":r16.STABLE_PIN,
  "protocol_sha256":sha(PROTOCOL),
  "historic_count":len(used),
  "historic_sha256":hashlib.sha256("\n".join(sorted(used)).encode()).hexdigest(),
  "executables":{
    "same_binary_monitor_forced_r16_r20":sha(r16.previous.r14.r11.base.PATCHED),
    "original":sha(r16.previous.r14.r11.base.ORIGINAL),
    "v1531":sha(r16.previous.r14.r11.base.STABLE)},
  "cases":[{k:(str(v) if isinstance(v,Path) else v)
        for k,v in case.items() if k!="clauses"} for case in cases],
  "limits":"Synthetic Random3/Community3. SAT witnesses checked, UNSAT no independent proof."}
 (folder/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
 rows=[];traces=[]
 for case in cases:
  for rep in range(3):
   order=list(MODES)
   random.Random(202020+int(case["formula_sha256"][:12],16)+rep).shuffle(order)
   for mode in order:
    row,trace=run_one(case,rep,mode,runner)
    rows.append(row);traces.append(trace)
    writecsv(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:
     f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R20_NATIVE",category,case["formula"],rep,mode,row["status"],
      "PAR2",row["par2_s"],"selected",row["r20_python_selected"],
      "stagnant",row["r20_python_stagnating"],
      "switch",row["switch_at"],flush=True)
    if row["error"]:
     (folder/"error.json").write_text(json.dumps(row,indent=2,sort_keys=True)+"\n")
     raise RuntimeError("R20 NATIVE RESULT INVALID "+row["error"])
  statuses={x["status"] for x in rows if x["formula"]==case["formula"]
            and x["status"] in ("SAT","UNSAT")}
  if len(statuses)>1:raise RuntimeError("R20 SAT/UNSAT CONTRADICTION")
 if len(rows)!=210 or len(traces)!=210:
  raise RuntimeError("R20 INCOMPLETE REAL SHARD")
 writecsv(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(
  json.dumps(x,sort_keys=True)+"\n" for x in traces))
 print("R20_COMPLETE_SHARD",category,210,flush=True)

def smoke():
 from tempfile import TemporaryDirectory
 with TemporaryDirectory() as d:
  cases=make_cases("n240_test0",Path(d),history())
  for case in cases:
   for mode in ("r20_local50","r20_inverse50"):
    row,trace=run_one(case,0,mode,"r20 smoke")
    if row["error"] or row["status"] not in ("SAT","UNSAT"):
     raise RuntimeError("R20 NATIVE SMOKE INVALID "+str(row))
    if row["r20_native_decision"]:
     print("R20_NATIVE_LOCAL_SCORE_PARITY_PASS",case["formula"],mode,
       "reuse",row["r20_reuse_prev"],row["r20_reuse_recent"],flush=True)
     return
 raise RuntimeError("R20 NO 1024 LOCAL SCORE IN 10 SMOKE FORMULAS")
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--category",choices=SHARDS)
 p.add_argument("--smoke",action="store_true")
 args=p.parse_args()
 if args.smoke:smoke()
 elif args.category:shard(args.category)
 else:p.error("choose --smoke or --category")
