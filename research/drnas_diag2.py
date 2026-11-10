#!/usr/bin/env python3
"""DIAG2: compare base and cached blocker with phase-time and watch counters, one frozen CNF, 5 reps.
All five arms use the identical source-normalized SHA. Phase timers and WATCH1 counters are diagnostic builds only.
"""
import hashlib,io,json,os,pathlib,re,resource,subprocess,tarfile,time,urllib.request
OUT=pathlib.Path("mre_diag2");OUT.mkdir(exist_ok=True)
CAP=40
SHARD=0
m=json.loads(pathlib.Path("research/drnas-sat-v7-4/frozen_real_medium.json").read_text())
families=("uf250-1065","uuf250-1065","flat200-479","planning-logistics")
sources=[]
for family in families:
 entry=next(x for x in m["archives"] if x["set"]==family)
 with urllib.request.urlopen(entry["url"],timeout=60) as response:raw=response.read(16_000_000)
 assert hashlib.sha256(raw).hexdigest()==entry["archive_sha256"],"source SHA mismatch"
 with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as tf:
  items=[x for x in tf.getmembers() if x.isfile() and x.name.lower().endswith(".cnf")]
  items.sort(key=lambda x:hashlib.sha256((family+"|"+pathlib.PurePosixPath(x.name).name).encode()).hexdigest())
  # logistics has four entries: include all four and fill 6 from flat200 to total 40
  take=4 if family=="planning-logistics" else (16 if family=="flat200-479" else 10)
  for item in items[:take]:
   cnf=tf.extractfile(item).read()
   # Strict DIMACS canonicalization: preserve every actual clause and validate header.
   # SATLIB may append '%' / '0' terminators and comments after the clause stream.
   text=cnf.decode("ascii","strict")
   header=None;clauses=[];current=[];ended=False
   for line in text.splitlines():
    line=line.strip()
    if not line or line.startswith("c"):continue
    if line.startswith("%"):
     ended=True;continue
    if ended:
     if line=="0":continue
     raise RuntimeError(f"unexpected data after SATLIB terminator: {family} {item.name} {line[:60]}")
    if line.startswith("p "):
     if header is not None:raise RuntimeError("multiple DIMACS headers")
     fields=line.split()
     if len(fields)!=4 or fields[1]!="cnf":raise RuntimeError("bad DIMACS header")
     header=(int(fields[2]),int(fields[3]))
     continue
    if header is None:raise RuntimeError("clause before DIMACS header")
    for word in line.split():
     lit=int(word)
     if lit==0:
      clauses.append(current);current=[]
     else:
      if abs(lit)>header[0]:raise RuntimeError("literal exceeds variable bound")
      current.append(lit)
   if header is None or current:raise RuntimeError("missing header or unterminated clause")
   if len(clauses)!=header[1]:
    # Never silently drop clauses or alter declared clause count: quarantine source.
    raise RuntimeError(f"source header clause mismatch: {family} {item.name} declared={header[1]} actual={len(clauses)}")
   data=(f"p cnf {header[0]} {header[1]}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
   sources.append(dict(id=len(sources),family=family,archive_entry=item.name,
    archive_sha256=entry["archive_sha256"],sha256=hashlib.sha256(data).hexdigest(),
    raw_sha256=hashlib.sha256(cnf).hexdigest(),bytes=len(data),data=data))
assert len(sources)==40
sources=[x for x in sources if x["id"]==0]
assert len(sources)==1 and sources[0]["sha256"]=="484079ec921531ce1110207c7c14760fd7a38b85484e0ddeff54d1d2eb850608"
selection=[{k:v for k,v in x.items() if k!="data"} for x in sources]
(OUT/"sources.json").write_text(json.dumps(selection,indent=2))
print("WATCH1_SOURCES "+json.dumps(dict(total=1,selected=selection),sort_keys=True),flush=True)
def model_ok(path,stdout):
 assignment={}
 for line in stdout.splitlines():
  if line.startswith("v "):
   for word in line[2:].split():
    lit=int(word)
    if lit:assignment[abs(lit)]=lit>0
 if not assignment:return False
 clause=[]
 for line in path.read_text().splitlines():
  if line.startswith(("c","p","%")):continue
  for word in line.split():
   lit=int(word)
   if lit:clause.append(lit)
   else:
    if not any(assignment.get(abs(x))==(x>0) for x in clause):return False
    clause=[]
 return not clause
def run(path,arm):
 args=[str((OUT/({"A":"bin/drnas_baseline","one2":"bin/drnas_one2","A_diag":"bin/drnas_baseline_diag","one2_diag":"bin/drnas_one2_diag"}[arm])).resolve()),str(path.resolve()),"--mode","A","--time",str(CAP)] if arm!="kissat" else [str((OUT/"bin/kissat").resolve()),str(path.resolve())]
 def limits():
  resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
  resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
 start=time.monotonic()
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=CAP+3,preexec_fn=limits)
  rc=p.returncode;stdout=p.stdout;stderr=p.stderr
 except subprocess.TimeoutExpired:
  rc=124;stdout="";stderr="wall timeout"
 elapsed=time.monotonic()-start
 status={10:"SAT",20:"UNSAT"}.get(rc,"UNKNOWN")
 if status=="SAT" and not model_ok(path,stdout):raise RuntimeError(f"invalid SAT witness {path} {arm}")
 if status=="UNKNOWN" and rc not in (0,124,-24,-9):
  raise RuntimeError(f"solver error {arm} {rc} {stderr[-400:]}")
 telemetry={}
 m=re.search(r"^FACTOR2_TRIAL (.*)$",stdout,re.M)
 if m:telemetry=dict(x.split("=",1) for x in m.group(1).split() if "=" in x)
 profile=re.search(r"^DRNAS_PROFILE (.*)$",stdout,re.M)
 if arm.endswith("_diag") and status!="UNKNOWN" and not profile:raise RuntimeError(f"missing profile {arm}")
 if profile:telemetry["profile"]=dict(x.split("=",1) for x in profile.group(1).split() if "=" in x)
 pm=re.search(r"^DRNAS_WATCH1 (.*)$",stdout,re.M)
 if pm:telemetry["watchdiag"]=dict(x.split("=",1) for x in pm.group(1).split() if "=" in x)
 if arm.endswith("_diag") and status!="UNKNOWN":
  assert "watchdiag" in telemetry, f"missing watchdiag telemetry for {path}"
  w=telemetry["watchdiag"]
  assert int(w["visits_original"])+int(w["visits_learned"])==int(w["binary_visits"])+int(w["long_visits"]), "watch accounting mismatch"
  assert int(w["cache_hit"])==0 if arm=="A_diag" else int(w["cache_hit"])>=0, "invalid cache-hit count"
  assert sum(int(w[f"width_bucket_{i}"]) for i in range(7))==int(w["binary_visits"])+int(w["long_visits"]), "watch width accounting mismatch"
 return dict(arm=arm,status=status,E2E_s=round(elapsed,6),
  PAR2_s=round(elapsed if status!="UNKNOWN" else 2*CAP,6),
  SAT_original_verified=status=="SAT",UNSAT_independent_LRAT=False,
  returncode=rc,telemetry=telemetry)
