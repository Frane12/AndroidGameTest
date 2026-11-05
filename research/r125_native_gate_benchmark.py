#!/usr/bin/env python3
"""R125 native local gate common-subexpression experiment.

Control: independently validate exact gate clauses, signed arc normalizations,
and each implied output equality by exhaustive truth assignments.

Monitor: measure native C++ scanning overhead on 160 *reused* R123 inputs.
Prospective: download NEW official/miter formulas, excluding R120/R121/R123
CNF SHA and historical pinned IDs, compare a guarded source-preserving
preprocessor + pinned Kissat to identical clean pinned Kissat.
Do not train/tune on prospective timing. Actual SAT witnesses are verified
against unchanged source; UNSAT proofs of solver search are not LRAT verified.
"""
from __future__ import annotations
import argparse,bz2,csv,gzip,hashlib,io,itertools,json,lzma,os,pathlib,random,re,subprocess,time,urllib.request
from collections import Counter,defaultdict

ROOT=pathlib.Path("r125")
ROOT.mkdir(exist_ok=True)
PROTO="R125-NATIVE-GATE-EQUIVALENCE-20261105-V1"
NATIVE=pathlib.Path("r125/r125_native").resolve()
KISSAT=pathlib.Path("built/bin/kissat_4_0_4").resolve()
CAP=15.0
REPS=2
SHARDS=8
MONITOR_SHARDS=8
MAX_INPUT_BYTES=8_000_000
SOURCES={
 "miter":("https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",30),
 "official2026":("https://satcompetition.github.io/2026/downloads/track_main_2026.uri",60),
}
HISTORIC_IDS={
 "42f1311ce504db8cc0cb590a568da20a","75429ff7acb5acb597abe01aa745c2a6",
 "01d6fa8efd18ebfecd06af408958477b","0efcbd10294eb001b16b4d126923372f",
 "0e06895600b5cd0b6fadb87e17bf8145","180e6d8b61fe6bab26126b78591e324e",
 "2b7e863462991fd008f9898eca63ebf4","3b0eeddcabf36da8642c5774ac67680c",
 "4e0de894799790b06e8d6d3efd109ade","4e0de894799790b06e8d6c3efd109ade",
 "5f9d0127b390a4686171311d38f3fbf8","860788f93fb766e83e00a29de84180e7",
 "991aec61a2751602d6d7b3e838035610","aa0eadb6c4935468fd6954e23a550504",
 "ba14be209c2fc064726025f017cef17a","d4a6b1a299c7a8ad6ea9769abcc60507",
 "e85fb114c33f450dc2622c78bc6fa019","fd1e0ce3662b9b25d23eb01c6e53a425",
}
def sha(x):return hashlib.sha256(x).hexdigest()
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()

def get_binary(require_kissat=False):
 assert NATIVE.is_file(),("missing native gate detector",NATIVE)
 if require_kissat:
  assert KISSAT.is_file(),("missing pinned Kissat binary",KISSAT)
def native(source,out="-",proof="-",timeout=6):
 get_binary()
 run=subprocess.run([str(NATIVE),str(source),str(out),str(proof)],
     capture_output=True,text=True,timeout=timeout)
 if run.returncode:
  raise RuntimeError("NATIVE_EXIT "+str(run.returncode)+" "+run.stdout[-300:]+" "+run.stderr[-400:])
 marker=re.findall(r"^R125_SUMMARY (\{.*\})$",run.stdout,re.M)
 if len(marker)!=1:
  raise RuntimeError("missing unique native audit summary "+run.stdout[-500:])
 return json.loads(marker[0])

def norm(op,a,b,z):
 if op=="X":
  na=abs(a);nb=abs(b)
  sign=-1 if ((a<0)^(b<0)^(z<0)) else 1
  return ("X",tuple(sorted((na,nb))),sign*abs(z))
 if op=="O":a,b,z=-a,-b,-z
 return ("A",tuple(sorted((a,b))),z)

def gate_requirements(op,a,b,z):
 def c(*lits):return tuple(sorted(lits))
 if op=="X":return [c(a,b,-z),c(a,-b,z),c(-a,b,z),c(-a,-b,-z)]
 if op=="A":return [c(-a,-b,z),c(a,-z),c(b,-z)]
 if op=="O":return [c(a,b,-z),c(-a,z),c(-b,z)]
 raise ValueError("bad native gate type "+op)

def literal_value(lit,assignment):
 return assignment[abs(lit)]==(lit>0)

