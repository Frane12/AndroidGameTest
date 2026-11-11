#!/usr/bin/env python3
"""ATLAS-X S3: source-selected new structured SATLIB SHA + planted controls.

Shards 0..3 use new external archived originals (planning, graph-coloring) not selected in S1/S2.
Shards 4..5 are planted structurally redundant Boolean relations.
Shards 6..7 are planted AND/XOR/ITE circuit encodings.
Never select or replace sources using runtime, solver verdict, or gate impact.
"""
from __future__ import annotations
import hashlib, io, json, os, pathlib, random, re, resource
import subprocess, tarfile, time, urllib.request

ROOT=pathlib.Path("mre_atlasx_s3")
ROOT.mkdir(exist_ok=True)
SHARD=int(os.environ.get("ATLASX_S3_SHARD","0"))
assert 0<=SHARD<8
REPS=3
CAP=8
ARMS=("A","ATLAS1","ATLASX","kissat","cadical")
# Original source SHA and fixed source-only ranks, before solver invocation.
ARCHIVES={
 "planning-logistics":dict(url="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/PLANNING/Logistics/logistics.tar.gz",
  archive_sha256="dcd3b7abfcf25ddf264d46b6ed95ec597eefcdcad88659877812a427c1c576af"),
 "flat200-479":dict(url="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/GCP/flat200-479.tar.gz",
  archive_sha256="a27f57132377dc6be4fd11a938c78e6ec245e65fb33fa7a86579ef986c7c242b")
}
FROZEN_CASES=(
 ("planning-logistics",0),("planning-logistics",1),
 ("flat200-479",21),("flat200-479",37),
 ("redundant",0xAD31),("redundant",0xB7D3),
 ("standard_gates",0xC891),("standard_gates",0xDB92),
)
name,selector=FROZEN_CASES[SHARD]

def fail(ok,msg):
 if not ok:raise RuntimeError("ATLASX_S3_FAIL_CLOSED "+msg)
def sha(bs):return hashlib.sha256(bs).hexdigest()
def parse_dimacs(raw):
 n=None;nc=None;clauses=[];partial=[]
 for line in raw.decode("ascii").splitlines():
  s=line.strip()
  if not s or s.startswith("c"):continue
  if s.startswith("%"):break
  if s.startswith("p "):
   tokens=s.split()
   fail(len(tokens)==4 and tokens[1]=="cnf" and n is None,"invalid header")
   n=int(tokens[2]);nc=int(tokens[3]);continue
  fail(n is not None,"clause before header")
  for token in s.split():
   lit=int(token)
   fail(abs(lit)<=n,"literal range")
   if lit:partial.append(lit)
   else:
    fail(len(partial)==len(set(partial)),"duplicate literal in source")
    fail(not any(-l in partial for l in partial),"tautological source clause")
    clauses.append(partial);partial=[]
 fail(n is not None and not partial and len(clauses)==nc,"DIMACS clause count mismatch")
 return n,clauses
