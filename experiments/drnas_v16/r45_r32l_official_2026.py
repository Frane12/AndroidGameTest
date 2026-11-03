#!/usr/bin/env python3
"""R45: genuine SAT Competition 2026 external benchmark of frozen R32l GF(2).

No source-code edits to the 2026-11-03 R32l binaries. Reuse SHA-pinned clean
Kissat and native R32l pair from already audited run 41647823014.

- 12 official originals from earlier SHA-verified public 18+12 manifests;
  input selection frozen before any R45 solver output.
- 6 SAT + 6 UNSAT, size <= 2.5 MB and published CaDiCaL 2026 time 1-60 s;
  feasibility criteria are biased and not a random competition sample.
- Two sequential repeats per formula, four modes per repeat: 96 trials.
- Original SAT witnesses validated by re-evaluating original CNF.
- GF(2) injected units cross-checked with independent original-source proof,
  but no external UNSAT proof certificate.
- Time cap 20 s, PAR2 40 s; CPU affinity and mode order controlled.
- Mechanistic outcome: how often actual root-unit intervention is possible.
"""
from __future__ import annotations
import argparse,hashlib,json,os,random,re,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_shortlong_select import download_and_features
import r32b_native_shadow_benchmark as b
import r32l_early_cdcl_benchmark as l

PROTO="DRNAS-R45-R32L-REAL-OFFICIAL-2026-20261103-v1"
SALT="DRNAS-R45-OFFICIAL-FROZEN-SHA-20261103"
MODES=("clean","native_off","full","first8")
CAP=20.0
REPS=2
SHARDS=4
CAP_BYTES=2500000
def check(v,msg):
 if not v:raise RuntimeError("R45_AUDIT_ERROR "+str(msg))
def sha_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def textify(s):
 if s is None:return ""
 return s.decode("utf-8","replace") if isinstance(s,bytes) else s

def freeze(args):
 a=json.loads(Path(args.prior18).read_text())
 z=json.loads(Path(args.prior12).read_text())
 check(len(a["cases"])==18 and len(z["cases"])==12,"wrong prior manifest sizes")
 pool=a["cases"]+z["cases"]
 check(len({x["id"] for x in pool})==30 and len({x["sha256"] for x in pool})==30,"prior source overlap")
 selected=[]
 counts={}
 for label in ("SAT","UNSAT"):
  filtered=[x for x in pool if x["official_label"]==label
     and x["cnf_bytes"]<=CAP_BYTES
     and 1.0<=float(x["official_baseline_s"])<=60.0]
  ranked=sorted(filtered,key=lambda x:hashlib.sha256((SALT+"/"+label+"/"+x["id"]).encode()).hexdigest())
  check(len(ranked)>=6,f"Not enough original {label} verified candidate CNFs: {len(ranked)}")
  selected.extend(ranked[:6])
  counts[label]=len(ranked)
 selected.sort(key=lambda x:hashlib.sha256((SALT+":schedule:"+x["id"]).encode()).hexdigest())
 check(len(selected)==12 and len({x["sha256"] for x in selected})==12,"freeze cardinality")
 out=dict(protocol=PROTO,selection={
   "basis":"official 2026 CaDiCaL runtime and DIMACS size, precommitted feasibility only",
   "known_r32l_exposure":"never evaluated by R32l, though some were tested in DRNAS V9/R37",
   "source_prior18_sha256":sha_file(args.prior18),
   "source_prior12_sha256":sha_file(args.prior12),
   "candidates_by_label":counts,"size_cap_bytes":CAP_BYTES,
   "official_runtime_window_s":[1.0,60.0],
   "quota":{"SAT":6,"UNSAT":6},"salt":SALT},
   cases=selected,modes=MODES,cap_s=CAP,reps=REPS,shards=SHARDS,
   expected_trials=len(selected)*len(MODES)*REPS,
   caveats=["Original SAT Competition 2026 CNFs, not generated",
     "Not a globally blind holdout; reused previously frozen official identities",
     "Selection on known competition time and file size is not representative",
     "This is pinned R32l GF2 intervention on SAME upstream Kissat, not V15.3.1",
     "Time cap 20s; a timeout counts PAR2 40s",
     "Two repeats per formula, not independent random solver seeds",
     "Published SAT/UNSAT status is ground truth; no UNSAT certificate produced",
     "If no additional certified root GF(2) units are injected, no speedup is attributable to GF(2)"]
 )
 dst=Path(args.out);dst.parent.mkdir(parents=True,exist_ok=True)
 dst.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
 for c in selected:
  print("R45_FREEZE",c["id"],c["official_label"],c["stratum"],
        c["cnf_bytes"],"official_ref_s",c["official_baseline_s"],flush=True)
 print("R45_FREEZE_PASS",len(selected), "sha256",sha_file(dst),flush=True)

