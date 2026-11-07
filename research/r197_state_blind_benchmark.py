#!/usr/bin/env python3
"""R197: original CNF causal ablations and prospective new-to-R195 holdout.
A: four known R195/R196 cases; 4 seeds x 7 modes.
B: eight SHA-disjoint original official SAT2026 cases; 3 seeds x 2 modes.
No post-outcome tuning. Global historical blind status not certified.
"""
import argparse,collections,hashlib,json,pathlib,random,re,subprocess,time
import r188_feedback_benchmark as helper
import r195_dualkeep_real_benchmark as old

ROOT=pathlib.Path("r197")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-R197-STATE-ABLATION-HOLDOUT-20261107-v1"
OLD_SHA="caae5fe7abde52e3d886add24bf23cd925411504e9c866dddcbd2fc8cb595be4"
DEV_IDS=("1236c1406a2749b8022b5196e93de589",
"20ca08f58828637815d93f46ef60b517",
"262a226a47330987f038128579967405",
"db099269d468029b70419bf4a49e99a1")
DEV_MODES=("default","split256","split256_keep_restart","split256_keep_rephase",
"split256_keep_stabilize","split256_keep_all","split128_twice")
BLIND_MODES=("default","split256")
DEV_SEEDS=(11,23,37,47)
BLIND_SEEDS=(11,23,37)
CAP=45.0
BLIND_N=8
SHARDS=12
MAX_TRIES=56
def need(x,message):
 if not x:raise RuntimeError("R197_FAIL_CLOSED "+str(message))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,d):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
def selftest():
 need(len(DEV_IDS)==4 and len(DEV_MODES)==7 and len(BLIND_MODES)==2,"arms/sources")
 need(len(DEV_SEEDS)==4 and len(BLIND_SEEDS)==3,"seeds")
 need(SHARDS==12 and BLIND_N==8 and CAP==45 and MAX_TRIES==56,"protocol")
 print("R197_SELFTEST_PASS",flush=True)
def freeze():
 base=ROOT/"archive"/"frozen"
 need(sha(base/"manifest.json")==OLD_SHA,"wrong source archive")
 prev=load(base/"manifest.json")["cases"]
 need(len(prev)==37,"original source count")
 known={c["id"]:c for c in prev}
 hashes={c["original_sha256"] for c in prev}
 FROZEN.mkdir(parents=True,exist_ok=True)
 cases=[]
 for ident in DEV_IDS:
  need(ident in known,"missing development original")
  c=known[ident];p=base/(ident+".cnf")
  need(sha(p)==c["original_sha256"],"dev source drift")
  (FROZEN/(ident+".cnf")).write_bytes(p.read_bytes())
  cases.append(dict(id=ident,sha=c["original_sha256"],cohort="development",
    source=c["source"],expected=c["expected"],cap_s=CAP))
 urls=old.download_bytes(old.URI,150000,14).decode("ascii").splitlines()
 candidates=[u.strip() for u in urls if re.fullmatch(
    r"https?://benchmark-database\.de/file/[a-f0-9]{32}",u.strip())]
 need(len(candidates)>100 and len(set(candidates))==len(candidates),"official URI source")
 candidates.sort(key=lambda u:hashlib.sha256((PROTO+u).encode()).hexdigest())
 accepted=0;attempts=0;retrieval=[]
 for url in candidates:
  if accepted>=BLIND_N or attempts>=MAX_TRIES:break
  ident=url.split("/")[-1]
  if ident in known:continue
  attempts+=1
  try:
   data=old.decode_cnf(old.download_bytes(url,old.MAX_COMPRESSED,14))
   digest=hashlib.sha256(data).hexdigest()
   need(digest not in hashes,"R195 source SHA overlap")
   need(digest not in {c["sha"] for c in cases},"duplicate selected SHA")
   (FROZEN/(ident+".cnf")).write_bytes(data)
   cases.append(dict(id=ident,sha=digest,cohort="blind_new_to_R195_R196",
       source=url,expected="UNKNOWN",cap_s=CAP))
   retrieval.append(dict(id=ident,ok=True,sha=digest))
   accepted+=1
   print("R197_BLIND_ACCEPT",ident,digest,len(data),flush=True)
  except Exception as e:
   retrieval.append(dict(id=ident,ok=False,reason=str(e)[:125]))
   print("R197_BLIND_REJECT",ident,str(e)[:125],flush=True)
 need(accepted==BLIND_N,"insufficient available new official CNFs")
 need(len({x["sha"] for x in cases})==SHARDS,"duplicated sources")
 save(FROZEN/"manifest.json",dict(protocol=PROTO,archive_sha=OLD_SHA,
      new_to_R195_R196=True,global_blind_not_certified=True,
      frozen_prior_to_any_R197_benchmark=True,precommitted_source_selection=True,
      original_index_sha256=hashlib.sha256("\n".join(urls).encode()).hexdigest(),
      attempts=retrieval,cases=cases))
 verify()
 print("R197_FREEZE_PASS",json.dumps(dict(dev=4,blind=accepted,total=len(cases),
       manifest_sha=sha(FROZEN/"manifest.json"))),flush=True)
