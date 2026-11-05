#!/usr/bin/env python3
"""R121: prospective external XOR transfer, separate retrospective R117/118/120 033 proof.
Selection uses frozen external URL order, size/hash policy, never solver runtime.
All successful R28/R118 direct UNSAT claims are independently checked against CNF.
Fallback delegates to the identical pinned Kissat: do not count fallback as a new solver win.
"""
import argparse,bz2,csv,gzip,hashlib,io,json,lzma,os,pathlib,random,re,statistics,subprocess,time,urllib.request
from collections import defaultdict,Counter
ROOT=pathlib.Path("r121")
ROOT.mkdir(exist_ok=True)
SEED="R121-20261105-FROZEN-PROSPECTIVE-150-V1"
SOURCES={
 "official2026":("https://satcompetition.github.io/2026/downloads/track_main_2026.uri",105),
 "miter":("https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",45),
}
CAP=15.0
REPS=2
SHARDS=12
MODES=("r28","r118","kissat","cryptominisat")
RAW_MAX=8_000_000
CNF_MAX=40_000_000
# Prior research comparison/discovery IDs must not be called independent unseen tests.
KNOWN_GBD={
 "42f1311ce504db8cc0cb590a568da20a", # R117/118 -> R120 033
 "75429ff7acb5acb597abe01aa745c2a6",
 "01d6fa8efd18ebfecd06af408958477b",
 "0efcbd10294eb001b16b4d126923372f",
 "0e06895600b5cd0b6fadb87e17bf8145",
 "180e6d8b61fe6bab26126b78591e324e",
 "2b7e863462991fd008f9898eca63ebf4",
 "3b0eeddcabf36da8642c5774ac67680c",
 "4e0de894799790b06e8d6c3efd109ade",
 "5f9d0127b390a4686171311d38f3fbf8",
 "75429ff7acb5acb597abe01aa745c2a6",
 "860788f93fb766e83e00a29de84180e7",
 "991aec61a2751602d6d7b3e838035610",
 "aa0eadb6c4935468fd6954e23a550504",
 "ba14be209c2fc064726025f017cef17a",
 "d4a6b1a299c7a8ad6ea9769abcc60507",
 "e85fb114c33f450dc2622c78bc6fa019",
 "fd1e0ce3662b9b25d23eb01c6e53a425",
}
CONTROL033={
 "gbd":"42f1311ce504db8cc0cb590a568da20a",
 "sha256":"9e4c57b9739f39a924d03267f05542831dc87fec9e9e2238f5e4ba11886378f4",
 "prior":"R117 discovery; R118 paired test; R120 033.cnf, NOT unseen",
}
def digest(data):return hashlib.sha256(data).hexdigest()
def download(url,limit=RAW_MAX):
 req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R121-Frozen-Independent-Transfer/1.0"})
 with urllib.request.urlopen(req,timeout=45) as f:
  data=f.read(limit+1)
  if len(data)>limit:raise ValueError("compressed/download size cap")
  return data
def decode(raw):
 if raw.startswith(b"\xfd7zXZ"):
  fh=lzma.LZMAFile(io.BytesIO(raw))
 elif raw.startswith(b"\x1f\x8b"):
  fh=gzip.GzipFile(fileobj=io.BytesIO(raw))
 elif raw.startswith(b"BZh"):
  fh=bz2.BZ2File(io.BytesIO(raw))
 else:
  if len(raw)>CNF_MAX:raise ValueError("original size cap")
  return raw
 with fh:
  plain=fh.read(CNF_MAX+1)
 if len(plain)>CNF_MAX:raise ValueError("decompressed size cap")
 return plain
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()
def get_uri_list(url):
 body=download(url,4_000_000).decode("utf-8")
 urls=[x.strip() for x in body.splitlines() if x.strip().startswith(("https://","http://"))]
 assert urls,("no valid URLs from source",url,body[:180])
 return sorted(set(urls))
def meta(cnf):
 hdr=[line for line in cnf.splitlines() if line.startswith(b"p cnf ")]
 if len(hdr)!=1:raise ValueError("DIMACS p cnf header not unique")
 parts=hdr[0].split()
 if len(parts)!=4:raise ValueError("invalid header")
 n,m=map(int,parts[2:])
 if n<=0 or m<=0:raise ValueError("invalid DIMACS dimensions")
 return n,m