def full_original_sat_witness_check(path,output):
 """Validate Kissat SAT witness against the COMPLETE original DIMACS CNF.

 Earlier R30 verifier was intentionally guarded at 1024 vars/10000 clauses.
 This is a file-streamed verifier, not a new SAT solve.
 """
 model={}
 for line in output.splitlines():
  if line.startswith("v "):
   for word in line.split()[1:]:
    lit=int(word)
    if lit:
     var=abs(lit);value=(lit>0)
     if var in model:check(model[var]==value,"contradictory model literals")
     model[var]=value
 check(bool(model),"Kissat reported SAT without a witness")
 n=None;declared=None;done=0;clause_open=False;clause_satisfied=False
 with Path(path).open("rb") as file:
  for raw in file:
   line=raw.strip()
   if not line or line.startswith((b"c",b"%")):continue
   if line.startswith(b"p "):
    check(n is None,"duplicated DIMACS header")
    parts=line.split()
    check(len(parts)==4 and parts[1]==b"cnf","malformed DIMACS header")
    n=int(parts[2]);declared=int(parts[3]);continue
   check(n is not None,"missing CNF header")
   for word in line.split():
    lit=int(word)
    if lit:
     check(abs(lit)<=n,"invalid variable index in original DIMACS")
     clause_open=True
     if model.get(abs(lit))==(lit>0):clause_satisfied=True
    else:
     check(clause_open and clause_satisfied,"SAT witness falsifies original clause "+str(done))
     done+=1;clause_open=False;clause_satisfied=False
 check(n is not None and done==declared and not clause_open,
   "DIMACS clause structure or declared count invalid")
 return "SAT_witness_verified_complete_original_DIMACS"

