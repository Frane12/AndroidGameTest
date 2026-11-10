#!/usr/bin/env python3
"""FACTOR5M sidecar. Four SATLIB sources from previously frozen V7.4 archives.
SATLIB, not official SAT Competition; medium difficulty not guaranteed.
"""
import hashlib,io,json,pathlib,tarfile,urllib.request,subprocess,resource,re,time
OUT=pathlib.Path("mre_factor5m");OUT.mkdir(exist_ok=True)
CAP=40
MANIFEST="research/drnas-sat-v7-4/frozen_real_medium.json"
manifest=json.loads(pathlib.Path(MANIFEST).read_text())
families=("uf250-1065","uuf250-1065","flat200-479","planning-logistics")
sources=[]
for i,family in enumerate(families):
 entry=next(x for x in manifest["archives"] if x["set"]==family)
 with urllib.request.urlopen(entry["url"],timeout=50) as response:raw=response.read(12_000_000)
 if hashlib.sha256(raw).hexdigest()!=entry["archive_sha256"]:raise RuntimeError("SATLIB pinned archive SHA mismatch: "+family)
 with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as tf:
  items=[x for x in tf.getmembers() if x.isfile() and x.name.lower().endswith(".cnf")]
  if not items:raise RuntimeError("no CNFs in "+family)
  items.sort(key=lambda x:hashlib.sha256((family+"|"+pathlib.PurePosixPath(x.name).name).encode()).hexdigest())
  item=items[2 if len(items)>2 else 0] # previously frozen selection rank, not runtime
  cnf=tf.extractfile(item).read()
  if not re.search(rb"(?mi)^\\s*p\\s+cnf\\s+\\d+\\s+\\d+",cnf):raise RuntimeError("bad original CNF "+family+" "+item.name+" prefix="+repr(cnf[:160]))
  path=OUT/f"medium_{i}.cnf";path.write_bytes(cnf)
  sources.append(dict(id=i,family=family,source_archive=entry["url"],archive_sha256=entry["archive_sha256"],entry=item.name,sha256=hashlib.sha256(cnf).hexdigest(),bytes=len(cnf)))
print("FACTOR5M_SOURCES "+json.dumps(sources,sort_keys=True),flush=True)
def check_sat(path,stdout):
 lits=[]
 for line in stdout.splitlines():
  if line.startswith("v ") or line.startswith("v\t"):lits.extend(int(x) for x in line[1:].split() if x!="0")
 a={abs(x):x>0 for x in lits}
 if not a:return False
 clause=[]
 for line in path.read_text(errors="replace").splitlines():
  if line.startswith(("c","p","%")):continue
  for word in line.split():
   lit=int(word)
   if lit:clause.append(lit)
   else:
    if not any(a.get(abs(x))==(x>0) for x in clause):return False
    clause=[]
 return not clause
def trial(path,arm):
 if arm=="drnas_plain":args=["mre_factor5m/bin/drnas_factor4",str(path),"--mode","A","--time","40"]
 elif arm=="drnas_factor4":args=["mre_factor5m/bin/drnas_factor4",str(path),"--mode","C","--time","40"]
 elif arm=="kissat":args=["mre_factor5m/bin/kissat",str(path)]
 else:args=["mre_factor5m/bin/cryptominisat5","--verb","0",str(path)]
 def limit():
  resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
  resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
 start=time.monotonic()
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=CAP+3,preexec_fn=limit)
  code=p.returncode;out=p.stdout;err=p.stderr
 except subprocess.TimeoutExpired as e:
  code=124;out=e.stdout.decode(errors="replace") if isinstance(e.stdout,bytes) else (e.stdout or "");err=""
 elapsed=time.monotonic()-start
 status={10:"SAT",20:"UNSAT"}.get(code,"UNKNOWN")
 if status=="SAT" and not check_sat(path,out):raise RuntimeError("SAT original model invalid: "+arm)
 metrics={}
 m=re.search(r"^FACTOR2_TRIAL (.*)$",out,re.M)
 if m:metrics=dict(t.split("=",1) for t in m.group(1).split() if "=" in t)
 return dict(arm=arm,status=status,E2E_s=round(elapsed,6),PAR2_s=round(elapsed if status!="UNKNOWN" else 80,6),SAT_original_verified=status=="SAT",UNSAT_independent_LRAT=False,returncode=code,metrics=metrics,stderr_tail=err[-180:])
rows=[]
for source in sources:
 for arm in ("drnas_plain","drnas_factor4","kissat","cms"):
  row=dict(source_id=source["id"],sha256=source["sha256"],**trial(OUT/f"medium_{source['id']}.cnf",arm))
  rows.append(row);print("FACTOR5M_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
 outcomes={r["status"] for r in rows if r["source_id"]==source["id"] and r["status"]!="UNKNOWN"}
 if len(outcomes)>1:raise RuntimeError("solver SAT/UNSAT disagreement")
summary={a:dict(solved=sum(r["status"]!="UNKNOWN" for r in rows if r["arm"]==a),
 PAR2_s=round(sum(r["PAR2_s"] for r in rows if r["arm"]==a),6))
 for a in ("drnas_plain","drnas_factor4","kissat","cms")}
audit=dict(protocol="FACTOR5M-SATLIB-V74-PREVIOUSLY-FROZEN-FAMILIES-4x4-40S",
 not_SAT_competition=True,not_reference_medium_runtime_certified=True,oneCPU=True,
 source=sources,summary=summary,rows=rows,UNSAT_independent_LRAT=False)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("FACTOR5M_FINAL "+json.dumps({k:v for k,v in audit.items() if k not in ("rows","source")},sort_keys=True),flush=True)
