#!/usr/bin/env python3
"""ATLAS21 source-frozen pilot: 4 original SAT Competition 2024 CNFs, 6 arms x 2 reps.
No UNSAT certification without independent proof. First-stage pilot, not 100-SHA cohort.
"""
import argparse,hashlib,json,pathlib,resource,subprocess,time,os
from remotezip import RemoteZip
import gzip,lzma,bz2
ARCHIVE="https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1"
OUT=pathlib.Path("mre_atlas21");OUT.mkdir(exist_ok=True)
ARMS=("A","C6_KEEP","C7_ADAPT","C7_ADAPT_GAUSS","KISSAT","CMS")
CAP=30.0
def sources():
 with RemoteZip(ARCHIVE,timeout=90) as z:
  files=sorted((i for i in z.infolist() if not i.is_dir() and
   i.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2")) and
   70000<=i.file_size<=2000000),key=lambda i:(i.file_size,i.filename))
  assert len(files)>=4,"official archive lacks four eligible sources"
  picks=[files[(len(files)-1)*j//3] for j in range(4)]
  out=[]
  for i,item in enumerate(picks):
   raw=z.read(item)
   if item.filename.endswith(".xz"):raw=lzma.decompress(raw)
   elif item.filename.endswith(".gz"):raw=gzip.decompress(raw)
   elif item.filename.endswith(".bz2"):raw=bz2.decompress(raw)
   assert len(raw)<30000000 and b"p cnf " in raw
   sha=hashlib.sha256(raw).hexdigest()
   p=OUT/f"original_{i}.cnf";p.write_bytes(raw)
   out.append(dict(id=i,sha256=sha,archive_entry=item.filename,bytes=len(raw),path=str(p)))
  assert len({x["sha256"] for x in out})==4
  (OUT/"manifest.json").write_text(json.dumps(out,indent=2))
  print("ATLAS21_SOURCES "+json.dumps(out),flush=True)
  return out
def model_ok(path,output):
 model={}
 for line in output.splitlines():
  if line.startswith("v ") or line.startswith("v\\t"):
   for token in line[1:].split():
    lit=int(token)
    if lit==0:continue
    if abs(lit) in model and model[abs(lit)]!=(lit>0):return False
    model[abs(lit)]=lit>0
 if not model:return False
 pending=[]
 with open(path,errors="replace") as fp:
  for line in fp:
   if line.startswith(("c","p","%")):continue
   for tok in line.split():
    lit=int(tok)
    if lit:pending.append(lit)
    else:
     if not any(model.get(abs(v))==(v>0) for v in pending):return False
     pending=[]
 return not pending
def run(s,arm,rep):
 path=s["path"]
 assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()==s["sha256"]
 if arm=="KISSAT":cmd=["mre_atlas21/bin/kissat",path]
 elif arm=="CMS":cmd=["cryptominisat5","--threads=1","--verb=0",path]
 else:
  cmd=["mre_atlas21/bin/drnas_atlas21",path,"--mode",arm,"--time",str(CAP),"--seed",str(rep+1)]
  if arm!="A":cmd+=["--policy","1.0,0.85"]
 def limit():
  resource.setrlimit(resource.RLIMIT_CPU,(32,33))
  resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
 t=time.monotonic()
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP,preexec_fn=limit)
  rc,out,err=p.returncode,p.stdout,p.stderr
 except subprocess.TimeoutExpired:rc,out,err=124,"","timeout"
 elapsed=round(time.monotonic()-t,6)
 if rc not in (0,10,20,124,-9,-24,-25,15,-15):
  raise RuntimeError(f"solver crashed {arm} rc={rc} {err[-500:]}")
 sat=rc==10 and model_ok(path,out)
 if rc==10 and not sat:raise RuntimeError("invalid original CNF SAT witness "+arm)
 # No independent LRAT or GF2 core verifier for these original archive sources.
 status="SAT_VERIFIED" if sat else "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN"
 stats={}
 for line in out.splitlines():
  if line.startswith("ATLAS13_TRIAL "):
   stats=dict(chunk.split("=",1) for chunk in line.split()[1:] if "=" in chunk)
 tel={k:int(float(stats.get(k) or 0)) for k in
  ("decisions","conflicts","propagations","watch_visits","atlas15_deleted",
   "atlas16_compactions","atlas16_maxrss_kb","atlas15_minimized")}
 return dict(sha256=s["sha256"],source_id=s["id"],arm=arm,rep=rep,status=status,
  E2E_s=elapsed,PAR2_reported_s=elapsed if rc in (10,20) else 2*CAP,
  PAR2_verified_s=elapsed if sat else 2*CAP,independent_UNSAT=False,telemetry=tel)
def main():
 a=argparse.ArgumentParser();a.add_argument("--smoke",action="store_true");args=a.parse_args()
 ss=sources()
 if args.smoke:ss=ss[:1]
 rows=[]
 for s in ss:
  for rep in range(1 if args.smoke else 2):
   outcomes=set()
   for arm in ARMS:
    r=run(s,arm,rep);rows.append(r);print("ATLAS21_TRIAL "+json.dumps(r),flush=True)
    if r["status"]!="UNKNOWN":outcomes.add(r["status"])
   assert not ("SAT_VERIFIED" in outcomes and "UNSAT_UNVERIFIED" in outcomes),"SAT UNSAT contradiction"
 (OUT/("smoke.json" if args.smoke else "pilot.json")).write_text(json.dumps(dict(sources=ss,rows=rows),indent=2))
 summary={arm:dict(trials=sum(r["arm"]==arm for r in rows),
  SAT_verified=sum(r["arm"]==arm and r["status"]=="SAT_VERIFIED" for r in rows),
  UNSAT_unverified=sum(r["arm"]==arm and r["status"]=="UNSAT_UNVERIFIED" for r in rows),
  PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in rows if r["arm"]==arm),5),
  PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in rows if r["arm"]==arm),5),
  E2E_s=round(sum(r["E2E_s"] for r in rows if r["arm"]==arm),5)) for arm in ARMS}
 print("ATLAS21_FINAL "+json.dumps(dict(smoke=args.smoke,source_count=len(ss),trials=len(rows),summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":main()
