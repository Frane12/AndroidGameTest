#!/usr/bin/env python3
"""R157 in-process CaDiCaL IPASIR-UP XOR propagation paired diagnostic.

Original four mixed formulas only. Cross-compare clean same-CaDiCaL,
frozen source XOR observation, reversible watched rows, source-certified
learnt clauses and direct implied literals with immutable CNF reasons.
Record R157_PROGRESS even on TIMEOUT, unlike older R155 run. All sources
previously exposed; development evidence only, not blind holdout.
"""
import argparse,hashlib,json,os,pathlib,random,re,statistics,subprocess,time,sys
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r157_source_certified_xor as proofgen
ROOT=pathlib.Path("r157");FROZEN=ROOT/"frozen";CAP=15.0
MODES=("clean","freeze","watch","clause","direct")
REPS=2;SHARDS=4
PROTO="DRNAS-R157-NATIVE-CDCL-GF2-IPASIRUP-MIXED-4-DEV-20261105-v1"
def need(x,msg):
 if not x:raise RuntimeError("R157_AUDIT_REFUSED "+msg)
def sha(x):return hashlib.sha256(pathlib.Path(x).read_bytes()).hexdigest()
def rd(x):return json.loads(pathlib.Path(x).read_text())
def wr(p,obj):pathlib.Path(p).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def sources():
 m=rd(FROZEN/"manifest.json")
 need(len(m["cases"])==25 and m["cohort_counts"]["mixed_residual"]==4,"unexpected original R154 frozen manifest")
 selected=sorted((x for x in m["cases"] if x["cohort"]=="mixed_residual"),key=lambda x:x["id"])
 need(len(selected)==4,"exactly four original mixed cases expected")
 for c in selected:need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"original source SHA changed")
 return selected
def parse_native(out):
 text=out.decode(errors="replace")
 mt=re.search(r"^R157_START mode=(\w+) source_rows=(\d+) derived_rows=(\d+) clauses=(\d+) observed_vars=(\d+)$",text,re.M)
 progress=re.findall(r"^R157_PROGRESS mode=direct assignments=(\d+) backtracks=(\d+) rows_scanned=(\d+) direct_proposals=(\d+) reason_requests=(\d+) budget_off=(\d+) disabled=(\d+)$",text,re.M)
 final=re.search(r"^R157_RESULT ([^\n]+)$",text,re.M)
 return (dict(mode=mt[1],source_rows=int(mt[2]),derived_rows=int(mt[3]),clauses=int(mt[4]),vars=int(mt[5])) if mt else None,
         ([int(v) for v in progress[-1]] if progress else None),
         dict(re.findall(r"(\w+)=([^\s]+)",final[1])) if final else None)
def run(case,mode,rep,binary,rows,prep,evidence):
 cnf=FROZEN/(case["id"]+".cnf")
 need(sha(cnf)==case["sha256"],"source SHA mismatch")
 charge=0.0 if mode=="clean" else prep
 deadline=max(0.01,CAP-charge)
 t0=time.perf_counter();timedout=False;stdout=b"";returncode=None;elapsed=CAP
 try:
  p=subprocess.run([str(binary.resolve()),mode,str(cnf.resolve()),str(rows.resolve())],
     stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=deadline)
  stdout=p.stdout;returncode=p.returncode
  elapsed=min(CAP,time.perf_counter()-t0+charge)
  need(returncode in (10,20),f"solver failed {mode} code={returncode} err={p.stderr[-250:]}")
 except subprocess.TimeoutExpired as exc:
  stdout=exc.stdout or b""
  timedout=True
 started,progress,result=parse_native(stdout)
 need(started and started["mode"]==mode,"missing original source START telemetry")
 need(started["source_rows"]==(0 if mode=="clean" else evidence["selected_rows"]),"source row binding changed")
 status="TIMEOUT" if timedout or elapsed>=CAP else "SAT" if returncode==10 else "UNSAT"
 if status!="TIMEOUT":
  need(result and result["status"]==status,"missing consistent CaDiCaL final result")
  need(result["disabled"]=="0","GF2 watched trail invariant disabled")
  if status=="SAT":need(result["sat_witness_checked"]=="1","SAT original source witness invalid")
 if mode=="direct" and progress:
  need(progress[5]==0 and progress[6]==0,"unsafe direct bridge disabled")
 fields=("direct_proposals","direct_reason_requests","direct_reason_lits","rows_scanned","assignments","backtracks")
 activity={v:int(result[v]) for v in fields} if result else {
  "direct_proposals":progress[3] if progress else None,
  "direct_reason_requests":progress[4] if progress else None,
  "direct_reason_lits":None,
  "rows_scanned":progress[2] if progress else None,
  "assignments":progress[0] if progress else None,
  "backtracks":progress[1] if progress else None}
 return dict(id=case["id"],cohort=case["cohort"],sha256=case["sha256"],mode=mode,repeat=rep,
   source_rows=evidence["selected_rows"],source_unit_simplified=evidence["source_unit_simplified"],
   source_proof_sha=sha(rows),status=status,par2=round(2*CAP if status=="TIMEOUT" else elapsed,6),
   time_s=round(CAP if status=="TIMEOUT" else elapsed,6),prep_s=round(charge,6),
   timeout_progress_recovered=bool(status=="TIMEOUT" and progress),**activity)
