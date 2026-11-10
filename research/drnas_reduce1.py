#!/usr/bin/env python3
"""REDUCE1: offline resolution audit of the 16-20 conflict chain plus a small control.
Compare two original instances without solver-time-based instance selection.
"""
import hashlib,io,json,os,pathlib,re,resource,subprocess,tarfile,time,urllib.request
OUT=pathlib.Path("mre_reduce1");OUT.mkdir(exist_ok=True)
SHARD=int(os.environ.get("MICRO_SHARD","0"));assert SHARD in (0,1)
FAMILY=("uf20-91","uf50-218")[SHARD]
VARS,CLAUSES=((20,91),(50,218))[SHARD]
URL="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/"+FAMILY+".tar.gz"
CAP=10;REPEATS=3
with urllib.request.urlopen(URL,timeout=90) as rsp:archive=rsp.read(20_000_000)
archive_sha=hashlib.sha256(archive).hexdigest()
with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as tf:
 entries=sorted((x for x in tf.getmembers() if x.isfile() and x.name.lower().endswith(".cnf")),key=lambda x:hashlib.sha256((FAMILY+"|"+pathlib.PurePosixPath(x.name).name).encode()).hexdigest())
 assert entries
 item=entries[0];raw=tf.extractfile(item).read()
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
src=dict(family=FAMILY,entry=item.name,archive_sha256=archive_sha,raw_sha256=hashlib.sha256(raw).hexdigest(),sha256=sha,variables=VARS,clauses=CLAUSES)
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
 binaries={"drnas":"drnas","drnas_trace":"drnas_trace","kissat":"kissat","cadical":"cadical"}
 cmd=[str((OUT/"bin"/binaries[arm]).resolve()),str(path.resolve())]
 if arm.startswith("drnas"):cmd+=["--mode","A","--time",str(CAP)]
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
 for marker in ("FACTOR2_TRIAL","DRNAS_PROFILE"):
  m=re.search("^"+marker+r" (.*)$",stdout,re.M)
  if m:stats[marker]=dict(x.split("=",1) for x in m.group(1).split() if "=" in x)
 events=[line for line in stderr.splitlines() if line.startswith("MICRO_EVENT ")]
 if arm=="drnas_trace" and rep==0:
  (OUT/"trace.log").write_text("\n".join(events)+"\n")
  parsed=[]
  for e in events:
   d=dict(x.split("=",1) for x in e.split()[1:] if "=" in x)
   parsed.append(d)
  from collections import Counter
  kinds=Counter(x.get("kind") for x in parsed)
  conflicts=[x for x in parsed if x.get("kind")=="conflict"]
  learns=[x for x in parsed if x.get("kind")=="learn"]
  decisions=[x for x in parsed if x.get("kind")=="decision"]
  assigns=[x for x in parsed if x.get("kind")=="assign"]
  widths=Counter(int(x["width"]) for x in learns)
  jump_lengths=[int(x["from"])-int(x["backjump"]) for x in learns]
  per_conflict=[]
  last_prop=0;last_visit=0;last_dec=0
  for x in conflicts:
   prop=int(x["propagations"]);visit=int(x["visits"]);dec=int(x["decisions"])
   per_conflict.append(dict(number=int(x["number"]),level=int(x["level"]),
      decisions=dec,propagations=prop,watch_visits=visit,
      delta_propagations=prop-last_prop,delta_watch_visits=visit-last_visit,
      delta_decisions=dec-last_dec,trail=int(x["trail"])))
   last_prop=prop;last_visit=visit;last_dec=dec
  report=dict(source=src,total_events=len(parsed),event_counts=dict(kinds),
   conflict_count=len(conflicts),learned_widths=dict(sorted(widths.items())),
   max_backjump=max(jump_lengths,default=0),
   mean_backjump=round(sum(jump_lengths)/len(jump_lengths),3) if jump_lengths else 0,
   conflict_sequence=per_conflict,
   learned_clauses=[dict(width=int(x["width"]),clause=x["clause"],
       from_level=int(x["from"]),backjump=int(x["backjump"])) for x in learns])
  (OUT/"path_analysis.json").write_text(json.dumps(report,indent=2,sort_keys=True))
  print("REDUCE1_ANALYSIS "+json.dumps({k:v for k,v in report.items() if k not in ("learned_clauses",)},sort_keys=True),flush=True)
  for x in per_conflict:print("REDUCE1_CONFLICT "+json.dumps(x,sort_keys=True),flush=True)
  from drnas_atom_reduce1 import from_trace
  reduction=from_trace(OUT/"trace.log",path,OUT/"reduction_audit.json")
  print("REDUCE1_REDUCTION "+json.dumps(dict(family=FAMILY,**reduction["summary"]),sort_keys=True),flush=True)
  for c in reduction["candidates"][:15]:
   print("REDUCE1_CANDIDATE "+json.dumps(c,sort_keys=True),flush=True)

 return dict(arm=arm,repeat=rep,status=status,E2E_s=round(elapsed,6),PAR2_s=round(elapsed if status!="UNKNOWN" else 2*CAP,6),SAT_original_verified=status=="SAT",UNSAT_independent_LRAT=False,trace_events=len(events),telemetry=stats)
rows=[]
for rep in range(REPEATS):
 for arm in ("drnas","drnas_trace","kissat","cadical"):
  row=run(arm,rep);rows.append(row)
  print("MICRO_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
summary={arm:dict(solved=sum(r["status"]=="SAT" for r in rows if r["arm"]==arm),
 PAR2_s=round(sum(r["PAR2_s"] for r in rows if r["arm"]==arm),6),trials=REPEATS) for arm in ("drnas","drnas_trace","kissat","cadical")}
audit=dict(protocol="REDUCE1-TWO-SATLIB-SHA-ONECPU-3REPS",source=src,cap_s=CAP,rows=rows,summary=summary,oneCPU=True)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("MICRO_FINAL "+json.dumps(dict(family=FAMILY,sha256=sha,summary=summary),sort_keys=True),flush=True)
