#!/usr/bin/env python3
"""FACTOR5: four real SAT Competition 2024 main-track CNFs, 40 CPU-sec each.
Official Zenodo archive accessed by HTTP Range via remotezip, no synthetic
substitution. Fail closed if source unavailable. Source selection is solely
file size and archive order, before any solver results.
"""
import hashlib,json,os,pathlib,re,resource,subprocess,time,zipfile
from remotezip import RemoteZip
OUT=pathlib.Path("mre_factor5");OUT.mkdir(exist_ok=True)
ARCHIVE="https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1"
# Main-track original archive: 4.3GB. Range access only; do not fetch whole zip.
MAX_SOURCE_BYTES=2_000_000
MIN_SOURCE_BYTES=70_000
CAP=40
def select():
 with RemoteZip(ARCHIVE,timeout=60) as z:
  files=[i for i in z.infolist() if not i.is_dir() and
    i.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2")) and
    MIN_SOURCE_BYTES<=i.file_size<=MAX_SOURCE_BYTES]
  files.sort(key=lambda i:(i.file_size,i.filename))
  # Precommitted deterministic spread through candidate size distribution.
  if len(files)<4:raise RuntimeError(f"only {len(files)} suitable official entries")
  picks=[files[(len(files)-1)*j//3] for j in range(4)]
  sources=[]
  for idx,item in enumerate(picks):
   data=z.read(item)
   if item.filename.endswith(".xz"):
    import lzma;data=lzma.decompress(data)
   elif item.filename.endswith(".gz"):
    import gzip;data=gzip.decompress(data)
   elif item.filename.endswith(".bz2"):
    import bz2;data=bz2.decompress(data)
   if len(data)>30_000_000:raise RuntimeError("decompressed source too large")
   header=next((l for l in data.splitlines() if l.startswith(b"p cnf ")),None)
   if not header:raise RuntimeError(f"not a DIMACS CNF: {item.filename}")
   path=OUT/f"official_{idx}.cnf";path.write_bytes(data)
   sources.append(dict(id=idx,archive_entry=item.filename,
    original_archive=ARCHIVE,sha256=hashlib.sha256(data).hexdigest(),
    bytes=len(data),header=header.decode("ascii","replace")))
  return sources
def model_ok(path,stdout):
 # Streaming CNF witness verification on ORIGINAL source, not reduced CNF.
 lits=[]
 for line in stdout.splitlines():
  if line.startswith("v ") or line.startswith("v\t"):
   lits.extend(int(x) for x in line[1:].split() if x!="0")
 assignment={abs(x):x>0 for x in lits}
 if not assignment:return False
 pending=[]
 with path.open("rt",errors="replace") as fp:
  for line in fp:
   if line.startswith(("c","p","%")):continue
   for token in line.split():
    x=int(token)
    if x:
     pending.append(x)
    else:
     if not any(assignment.get(abs(l))==(l>0) for l in pending):
      return False
     pending=[]
 return not pending
def run(arm,path):
 if arm=="drnas_plain":args=["mre_factor5/bin/drnas_factor4",str(path),"--mode","A","--time",str(CAP)]
 elif arm=="drnas_factor4":args=["mre_factor5/bin/drnas_factor4",str(path),"--mode","C","--time",str(CAP)]
 elif arm=="kissat":args=["mre_factor5/bin/kissat",str(path)]
 elif arm=="cms":args=["mre_factor5/bin/cryptominisat5","--verb","0",str(path)]
 else:raise ValueError(arm)
 def limit():
  resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
  resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
 started=time.monotonic()
 try:
  p=subprocess.run(args,text=True,capture_output=True,timeout=CAP+3,preexec_fn=limit)
  stdout=p.stdout;stderr=p.stderr;code=p.returncode
 except subprocess.TimeoutExpired as e:
  stdout=(e.stdout or b"").decode("utf8","replace") if isinstance(e.stdout,bytes) else (e.stdout or "")
  stderr=(e.stderr or b"").decode("utf8","replace") if isinstance(e.stderr,bytes) else (e.stderr or "")
  code=124
 elapsed=time.monotonic()-started
 status="UNKNOWN"
 if code==10:status="SAT"
 if code==20:status="UNSAT"
 verified=None
 if status=="SAT":
  verified=model_ok(path,stdout)
  if not verified:raise RuntimeError(f"unverified SAT {arm} {path}")
 telemetry={}
 if arm.startswith("drnas"):
  m=re.search(r"^FACTOR2_TRIAL (.*)$",stdout,re.M)
  if m:telemetry=dict(t.split("=",1) for t in m.group(1).split() if "=" in t)
 # UNSAT is a solver claim only, not independently certified by this protocol.
 return dict(arm=arm,status=status,E2E_s=round(elapsed,6),
   PAR2_s=round(elapsed if status!="UNKNOWN" else 2*CAP,6),
   SAT_original_witness_verified=verified,UNSAT_independent_LRAT=False,
   returncode=code,telemetry=telemetry,stderr_tail=stderr[-350:])
sources=select()
(OUT/"sources.json").write_text(json.dumps(sources,indent=2))
print("FACTOR5_SOURCES "+json.dumps(sources,sort_keys=True),flush=True)
rows=[]
for source in sources:
 path=OUT/f"official_{source['id']}.cnf"
 for arm in ("drnas_plain","drnas_factor4","kissat","cms"):
  row=dict(source_id=source["id"],sha256=source["sha256"],**run(arm,path))
  rows.append(row)
  print("FACTOR5_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
 for arm in ("drnas_plain","drnas_factor4","kissat","cms"):
  outcomes={r["status"] for r in rows if r["source_id"]==source["id"] and r["arm"]==arm}
  if "SAT" in outcomes and "UNSAT" in outcomes:raise RuntimeError("internal inconsistent outcomes")
 solved={r["status"] for r in rows if r["source_id"]==source["id"] and r["status"]!="UNKNOWN"}
 if len(solved)>1:raise RuntimeError(f"solver disagreement source {source['id']}")
summary={}
for arm in ("drnas_plain","drnas_factor4","kissat","cms"):
 sub=[r for r in rows if r["arm"]==arm]
 summary[arm]=dict(solved=sum(r["status"]!="UNKNOWN" for r in sub),
  PAR2_s=round(sum(r["PAR2_s"] for r in sub),6),
  elapsed_s=round(sum(r["E2E_s"] for r in sub),6))
audit=dict(protocol="FACTOR5-4-OFFICIAL-2024-MAIN-4-ARMS-40S-ONECPU",
 source_selection="archive entry uncompressed size 70k-2MB, sorted by size, 4 quantiles",
 cap_cpu_s=40,PAR2_timeout_penalty_s=80,
 single_logical_cpu=True,repeat_count=1,source=sources,
 UNSAT_independent_LRAT=False,SAT_original_witness_verified=True,
 summary=summary,rows=rows)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("FACTOR5_FINAL "+json.dumps({k:v for k,v in audit.items() if k not in ("rows","source")},sort_keys=True))