def one(case,path,mode,clean,native):
 cmd=[str(clean if mode=="clean" else native),str(path)]
 env=os.environ.copy()
 env["R32B_MODE"]="off" if mode in ("clean","native_off") else "r32k"
 env.pop("R32K_VARIANT",None)
 if mode in ("full","first8"):env["R32K_VARIANT"]=mode
 if mode=="clean":env.pop("R32L_TRACE",None)
 else:env["R32L_TRACE"]="1"
 start=time.monotonic()
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",env=env,timeout=CAP,check=False)
  elapsed=time.monotonic()-start
  check(p.returncode in (10,20),f"Bad native exit {p.returncode}, stderr={p.stderr[-300:]}")
  status="SAT" if p.returncode==10 else "UNSAT"
  check(status==case["official_label"],f"Official SAT/UNSAT label conflict {mode} {status}")
  stdout=p.stdout
  validation=(full_original_sat_witness_check(path,stdout) if status=="SAT" else "published_verified_UNSAT_label")
 except subprocess.TimeoutExpired as ex:
  elapsed=CAP
  status="TIMEOUT"
  stdout=textify(ex.stdout)
  validation="censored"
 probes,final=b.parse_native(stdout)
 if mode=="clean":
  check(not probes and final is None,"Clean original Kissat emitted R32l modifications")
 if mode=="native_off":
  check(not probes,"Native OFF ran GF2 probe")
 if status!="TIMEOUT" and mode!="clean":
  check(final is not None and final["status"]==(10 if status=="SAT" else 20),"Incorrect native final telemetry")

 root=None;proof=None;ablation=None
 if mode in ("full","first8"):
  roots=[x for x in probes if x.get("mark")==9999]
  check(len(roots)<=1,"duplicate native root GF2 probes")
  if roots:
   root=roots[0]
   proof=b.compare_root(root,path)
   check(proof["status"] in ("independent_proof_match","old_python_guard"),
         "GF2 root does not match original source")
   raw=re.findall(
    r"^c R32K_ABLATION variant=([a-z0-9]+) available=(\d+) injected=(\d+) equations=(\d+) resolved=(\d+)$",
    stdout,re.MULTILINE)
   check(len(raw)<=1,"duplicate R32k ablation records")
   if raw:
    name,avail,inj,eq,res=raw[0]
    check(name==mode and int(eq)==int(root["equations"]) and int(res)==int(root["resolved"]),
          "Native feature counters mismatch")
    eligible=(root["signal"]=="CONSISTENT_GAP" and 0<int(root["extra"])<=12)
    intended=(int(root["extra"]) if mode=="full" else min(8,int(root["extra"]))) if eligible else 0
    check(int(avail)==(int(root["extra"]) if root["signal"]=="CONSISTENT_GAP" else 0),
          "wrong source certified extra units")
    check(int(inj)==intended,"unexpected injected GF2 units")
    if intended:
     claim=re.findall(r"^c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)$",stdout,re.MULTILINE)
     check(len(claim)==1 and int(claim[0][0])==intended,"Missing injected literals")
     signed=[int(x) for x in claim[0][1].split(",")]
     check(signed==root["sample"][:intended],"Causal hint order mismatch")
    ablation=dict(variant=mode,available=int(avail),injected=int(inj),
      source_signal=root["signal"],proof=proof["status"],root_equations=int(eq))
   else:
    # R32k legitimately skips the ablation record on root INPUT_GUARD.
    # A timeout may also interrupt processing between a root probe and
    # the intervention decision. Never impute a zero injection from silence.
    guard=re.findall(r"^c R32C_ACTIVE signal=INPUT_GUARD injected=0 certified=0$",stdout,re.MULTILINE)
    if root["signal"]=="INPUT_GUARD" and guard:
     ablation=dict(variant=mode,available=0,injected=0,
       source_signal=root["signal"],proof="native_input_guard_no_action",
       root_equations=root.get("equations",0))
    elif status!="TIMEOUT":
     raise RuntimeError("R45 completed active solve without a documented ablation decision")
  elif status!="TIMEOUT":
   raise RuntimeError("R45 completed native active solve without GF2 root proof")
 # Preserve early CDCL observables, including incomplete on timeout
 events=l.parse_early_cdcl(stdout,status,mode,final)
 event_types=[e["kind"] for e in events]
 return dict(status=status,wall_s=round(elapsed,6),
  par2_s=round(elapsed,6) if status!="TIMEOUT" else 2*CAP,
  witness_validation=validation,root_signal=(root or {}).get("signal"),
  ablation=ablation,checkpoint_types=event_types,
  final_counters=final,root_proof=(proof or {}).get("status"),
  timeout_before_root=(mode in ("full","first8") and root is None and status=="TIMEOUT"),
  timeout_before_action=(mode in ("full","first8") and ablation is None and status=="TIMEOUT"))