def verify_pair_semantics(rec,source_clauses):
 op1,a1,b1,z1,op2,a2,b2,z2,q1,q2=rec
 req1=gate_requirements(op1,a1,b1,z1)
 req2=gate_requirements(op2,a2,b2,z2)
 source={tuple(sorted(c)) for c in source_clauses}
 for clause in req1+req2:
  if clause not in source:raise AssertionError(("GATE_NOT_IN_SOURCE",clause))
 s1=norm(op1,a1,b1,z1)
 s2=norm(op2,a2,b2,z2)
 assert s1[:2]==s2[:2] and s1[2]==q1 and s2[2]==q2,("SIGNATURE_MISMATCH",rec,s1,s2)
 assert abs(q1)!=abs(q2)
 vars_=sorted({abs(v) for c in req1+req2 for v in c})
 assert len(vars_)<=4
 any_model=False
 for bits in itertools.product((False,True),repeat=len(vars_)):
  assignment=dict(zip(vars_,bits))
  gates_satisfied=all(any(literal_value(l,assignment) for l in c) for c in req1+req2)
  if gates_satisfied:
   any_model=True
   assert literal_value(q1,assignment)==literal_value(q2,assignment),("UNSOUND_OUTPUT_EQUIVALENCE",rec,assignment)
 assert any_model,("VACUOUS_GATE_COMPOSITION",rec)
 return [tuple(sorted((-q1,q2))),tuple(sorted((q1,-q2)))]

def parse_dimacs(bytes_):
 # Reuse independent R118 parser for source-clause audit.
 from r118_xor_paired_real import parse_cnf
 return parse_cnf(bytes_)

def verify_augmentation(original,augmented,proof):
 n,clauses=parse_dimacs(original.read_bytes())
 n2,extended=parse_dimacs(augmented.read_bytes())
 assert n==n2 and extended[:len(clauses)]==clauses,("MODIFIED_ORIGINAL_SOURCE_CLAUSES",str(original))
 with open(proof,newline="") as f:
  rows=list(csv.DictReader(f,delimiter="\t"))
 assert rows,("ACTIVATION_WITHOUT_CERTIFICATE",str(proof))
 expected=[]
 for row in rows:
  rec=(row["op1"],int(row["a1"]),int(row["b1"]),int(row["z1"]),
       row["op2"],int(row["a2"]),int(row["b2"]),int(row["z2"]),
       int(row["q1"]),int(row["q2"]))
  expected.extend(verify_pair_semantics(rec,clauses))
 assert [tuple(sorted(c)) for c in extended[len(clauses):]]==expected, "CNF_PROOF_NOT_MATCHING_OUTPUT"
 return dict(derived_pairs=len(rows),derived_clauses=len(expected),
             proof="independent_original_clause_16_row_boolean_implication_check")

def synthetic(path,clauses,n=7):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text("p cnf %d %d\n"%(n,len(clauses))+
                 "".join(" ".join(str(x) for x in clause)+" 0\n" for clause in clauses))

def control():
 get_binary()
 root=ROOT/"controls";root.mkdir(exist_ok=True)
 scenarios=[
  # Same AND function at distinct output variables.
  ("AND_DUP",gate_requirements("A",1,2,3)+gate_requirements("A",1,2,4),True),
  ("XOR_DUP",gate_requirements("X",1,2,3)+gate_requirements("X",1,2,4),True),
  ("OR_DEMORGAN",gate_requirements("O",1,2,3)+gate_requirements("A",-1,-2,4),True),
  ("XOR_SIGNED",gate_requirements("X",-1,2,3)+gate_requirements("X",1,2,-4),True),
  ("AND_NOT_DUP",gate_requirements("A",1,2,3)+gate_requirements("A",-1,2,4),False),
  ("AND_MISSING",gate_requirements("A",1,2,3)+gate_requirements("A",1,2,4)[:-1],False),
 ]
 records=[]
 for key,clauses,positive in scenarios:
  extra=[(5,6,7),(-5,6)]
  cnf=root/(key+".cnf")
  synthetic(cnf,clauses+extra)
  augmented=root/(key+".aug.cnf")
  proof=root/(key+".proof.tsv")
  result=native(cnf,augmented,proof)
  should=result["equivalence_pairs"]>0
  assert should==positive,(key,"incorrect activation",result)
  if positive:
   assert augmented.exists()
   audit=verify_augmentation(cnf,augmented,proof)
  else:
   assert not augmented.exists(),key
   audit=dict(derived_pairs=0,proof="no inference")
  records.append(dict(test=key,activated=should,native=result,proof=audit))
 (root/"control-results.json").write_text(json.dumps(records,indent=2)+"\n")
 print("R125_CONTROL_PASS",json.dumps(records),flush=True)