def freeze():
 old=json.loads(pathlib.Path("r121/prior-r120/manifest.json").read_text())
 assert len(old["selected"])==150,"Previous external exclusion manifest not complete"
 oldsha={c["sha256"] for c in old["selected"]}
 oldurl={c["url"].split("/")[-1] for c in old["selected"]}
 selected=[];rejected=[];lists={}
 for cohort,(index,target) in SOURCES.items():
  try:urls=get_uri_list(index)
  except Exception as e:
   rejected.append(dict(cohort=cohort,reason="INDEX_ERROR: "+str(e)[:220]))
   urls=[]
  random.Random(SEED+cohort).shuffle(urls)
  lists[cohort]=dict(index=index,candidates=len(urls),sha256=digest("\n".join(urls).encode()))
  for url in urls:
   if sum(x["cohort"]==cohort for x in selected)>=target:break
   gbd=url.rsplit("/",1)[-1]
   if gbd in KNOWN_GBD or gbd in oldurl:
    rejected.append(dict(cohort=cohort,gbd=gbd,reason="previous research formula excluded"))
    continue
   try:
    raw=download(url);plain=decode(raw);n,m=meta(plain)
    sha=digest(plain)
    if sha in oldsha or sha in {x["sha256"] for x in selected}:raise ValueError("duplicate or prior R120 SHA")
    name=f"{cohort}-{sum(x['cohort']==cohort for x in selected):03d}.cnf"
    (ROOT/name).write_bytes(plain)
    selected.append(dict(name=name,cohort=cohort,url=url,gbd=gbd,sha256=sha,bytes=len(plain),variables=n,clauses=m))
    print("R121_FREEZE_SELECTED",cohort,len(selected),name,gbd,flush=True)
   except Exception as e:
    rejected.append(dict(cohort=cohort,gbd=gbd,reason=(type(e).__name__+": "+str(e))[:160]))
    if len(rejected)>1000:break
 manifest=dict(protocol=SEED,source_lists=lists,selected=selected,exclusions=rejected,
  prior_exclusion="R120 150 CNF hashes + R117/R118/R32p GBD pins; not exhaustive across every historic experiment",
  rules="fixed shuffled GBD source URLs; only SHA/download/size exclusions; no runtime or solver-based selection",
  n_target=150,reps=REPS,cap_seconds=CAP,shards=SHARDS,modes=MODES,
  limitation="Local size-limited prospective subset, not official competition scoring/ranking")
 (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
 print("R121_FREEZE_FINAL",json.dumps({k:v for k,v in Counter(c["cohort"] for c in selected).items()}),
       "total",len(selected),"exclusions",len(rejected),flush=True)
 assert len(selected)>=100,"FAIL_CLOSED: fewer than 100 fresh external CNFs"
 assert sum(x["cohort"]=="official2026" for x in selected)>=80,"FAIL_CLOSED: insufficient official2026 cohort"
def verify_sat(stdout,n,clauses):
 from r118_xor_paired_real import check_sat_model
 check_sat_model(stdout,n,clauses)
def verify_unsat(stdout,clauses,mode):
 from r118_xor_paired_real import check_unsat_cert
 return check_unsat_cert(stdout,clauses,mode.upper())
def run(mode,cnf,bins,cap):
 argv=([str(bins[mode]),str(cnf),str(bins["kissat"])]
       if mode in ("r28","r118") else [str(bins[mode]),str(cnf)])
 t=time.perf_counter()
 try:
  p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap)
  dt=time.perf_counter()-t
  if p.returncode not in (10,20):
   raise RuntimeError("solver "+mode+" exit "+str(p.returncode)+
      " stderr="+p.stderr[-200:].decode(errors="replace"))
  status="SAT" if p.returncode==10 else "UNSAT"
  route=next((x for x in ("certified_xor_contradiction","certified_pure_xor_sat","fallback") if x.encode() in p.stdout),
             "baseline")
  return dict(status=status,seconds=round(dt,6),par2=round(dt,6),route=route,stdout=p.stdout)
 except subprocess.TimeoutExpired:
  return dict(status="TIMEOUT",seconds=cap,par2=2*cap,route="timeout",stdout=b"")