def text_dimacs(n,clauses):
 return (f"p cnf {n} {len(clauses)}\n"+
         "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
def get_original(family,rank):
 entry=ARCHIVES[family]
 with urllib.request.urlopen(entry["url"],timeout=90) as resp:
  data=resp.read(14_000_000)
 fail(sha(data)==entry["archive_sha256"],"external archive digest drift")
 with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as tar:
  names=sorted((m for m in tar.getmembers() if m.isfile() and m.name.lower().endswith(".cnf")),
       key=lambda m:sha((family+"|"+pathlib.PurePosixPath(m.name).name).encode()))
  fail(len(names)>rank,"source rank missing")
  item=names[rank]
  original=tar.extractfile(item).read()
 n,cls=parse_dimacs(original)
 return n,cls,dict(cohort="external_structured_original",family=family,rank=rank,
    archive_url=entry["url"],archive_sha256=entry["archive_sha256"],
    archive_entry=item.name,raw_sha256=sha(original),status_source="SATLIB_SAT_family")
def xor3(a,b,c,rhs):
 clauses=[]
 for mask in range(8):
  if mask.bit_count()%2==rhs:continue
  clauses.append([(-v if (mask>>i)&1 else v) for i,v in enumerate((a,b,c))])
 return clauses
def gen_redundant(seed):
 rng=random.Random(seed)
 g=28;n=5*g
 clauses=[];truth={}
 for block in range(g):
  a,b,c,d,e=range(block*5+1,block*5+6)
  av,bv=rng.randrange(2),rng.randrange(2)
  if not(av or bv):av=1
  for v,val in ((a,av),(b,bv),(c,rng.randrange(2)),
                (d,rng.randrange(2)),(e,rng.randrange(2))):
   truth[v]=bool(val)
  # Two 3-variable clauses imply a|b. Two distinct 4-variable
  # clauses are then redundant but do not duplicate any clause.
  clauses += [[a,b,c],[a,b,-c],[a,b,d,e],[a,b,-d,-e]]
 for _ in range(22):
  a,b,c=(5*group+1 for group in rng.sample(range(g),3))
  clauses+=xor3(a,b,c,int(truth[a])^int(truth[b])^int(truth[c]))
 return n,clauses,truth
def gen_gates(seed):
 rng=random.Random(seed)
 n=28
 truth={i:bool(rng.randrange(2)) for i in range(1,n+1)}
 cls=[]
 for step in range(78):
  op=("and","xor","ite")[step%3]
  k=2 if op!="ite" else 3
  x=rng.sample(range(1,n+1),k)
  n+=1
  if op=="and":
   a,b=x;z=n
   cls.extend([[-a,-b,z],[a,-z],[b,-z]])
   truth[z]=truth[a] and truth[b]
  elif op=="xor":
   a,b=x;z=n
   truth[z]=truth[a]!=truth[b]
   cls+=xor3(a,b,z,0)
  else:
   c,a,b=x;z=n
   truth[z]=truth[a] if truth[c] else truth[b]
   cls.extend([[-c,-a,z],[-c,a,-z],[c,-b,z],[c,b,-z]])
 # A small planted observation set creates genuine propagation.
 for v in rng.sample(list(range(29,n+1)),10):
  cls.append([v if truth[v] else -v])
 return n,cls,truth
if SHARD<4:
 n,clauses,src=get_original(name,selector)
 plant=None
else:
 n,clauses,plant=(gen_redundant(selector) if name=="redundant" else gen_gates(selector))
 src=dict(cohort="planted_synthetic_control",family=name,seed=selector,
    source_rule="deterministic predeclared generator with planted witness",
    status_source="plant_verified_against_original")
data=text_dimacs(n,clauses)
source_path=ROOT/f"source_{SHARD}.cnf"
source_path.write_bytes(data)
src.update(shard=SHARD,sha256=sha(data),variables=n,clauses=len(clauses),bytes=len(data))
if plant is not None:
 fail(all(any(plant[abs(l)]==(l>0) for l in c) for c in clauses),
      "synthetic planted witness is invalid")
 src["independent_planted_SAT"]=True
 (ROOT/"planted_witness.sha256").write_text(sha(
   "".join(str(int(plant[i])) for i in range(1,n+1)).encode())+"\n")
(ROOT/"source.json").write_text(json.dumps(src,indent=2,sort_keys=True)+"\n")
print("ATLASX_S3_SOURCE "+json.dumps(src,sort_keys=True),flush=True)
def check_sat(output):
 assignment={}
 for line in output.splitlines():
  if line.startswith("v "):
   for word in line[2:].split():
    l=int(word)
    if l:
     fail(abs(l) not in assignment or assignment[abs(l)]==(l>0),"contradictory SAT model")
     assignment[abs(l)]=l>0
 fail(bool(assignment),"missing SAT witness")
 return all(any(assignment.get(abs(l))==(l>0) for l in c) for c in clauses)

exe=ROOT/"bin/drnas_atlasx"
def run(arm,rep):
 binary=({"kissat":"kissat","cadical":"cadical"}.get(arm,"drnas_atlasx"))
 argv=[str((ROOT/"bin"/binary).resolve()),str(source_path.resolve())]
 if arm in ("A","ATLAS1","ATLASX"):argv+=["--mode",arm,"--time",str(CAP)]
 def limits():
  resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
  resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
 t=time.monotonic()
 try:
  process=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
          text=True,timeout=CAP+3,preexec_fn=limits)
  rc=process.returncode;out=process.stdout;err=process.stderr
 except subprocess.TimeoutExpired:
  rc=124;out="";err="external watchdog timeout"
 elapsed=time.monotonic()-t
 status={10:"SAT",20:"UNSAT"}.get(rc,"UNKNOWN")
 if rc not in (0,10,20,124,-9,-24):
  raise RuntimeError(f"subprocess error {src['family']} {arm} rc={rc} stderr={err[-400:]}")
 if status=="SAT":
  fail(check_sat(out),f"SAT original witness invalid for {arm}")
 if status=="UNSAT":
  # All selected cases are supposed SAT. Without LRAT, fail closed.
  raise RuntimeError(f"unexpected unverified UNSAT from {arm}")
 native=None
 if arm in ("A","ATLAS1","ATLASX"):
  mat=re.search(r"^ATLASX_TRIAL (.+)$",out,re.M)
  if mat:
   native=dict(field.split("=",1) for field in mat.group(1).split() if "=" in field)
  fail(native is not None or status=="UNKNOWN","missing native telemetry")
  if native and status=="SAT":
   fail(native["SAT_original_verified"]=="1","native source model not checked")
  if arm=="ATLASX" and native:
   fail(int(native["final_clauses"])==
      len(clauses)-int(native["removed"])+int(native["added"]),
      "clause accounting mismatch")
 verified=status=="SAT"
 return dict(arm=arm,rep=rep,shard=SHARD,cohort=src["cohort"],family=src["family"],
   source_sha256=src["sha256"],status=status,verified_SAT=verified,
   UNSAT_independent_LRAT=False,
   E2E_s=round(elapsed,6),PAR2_s=round(elapsed if verified else 2*CAP,6),
   native=native)
