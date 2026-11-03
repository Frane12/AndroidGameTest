#!/usr/bin/env python3
"""DRNAS SAT R61 'Killer' TRANSFER evaluation, not a record claim.

Research question: can the R55 16+17+24 certified resolvent speedup generalize
to entirely source-disjoint real SAT Competition 2026 CNFs WITHOUT regressions?

Six PRECOMMITTED approaches:
  clean: pinned unmodified Kissat on one core
  r49_gate40: previous R49 certified clauses
  r55_fixed18: R55 first16+17th+24th if R49 gate, same literal positions
  r61_pair18: first16+one ternary/binary disjoint pair from remaining 24
  r61_dualcore_race: clean Kissat on core A at t=0, R61 candidate on core B
     after proof verification; whichever returns valid answer first wins
  cadical3: pinned CaDiCaL 3.0.1 on one core

The two-core portfolio costs TWO hardware cores; its wall-clock results are
NEVER a fair one-core speedup ranking. Every mode includes certificate and
preprocessing overhead in 40s elapsed wall-time. R49 is unchanged and all
added clauses are 2-parent source-proven resolvents. No R57/R60 ML/UP scan.
This branch does not alter any previous historic experiment.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, os, random, resource
import subprocess, sys, tempfile, time
from pathlib import Path
import r32p_real_satcomp26_benchmark as r32p
import r32r_more_real_satcomp26_benchmark as r32r
import r52_prospective_2026_toprefs as r52
import r49_pivot_coherence_gate as r49

PROTO="DRNAS-R61-KILLER-REAL2026-TRANSFER-PRECOMMIT-20261103-v1"
SALT="R61-KILLER-TRANSFER-NEW-SOURCE-20261103-FROZEN-V1"
PARENT_RUNS=(41684183452,41691243486,41694594541,41698075753)
CAP=40.0
REPS=2
SHARDS=8
MODES=("clean","r49_gate40","r55_fixed18","r61_pair18","r61_dualcore_race","cadical3")
STRATA=("sat_fast","unsat_fast","sat_mid","unsat_mid","sat_slow","unsat_slow")
MAX_PER_STRATUM=34
TARGET_READY=16
MIN_READY=8
CNF_BYTES_MAX=48*1024*1024
RAW_BYTES_MAX=28*1024*1024

def check(v,message):
 if not v:raise RuntimeError("R61_FAIL_CLOSED: "+str(message))
def sha(path):return r52.digest(path)
def hashed(v):return hashlib.sha256((SALT+":"+v).encode()).hexdigest()

def choose(plan,mode):
 """Only source-proven R47 resolvents, never changes SAT search logic."""
 c=plan["clauses"];p=plan["proofs"]
 check(len(c)==len(p)<=40,"bad certified clause plan")
 if mode=="r49_gate40":return c if plan["gate"] else []
 if mode=="r55_fixed18":
  return c[:16]+[c[16],c[23]] if plan["gate"] and len(c)>=24 else []
 if mode=="r61_pair18":
  if not plan["gate"] or len(c)<24:return []
  original=c[:16]
  rest=list(enumerate(zip(c,p),start=0))[16:]
  triples=[(i,cl,proof) for i,(cl,proof) in rest if len(cl)==3]
  binaries=[(i,cl,proof) for i,(cl,proof) in rest if len(cl)==2]
  options=[]
  prefix_vars=set(abs(x) for cl in original for x in cl)
  for i,tri,tp in triples:
   for j,bi,bp in binaries:
    if tp["pivot"]!=bp["pivot"]:continue
    if set(map(abs,tri)) & set(map(abs,bi)):continue
    # Frozen, cheap clause/proof-only priority, NOT learned from held-out times.
    support_overlap=len(set(tp["support"]) & set(bp["support"]))
    prefix_touch=len((set(map(abs,tri))|set(map(abs,bi))) & prefix_vars)
    score=(support_overlap,prefix_touch,-(i+j),-i,-j)
    options.append((score,i,j))
  if not options:return []
  _,i,j=max(options)
  return original+[c[k] for k in sorted([i,j])]
 raise RuntimeError("unknown clause selection "+mode)

def make_candidate(source,candidate,mode):
 plan=r49.compute_plan(source)
 selected=choose(plan,mode)
 check(len(selected)<=40,"unsafe injection")
 if selected:
  result=r49.r48.safe_rewrite(source,candidate,selected)
  check(result["added"]==len(selected),"rewritten DIMACS mismatch")
  return str(candidate),len(selected),plan
 return str(source),0,plan

def source_meta(a):
 root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
 manifests={}
 paths=(("R52",a.prior52),("R55b",a.prior55),("R57",a.prior57),("R60",a.prior60))
 sizes=(11,11,8,9)
 for (key,path),expected in zip(paths,sizes):
  m=json.loads((Path(path)/"manifest.json").read_text())
  check(len(m["cases"])==expected,"earlier frozen manifest changed "+key)
  manifests[key]=m
 old_ids=set(g for _,g in r32p.PINS)|set(g for _,g in r32r.PINS)
 check(len(old_ids)==37,"old pinned registry changed")
 old_sha=set()
 for key,m in manifests.items():
  for c in m["cases"]:
   check(c["gbd"] not in old_ids,"old cohort GBD repetition")
   old_ids.add(c["gbd"])
   old_sha.add(c.get("sha256",c.get("source_sha256")))
 check(len(old_ids)==76 and len(old_sha)==39,
       "old SAT2026 cohort overlap or changed identities")
 official=r52.fetch_bytes(r52.URI,100000)
 ids=[s.rsplit("/",1)[-1] for s in official.decode().strip().splitlines()]
 check(len(ids)==400 and len(set(ids))==400,"official 2026 400 ID list changed")
 score_raw=r52.fetch_bytes(r52.SCORES,32*1024*1024)
 scores=[x for x in csv.DictReader(io.StringIO(score_raw.decode("utf-8")))
  if x["solverid"]=="biere_cadical3[main]" and x["instanceid"] in set(ids)]
 check(len(scores)==400,"public CaDiCaL 2026 score rows drift")
 pools={s:[] for s in STRATA}
 for x in scores:
  g=x["instanceid"]
  if g in old_ids or x["status"] not in ("sat-verified","unsat-verified"):continue
  t=float(x["runtime"])
  tier="fast" if 0<=t<10 else "mid" if t<80 else "slow" if t<5000 else None
  if not tier:continue
  s=("sat" if x["status"]=="sat-verified" else "unsat")+"_"+tier
  pools[s].append(dict(gbd=g,stratum=s,official_status=
   "SAT" if x["status"]=="sat-verified" else "UNSAT",
   public_cadical_s=t))
 sorted_pools={k:sorted(v,key=lambda c:hashed(k+"/"+c["gbd"]))[:MAX_PER_STRATUM]
                for k,v in pools.items()}
 ordered=[]
 for i in range(MAX_PER_STRATUM):
  for key in STRATA:
   if i<len(sorted_pools[key]):ordered.append(sorted_pools[key][i])
 r32p.CNF_LIMIT=CNF_BYTES_MAX
 accepted=[];trials=[];seen=set()
 for q in ordered:
  if len(accepted)>=TARGET_READY:break
  g=q["gbd"]
  check(g not in seen and g not in old_ids,"source identity duplicate");seen.add(g)
  file=root/(g+".cnf")
  record=dict(gbd=g,stratum=q["stratum"])
  try:
   packed,redirect=r32p.request_url(
      "https://benchmark-database.de/file/"+g,RAW_BYTES_MAX,seconds=55)
   plain,compression=r32p.decode(packed)
   check(len(plain)<=CNF_BYTES_MAX,"uncompressed byte cap")
   vars_,nclauses=r32p.parse_dimacs_metadata(plain)
   file.write_bytes(plain)
   digest=sha(file)
   check(digest not in old_sha,"source SHA previously seen")
   # Do NOT inspect clause structures, R55 derived gates, or timings for selection.
   selected=dict(**q,filename=file.name,sha256=digest,
      original_variables=vars_,original_clauses=nclauses,
      compressed_bytes=len(packed),source_bytes=len(plain),
      compression=compression,redirect=redirect)
   accepted.append(selected)
   record.update(state="FROZEN",sha256=digest,source_bytes=len(plain))
  except Exception as exc:
   file.unlink(missing_ok=True)
   record.update(state="EXCLUDED_PRECOMMITTED_SIZE_OR_PARSE",
                 reason=str(exc)[:270])
  trials.append(record)
  print("R61_SOURCE_FREEZE_CANDIDATE",json.dumps(record,sort_keys=True),flush=True)
 check(len(accepted)>=MIN_READY,"too few unseen official real CNFs; no benchmark")
 check(len({v["sha256"] for v in accepted})==len(accepted),"duplicate SHA")
 m=dict(protocol=PROTO,salt=SALT,source_selection=
   "frozen salted official public CaDiCaL SAT/UNSAT+runtime strata and size guards only",
   excluded_previous_ids=sorted(old_ids),
   exclusion_parent_runs=list(PARENT_RUNS),
   previous_manifests_sha={name:sha(Path(path)/"manifest.json")
                 for name,path in paths},
   no_DRNAS_outcomes_or_derived_features_used_for_selection=True,
   official_uri_sha=hashlib.sha256(official).hexdigest(),
   official_scores_sha=hashlib.sha256(score_raw).hexdigest(),
   cases=accepted,selection_attempts=trials,cap_s=CAP,reps=REPS,
   shards=SHARDS,methods=list(MODES),
   policies={
      "r49_gate40":"R49 >=24 resolved and dominance >=.8, 40 source-certified clauses",
      "r55_fixed18":"R49 gate then exact first16 plus positions 17 and 24",
      "r61_pair18":"R49 gate then first16 and a deterministic same-pivot disjoint ternary+binary from positions 17..40",
      "r61_dualcore_race":"two-core concurrent baseline and prepared r61_pair18 (baseline starts first)",
   },
   limitations=[
      "R55 pair selected on one prior known formula; transfer is hypothesis only",
      "Neither one-core approach can guarantee zero regressions",
      "Dualcore portfolio uses two cores: NOT comparable resource cost to one-core runs",
      "Only recorded past cohorts excluded, not all project historical runs",
      "Official competition scores select runtime strata, not an official contest replay",
      "SAT witness verified against unchanged original; no independent LRAT UNSAT proof",
      "Only frozen derived certified clauses; no R57/R60 expensive learning scan"])
 (root/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
 (root/"source.sha256").write_text("".join(
       c["sha256"]+"  "+c["filename"]+"\n" for c in accepted))
 print("R61_SOURCE_FREEZE_PASS",len(accepted),"total_methods",
   len(accepted)*REPS*len(MODES),"unique_fresh_sha",len(accepted),flush=True)

def child_limits(cpu):
 def f():
  resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
  if cpu is not None:os.sched_setaffinity(0,{cpu})
 return f

def ordinary_trial(source,kissat,cadical,mode,first_cpu):
 begin=time.monotonic()
 added=0;status="TIMEOUT"
 with tempfile.TemporaryDirectory(prefix="r61-onecore-") as d:
  target=str(source)
  if mode in ("r49_gate40","r55_fixed18","r61_pair18"):
   target,added,_=make_candidate(source,Path(d)/"candidate.cnf",mode)
  prep=time.monotonic()-begin
  if prep<CAP:
   binary=cadical if mode=="cadical3" else kissat
   try:
    p=subprocess.run([str(binary),target],
       stdout=subprocess.PIPE,stderr=subprocess.PIPE,
       text=True,errors="replace",timeout=CAP-prep,
       preexec_fn=child_limits(first_cpu))
    check(p.returncode in (10,20),
      "solver process error "+str(p.returncode)+" "+p.stderr[-160:])
    status="SAT" if p.returncode==10 else "UNSAT"
    if status=="SAT":r32p.verify_sat_witness(source,p.stdout)
   except subprocess.TimeoutExpired:
    status="TIMEOUT"
  wall=time.monotonic()-begin
  if wall>CAP:status="TIMEOUT"
 return dict(status=status,wall_s=round(min(CAP,wall),6),
    prep_s=round(prep,6),par2_s=round(
       min(CAP,wall) if status!="TIMEOUT" else 80.0,6),
    added=added,cores=1,winner=mode)

def prepare_worker(a):
 source=Path(a.source)
 start=time.monotonic()
 chosen,n,plan=make_candidate(source,Path(a.candidate),"r61_pair18")
 meta=dict(added=n,candidate=chosen,
    gate=bool(plan["gate"]),derived=plan["derived"],
    elapsed_s=round(time.monotonic()-start,6))
 # Atomically publish complete decisions after candidate bytes are fully written.
 tmp=Path(a.meta+".tmp")
 tmp.write_text(json.dumps(meta)+"\n")
 tmp.replace(a.meta)

def race_trial(source,kissat,cpus):
 check(len(cpus)>=2,"two-core race requires >=2 distinct CPU cores")
 start=time.monotonic()
 core0,core1=cpus[:2]
 processes=[]
 handles=[]
 status="TIMEOUT"
 winner="none"
 added=0;candidate_started=False
 prep=0.0
 with tempfile.TemporaryDirectory(prefix="r61-two-core-") as folder:
  d=Path(folder)
  base_out,base_err=d/"baseline.out",d/"baseline.err"
  base_stdout=open(base_out,"w");base_stderr=open(base_err,"w")
  handles.extend([base_stdout,base_stderr])
  baseline=subprocess.Popen([str(kissat),str(source)],
      stdout=base_stdout,stderr=base_stderr,preexec_fn=child_limits(core0))
  processes.append(baseline)
  # Independent process on second core; baseline starts before preprocessing.
  ready=d/"meta.json"
  candidate=d/"augmented.cnf"
  prepared_err=open(d/"prepare.stderr","w")
  handles.append(prepared_err)
  work=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"prepare",
        "--source",str(source),"--candidate",str(candidate),"--meta",str(ready)],
      stdout=subprocess.DEVNULL,stderr=prepared_err,
      preexec_fn=child_limits(core1))
  processes.append(work)
  other=None
  output_by_process={baseline:base_out}
  errors_by_process={baseline:base_err}
  try:
   while time.monotonic()-start<CAP:
    # Check whichever valid SAT/UNSAT completion occurred; baseline first on ties.
    for who,tag in ((baseline,"baseline"),(other,"candidate")):
     if who is None:continue
     returncode=who.poll()
     if returncode is None:continue
     if returncode not in (10,20):
      check(False,"two-core solver process unexpectedly exited: "+tag+" "+str(returncode))
     answer="SAT" if returncode==10 else "UNSAT"
     if answer=="SAT":
      r32p.verify_sat_witness(source,output_by_process[who].read_text())
     status=answer
     winner=tag
     break
    if status!="TIMEOUT":break
    if other is None and work.poll() is not None:
     check(work.returncode==0 and ready.is_file(),
          "certified clause preparation failed: "+(d/"prepare.stderr").read_text()[-260:])
     meta=json.loads(ready.read_text())
     prep=float(meta["elapsed_s"])
     added=int(meta["added"])
     # Zero-case abstention: no competing solver; only baseline stays alive.
     if added:
      check(meta["candidate"]==str(candidate) and candidate.is_file(),
            "prepared candidate path or source invalid")
      second_out,second_err=d/"candidate.out",d/"candidate.err"
      oh=open(second_out,"w");eh=open(second_err,"w")
      handles.extend([oh,eh])
      other=subprocess.Popen([str(kissat),str(candidate)],
           stdout=oh,stderr=eh,preexec_fn=child_limits(core1))
      processes.append(other)
      output_by_process[other]=second_out
      errors_by_process[other]=second_err
     else:
      # Keep the original Kissat only (no point in duplicate identical race).
      other=baseline if False else None
      # Mark no second worker to start by removing the worker object.
      work=None
    time.sleep(.004)
  finally:
   for proc in processes:
    if proc.poll() is None:
     proc.terminate()
     try:proc.wait(timeout=2)
     except subprocess.TimeoutExpired:
      proc.kill();proc.wait(timeout=2)
   for handle in handles:
    handle.close()
 wall=time.monotonic()-start
 if wall>CAP:status="TIMEOUT"
 return dict(status=status,wall_s=round(min(CAP,wall),6),
  prep_s=round(prep,6),par2_s=round(
    min(CAP,wall) if status!="TIMEOUT" else 80,6),
  added=added,cores=2,winner=winner)

def measure(a):
 m=json.loads((Path(a.sources)/"manifest.json").read_text())
 check(m["protocol"]==PROTO and a.shard in range(SHARDS),"source design mismatch")
 kb=Path(a.kissat).resolve()
 cb=Path(a.cadical).resolve()
 check(kb.is_file() and cb.is_file(),"missing pinned executables")
 cpus=sorted(os.sched_getaffinity(0))
 check(len(cpus)>=2,"R61 two-core portfolio requires 2 CPU cores")
 # One-core mode binds to first CPU, dual-core portfolio to first 2.
 root=Path(a.sources)
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 metadata=dict(protocol=PROTO,shard=a.shard,
      manifest_sha=sha(root/"manifest.json"),kissat_sha=sha(kb),
      cadical_sha=sha(cb),cpu_set=cpus[:2])
 (out/"meta.json").write_text(json.dumps(metadata,indent=2)+"\n")
 rows=[]
 for c in m["cases"][a.shard::SHARDS]:
  source=root/c["filename"]
  check(sha(source)==c["sha256"],"SHA-frozen source changed")
  for rep in range(REPS):
   modes=list(MODES)
   random.Random(int(hashed(c["sha256"]+"/"+str(rep)),16)).shuffle(modes)
   for mode in modes:
    result=(race_trial(source,kb,cpus) if mode=="r61_dualcore_race"
           else ordinary_trial(source,kb,cb,mode,cpus[0]))
    check(result["status"]=="TIMEOUT" or result["status"]==c["official_status"],
      "different SAT answer from official source")
    row=dict(gbd=c["gbd"],source_sha=c["sha256"],rep=rep,mode=mode,**result)
    rows.append(row)
    print("R61_REAL2026_TRIAL",c["gbd"],"rep",rep,mode,result["status"],
      result["wall_s"],"PAR2",result["par2_s"],
      "prep",result["prep_s"],"added",result["added"],
      "winner",result["winner"],flush=True)
    (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
 check(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),
   "incomplete runner shard")

def audit(a):
 root=Path(a.sources)
 m=json.loads((root/"manifest.json").read_text())
 check(m["protocol"]==PROTO,"wrong frozen experiment")
 rows=[];pins=set();seen=set()
 for i in range(SHARDS):
  d=Path(a.combined)/f"r61-shard-{i}"/"results"
  meta=json.loads((d/"meta.json").read_text())
  check(meta["protocol"]==PROTO and meta["shard"]==i
        and meta["manifest_sha"]==sha(root/"manifest.json"),
        "shard source manifest mismatch")
  pins.add((meta["kissat_sha"],meta["cadical_sha"]))
  partial=json.loads((d/"rows.json").read_text())
  check(len(partial)==len(m["cases"][i::SHARDS])*len(MODES)*REPS,
        "shard rows missing")
  for z in partial:
   key=(z["source_sha"],z["rep"],z["mode"])
   check(key not in seen,"duplicate result")
   seen.add(key)
   rows.append(z)
 check(len(pins)==1 and len(rows)==len(m["cases"])*REPS*len(MODES),
       "mixed pinned binaries or incomplete comparison")
 methods={}
 for mode in MODES:
  x=[r for r in rows if r["mode"]==mode]
  methods[mode]=dict(attempts=len(x),
    solved=sum(r["status"]!="TIMEOUT" for r in x),
    timeout=sum(r["status"]=="TIMEOUT" for r in x),
    par2_total_s=round(sum(r["par2_s"] for r in x),6),
    prep_total_s=round(sum(r["prep_s"] for r in x),6),
    added_total=sum(r["added"] for r in x),
    cores=max(r["cores"] for r in x),
    portfolio_wins={
      "baseline":sum(r["winner"]=="baseline" for r in x),
      "candidate":sum(r["winner"]=="candidate" for r in x)})
 baseline=methods["clean"]["par2_total_s"]
 for v in methods.values():
  v["delta_vs_clean_pct"]=round(100*(v["par2_total_s"]/baseline-1),4)
 per_case={};regressions={mode:0 for mode in MODES}
 for c in m["cases"]:
  rr=[r for r in rows if r["gbd"]==c["gbd"]]
  check(len(rr)==REPS*len(MODES)
    and all(z["source_sha"]==c["sha256"] for z in rr),"formula mismatch")
  for rep in range(REPS):
   sample=[r for r in rr if r["rep"]==rep]
   check(set(z["mode"] for z in sample)==set(MODES),"missing paired mode")
  stat={}
  for mode in MODES:
   xs=sorted([z for z in rr if z["mode"]==mode],key=lambda z:z["rep"])
   stat[mode]=dict(par2_sum=round(sum(x["par2_s"] for x in xs),6),
        wall_times=[x["wall_s"] if x["status"]!="TIMEOUT" else "TO" for x in xs],
        clauses_added=[x["added"] for x in xs],
        winner=[x["winner"] for x in xs])
  b=stat["clean"]["par2_sum"]
  for mode in MODES:
   # Preregister operational regression: >= 0.5 seconds worse PAR2 per
   # source across two attempts (more severe penalty on timeout).
   if stat[mode]["par2_sum"]>b+0.5:regressions[mode]+=1
  per_case[c["gbd"]]=stat
 report=dict(protocol=PROTO,source_originals=len(m["cases"]),
   total_attempts=len(rows),methods=methods,regressions_over_half_second=regressions,
   per_case=per_case,rows=rows,manifest=m,
   pinned_binaries=next(iter(pins)),
   promotion_check={
      "onecore_r55_fixed18_zero_half_second_regressions":regressions["r55_fixed18"]==0,
      "onecore_r61_pair18_zero_half_second_regressions":regressions["r61_pair18"]==0,
      "two_core_portfolio_zero_half_second_regressions":regressions["r61_dualcore_race"]==0,
      "onecore_any_proven_global_PAR2_gain":any(methods[mode]["par2_total_s"]<baseline
           for mode in ("r55_fixed18","r61_pair18"))})
 Path(a.json).write_text(json.dumps(report,indent=2)+"\n")
 lines=["# R61 — DRNAS SAT 'Killer' transfer and non-regression gate",
   f"**{len(m['cases'])} new real official SAT Competition 2026 original CNFs, {len(rows)} completed attempts.**",
   "Original SHA-disjoint from R32p/R32r, R52, R55b, R57 and R60 official cohorts.",
   "Fixed pair R55 and source-proof-driven general structural pair selected BEFORE unseen timings.",
   "Zero-regression promotion check is ≥0.5s PAR2 penalty on two repeats per original.",
   "**2-core race NOT fair as an equal-resource single-core speedup.**",
   "40s total end-to-end cap per trial, 80s PAR2 per timeout, SAT model checked.",
   "",
   "## Summary",
   "| Mode | CPU cores | Solved | PAR2 sum s | vs clean | >0.5s source regressions |",
   "|---|---:|---:|---:|---:|---:|"]
 for mode in MODES:
  x=methods[mode]
  lines.append(f'| {mode} | {x["cores"]} | {x["solved"]}/{x["attempts"]} | {x["par2_total_s"]:.3f} | {x["delta_vs_clean_pct"]:+.2f}% | {regressions[mode]} |')
 lines+=["","## Per original formula (PAR2 seconds, two matched repeats)",
     "| Official GBD | "+" | ".join(MODES)+" |",
     "|---|"+("|---:|"*len(MODES))]
 for c in m["cases"]:
  p=per_case[c["gbd"]]
  lines.append("| "+c["gbd"][:12]+" | "+
   " | ".join(f'{p[mode]["par2_sum"]:.3f}' for mode in MODES)+" |")
 lines+=["","## Decision",
   "A solver candidate can only be called 'ready to promote' if it improves"
   " total single-core PAR2 *and* does not regress any measured source by >0.5 seconds.",
   "Even this empirical condition does NOT guarantee no regressions on all CNFs.",
   "Two-core portfolio needs separate CPU-normalized evaluation; resource cost is doubled.",
   "Historic R57/R60 expensive probing gates deliberately excluded.",
   "Full rows, CPU core counts, winner and SHA are archived in JSON.",
   "No formal SAT world-record or P=NP claim."]
 Path(a.md).write_text("\n".join(lines)+"\n")
 print("R61_FINAL_AUDIT_PASS",len(rows),
    json.dumps(dict(methods=methods,regression_sources=regressions,
                    promotion=report["promotion_check"]),sort_keys=True),flush=True)

def main():
 p=argparse.ArgumentParser()
 sub=p.add_subparsers(dest="cmd",required=True)
 f=sub.add_parser("freeze")
 for name in ("prior52","prior55","prior57","prior60","out"):
  f.add_argument("--"+name,required=True)
 t=sub.add_parser("measure")
 for name in ("sources","shard","kissat","cadical","out"):
  t.add_argument("--"+name,required=True)
 w=sub.add_parser("prepare")
 for name in ("source","candidate","meta"):w.add_argument("--"+name,required=True)
 a=sub.add_parser("audit")
 for name in ("sources","combined","json","md"):a.add_argument("--"+name,required=True)
 x=p.parse_args()
 if x.cmd=="freeze":source_meta(x)
 elif x.cmd=="measure":
  x.shard=int(x.shard);measure(x)
 elif x.cmd=="prepare":prepare_worker(x)
 else:audit(x)
if __name__=="__main__":main()