def prior():
 ledger=ROOT/"prior"
 seen_sha=set();ids=set(HISTORIC_IDS);report={}
 for r,kind,expected in (("r120","selected",150),("r121","selected",150),
                         ("r122","cases",192),("r123","cases",160)):
  path=ledger/r/"manifest.json"
  if not path.is_file():raise RuntimeError("MISSING_PRIOR_MANIFEST "+str(path))
  manifest=json.loads(path.read_text())
  cases=manifest[kind]
  assert len(cases)==expected,(r,len(cases))
  report[r]=sha_file(path)
  for c in cases:
   seen_sha.add(c["sha256"])
   for key in ("gbd","url"):
    if c.get(key):ids.add(c[key].rsplit("/",1)[-1].split("?")[0])
 return seen_sha,ids,report

def fetch(url,maxbytes):
 req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R125-Prospective-Gate-Preprocessor/1.0"})
 with urllib.request.urlopen(req,timeout=60) as f:
  raw=f.read(maxbytes+1)
 if len(raw)>maxbytes:raise ValueError("size cap exceeded")
 return raw
def decode(raw):
 if raw.startswith(b"\xfd7zXZ"):f=lzma.LZMAFile(io.BytesIO(raw))
 elif raw.startswith(b"\x1f\x8b"):f=gzip.GzipFile(fileobj=io.BytesIO(raw))
 elif raw.startswith(b"BZh"):f=bz2.BZ2File(io.BytesIO(raw))
 else:return raw
 with f:data=f.read(MAX_INPUT_BYTES+1)
 if len(data)>MAX_INPUT_BYTES:raise ValueError("decompressed size cap")
 return data
def source_list(index):
 body=fetch(index,4_000_000).decode("utf-8")
 urls=sorted(set(x.strip() for x in body.splitlines() if x.strip().startswith(("https://","http://"))))
 assert urls,("INVALID_EMPTY_GBD_INDEX",index)
 return urls