rows=[]
for source in sources:
 path=OUT/f"case_{source['id']:02}.cnf";path.write_bytes(source["data"])
 for repeat in range(5):
  for arm in ("A","one2","A_diag","one2_diag","kissat"):
   row=dict(id=source["id"],repeat=repeat,family=source["family"],sha256=source["sha256"],**run(path,arm))
   rows.append(row);print("DIAG2_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
  statuses={r["status"] for r in rows if r["repeat"]==repeat and r["status"]!="UNKNOWN"}
  if len(statuses)>1:raise RuntimeError("SAT UNSAT disagreement on same SHA")
summary={arm:dict(solved=sum(x["status"]!="UNKNOWN" for x in rows if x["arm"]==arm),
 PAR2_s=round(sum(x["PAR2_s"] for x in rows if x["arm"]==arm),6),
 trials=sum(x["arm"]==arm for x in rows)) for arm in ("A","one2","A_diag","one2_diag","kissat")}
audit=dict(protocol="DIAG2-PROFILE-WATCH-ONE-SHA-FIVE-REPEATS-ONECPU",source_count=1,cap_cpu_s=40,oneCPU=True,
 SAT_original_verified=True,UNSAT_independent_LRAT=False,
 normalization="strict parsed DIMACS; original and normalized SHA logged",
 sources=selection,rows=rows,summary=summary)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("DIAG2_FINAL "+json.dumps(dict(summary=summary),sort_keys=True),flush=True)