rows=[]
for rep in range(REPS):
 for arm in ARMS:
  item=run(arm,rep);rows.append(item)
  print("ATLASX_S3_TRIAL "+json.dumps(item,sort_keys=True),flush=True)
summary={}
for arm in ARMS:
 selected=[x for x in rows if x["arm"]==arm]
 summary[arm]=dict(solved=sum(x["verified_SAT"] for x in selected),
   trials=len(selected),PAR2_s=round(sum(x["PAR2_s"] for x in selected),6),
   commits=sum(x["native"] is not None and x["native"]["decision"]=="commit" for x in selected),
   l2_expansions=sum(int(x["native"]["l2_expansions"]) for x in selected if x["native"]),
   L0_sleeps=sum(x["native"] is not None and x["native"]["reason"].startswith("L0_no_") for x in selected),
   subset_modules=sum(int(x["native"].get("subset_modules","0")) for x in selected if x["native"]),
   subset_clauses=sum(int(x["native"].get("subset_module_clauses","0")) for x in selected if x["native"]),
   saved_literals=sum(int(x["native"].get("saved_literals","0")) for x in selected if x["native"]),
   preprocess_s=round(sum(float(x["native"].get("preprocess_s","0")) for x in selected if x["native"]),8))
report=dict(protocol="ATLASX-S3-NEW-SOURCES-4-EXTERNAL-4-PLANTED-5ARMS-3REPS-8S-ONECPU",
 source=src,reps=REPS,oneCPU=True,cap_s=CAP,
 separate_external_from_planted=True,rows=rows,summary=summary)
(ROOT/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print("ATLASX_S3_FINAL "+json.dumps(dict(source=src,summary=summary),sort_keys=True),flush=True)