def freeze():
 used,ids,prior_sha=prior()
 dest=ROOT/"prospective";dest.mkdir(exist_ok=True)
 cases=[];exclude=[];lists={}
 for cohort,(index,target) in SOURCES.items():
  urls=source_list(index)
  lists[cohort]=dict(index=index,sha256=sha("\n".join(urls).encode()),count=len(urls),target=target)
  random.Random(PROTO+cohort).shuffle(urls)
  acquired=0
  for url in urls:
   if acquired>=target:break
   gbd=url.rsplit("/",1)[-1].split("?")[0]
   if gbd in ids:
    exclude.append(dict(cohort=cohort,gbd=gbd,reason="previously used GBD identity"))
    continue
   try:
    raw=fetch(url,MAX_INPUT_BYTES)
    plain=decode(raw)
    if len(plain)>MAX_INPUT_BYTES:raise ValueError("native input size guard")
    digest=sha(plain)
    if digest in used:raise ValueError("previous SHA identity")
    if any(x["sha256"]==digest for x in cases):raise ValueError("duplicate selection")
    head=[x.split() for x in plain.splitlines() if x.startswith(b"p cnf ")]
    if len(head)!=1 or len(head[0])!=4:raise ValueError("invalid DIMACS header")
    variables,clauses=map(int,head[0][2:])
    if variables<=0 or clauses<=0:raise ValueError("invalid dimensions")
    name=f"{cohort}-{acquired:03d}.cnf"
    (dest/name).write_bytes(plain)
    cases.append(dict(id=name,cohort=cohort,url=url,gbd=gbd,
       sha256=digest,download_sha256=sha(raw),bytes=len(plain),
       variables=variables,clauses=clauses))
    acquired+=1
    print("R125_FREEZE_CASE",cohort,acquired,name,gbd,flush=True)
   except Exception as e:
    exclude.append(dict(cohort=cohort,gbd=gbd,reason=(type(e).__name__+": "+str(e))[:160]))
   if len(exclude)>1500:break
 counts=dict(Counter(c["cohort"] for c in cases))
 manifest=dict(protocol=PROTO,source_lists=lists,prior_sha256=prior_sha,
  cases=cases,counts=counts,exclusions=exclude,cap_seconds=CAP,reps=REPS,
  shards=SHARDS,sampling="randomized external URI order, not chosen by solver timing",
  limitation="Restricted size-limited GBD sample; identity exclusions cover R120/R121/R122/R123 plus R118/R32p pins, not every historical DRNAS experiment")
 (dest/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
 print("R125_FREEZE_FINAL",json.dumps(dict(counts=counts,cases=len(cases),exclusions=len(exclude))),flush=True)
 if len(cases)<70 or counts.get("official2026",0)<45 or counts.get("miter",0)<20:
  raise RuntimeError("R125_FREEZE_INSUFFICIENT_NEW_HOLDOUT")

def monitor(shard):
 manifest=json.loads((ROOT/"old-r123/manifest.json").read_text())
 cases=manifest["cases"]
 assert len(cases)==160 and 0<=shard<MONITOR_SHARDS
 results=[]
 for i,c in enumerate(cases):
  if i%MONITOR_SHARDS!=shard:continue
  source=ROOT/"old-r123"/c["id"]
  assert sha_file(source)==c["sha256"]
  t=time.perf_counter()
  x=native(source)
  wall=time.perf_counter()-t
  row=dict(id=c["id"],cohort=c["cohort"],sha256=c["sha256"],native=x,wall_seconds=round(wall,6),
           reused_diagnostic=True,proof_scope="not a SAT performance result")
  results.append(row)
  print("R125_MONITOR",json.dumps(row),flush=True)
 (ROOT/f"monitor-{shard}.json").write_text(json.dumps(results)+"\n")
 print("R125_MONITOR_SHARD_PASS",shard,len(results),flush=True)

def solve_clean(source,cap):
 t=time.perf_counter()
 try:
  p=subprocess.run([str(KISSAT),str(source)],capture_output=True,timeout=cap)
  dt=time.perf_counter()-t
  if p.returncode not in (10,20):
   raise RuntimeError("KISSAT_EXIT "+str(p.returncode)+" "+p.stderr[-200:].decode(errors="replace"))
  return dict(status="SAT" if p.returncode==10 else "UNSAT",
    seconds=round(dt,6),par2=round(dt,6),stdout=p.stdout)
 except subprocess.TimeoutExpired:
  return dict(status="TIMEOUT",seconds=cap,par2=2*cap,stdout=b"")

def solve_selective(source,key):
 t=time.perf_counter()
 augmented=ROOT/"tmp"/(key+".aug.cnf")
 proof=ROOT/"proofs"/(key+".proof.tsv")
 augmented.parent.mkdir(exist_ok=True,parents=True)
 proof.parent.mkdir(exist_ok=True,parents=True)
 if augmented.exists():augmented.unlink()
 if proof.exists():proof.unlink()
 try:
  x=native(source,augmented,proof,timeout=4)
 except subprocess.TimeoutExpired:
  return dict(status="TIMEOUT",seconds=CAP,par2=2*CAP,stdout=b"",
    native={"status":"native_timeout"},proof="timed_out",modified=False)
 pairs=x["equivalence_pairs"]
 # No augmented file on fallback; do NOT count the detector as an active gate.
 if pairs==0:
  assert not augmented.exists()
  target=source
  proof_status="no_activation"
 else:
  assert x["status"]=="ok" and augmented.exists() and proof.exists()
  proof_status=verify_augmentation(source,augmented,proof)
 target=augmented if pairs else source
 spent=time.perf_counter()-t
 if spent>=CAP:
  return dict(status="TIMEOUT",seconds=CAP,par2=2*CAP,stdout=b"",
    native=x,proof=proof_status,modified=bool(pairs))
 remaining=CAP-spent
 try:
  p=subprocess.run([str(KISSAT),str(target)],capture_output=True,timeout=remaining)
  dt=time.perf_counter()-t
  if p.returncode not in (10,20):
   raise RuntimeError("SELECTIVE_KISSAT_EXIT "+str(p.returncode)+" "+
                       p.stderr[-200:].decode(errors="replace"))
  return dict(status="SAT" if p.returncode==10 else "UNSAT",
    seconds=round(dt,6),par2=round(dt,6),stdout=p.stdout,
    native=x,proof=proof_status,modified=bool(pairs))
 except subprocess.TimeoutExpired:
  return dict(status="TIMEOUT",seconds=CAP,par2=2*CAP,stdout=b"",
    native=x,proof=proof_status,modified=bool(pairs))

def witness_verified(source,result):
 if result["status"]!="SAT":return "UNSAT_search_proof_not_independently_checked" if result["status"]=="UNSAT" else "timeout"
 from r118_xor_paired_real import parse_cnf,check_sat_model
 n,clauses=parse_cnf(source.read_bytes())
 check_sat_model(result["stdout"],n,clauses)
 return "original_source_SAT_model_verified"

def benchmark(shard):
 get_binary(require_kissat=True)
 dest=ROOT/"prospective";manifest=json.loads((dest/"manifest.json").read_text())
 cases=manifest["cases"]
 assert manifest["protocol"]==PROTO and 0<=shard<SHARDS
 if hasattr(os,"sched_getaffinity"):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 rows=[]
 for i,c in enumerate(cases):
  if i%SHARDS!=shard:continue
  source=dest/c["id"]
  assert sha_file(source)==c["sha256"]
  for rep in range(REPS):
   for mode in (("selective","kissat") if (i+rep)%2==0 else ("kissat","selective")):
    if mode=="selective":
     x=solve_selective(source,f"shard-{shard}-{c['id']}-{rep}")
    else:
     x=solve_clean(source,CAP)
    proof=witness_verified(source,x)
    native_meta=x.get("native",{})
    row=dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],rep=rep,solver=mode,
      status=x["status"],seconds=x["seconds"],par2=x["par2"],
      proof=proof,proof_equivalences=x.get("proof","baseline"),
      native=native_meta,modified=x.get("modified",False))
    rows.append(row)
    print("R125_TRIAL",json.dumps(row,sort_keys=True),flush=True)
   observed={r["status"] for r in rows[-2:] if r["status"]!="TIMEOUT"}
   assert len(observed)<=1,("R125_SAT_UNSAT_DISAGREEMENT",c["id"],rep,observed)
   (ROOT/f"shard-{shard}.json").write_text(json.dumps(rows)+"\n")
 assert len(rows)==len(cases[shard::SHARDS])*REPS*2
 print("R125_BENCH_SHARD_PASS",shard,len(rows),flush=True)

