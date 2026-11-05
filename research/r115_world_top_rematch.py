#!/usr/bin/env python3
"""R115 official 2026 instance rematch with published per-instance virtual-best times.

Three explicitly SEEN controls (R115 + two R117), plus 12 preselected random
official 2026 instances; not claim global novelty or official re-ranking.
Original R28 GF(2) code frozen; compare same host with pinned Kissat/CaDiCaL.
Reconstruct XOR contradiction independently from original DIMACS, validate SAT
witnesses against unmodified original. Official historical times are recorded
as cross-machine context, NEVER paired same-host results.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,os,pathlib,random,re,subprocess,sys,time,urllib.request
from collections import Counter,defaultdict
ROOT=pathlib.Path("r115_world");ROOT.mkdir(exist_ok=True)
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/"experiments/drnas_v16"))
import r32p_real_satcomp26_benchmark as source
PROTO="DRNAS-R115-OFFICIAL-2026-VBS-REPEAT-20261105-v1"
SHARDS=6;CAP=5.0;MODES=("r28","kissat","cadical")
CSV_URL="https://satcompetition.github.io/2026/downloads/scores.csv"
KNOWN=[
 ("75429ff7acb5acb597abe01aa745c2a6","R115_HISTORICAL",5),
 ("01d6fa8efd18ebfecd06af408958477b","R117_PREVIOUSLY_SEEN_SAT2026",3),
 ("0efcbd10294eb001b16b4d126923372f","R117_PREVIOUSLY_SEEN_UNSAT2026",3),
]
KISSAT=pathlib.Path("built/bin/kissat_4_0_4").resolve()
CADICAL=pathlib.Path("built/bin/cadical_3_0_1").resolve()
R28=pathlib.Path("r115_world/r28").resolve()

def need(v,msg):
 if not v:raise RuntimeError("R115_WORLD_AUDIT_FAIL "+str(msg))
def sha(b):return hashlib.sha256(b).hexdigest()
def file_sha(path):return sha(pathlib.Path(path).read_bytes())
def write(path,data):pathlib.Path(path).write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def read(path):return json.loads(pathlib.Path(path).read_text())
def fetch(url,limit=4_000_000):
 req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R115-Official-Audit/1.0"})
 with urllib.request.urlopen(req,timeout=55) as r:data=r.read(limit+1)
 need(len(data)<=limit,"source too large "+url)
 return data
def score_source():
 raw=fetch(CSV_URL,8_000_000)
 text=raw.decode("utf-8")
 rows=list(csv.DictReader(io.StringIO(text)))
 need(len(rows)>=10000 and all(set(("solverid","instanceid","runtime","status","score","vresult"))<=set(row) for row in rows[:1]),"official score file layout")
 grouped=defaultdict(list)
 for r in rows:
  key=r["instanceid"]
  if len(key)!=32:continue
  if r["status"] in ("sat-verified","unsat-verified"):
   t=float(r["runtime"])
   if t>0 and t<=5000.2:
    grouped[key].append({"solver":r["solverid"],"seconds":t,"status":r["status"],
                         "official_result":r["vresult"]})
 data={}
 for k,v in grouped.items():
  v.sort(key=lambda z:z["seconds"])
  mains=sorted((z for z in v if z["solver"].endswith("[main]")),key=lambda z:z["seconds"])
  data[k]={"best_verified":v[0],"best_main":mains[0] if mains else None,
           "verified_solvers":len(v)}
 return data,sha(raw),len(rows)

def freeze():
 scores,digest,score_rows=score_source()
 known_set={k for k,_,_ in KNOWN}
 ids=sorted(k for k,v in scores.items() if k not in known_set and v["best_verified"]["seconds"]>0)
 random.Random(PROTO+"|RANDOM_OFFICIAL_INSTANCES").shuffle(ids)
 chosen=[dict(id=k,cohort=label,reps=reps,known=True) for k,label,reps in KNOWN]
 for c in chosen:need(c["id"] in scores,"known control lacks official verified score "+c["id"])
 n=0;skips=Counter();claimed=set(known_set)
 for id in ids:
  if n>=12:break
  if id in claimed:continue
  # Only source size and official membership determine inclusion, no DRNAS timing.
  try:
   raw,_=source.request_url("https://benchmark-database.de/file/"+id,28*1024*1024,seconds=55)
   plain,_=source.decode(raw)
   if len(plain)>12*1024*1024:raise ValueError("R28 source file upper bound")
   nv,nc=source.parse_dimacs_metadata(plain)
   if nv>3000 or nc>150000 or min(nv,nc)<1:raise ValueError("R28 source parser dimensions")
   chosen.append(dict(id=id,cohort="random_official_2026_not_claimed_never_seen",reps=2,known=False))
   p=ROOT/"frozen"/(id+".cnf");p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(plain)
   chosen[-1].update(sha256=sha(plain),download_sha256=sha(raw),variables=nv,clauses=nc,bytes=len(plain))
   n+=1;claimed.add(id)
   print("R115_WORLD_FROZEN_RANDOM",n,id,flush=True)
  except Exception as e:
   skips[type(e).__name__]+=1
  if sum(skips.values())>=500:break
 need(n>=8,"too few random official source formulas: "+str(n))
 for c in chosen[:len(KNOWN)]:
  id=c["id"]
  raw,_=source.request_url("https://benchmark-database.de/file/"+id,28*1024*1024,seconds=55)
  plain,_=source.decode(raw)
  nv,nc=source.parse_dimacs_metadata(plain)
  if id==KNOWN[0][0]:need((nv,nc)==(250,1000),"R115 known original dimensions")
  need(len(plain)<=12*1024*1024 and nv<=3000 and nc<=150000,"R28 known source dimensional bound")
  p=ROOT/"frozen"/(id+".cnf");p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(plain)
  c.update(sha256=sha(plain),download_sha256=sha(raw),variables=nv,clauses=nc,bytes=len(plain))
 for c in chosen:
  c["official"]=scores[c["id"]]
  need(len(c["sha256"])==64,"formula SHA")
 need(len({c["sha256"] for c in chosen})==len(chosen),"formula content duplicates")
 write(ROOT/"frozen"/"manifest.json",dict(protocol=PROTO,official_score_csv_url=CSV_URL,
   official_csv_sha256=digest,official_rows=score_rows,source_scheme="GBD official instanceid",
   selection="3 known controls + seeded random 2026 IDs; source-size and R28 parser limits only; no solver timing filters",
   prospective_caveat="Random 2026 cases may be in earlier DRNAS experiments, no global novelty guaranteed",
   formula_count=len(chosen),shards=SHARDS,timeout_s=CAP,solvers=MODES,method_source="unchanged R28 exact GF2",
   cases=chosen,skipped_by_reason=dict(skips)))
 print("R115_WORLD_FREEZE_PASS",json.dumps({"cases":len(chosen),"random":n,"official_scores_sha":digest}),flush=True)

def parse_clauses(p):
 clauses=[];n=0;header=False;acc=[]
 for line in p.read_text().splitlines():
  if not line or line.startswith(("c","%")):continue
  if line.startswith("p cnf "):
   cols=line.split();n=int(cols[2]);header=True;continue
  for t in line.split():
   a=int(t)
   if a:acc.append(a)
   else:clauses.append(acc);acc=[]
 need(header and not acc,"original DIMACS parse")
 return n,clauses

def sat_model_check(cnf,output):
 n,clauses=parse_clauses(cnf)
 lits=[]
 for l in output.decode(errors="replace").splitlines():
  if l.startswith("v "):
   for a in l[2:].split():
    x=int(a)
    if x:lits.append(x)
 truth={abs(x):(x>0) for x in lits}
 need(len(truth)==n,"SAT witness missing/incomplete "+cnf.name)
 need(all(any(truth.get(abs(x))==(x>0) for x in c) for c in clauses),
      "SAT witness invalid on original CNF "+cnf.name)
 return True

def xor_unsat_check(cnf,output):
 n,clauses=parse_clauses(cnf)
 groups=defaultdict(set)
 for cl in clauses:
  if not 2<=len(cl)<=6 or len({abs(x) for x in cl})!=len(cl):continue
  literals=sorted(cl,key=lambda x:abs(x));vs=tuple(abs(x) for x in literals)
  mask=sum((1<<i) for i,x in enumerate(literals) if x<0)
  groups[vs].add(mask)
 equations={}
 text=output.decode(errors="replace")
 for line in text.splitlines():
  m=re.fullmatch(r"c R28_EQ id=(\d+) rhs=([01]) vars=([\d,]+)",line)
  if not m:continue
  eid=int(m[1]);rhs=int(m[2]);vs=tuple(map(int,m[3].split(",")))
  need(2<=len(vs)<=6 and tuple(sorted(vs))==vs and eid not in equations,
       "invalid EQ provenance")
  required={mask for mask in range(1<<len(vs)) if mask.bit_count()%2==(1-rhs)}
  need(required<=groups[vs],"R28 parity equation NOT source-implied")
  equations[eid]=(rhs,vs)
 match=re.search(r"^c R28_UNSAT_CERT ids=([\d,]*)$",text,re.M)
 need(match is not None and "c R28_ROUTE certified_xor_contradiction" in text,"missing XOR UNSAT trace")
 ids=[int(x) for x in match[1].split(",") if x]
 need(bool(ids) and len(set(ids))==len(ids) and all(x in equations for x in ids),"invalid contradiction IDs")
 rhs=0;bits=set()
 for ix in ids:
  er,vs=equations[ix];rhs^=er
  for v in vs:
   if v in bits:bits.remove(v)
   else:bits.add(v)
 need(not bits and rhs==1,"independent GF2 contradiction failed")
 return True

def trial(c,mode,rep):
 cnf=ROOT/"frozen"/(c["id"]+".cnf")
 need(file_sha(cnf)==c["sha256"],"CNF SHA mismatch")
 cmd=[str(R28),str(cnf),str(KISSAT)] if mode=="r28" else \
     [str(KISSAT),str(cnf)] if mode=="kissat" else [str(CADICAL),str(cnf)]
 start=time.perf_counter();status="TIMEOUT";route="timeout";proof="timeout";elapsed=CAP
 try:
  run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  elapsed=time.perf_counter()-start
  need(run.returncode in (10,20),f"{mode} exit={run.returncode} stderr="+run.stderr[-250:].decode(errors="replace"))
  status="SAT" if run.returncode==10 else "UNSAT"
  route=("gf2_sat" if b"R28_ROUTE certified_pure_xor_sat" in run.stdout else
         "gf2_unsat" if b"R28_ROUTE certified_xor_contradiction" in run.stdout else "fallback_or_direct")
  if mode=="r28" and route=="gf2_unsat":
   xor_unsat_check(cnf,run.stdout);proof="independently_replayed_XOR_subset_UNSAT"
  elif status=="SAT":
   sat_model_check(cnf,run.stdout);proof="source_CNF_SAT_model_checked"
  elif status=="UNSAT":
   proof="UNSAT_no_independent_search_certificate"
  need(c["official"]["best_verified"]["status"].startswith(status.lower()),
       "solver answer contradicts verified official result")
 except subprocess.TimeoutExpired:
  status="TIMEOUT";elapsed=CAP;route="timeout";proof="timeout"
 elapsed=min(CAP,elapsed)
 return dict(case_id=c["id"],cohort=c["cohort"],formula_sha256=c["sha256"],
   mode=mode,rep=rep,status=status,seconds=round(elapsed,6),par2=10. if status=="TIMEOUT" else round(elapsed,6),
   route=route,proof=proof)

def runshard(i):
 need(0<=i<SHARDS,"shard")
 m=read(ROOT/"frozen"/"manifest.json");cases=m["cases"]
 if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 rows=[]
 for ix,c in enumerate(cases):
  if ix%SHARDS!=i:continue
  for rep in range(c["reps"]):
   modes=list(MODES);random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
   seen=set()
   for mode in modes:
    r=trial(c,mode,rep);rows.append(r)
    if r["status"]!="TIMEOUT":
     seen.add(r["status"]);need(len(seen)<=1,"SAT/UNSAT disagreement")
    print("R115_WORLD_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    write(ROOT/f"shard-{i}.json",rows)
 need(len(rows)==sum(c["reps"]*len(MODES) for j,c in enumerate(cases) if j%SHARDS==i),"shard incomplete")
 print("R115_WORLD_SHARD_PASS",i,len(rows),flush=True)

def aggregate():
 m=read(ROOT/"frozen"/"manifest.json");cases=m["cases"]
 ids={c["id"]:c for c in cases}
 rows=[];seen=set();pins=set();commits=set();cpus=set()
 for i in range(SHARDS):
  path=ROOT/f"shard-{i}.json";need(path.is_file(),"missing shard "+str(i))
  block=read(path)
  need(len(block)==sum(c["reps"]*len(MODES) for j,c in enumerate(cases) if j%SHARDS==i),"shard incomplete "+str(i))
  pin=read(ROOT/f"pin-{i}.json");pins.add(json.dumps(pin["binaries"],sort_keys=True));commits.add(pin["commit"]);cpus.add(pin["cpu"])
  for r in block:
   c=ids.get(r["case_id"])
   need(c and r["formula_sha256"]==c["sha256"],"source identity")
   key=(r["case_id"],r["rep"],r["mode"])
   need(key not in seen,"duplicate attempt");seen.add(key)
   need(r["rep"] in range(c["reps"]) and r["mode"] in MODES,"invalid mode/repetition")
   need(abs(r["par2"]-(10 if r["status"]=="TIMEOUT" else r["seconds"]))<.000001,"PAR2 invalid")
   if r["status"]=="SAT":need(r["proof"]=="source_CNF_SAT_model_checked","SAT model not checked")
   if r["status"]=="UNSAT" and r["route"]=="gf2_unsat":
    need(r["proof"]=="independently_replayed_XOR_subset_UNSAT","XOR proof not checked")
  rows+=block
 need(len(rows)==sum(c["reps"]*len(MODES) for c in cases),"attempts")
 need(len(pins)==len(commits)==1,"mismatched binaries or commits")
 by=defaultdict(lambda:defaultdict(list))
 for r in rows:by[r["case_id"]][r["mode"]].append(r)
 out=[]
 for c in cases:
  grouped=by[c["id"]]
  need(all(len(grouped[x])==c["reps"] for x in MODES),"not paired")
  if len({r["status"] for mode in MODES for r in grouped[mode] if r["status"]!="TIMEOUT"})>1:
   raise RuntimeError("CONTRADICTORY_SOLVER_STATUS")
  x=dict(id=c["id"],cohort=c["cohort"],sha256=c["sha256"],reps=c["reps"],
      official_best=c["official"]["best_verified"],official_main=c["official"]["best_main"],
      official_verified_solvers=c["official"]["verified_solvers"])
  for mode in MODES:
   g=grouped[mode];x[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in g),
        avg_par2=round(sum(r["par2"] for r in g)/len(g),6),
        avg_solved_seconds=round(sum(r["seconds"] for r in g)/len(g),6) if all(r["status"]!="TIMEOUT" for r in g) else None,
        routes=dict(Counter(r["route"] for r in g)),proofs=dict(Counter(r["proof"] for r in g)))
  if x["r28"]["avg_solved_seconds"] is not None:
   x["official_fastest_cross_machine_ratio"]=round(c["official"]["best_verified"]["seconds"]/x["r28"]["avg_solved_seconds"],3)
   x["official_main_cross_machine_ratio"]=round(c["official"]["best_main"]["seconds"]/x["r28"]["avg_solved_seconds"],3) if c["official"]["best_main"] else None
  out.append(x)
 report=dict(protocol=PROTO,official_scores_sha256=m["official_csv_sha256"],
     run_commits=sorted(commits),binary_pins=json.loads(next(iter(pins))),cpu_models=sorted(cpus),
     official_world_times_are_different_hardware=True,official_runtime_precision_may_be_centiseconds=True,
     no_official_world_record_claim=True,claims="Only same-host R28 vs Kissat/CaDiCaL are directly paired; published VBS is cross-host contextual estimate",
     historical_controls=3,new_random_official_cases=len(cases)-3,
     formulas=len(cases),attempts=len(rows),by_formula=out,
     R28_internal_xor_unsat_independently_replayed=True,
     fallback_unsat_without_LRAT_is_unverified=True,original_R28_code_unchanged=True)
 write(ROOT/"results.json",report)
 with (ROOT/"comparison.csv").open("w",newline="") as f:
  w=csv.writer(f);w.writerow(("id","cohort","official_fastest_solver","official_fastest_seconds",
     "official_main_solver","official_main_seconds","r28_avg_solved_s","r28_avg_par2",
     "kissat_avg_par2","cadical_avg_par2","cross_host_ratio_approx"))
  for x in out:
   w.writerow((x["id"],x["cohort"],x["official_best"]["solver"],x["official_best"]["seconds"],
       (x["official_main"] or {}).get("solver"),(x["official_main"] or {}).get("seconds"),
       x["r28"]["avg_solved_seconds"],x["r28"]["avg_par2"],x["kissat"]["avg_par2"],
       x["cadical"]["avg_par2"],x.get("official_fastest_cross_machine_ratio")))
 print("R115_WORLD_FINAL",json.dumps(report,sort_keys=True),flush=True)
 
if __name__=="__main__":
 a=argparse.ArgumentParser();a.add_argument("action",choices=("freeze","shard","aggregate"));a.add_argument("--shard",type=int,default=0)
 args=a.parse_args()
 {"freeze":freeze,"shard":lambda:runshard(args.shard),"aggregate":aggregate}[args.action]()