def verify():
 d=load(FROZEN/"manifest.json")
 need(d["protocol"]==PROTO and d["archive_sha"]==OLD_SHA,"protocol")
 cs=d["cases"]
 need(len(cs)==SHARDS and sum(c["cohort"]=="development" for c in cs)==4,
      "source cardinality")
 for c in cs:
  need(sha(FROZEN/(c["id"]+".cnf"))==c["sha"],"original CNF SHA drift")
 return cs
def native(binary,source,mode,seed,cap):
 start=time.perf_counter()
 try:
  run=subprocess.run([str(binary.resolve()),str(source.resolve()),str(cap),
      mode,str(seed)],capture_output=True,timeout=cap+3,check=False)
 except subprocess.TimeoutExpired:
  return dict(status="TIMEOUT",model={},stats={},states=[],watchdog=True,
              elapsed_s=time.perf_counter()-start)
 out=run.stdout.decode(errors="replace")
 err=run.stderr.decode(errors="replace")
 need(run.returncode==0,"native execution failed "+err[-600:])
 m=re.search(r"(?m)^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\s+solver_s=([0-9.]+)",out)
 p=re.search(r"(?m)^R197_POLICY mode=(\w+) seed=(\d+) keep=(\w+)",out)
 need(m and p and p[1]==mode and int(p[2])==seed,"bad native policy/result")
 keep={"split256_keep_restart":"restart","split256_keep_rephase":"rephase",
   "split256_keep_stabilize":"stabilize","split256_keep_all":"all"}.get(mode,"none")
 need(p[3]==keep,"wrong isolation mode")
 pat=(r"R197_STATE when=(before|after) keep=(\w+) conflicts=(\d+) "
      r"restarts=(\d+) restart_limit=(-?\d+) rephase_limit=(-?\d+) "
      r"stabilize_limit=(-?\d+) stable=(\d+) "
      r"rephase_count0=(-?\d+) rephase_count1=(-?\d+)")
 states=[]
 for v in re.finditer(pat,err):
  need(v[2]==keep,"unexpected instrumented state")
  states.append(dict(when=v[1],restart=int(v[5]),rephase=int(v[6]),
     stabilize=int(v[7]),stable=int(v[8]),conflicts=int(v[3]),
     rephase0=int(v[9]),rephase1=int(v[10])))
 need(len(states) in (0,2,4),"unexpected boundary measurements")
 for k in range(0,len(states),2):
  a,b=states[k:k+2]
  need(a["when"]=="before" and b["when"]=="after","boundary order")
  need(a["conflicts"]==b["conflicts"],"boundary conflict drift")
  keys=({"restart":["restart"],"rephase":["rephase","rephase0","rephase1"],
    "stabilize":["stabilize","stable"],"all":["restart","rephase",
    "stabilize","stable","rephase0","rephase1"]}.get(keep,[]))
  for key in keys:need(a[key]==b[key],"state component changed: "+key)
 sect=re.search(r"(?ms)^R197_STATS_BEGIN\n(.*?)^R197_STATS_END$",out)
 need(sect,"native stats missing")
 stats={}
 for key in ("conflicts","decisions","propagations","restarts"):
  v=re.search(r"(?m)^\s*(?:c\s+)?"+key+r":\s+(\d+)",sect[1])
  need(v,"native stats missing "+key)
  stats[key]=int(v[1])
 model={}
 if m[1]=="SAT":
  for line in out.splitlines():
   if line.startswith("v "):
    for lit in map(int,line[2:].split()):
     if not lit:continue
     need(abs(lit) not in model or model[abs(lit)]==(lit>0),"model contradiction")
     model[abs(lit)]=(lit>0)
 return dict(status=m[1],model=model,stats=stats,states=states,
       watchdog=False,elapsed_s=time.perf_counter()-start)
def trial(c,mode,seed,binpath):
 started=time.perf_counter()
 source=FROZEN/(c["id"]+".cnf")
 need(sha(source)==c["sha"],"source drift per trial")
 r=native(binpath,source,mode,seed,c["cap_s"])
 status=r["status"];proof="CAP"
 if status=="SAT":
  _,clauses=helper.gf.dimacs(source)
  helper.gf.sat_check(clauses,r["model"])
  proof="SAT_ORIGINAL_MODEL_CHECKED"
 if status=="UNSAT":proof="NATIVE_UNSAT_NO_INDEPENDENT_LRAT"
 need(c["expected"]=="UNKNOWN" or status=="TIMEOUT" or
      c["expected"]==status,"known outcome contradicts source")
 sec=time.perf_counter()-started
 if sec>=c["cap_s"]:status="TIMEOUT"
 return dict(id=c["id"],sha=c["sha"],cohort=c["cohort"],seed=seed,
  mode=mode,status=status,elapsed_s=round(sec,6),
  par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else sec,6),
  stats=r["stats"],states=r["states"],watchdog=r["watchdog"],proof=proof)