def aggregate():
 old=json.loads((ROOT/"old-r123/manifest.json").read_text())["cases"]
 fresh=json.loads((ROOT/"prospective/manifest.json").read_text())["cases"]
 assert len(old)==160 and len(fresh)>=70
 mons=[];meas=[];commits=set();bins=set();cpu=set()
 for i in range(SHARDS):
  mon=json.loads((ROOT/f"monitor-{i}.json").read_text())
  runs=json.loads((ROOT/f"shard-{i}.json").read_text())
  assert len(mon)==len(old[i::MONITOR_SHARDS])
  assert len(runs)==len(fresh[i::SHARDS])*REPS*2
  mons+=mon;meas+=runs
  path=ROOT/f"commit-{i}.txt"
  bp=ROOT/f"bins-{i}.txt"
  cp=ROOT/f"cpu-{i}.txt"
  assert path.is_file() and bp.is_file() and cp.is_file()
  commits.add(path.read_text().strip());bins.add(bp.read_text().strip())
  cpu.add(next((x.strip() for x in cp.read_text().splitlines()
             if x.strip().startswith("Model name:")),"unknown"))
 assert len(commits)==1 and len(bins)==1,("mixed source or solver binary SHA",commits,len(bins))
 assert len({m["id"] for m in mons})==160
 assert len(meas)==len(fresh)*REPS*2
 src={c["id"]:c for c in fresh};mm={c["id"]:c for c in old}
 for x in mons:assert x["sha256"]==mm[x["id"]]["sha256"]
 pairs=defaultdict(dict);unique=set()
 for row in meas:
  assert row["sha256"]==src[row["id"]]["sha256"]
  key=(row["id"],row["rep"],row["solver"])
  assert key not in unique;unique.add(key)
  pairs[row["id"],row["rep"]][row["solver"]]=row
  assert row["par2"]==round(CAP*2,6) if row["status"]=="TIMEOUT" else abs(row["par2"]-row["seconds"])<1e-5
  if row["modified"]:
   assert row["solver"]=="selective"
   assert isinstance(row["proof_equivalences"],dict)
   assert row["proof_equivalences"]["derived_pairs"]>0
   assert row["native"]["equivalence_pairs"]==row["proof_equivalences"]["derived_pairs"]
  if row["status"]=="SAT":assert row["proof"]=="original_source_SAT_model_verified"
 for pair in pairs.values():
  assert set(pair)=={"kissat","selective"}
  assert len({v["status"] for v in pair.values()}-{"TIMEOUT"})<=1
 assert len(pairs)==len(fresh)*REPS
 monitor={}
 for cohort in ("miter","official2026","all"):
  group=[x for x in mons if cohort=="all" or x["cohort"]==cohort]
  monitor[cohort]=dict(formulas=len(group),
     recognizable_gate_candidates=sum(x["native"].get("verified_gate_candidates",0) for x in group),
     formulas_with_gate_candidates=sum(x["native"].get("verified_gate_candidates",0)>0 for x in group),
     equivalence_pairs=sum(x["native"].get("equivalence_pairs",0) for x in group),
     formulas_with_equivalence_pairs=sum(x["native"].get("equivalence_pairs",0)>0 for x in group),
     native_wall_seconds=round(sum(x["wall_seconds"] for x in group),6),
     native_internal_ms=round(sum(x["native"].get("native_ms",0) for x in group),3),
     budget_limited=sum(x["native"].get("budget_limited",False) for x in group))
 stats={}
 for cohort in ("miter","official2026","all"):
  group=[x for x in meas if cohort=="all" or x["cohort"]==cohort]
  names=[c["id"] for c in fresh if cohort=="all" or c["cohort"]==cohort]
  bymode={}
  for mode in ("kissat","selective"):
   rs=[x for x in group if x["solver"]==mode]
   bymode[mode]=dict(attempts=len(rs),
     solved=sum(x["status"]!="TIMEOUT" for x in rs),
     timeouts=sum(x["status"]=="TIMEOUT" for x in rs),
     par2_s=round(sum(x["par2"] for x in rs),6),
     activated=sum(x["modified"] for x in rs),
     source_SAT_model_verified=sum(x["proof"]=="original_source_SAT_model_verified" for x in rs),
     independently_proven_derived_equivalences=sum(x["proof_equivalences"].get("derived_pairs",0)
      for x in rs if isinstance(x["proof_equivalences"],dict)))
  formula={x:{mode:sum(r["par2"] for r in group if r["id"]==x and r["solver"]==mode)
                  for mode in ("kissat","selective")} for x in names}
  rng=random.Random(PROTO+cohort)
  gains=[]
  for _ in range(1000):
   sample=[rng.choice(names) for _ in names]
   a=sum(formula[x]["selective"] for x in sample)
   b=sum(formula[x]["kissat"] for x in sample)
   if a:gains.append(100*(b/a-1))
  gains.sort()
  a=bymode["selective"]["par2_s"];b=bymode["kissat"]["par2_s"]
  stats[cohort]=dict(formulas=len(names),solvers=bymode,
    speedup_vs_kissat=round(b/a,6) if a else None,
    gain_percent=round(100*(b/a-1),5) if a else None,
    bootstrap95_gain_percent=[round(gains[int(.025*(len(gains)-1))],4),
      round(gains[int(.975*(len(gains)-1))],4)] if gains else None,
    wins_ge2x=sum(formula[x]["kissat"]>=2*formula[x]["selective"] for x in names),
    regressions_ge2x=sum(formula[x]["selective"]>=2*formula[x]["kissat"] for x in names))
 report=dict(protocol=PROTO,run_source_commits=sorted(commits),
  binary_sha256_file_digest=sha(next(iter(bins)).encode()),cpu_models=sorted(cpu),
  monitor_source="160 R123 previously used external CNFs; NOT independent benchmark",
  prospective_source="NEW frozen GBD 2026 and miter inputs excluding R120/121/122/123 SHA and GBD IDs",
  prospective_formulas=len(fresh),attempts=len(meas),shards=SHARDS,
  experiment_type="conservative native gate detection, equivalence clause augmentation only when independent source proof passes",
  original_formula_unchanged=True,original_kissat_unmodified=True,limit_s=CAP,
  monitor=monitor,prospective=stats,
  unsat_caveat="Extra clauses are implied by source gate blocks, independently exhaustively checked (<=4 variables). No independent UNSAT search proof for Kissat.",
  failure_rule="no activation does NOT imply speedup; overhead included in selective timing; never promote on CI success alone")
 (ROOT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
 print("R125_FINAL",json.dumps(report),flush=True)

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("command",choices=("control","freeze","monitor","benchmark","aggregate"))
 ap.add_argument("--shard",type=int,default=0)
 args=ap.parse_args()
 {"control":control,"freeze":freeze,"monitor":lambda:monitor(args.shard),
  "benchmark":lambda:benchmark(args.shard),"aggregate":aggregate}[args.command]()
