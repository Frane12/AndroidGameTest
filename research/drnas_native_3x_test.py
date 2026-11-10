#!/usr/bin/env python3
"""DRNAS Native 3X: 100% original C++ CDCL search/branching.

Development-only 6 existing original SHA from MIXAB3, 6 solver modes,
2 repetitions, 3 independent source shards, strict one logical CPU,
6 s per original E2E; no CaDiCaL, Kissat, CMS, IPASIR backend.
UNSAT is UNVERIFIED unless independent DRAT/LRAT is provided (not here).
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,subprocess,tempfile,time
import drnas_native_core_r2_test as checks

ROOT=pathlib.Path("mre_drnas_native_3x")
CNFS=ROOT/"cases"
BINARY=ROOT/"bin/drnas_native_3x"
MODES=("plain","gf2","gf2_shadow","gf2_static","gf2_live","gf2_live_strong")
REPS=2
SHARDS=3
N=6
CAP=6.0
EXPECTED=N*len(MODES)*REPS
PROTO="DRNAS-NATIVE-3X-SIX-MODE-GF2-CDCL-BRANCH-72-ORIGINAL-ONECPU-6S-v1"
PINNED=(
"daa0360a834fbd9f49437d2b3fd6b372d331774100d913d55c57c0de547eb623",
"e3e6b2c71ca07f5f17491a38490b29fb63045be258ad6837bcc4530b31438162",
)
def need(ok,msg):
 if not ok:raise RuntimeError("NATIVE_3X_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p,v):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(v,sort_keys=True,indent=2)+"\n")
def load(p):return json.loads(pathlib.Path(p).read_text())
def source_originals():
 m=load("mre_mixab3/manifest.json")
 roster={c["sha256"]:c for c in m["original_cases"]}
 need(len(roster)==12 and all(x in roster for x in PINNED),"MIXAB3 source roster mismatch")
 ranked=sorted((c for c in roster.values() if c["sha256"] not in PINNED),
               key=lambda c:(pathlib.Path("mre_mixab3/cases",c["filename"]).stat().st_size,c["sha256"]))
 picks=[roster[k] for k in PINNED]+ranked[:N-len(PINNED)]
 need(len(picks)==N and len({c["sha256"] for c in picks})==N,"bad source-only selection")
 for c in picks:
  p=pathlib.Path("mre_mixab3/cases")/c["filename"]
  need(p.exists() and sha(p)==c["sha256"],"original source bytes SHA drift")
 return picks
def freeze():
 ROOT.mkdir(exist_ok=True);CNFS.mkdir(parents=True,exist_ok=True)
 picks=source_originals()
 cases=[]
 for c in picks:
  p=pathlib.Path("mre_mixab3/cases")/c["filename"]
  dst=CNFS/(c["sha256"]+".cnf")
  import shutil
  shutil.copyfile(p,dst)
  need(sha(dst)==c["sha256"],"source copy mutated")
  cases.append(dict(sha256=c["sha256"],filename=dst.name,
                    bytes=dst.stat().st_size,original_gbd=c["gbd"]))
 b=sha(BINARY)
 manifest=dict(protocol=PROTO,sources=cases,source_count=N,repetitions=REPS,
   arms=list(MODES),shards=SHARDS,cap_s=CAP,total_trials=EXPECTED,
   one_CPU_per_solver=True,single_binary_sha256=b,
   source_picks="two source-locked XOR positives + four smallest source-only remaining",
   previously_seen_originals=True,globally_blind=False,
   own_CPP_CDCL=True,third_party_sat_backend=False,
   independent_UNSAT_LRAT=False,source_artifact_run=42811023064)
 write(ROOT/"manifest.json",manifest)
 verify_sources()
 print("NATIVE_3X_FROZEN "+json.dumps(dict(sources=N,modes=len(MODES),trials=EXPECTED,binary_sha=b),sort_keys=True),flush=True)
def verify_sources():
 m=load(ROOT/"manifest.json")
 need(m["protocol"]==PROTO and m["arms"]==list(MODES) and m["source_count"]==N
      and m["total_trials"]==EXPECTED and m["shards"]==SHARDS and
      m["cap_s"]==CAP and m["single_binary_sha256"]==sha(BINARY),
      "frozen experiment binary or manifest drift")
 for c in m["sources"]:
  p=CNFS/c["filename"]
  need(p.is_file() and p.stat().st_size==c["bytes"] and sha(p)==c["sha256"],
       "source CNF SHA/byte drift")
 return m
def execute(path,mode,cap):
 need(mode in MODES and BINARY.is_file(),"invalid own solver mode/binary")
 if hasattr(os,"sched_getaffinity"):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 start=time.perf_counter()
 args=[str(BINARY.resolve()),str(path.resolve()),"--mode",mode,"--time",str(cap)]
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=cap+2.5)
 elapsed=time.perf_counter()-start
 need(p.returncode in (0,10,20),"native binary fatal "+p.stderr[-500:])
 m=re.search(r"^c DRNAS_NATIVE_3X_RESULT (.+)$",p.stdout,re.M)
 need(m,"missing C++ telemetry")
 kv=dict(part.split("=",1) for part in m.group(1).split() if "=" in part)
 status=kv["status"]
 need(p.returncode=={"SAT":10,"UNSAT":20,"UNKNOWN":0}[status],"C++ exit disagrees with status")
 need(kv["third_party_solver_calls"]=="0","not a standalone solver")
 need(kv.get("mode")==mode,"C++ mode did not follow precommitted arm")
 need(0<=elapsed<=cap+2.0,"E2E cap invalid")
 n,clauses=checks.parse_dimacs(path)
 if status=="SAT":
  witness={}
  for line in p.stdout.splitlines():
   if line.startswith("v "):
    for v in map(int,line[2:].split()):
     if v:
      need(abs(v) not in witness or witness[abs(v)]==(v>0),"contradictory SAT model")
      witness[abs(v)]=(v>0)
  need(len(witness)==n and checks.satisfied(clauses,witness),
       "SAT model not independently satisfied on original CNF")
 # UNSAT proof generation is not yet available in DRNAS R3X.
 fields=("conflicts","decisions","propagations","learned","xor_source_rows",
   "xor_derived_rows","xor_certified_candidates","xor_checks","xor_implications",
   "xor_derived_implications","xor_conflicts","xor_reasons","xor_budget_off",
   "branch_guidance_evals","branch_guidance_rows","branch_guidance_suggested",
   "branch_guidance_applied","branch_guidance_xor_chosen")
 metrics={k:int(kv[k]) for k in fields}
 if mode in ("plain","gf2"):
  need(metrics["branch_guidance_evals"]==0 and metrics["branch_guidance_applied"]==0,
       "control arm changed CDCL decisions")
 if mode=="gf2_shadow":
  need(metrics["branch_guidance_applied"]==0,"shadow changed CDCL decisions")
 if mode in ("gf2_shadow","gf2_static","gf2_live","gf2_live_strong"):
  need(metrics["branch_guidance_applied"]<=metrics["branch_guidance_suggested"],
       "invalid branch guided decision accounting")
 return dict(mode=mode,status=status,verified_SAT=status=="SAT",
    raw_UNSAT_no_independent_LRAT=status=="UNSAT",
    E2E_s=round(elapsed,6),solver_s=round(float(kv["solver_s"]),6),
    cap_s=cap,one_logical_CPU=True,
    third_party_solver_calls=0,metrics=metrics)
def verify():
 ROOT.mkdir(parents=True,exist_ok=True)
 p=subprocess.run([str(BINARY.resolve()),"--selftest"],stdout=subprocess.PIPE,
   stderr=subprocess.PIPE,text=True,timeout=100)
 need(p.returncode==0 and "DRNAS_NATIVE_3X_GF2_SELFTEST_PASS" in p.stdout
      and "DRNAS_NATIVE_3X_GUIDANCE_SELFTEST_PASS" in p.stdout
      and "DRNAS_NATIVE_3X_SELFTEST_PASS" in p.stdout,
      "self-contained C++ brute oracle failed "+p.stderr[-500:])
 print(p.stdout.strip(),flush=True)
 rng=random.Random(0x3A0026)
 checked=0
 with tempfile.TemporaryDirectory(dir=ROOT) as temp:
  path=pathlib.Path(temp)/"original.cnf"
  for i in range(160):
   n=rng.randint(1,9)
   clauses=[[rng.choice((-1,1))*rng.randint(1,n) for _ in range(rng.randrange(0,min(n+4,7)))]
       for __ in range(rng.randrange(0,5*n+5))]
   path.write_text(checks.content(n,clauses))
   expected=checks.independent_truth(n,clauses)
   for mode in MODES:
    got=execute(path,mode,1.5)
    need(got["status"]==expected,"exhaustive truth mismatch "+str(i)+" "+mode)
    checked+=1
  for i in range(70):
   a,b,c,d=rng.sample((1,2,3,4),4)
   rhs1,rhs2=rng.randrange(2),rng.randrange(2)
   assignment=rng.randrange(2)
   clauses=checks.xor_cnf((a,b,c),rhs1)+checks.xor_cnf((a,b,d),rhs2)
   clauses.append([c if assignment else -c])
   if i&1:
    desired=rhs1^rhs2^assignment
    clauses.append([-d if desired else d])
   path.write_text(checks.content(4,clauses))
   expected=checks.independent_truth(4,clauses)
   for mode in MODES:
    got=execute(path,mode,1.5)
    need(got["status"]==expected,"original GF2 proof mismatch "+mode)
    if mode!="plain":
     need(got["metrics"]["xor_derived_rows"]>=1 and
          got["metrics"]["xor_implications"]+got["metrics"]["xor_conflicts"]>=1,
          "native GF2 inference missing")
    checked+=1
 print("NATIVE_3X_VERIFY_PASS "+json.dumps(dict(checked=checked,
   modes=len(MODES),external_sat_backends=0),sort_keys=True),flush=True)
def shard(index,mode):
 m=verify_sources()
 need(index in range(SHARDS) and mode in MODES,"bad matrix coordinates")
 sources=[c for i,c in enumerate(m["sources"]) if i%SHARDS==index]
 need(len(sources)==2,"expected 2 frozen SHA per shard")
 rows=[]
 for c in sources:
  p=CNFS/c["filename"]
  for rep in range(REPS):
   z=execute(p,mode,CAP)
   need(sha(p)==c["sha256"],"source original changed during solve")
   z.update(sha256=c["sha256"],shard=index,rep=rep,source_bytes=c["bytes"])
   rows.append(z)
   write(ROOT/f"shard-{index}-{mode}.json",rows)
   print("NATIVE_3X_TRIAL "+json.dumps(z,sort_keys=True),flush=True)
 need(len(rows)==4,"incomplete native matrix")
 print("NATIVE_3X_SHARD_PASS",index,mode,len(rows),flush=True)
def audit():
 m=verify_sources();rows=[]; seen=set()
 for i in range(SHARDS):
  for mode in MODES:
   p=ROOT/f"shard-{i}-{mode}.json"
   rr=load(p);need(len(rr)==4,"missing 4 matched trials "+str(p))
   for z in rr:
    k=(z["sha256"],z["rep"],z["mode"])
    need(k not in seen and z["mode"]==mode and z["shard"]==i,
      "duplicate/inconsistent trial")
    seen.add(k);rows.append(z)
 expected={(c["sha256"],r,mode) for c in m["sources"] for r in range(REPS)
           for mode in MODES}
 need(len(rows)==len(seen)==EXPECTED and seen==expected,"incomplete 72 matched original trials")
 bykey={(z["sha256"],z["rep"],z["mode"]):z for z in rows}
 for c in m["sources"]:
  outcome={bykey[(c["sha256"],r,mode)]["status"] for r in range(REPS) for mode in MODES}
  need(not ("SAT" in outcome and "UNSAT" in outcome),"SAT and UNSAT contradiction")
 def score(z):
  return z["E2E_s"] if z["verified_SAT"] else 2*CAP
 def describe(group):
  return dict(trials=len(group),SAT_verified=sum(z["verified_SAT"] for z in group),
    raw_UNSAT_no_LRAT=sum(z["status"]=="UNSAT" for z in group),
    TIMEOUT=sum(z["status"]=="UNKNOWN" for z in group),
    strict_PAR2_s=round(sum(score(z) for z in group),6),
    solver_s=round(sum(z["solver_s"] for z in group),6),
    E2E_s=round(sum(z["E2E_s"] for z in group),6),
    native_decisions=sum(z["metrics"]["decisions"] for z in group),
    native_conflicts=sum(z["metrics"]["conflicts"] for z in group),
    GF2_derived_implications=sum(z["metrics"]["xor_derived_implications"] for z in group),
    GF2_reasons=sum(z["metrics"]["xor_reasons"] for z in group),
    branch_guidance_suggested=sum(z["metrics"]["branch_guidance_suggested"] for z in group),
    branch_guidance_applied=sum(z["metrics"]["branch_guidance_applied"] for z in group),
    branch_guidance_evals=sum(z["metrics"]["branch_guidance_evals"] for z in group))
 def compare(a,b):
  ds=[score(bykey[(c["sha256"],r,a)])-score(bykey[(c["sha256"],r,b)])
      for c in m["sources"] for r in range(REPS)]
  return dict(wins=sum(v<-.02 for v in ds),losses=sum(v>.02 for v in ds),
      ties=sum(abs(v)<=.02 for v in ds),net_strict_PAR2_gain_s=round(-sum(ds),6))
 result={mode:describe([z for z in rows if z["mode"]==mode]) for mode in MODES}
 for mode,v in result.items():
  v["speedup_vs_gf2_x"]=round(result["gf2"]["strict_PAR2_s"]/v["strict_PAR2_s"],6)
 report=dict(protocol=PROTO,verified_original_sha=N,one_logical_CPU=True,
   no_external_solver_in_any_arm=True,independent_original_SAT_witness=True,
   independent_original_UNSAT_LRAT=False,previously_seen_not_blind=True,
   total_trials=len(rows),scores=result,
   paired_vs_gf2={m:compare(m,"gf2") for m in MODES if m!="gf2"},
   guided_vs_shadow={m:compare(m,"gf2_shadow") for m in MODES if m.startswith("gf2_") and m!="gf2_shadow"},
   per_shard={str(i):{mode:describe([z for z in rows if z["shard"]==i and z["mode"]==mode])
       for mode in MODES} for i in range(SHARDS)},
   exact_binary_sha256=m["single_binary_sha256"],
   notes=["Original 6 SHA previously seen in MIXAB3, not a blind holdout",
      "A raw UNSAT from our CDCL without independent proof is NOT certified",
      "GF2 branch decision counts alone are not speedup evidence",
      "No third-party SAT libs or subprocesses inside solver"])
 write(ROOT/"audit.json",report)
 print("NATIVE_3X_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("command",choices=("verify","freeze","audit","shard"))
 p.add_argument("--shard",type=int,default=0)
 p.add_argument("--mode",default="plain",choices=MODES)
 a=p.parse_args()
 if a.command=="verify":verify()
 elif a.command=="freeze":freeze()
 elif a.command=="audit":audit()
 else:shard(a.shard,a.mode)