def shard(index,binary):
 cases=verify();need(0<=index<SHARDS and binary.is_file(),"invalid shard/native")
 pin=load(ROOT/"pin.json")
 need(sha(binary)==pin["driver_sha"],"native SHA modified")
 c=cases[index];dev=c["cohort"]=="development"
 seeds=DEV_SEEDS if dev else BLIND_SEEDS
 arms=DEV_MODES if dev else BLIND_MODES
 records=[]
 for seed in seeds:
  order=list(arms)
  random.Random(PROTO+c["sha"]+str(seed)).shuffle(order)
  for mode in order:
   r=trial(c,mode,seed,binary)
   records.append(r)
   save(ROOT/f"shard-{index}.json",records)
   print("R197_TRIAL",json.dumps({k:r[k] for k in (
      "id","cohort","seed","mode","status","elapsed_s","stats","states")}),flush=True)
 need(len(records)==len(seeds)*len(arms),"incomplete shard")
 print("R197_SHARD_PASS",index,len(records),flush=True)
def audit():
 cs=verify();rs=[];groups=collections.defaultdict(list)
 for i,c in enumerate(cs):
  batch=load(ROOT/f"shard-{i}.json")
  want=28 if c["cohort"]=="development" else 6
  need(len(batch)==want,"missing shard "+str(i))
  rs.extend(batch)
 need(len(rs)==160,"incomplete audit")
 cs_by_sha={c["sha"]:c for c in cs}
 for r in rs:
  c=cs_by_sha.get(r["sha"])
  need(c and c["id"]==r["id"] and c["cohort"]==r["cohort"],"source mismatch")
  exp=2*c["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
  need(abs(exp-r["par2_s"])<1e-5,"PAR2 mismatch")
  groups[r["sha"],r["seed"]].append(r)
 for c in cs:
  dev=c["cohort"]=="development"
  for seed in DEV_SEEDS if dev else BLIND_SEEDS:
   arr=groups[c["sha"],seed]
   expected=set(DEV_MODES if dev else BLIND_MODES)
   need(len(arr)==len(expected) and set(z["mode"] for z in arr)==expected,
        "paired arms missing")
   need(len({r["status"] for r in arr if r["status"]!="TIMEOUT"})<=1,
        "SAT/UNSAT contradictory")
 result={}
 for cohort,arms in (("development",DEV_MODES),
                      ("blind_new_to_R195_R196",BLIND_MODES)):
  modes={}
  for mode in arms:
   x=[r for r in rs if r["cohort"]==cohort and r["mode"]==mode]
   modes[mode]=dict(n=len(x),solved=sum(r["status"]!="TIMEOUT" for r in x),
    sat=sum(r["status"]=="SAT" for r in x),
    unsat=sum(r["status"]=="UNSAT" for r in x),
    PAR2_s=round(sum(r["par2_s"] for r in x),6))
  b=modes["default"]["PAR2_s"]
  for d in modes.values():d["speedup"]=round(b/d["PAR2_s"],6)
  result[cohort]=modes
 save(ROOT/"report.json",dict(status="R197_AUDIT_PASS",total=160,
   SHA_verified=True,paired_seeds=True,
   new_to_R195_R196=True,global_blind_history_unverified=True,
   SAT_models_checked_original=True,UNSAT_independent_proofs_absent=True,
   results=result))
 save(ROOT/"all-trials.json",rs)
 lines=["# R197 — causal restart/rephase/stabilization isolation",
        "Development: known R195/R196; prospective holdout: new to R195/R196,",
        "not certified globally unseen. No post-outcome tuning.",
        "","| Cohort | Arm | Solved | PAR2 seconds | Speedup |",
        "|---|---|---:|---:|---:|"]
 for cohort,v in result.items():
  for mode,m in v.items():
   lines.append("| %s | %s | %d/%d | %.6f | %.6fx |"%(cohort,mode,
           m["solved"],m["n"],m["PAR2_s"],m["speedup"]))
 lines+=["","SAT models checked against original SHA-pinned CNFs.",
    "Native UNSAT not independently LRAT verified.",
    "Patches only change next-solve scheduler reinitialization,",
    "not scores, learned clauses, or all internal CDCL state."]
 (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
 print("R197_FINAL",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
 ap.add_argument("--shard",type=int,default=0)
 ap.add_argument("--binary",default="r197/r197-driver")
 a=ap.parse_args()
 if a.action=="selftest":selftest()
 elif a.action=="freeze":freeze()
 elif a.action=="verify":print("R197_VERIFY_PASS",len(verify()),flush=True)
 elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
 else:audit()
