#!/usr/bin/env python3
"""40 SHA-locked SATLIB CNFs, source-selected without solver timing, one CPU.
5 shards x 8 CNFs x native A/native D/Kissat; 40 CPU seconds per trial.
"""
import hashlib,io,json,os,pathlib,re,resource,subprocess,tarfile,time,urllib.request
OUT=pathlib.Path("mre_factor42");OUT.mkdir(exist_ok=True)
CAP=40
SHARD=int(os.environ.get("FACTOR42_SHARD","0"))
assert 0<=SHARD<5
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
   # Original SATLIB often ends in '%' and has metadata "c edge" lines.
   lines=cnf.decode("ascii","replace").splitlines()
   lines=[line for line in lines if not line.lstrip().startswith("%")]
   data=("\n".join(lines)+"\n").encode()
   sources.append(dict(id=len(sources),family=family,archive_entry=item.name,
    archive_sha256=entry["archive_sha256"],sha256=hashlib.sha256(data).hexdigest(),
    raw_sha256=hashlib.sha256(cnf).hexdigest(),bytes=len(data),data=data))
assert len(sources)==40
selection=[{k:v for k,v in x.items() if k!="data"} for x in sources]
(OUT/"sources.json").write_text(json.dumps(selection,indent=2))
print("FACTOR42_SOURCES "+json.dumps(dict(total=40,shard=SHARD,selected=[x for x in selection if x["id"]%5==SHARD]),sort_keys=True),flush=True)
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
 args=[str((OUT/"bin/drnas_factor42").resolve()),str(path.resolve()),"--mode",arm,"--time",str(CAP)] if arm!="kissat" else [str((OUT/"bin/kissat").resolve()),str(path.resolve())]
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
 return dict(arm=arm,status=status,E2E_s=round(elapsed,6),
  PAR2_s=round(elapsed if status!="UNKNOWN" else 2*CAP,6),
  SAT_original_verified=status=="SAT",UNSAT_independent_LRAT=False,
  returncode=rc,telemetry=telemetry)
rows=[]
for source in sources:
 if source["id"]%5!=SHARD:continue
 path=OUT/f"case_{source['id']:02}.cnf";path.write_bytes(source["data"])
 for arm in ("A","D","kissat"):
  row=dict(id=source["id"],family=source["family"],sha256=source["sha256"],**run(path,arm))
  rows.append(row);print("FACTOR42_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
 statuses={r["status"] for r in rows if r["id"]==source["id"] and r["status"]!="UNKNOWN"}
 if len(statuses)>1:raise RuntimeError("SAT UNSAT disagreement on same SHA")
summary={arm:dict(solved=sum(x["status"]!="UNKNOWN" for x in rows if x["arm"]==arm),
 PAR2_s=round(sum(x["PAR2_s"] for x in rows if x["arm"]==arm),6),
 trials=sum(x["arm"]==arm for x in rows)) for arm in ("A","D","kissat")}
audit=dict(protocol="FACTOR42-40-FROZEN-SATLIB-SOURCE-LOCKED-40CPU-ONECPU",
 source_count=40,shard=SHARD,cap_cpu_s=40,oneCPU=True,
 SAT_original_verified=True,UNSAT_independent_LRAT=False,
 normalization="removed SATLIB percent terminators, original and normalized SHA both logged",
 sources=[x for x in selection if x["id"]%5==SHARD],rows=rows,summary=summary)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("FACTOR42_FINAL "+json.dumps(dict(shard=SHARD,summary=summary),sort_keys=True),flush=True)
