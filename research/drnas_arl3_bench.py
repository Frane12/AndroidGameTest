#!/usr/bin/env python3
"""ARL3 prospective stall diagnostic: 8 source-locked SATLIB CNFs, 5 solvers, one CPU each.
Frozen ARL2 routing rules, source-hash ranks 8/9 never used for gate selection, 3 matched replicates.

Compare frozen original inputs using the identical native solver with and without one bounded probe.
"""
import hashlib,io,json,os,pathlib,re,resource,subprocess,tarfile,time,urllib.request
OUT=pathlib.Path("mre_arl3");OUT.mkdir(exist_ok=True)
SHARD=int(os.environ.get("MICRO_SHARD","0"));assert 0<=SHARD<4
# Prospective source-only selection; no solver-time based choice.
FAMILIES=("uf200-860","uf200-860","uf250-1065","uf250-1065")
COUNTS=((200,860),(200,860),(250,1065),(250,1065))
FAMILY=FAMILIES[SHARD]
VARS,CLAUSES=COUNTS[SHARD]
RANK=10+SHARD%2
URL="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/"+FAMILY+".tar.gz"
CAP=30;REPEATS=2
with urllib.request.urlopen(URL,timeout=90) as rsp:archive=rsp.read(20_000_000)
archive_sha=hashlib.sha256(archive).hexdigest()
with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as tf:
 entries=sorted((x for x in tf.getmembers() if x.isfile() and x.name.lower().endswith(".cnf")),key=lambda x:hashlib.sha256((FAMILY+"|"+pathlib.PurePosixPath(x.name).name).encode()).hexdigest())
 assert entries
 assert len(entries)>RANK
 item=entries[RANK];raw=tf.extractfile(item).read()
header=None;all_clauses=[];current=[];ended=False
for line in raw.decode("ascii").splitlines():
 line=line.strip()
 if not line or line.startswith("c"):continue
 if line.startswith("%"):ended=True;continue
 if ended:
  if line=="0":continue
  raise ValueError("unexpected trailer")
 if line.startswith("p "):
  t=line.split();assert len(t)==4 and t[1]=="cnf" and header is None
  header=(int(t[2]),int(t[3]));continue
 assert header is not None
 for token in line.split():
  lit=int(token)
  if lit:
   assert abs(lit)<=header[0];current.append(lit)
  else:all_clauses.append(current);current=[]
assert header==(VARS,CLAUSES) and not current and len(all_clauses)==CLAUSES
data=(f"p cnf {VARS} {CLAUSES}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in all_clauses)).encode()
sha=hashlib.sha256(data).hexdigest()
src=dict(family=FAMILY,selection_rule="SHA256(family|basename) ascending, rank 10 or 11",rank=RANK,shard=SHARD,entry=item.name,archive_sha256=archive_sha,raw_sha256=hashlib.sha256(raw).hexdigest(),sha256=sha,variables=VARS,clauses=CLAUSES)
(OUT/"source.json").write_text(json.dumps(src,indent=2))
path=OUT/(FAMILY+".cnf");path.write_bytes(data)
print("MICRO_SOURCE "+json.dumps(src,sort_keys=True),flush=True)
def model_ok(stdout):
 assignment={}
 for line in stdout.splitlines():
  if line.startswith("v "):
   for token in line.split()[1:]:
    lit=int(token)
    if lit:assignment[abs(lit)]=lit>0
 if len(assignment)!=VARS:return False
 return all(any(assignment[abs(lit)]==(lit>0) for lit in c) for c in all_clauses)
def run(arm,rep):
 binaries={"drnas":"drnas_arl3","drnas_trace":"drnas_arl3","drnas_a":"drnas_arl2","kissat":"kissat","cadical":"cadical"}
 cmd=[str((OUT/"bin"/binaries[arm]).resolve()),str(path.resolve())]
 if arm.startswith("drnas"):cmd+=["--mode","ARL3" if arm=="drnas_trace" else "ARL2" if arm=="drnas_a" else "A","--time",str(CAP)]
 def limits():
  resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
  resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
 t=time.monotonic()
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+2,preexec_fn=limits)
  rc=p.returncode;stdout=p.stdout;stderr=p.stderr
 except subprocess.TimeoutExpired:rc=124;stdout="";stderr="timeout"
 elapsed=time.monotonic()-t;status={10:"SAT",20:"UNSAT"}.get(rc,"UNKNOWN")
 if status=="SAT" and not model_ok(stdout):raise RuntimeError("SAT model invalid: "+arm)
 if status=="UNSAT":raise RuntimeError("Unexpected UNSAT on SATLIB satisfiable instance: "+arm)
 if status=="UNKNOWN" and rc not in (0,124,-9,-24):raise RuntimeError(f"solver error {arm} {rc} {stderr[-300:]}")
 stats={}
 m=re.search(r"^(?:ARL3_TRIAL|ARL3_TRIAL) (.*)$",stdout,re.M)
 if m:stats["ARL3_TRIAL"]=dict(x.split("=",1) for x in m.group(1).split() if "=" in x)
 if arm=="drnas_trace":
  assert m,"missing ARL1E telemetry"
  d=stats["ARL3_TRIAL"]
  assert d["decision"] in ("commit","sleep","fallback"),d
  assert int(d["accepted"])<=4 and int(d["pairs"])<=4097,d
  assert int(d["final_clauses"])==int(d["original_clauses"])+int(d["accepted"]),d
  if rep==0:
   (OUT/"route_decision.json").write_text(json.dumps(dict(source=src,decision=d),indent=2,sort_keys=True))
   print("ARL3_ROUTE "+json.dumps(dict(family=FAMILY,rank=RANK,**d),sort_keys=True),flush=True)

 return dict(arm=arm,repeat=rep,status=status,E2E_s=round(elapsed,6),PAR2_s=round(elapsed if status!="UNKNOWN" else 2*CAP,6),SAT_original_verified=status=="SAT",UNSAT_independent_LRAT=False,telemetry=stats)
rows=[]
for rep in range(REPEATS):
 for arm in ("drnas","drnas_a","drnas_trace","kissat","cadical"):
  row=run(arm,rep);rows.append(row)
  print("MICRO_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
summary={arm:dict(solved=sum(r["status"]=="SAT" for r in rows if r["arm"]==arm),
 PAR2_s=round(sum(r["PAR2_s"] for r in rows if r["arm"]==arm),6),trials=REPEATS) for arm in ("drnas","drnas_a","drnas_trace","kissat","cadical")}
audit=dict(protocol="ARL3-4-SATLIB-30S-ONECPU-2REPS-PASSIVE",source=src,cap_s=CAP,rows=rows,summary=summary,oneCPU=True)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("MICRO_FINAL "+json.dumps(dict(family=FAMILY,rank=RANK,sha256=sha,summary=summary),sort_keys=True),flush=True)

# Frozen gate, independent original SAT model validation and per-arm PAR2.