def measure(args):
 frozen=Path(args.manifest);m=json.loads(frozen.read_text())
 check(m["protocol"]==PROTO and len(m["cases"])==12,"wrong R45 manifest")
 check(0<=args.shard<SHARDS,"wrong shard")
 cases=m["cases"][args.shard::SHARDS]
 check(len(cases)==3,"expected exactly 3 real official inputs per shard")
 clean=Path(args.clean).resolve()
 native=Path(args.native).resolve()
 check(clean.is_file() and native.is_file(),"missing source-equivalent Kissat binaries")
 core=min(os.sched_getaffinity(0))
 os.sched_setaffinity(0,{core})
 output=Path(args.outdir);output.mkdir(parents=True,exist_ok=True)
 binaries={"clean":sha_file(clean),"native":sha_file(native)}
 (output/"meta.json").write_text(json.dumps(dict(shard=args.shard,
    manifest_sha256=sha_file(frozen),binary_sha256=binaries,cap_s=CAP,
    modes=MODES,reps=REPS,core=core,
    case_ids=[c["id"] for c in cases]),indent=2)+"\n")
 rows=[]
 for case in cases:
  path=output/(case["id"]+".cnf")
  try:
   got=download_and_features(case["id"],path)
   check(got["sha256"]==case["sha256"] and got["features"]==case["features"],
         "Original official CNF SHA / features mismatch")
   print("R45_INPUT_SHA_PASS",case["id"],case["official_label"],flush=True)
   for rep in range(REPS):
    modes=list(MODES)
    random.Random(int(hashlib.sha256((SALT+"/"+case["sha256"]+"/"+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
    for mode in modes:
     result=one(case,path,mode,clean,native)
     row=dict(id=case["id"],sha256=case["sha256"],label=case["official_label"],
       cohort="real_sat_competition_2026",rep=rep,mode=mode,**result)
     rows.append(row)
     (output/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
     print("R45_TRIAL",case["id"][:8],rep,mode,
       row["status"],row["wall_s"],"GF2_units",
       (row["ablation"] or {}).get("injected","unknown"),
       "root",row["root_signal"],flush=True)
  finally:path.unlink(missing_ok=True)
 check(len(rows)==len(cases)*REPS*len(MODES),"incomplete shard")
 print("R45_SHARD_PASS",args.shard,len(rows),flush=True)

def aggregate(args):
 mf=Path(args.manifest);m=json.loads(mf.read_text())
 check(m["protocol"]==PROTO,"wrong frozen manifest")
 byid={c["id"]:c for c in m["cases"]}
 check(len(byid)==12,"wrong size")
 allrows=[];fingerprints=set()
 for shard in range(SHARDS):
  folder=Path(args.combined)/f"r45-shard-{shard}"/"results"
  meta=json.loads((folder/"meta.json").read_text())
  check(meta["shard"]==shard and meta["manifest_sha256"]==sha_file(mf),"wrong shard manifest")
  check(meta["modes"]==list(MODES) and meta["reps"]==REPS and meta["cap_s"]==CAP,"protocol drift")
  check(meta["case_ids"]==[c["id"] for c in m["cases"][shard::SHARDS]],"shard case drift")
  fingerprints.add(json.dumps(meta["binary_sha256"],sort_keys=True))
  rows=json.loads((folder/"rows.json").read_text())
  check(len(rows)==3*REPS*len(MODES),"incomplete shard trial count")
  allrows.extend(rows)
 check(len(fingerprints)==1 and len(allrows)==12*REPS*len(MODES),"mismatched binary/trials")
 lookup={}
 for r in allrows:
  c=byid[r["id"]]
  check(r["sha256"]==c["sha256"] and r["label"]==c["official_label"],"input identity drift")
  check(r["status"] in ("SAT","UNSAT","TIMEOUT"),"unexpected native status")
  if r["status"]!="TIMEOUT":
   check(r["status"]==c["official_label"],"incorrect SAT/UNSAT answer")
  key=(r["id"],r["rep"],r["mode"])
  check(key not in lookup,"duplicate")
  lookup[key]=r
 check(len(lookup)==len(allrows),"duplicate trials")
 check(set(lookup)=={(c["id"],rep,mode) for c in m["cases"] for rep in range(REPS) for mode in MODES},
   "incomplete original competition paired grid")
 bymode={}
 for mode in MODES:
  rows=[r for r in allrows if r["mode"]==mode]
  bymode[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in rows),
    timeouts=sum(r["status"]=="TIMEOUT" for r in rows),
    par2_sum_s=round(sum(r["par2_s"] for r in rows),6),
    par2_mean_s=round(statistics.mean(r["par2_s"] for r in rows),6),
    active_root_interventions=sum(bool(r["ablation"] and r["ablation"]["injected"]>0) for r in rows),
    confirmed_zero_unit_decisions=sum(bool(r["ablation"] and r["ablation"]["injected"]==0) for r in rows),
    unknown_intervention_before_timeout=sum(bool(r["timeout_before_action"]) for r in rows),
    uncertified_GF2_action=sum(bool(r["ablation"] and
      r["ablation"]["injected"]>0 and r["ablation"]["proof"]!="independent_proof_match") for r in rows))
 baseline=bymode["native_off"]["par2_mean_s"]
 for mode in ("clean","full","first8"):
  bymode[mode]["pct_vs_native_off_positive_is_regression"]=round(
    100*(bymode[mode]["par2_mean_s"]/baseline-1),4)
 bycase=[]
 for c in m["cases"]:
  modes={}
  for mode in MODES:
   rr=[lookup[(c["id"],rep,mode)] for rep in range(REPS)]
   modes[mode]=dict(mean_par2_s=round(statistics.mean(r["par2_s"] for r in rr),6),
      statuses=[r["status"] for r in rr],
      injected=[(r["ablation"] or {}).get("injected") for r in rr],
      root_signals=[r["root_signal"] for r in rr])
  bycase.append(dict(id=c["id"],label=c["official_label"],stratum=c["stratum"],
    size_bytes=c["cnf_bytes"],reference_cadical_s=c["official_baseline_s"],modes=modes))
 rng=random.Random(45031)
 ci={}
 for mode in ("full","first8"):
  draws=[]
  for _ in range(4000):
   ix=[rng.randrange(len(bycase)) for j in bycase]
   a=statistics.mean(bycase[i]["modes"]["native_off"]["mean_par2_s"] for i in ix)
   z=statistics.mean(bycase[i]["modes"][mode]["mean_par2_s"] for i in ix)
   draws.append(100*(z/a-1) if a else 0)
  draws.sort()
  ci[mode]=[round(draws[100],3),round(draws[3899],3)]
 result=dict(protocol=PROTO,sources="original SAT Competition 2026 DIMACS",
   known_not_blind=True,formula_count=len(bycase),attempts=len(allrows),
   caps_s=CAP,reps=REPS,manifest_sha256=sha_file(mf),
   binary_fingerprints=json.loads(next(iter(fingerprints))),
   mode_summary=bymode,case_summary=bycase,
   bootstrap_95_pct_by_formula=ci,
   limitations=m["caveats"])
 output=Path(args.out);output.write_text(json.dumps(result,indent=2)+"\n")
 print("R45_AUDIT_PASS",json.dumps({k:result[k] for k in
   ("formula_count","attempts","caps_s","bootstrap_95_pct_by_formula")},sort_keys=True),flush=True)
 print("R45_MODE_SUMMARY",json.dumps(bymode,sort_keys=True),flush=True)
 for c in bycase:
  print("R45_CASE",c["id"][:8],c["label"],
    json.dumps({k:{"par2":v["mean_par2_s"],"units":v["injected"]}
       for k,v in c["modes"].items()},sort_keys=True),flush=True)

if __name__=="__main__":
 p=argparse.ArgumentParser()
 sub=p.add_subparsers(dest="command",required=True)
 f=sub.add_parser("freeze")
 for name in ("prior18","prior12","out"):f.add_argument("--"+name,required=True)
 me=sub.add_parser("measure")
 for name in ("manifest","clean","native","outdir"):me.add_argument("--"+name,required=True)
 me.add_argument("--shard",type=int,required=True)
 ag=sub.add_parser("aggregate")
 for name in ("manifest","combined","out"):ag.add_argument("--"+name,required=True)
 x=p.parse_args()
 if x.command=="freeze":freeze(x)
 elif x.command=="measure":measure(x)
 else:aggregate(x)