def benchmark(shard):
 assert 0<=shard<SHARDS
 m=json.loads((ROOT/"manifest.json").read_text())
 assert m["protocol"]==SEED and m["modes"]==list(MODES)
 bins={name:pathlib.Path("r121/"+name).resolve() for name in ("r28","r118")}
 bins["kissat"]=pathlib.Path("built/bin/kissat_4_0_4").resolve()
 bins["cryptominisat"]=pathlib.Path(os.environ["CRYPTOMINISAT_BIN"]).resolve()
 assert all(p.is_file() for p in bins.values())
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 rows=[]
 for idx,c in enumerate(m["selected"]):
  if idx%SHARDS!=shard:continue
  cnf=ROOT/c["name"]
  assert sha_file(cnf)==c["sha256"],("mismatched SHA",c["name"])
  for rep in range(REPS):
   order=list(MODES);random.Random(SEED+c["sha256"]+str(rep)).shuffle(order)
   for mode in order:
    x=run(mode,cnf,bins,CAP)
    cert="none"
    if x["status"] in ("SAT","UNSAT"):
     # Check source witness and source XOR proof, never merely trust a solver's UNSAT word.
     if x["status"]=="SAT" or x["route"]=="certified_xor_contradiction":
      from r118_xor_paired_real import parse_cnf
      n,clauses=parse_cnf(cnf.read_bytes())
      if x["status"]=="SAT":
       verify_sat(x["stdout"],n,clauses);cert="SAT_model_verified"
      else:
       verify_unsat(x["stdout"],clauses,mode);cert="source_XOR_UNSAT_proof_verified"
     else:cert="UNSAT_no_independent_proof"
    row=dict(name=c["name"],cohort=c["cohort"],gbd=c["gbd"],sha256=c["sha256"],
             rep=rep,solver=mode,status=x["status"],route=x["route"],proof=cert,
             seconds=x["seconds"],par2=x["par2"])
    rows.append(row)
    print("R121_RESULT",json.dumps(row),flush=True)
  # Incremental checkpoint allows audit even when a shard is interrupted.
  (ROOT/f"shard-{shard}.json").write_text(json.dumps(rows)+"\n")
 (ROOT/f"shard-{shard}.json").write_text(json.dumps(rows)+"\n")
 print("R121_SHARD_PASS",shard,len(rows),flush=True)
def control():
 # Previously studied 2025 problem. Proof is a validation, NOT a blind holdout.
 gbd=CONTROL033["gbd"];raw=download("https://benchmark-database.de/file/"+gbd)
 plain=decode(raw);assert digest(plain)==CONTROL033["sha256"]
 original=ROOT/"discovery033.cnf";original.write_bytes(plain)
 from r118_xor_paired_real import parse_cnf
 n,clauses=parse_cnf(plain)
 bins={mode:pathlib.Path("r121/"+mode).resolve() for mode in ("r28","r118")}
 bins["kissat"]=pathlib.Path("built/bin/kissat_4_0_4").resolve()
 rows=[]
 for mode in ("r28","r118","kissat"):
  for rep in range(3):
   x=run(mode,original,bins,90.0)
   proof="not_independent"
   if x["status"]=="UNSAT" and x["route"]=="certified_xor_contradiction":
    verify_unsat(x["stdout"],clauses,mode);proof="source_XOR_UNSAT_proof_verified"
   elif x["status"]=="SAT":
    verify_sat(x["stdout"],n,clauses);proof="SAT_model_verified"
   row=dict(mode=mode,rep=rep,status=x["status"],route=x["route"],seconds=x["seconds"],par2=x["par2"],proof=proof)
   rows.append(row);print("R121_CONTROL_033",json.dumps(row),flush=True)
 (ROOT/"control-033.json").write_text(json.dumps(dict(**CONTROL033,records=rows),indent=2)+"\n")
 assert any(x["proof"]=="source_XOR_UNSAT_proof_verified" for x in rows), "033 has no independently checked source XOR proof"