def shard(idx,binary):
 need(0<=idx<SHARDS,"invalid shard")
 cs=sources()
 if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 rows=[]
 for j,c in enumerate(cs):
  if j%SHARDS!=idx:continue
  src=FROZEN/(c["id"]+".cnf")
  t=time.perf_counter()
  tsv=ROOT/("cert-"+c["id"]+".tsv")
  evfile=ROOT/("cert-"+c["id"]+".json")
  ev=proofgen.extract(src,tsv,evfile)
  prep=time.perf_counter()-t
  need(ev["source_sha256"]==sha(src) and ev["selected_rows"]>0,"no certified GF2 source rows")
  for rep in range(REPS):
   modes=list(MODES);random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
   for mode in modes:
    trial=run(c,mode,rep,binary,tsv,prep,ev)
    rows.append(trial);wr(ROOT/f"shard-{idx}.json",rows)
    print("R157_TRIAL",json.dumps(trial,sort_keys=True),flush=True)
 need(len(rows)==REPS*len(MODES),"short paired shard")
 print("R157_SHARD_PASS",idx,len(rows),flush=True)
def audit():
 cs=sources();allrows=[];keys=set();binary_hash=set()
 for idx in range(SHARDS):
  data=rd(ROOT/f"shard-{idx}.json")
  need(len(data)==REPS*len(MODES),"incomplete R157 shard "+str(idx))
  pin=rd(ROOT/f"pin-{idx}.json");binary_hash.add(pin["binary_sha"])
  for x in data:
   c=next((z for z in cs if z["id"]==x["id"]),None)
   need(c and c["sha256"]==x["sha256"],"R157 original source mismatch")
   key=(x["id"],x["repeat"],x["mode"])
   need(key not in keys,"duplicate R157 pair")
   keys.add(key)
   need(abs(x["par2"]-(2*CAP if x["status"]=="TIMEOUT" else x["time_s"]))<1e-5,"PAR2 wrong")
   if x["mode"]!="clean":need(x["source_rows"]>0,"no certified rows")
  allrows.extend(data)
 need(len(allrows)==4*REPS*len(MODES) and len(binary_hash)==1,"missing run or binary drift")
 for c in cs:
  q=[x for x in allrows if x["id"]==c["id"]]
  need(len(q)==REPS*len(MODES),"incomplete matched source")
  need(len({x["status"] for x in q if x["status"]!="TIMEOUT"})<=1,"SAT/UNSAT disagreement")
 out={}
 for mode in MODES:
  z=[x for x in allrows if x["mode"]==mode]
  out[mode]=dict(trials=len(z),solved=sum(x["status"]!="TIMEOUT" for x in z),
    PAR2_s=round(sum(x["par2"] for x in z),6),
    timeout_progress_recovered=sum(x["timeout_progress_recovered"] for x in z),
    proposals_completed=sum(x["direct_proposals"] or 0 for x in z),
    source_rows=sum(x["source_rows"] for x in z),
    progress=[dict(id=x["id"],notifications=x["assignments"],proposals=x["direct_proposals"],backtracks=x["backtracks"]) for x in z])
 base=out["clean"]["PAR2_s"]
 out["direct"]["PAR2_gain_vs_same_CaDiCaL_clean_pct"]=round(100*(base-out["direct"]["PAR2_s"])/base,4)
 result=dict(protocol=PROTO,status="AUDIT_PASS_RESEARCH_ONLY",not_blind=True,
  source_run=42107642696,original_formulas=4,trial_count=len(allrows),cap_s=CAP,
  paired_same_runner=True,immutable_original_sha=True,native_sha=next(iter(binary_hash)),
  original_sat_models_checked_native=True,independent_UNSAT_LRAT=False,
  notes=["All GF2 rows derived from original complete XOR + unit clauses and source SHA checked",
  "In-process direct IPASIR-UP reasons use reversible XOR trail and immutable original row",
  "Progress on TIMEOUT is checkpoint data, not final solver result",
  "Not a claim of speedup if all modes time out; development-only source reuse"],
  modes=out,rows=allrows)
 wr(ROOT/"report.json",result)
 print("R157_FINAL",json.dumps({k:result[k] for k in ("status","trial_count","modes")},sort_keys=True),flush=True)
if __name__=="__main__":
 a=argparse.ArgumentParser();a.add_argument("act",choices=("shard","audit"));a.add_argument("--shard",type=int,default=0);a.add_argument("--binary")
 opt=a.parse_args()
 if opt.act=="shard":
  need(opt.binary,"missing pinned CaDiCaL GF2 native binary")
  shard(opt.shard,pathlib.Path(opt.binary))
 else:audit()