def aggregate():
 m=json.loads((ROOT/"manifest.json").read_text());cases=m["selected"]
 rows=[]
 for shard in range(SHARDS):
  path=ROOT/f"shard-{shard}.json";assert path.is_file(),("missing shard",shard)
  these=json.loads(path.read_text())
  assert len(these)==len(cases[shard::SHARDS])*REPS*len(MODES),("incomplete shard",shard)
  rows+=these
 assert len(rows)==len(cases)*REPS*len(MODES)
 ident={(r["name"],r["rep"],r["solver"]) for r in rows}
 assert len(ident)==len(rows),"duplicate measurement"
 by=defaultdict(dict)
 for row in rows:
  by[row["name"],row["rep"]][row["solver"]]=row
 for key,pair in by.items():
  assert set(pair)==set(MODES),("missing paired runs",key)
  answers={x["status"] for x in pair.values()}-{"TIMEOUT"}
  assert len(answers)<=1,("SAT/UNSAT mismatch",key,answers)
  assert all(r["proof"]=="SAT_model_verified" for r in pair.values() if r["status"]=="SAT"),("uncertified SAT",key)
 for case in cases:
  assert sum(r["name"]==case["name"] for r in rows)==REPS*len(MODES)
 out={}
 for cohort in list(SOURCES)+["all"]:
  cr=[x for x in rows if cohort=="all" or x["cohort"]==cohort]
  solver={}
  for mode in MODES:
   r=[x for x in cr if x["solver"]==mode]
   solver[mode]=dict(attempts=len(r),solved=sum(x["status"]!="TIMEOUT" for x in r),
     timeouts=sum(x["status"]=="TIMEOUT" for x in r),
     par2_s=round(sum(x["par2"] for x in r),6),
     direct_xor=sum(x["route"].startswith("certified_") for x in r),
     fallback=sum(x["route"]=="fallback" for x in r),
     source_proofs=sum(x["proof"]=="source_XOR_UNSAT_proof_verified" for x in r))
  p=solver
  raw_speed=p["kissat"]["par2_s"]/p["r28"]["par2_s"] if p["r28"]["par2_s"] else None
  # Cluster bootstrap by formula, never treat repeats as independent samples.
  cases_in=[x["name"] for x in cases if cohort=="all" or x["cohort"]==cohort]
  scores={}
  for name in cases_in:
   rr=[x for x in cr if x["name"]==name]
   scores[name]={mode:sum(x["par2"] for x in rr if x["solver"]==mode) for mode in MODES}
  rng=random.Random(SEED+cohort+"bootstrap")
  boot=[]
  for k in range(1000):
   sample=[rng.choice(cases_in) for _ in cases_in] if cases_in else []
   a=sum(scores[name]["r28"] for name in sample)
   b=sum(scores[name]["kissat"] for name in sample)
   if a:boot.append((b/a-1)*100)
  boot.sort()
  ci=[round(boot[int(.025*(len(boot)-1))],3),round(boot[int(.975*(len(boot)-1))],3)] if boot else None
  out[cohort]=dict(formulas=len(cases_in),solvers=solver,
    r28_vs_kissat_speedup=round(raw_speed,6) if raw_speed else None,
    r28_gain_percent=round((raw_speed-1)*100,4) if raw_speed else None,
    bootstrap95_formula_percent=ci)
 report=dict(protocol=SEED,source="GBD 2026 main and GBD external miter; subset not official ranking",
  formula_total=len(cases),attempts=len(rows),shards=SHARDS,limit_seconds=CAP,
  by_cohort=out,retrospective_033="separate proof control; excluded from prospective sample",
  limitation="Full independent UNSAT proofs unavailable for baseline/fallback answers; no official world record.")
 (ROOT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
 print("R121_FINAL",json.dumps(report),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("action",choices=["freeze","benchmark","control","aggregate"])
 p.add_argument("--shard",type=int,default=0);args=p.parse_args()
 {"freeze":freeze,"benchmark":lambda:benchmark(args.shard),"control":control,"aggregate":aggregate}[args.action]()
