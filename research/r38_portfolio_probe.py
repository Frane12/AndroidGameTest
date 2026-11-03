#!/usr/bin/env python3
"""R38 selected real-official CNF causal probe + 4-core concurrent portfolio.

RETROSPECTIVE cases chosen from R37: NOT an independent holdout.
Only FIVE verified 2026 CNFs, ONE seed, fixed 8s cap, 12 isolated
single-core policy probes and one separate 4-core portfolio per formula.
Never re-runs original 120 R37 trials. Portfolio is NOT a 1-core speedup.
"""
import argparse,hashlib,json,os,random,resource,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"research/drnas-sat-v7-8"))
from official_v94_select import download_and_features
CASES=(
 "ee44c3f464238366729bf2cb16eb412a", # fast no-hints
 "12cd0c3196589ac8105653cbfe613fc6", # fast guided
 "5de866bc7ff4dfde3cd682b5aca75894", # fast sparse
 "0c9da400944b002f90fd385d4fdab385", # nearly tied
 "9ef9243ff051b32795890fccd6c3f6b2", # all timeouts
)
MODES=(
 "ca_plain","orig_v76","orig_v76_plain","v92_sparse","v94_cautious",
 "v91_always_late","v91_never_late",
 "v90_quality_guided","v90_quality_no_hints",
 "v89_rate_late_hints","v89_rate_no_hints","kissat_pinned",
)
PORTFOLIO=("kissat_pinned","orig_v76","orig_v76_plain","v92_sparse")
CAP=8.0
FIELDS=("v90_learned_256","v90_lbd2_256","v90_lbd4_256",
 "v90_props_256","v90_conflicts_256","v90_jumps_256","v90_jumpdepth_256",
 "v90_backtracks_256","cpu_256_ns","active_256","redundant_256",
 "v92_choice","v92_broad","v92_strong","v92_clause2","v92_clause3",
 "v92_clause4","v92_maxwidth","v92_static_us","v91_phase_applied",
 "gate_reason","hints","extended","stage1","stage2","total_us",
 "probe_us","extension_us","resume_us","learned_delta","cpu_total_ns")
def command(mode,cnf,seed,exe,kissat):
 if mode=="kissat_pinned":return [str(kissat),str(cnf)]
 return [str(exe),mode,str(cnf),str(seed)]
def decoded(mode,out,code,expected):
 if mode=="kissat_pinned":
  if code not in (10,20):return None,"kissat exit status "+str(code)
  status="SAT" if code==10 else "UNSAT"
  lines=[x.strip() for x in out.splitlines() if x.startswith("s ")]
  if not any(("UNSATISFIABLE" if status=="UNSAT" else "SATISFIABLE") in x for x in lines):
   return None,"kissat missing result marker"
  if status!=expected:return None,"Kissat official label contradiction"
  return dict(status=status,stats={}),""
 if code!=0:return None,"probe exit status "+str(code)
 lines=[x for x in out.splitlines() if x.startswith("DRNAS_CAUSAL\t")]
 if len(lines)!=1:return None,"not exactly one DRNAS_CAUSAL line"
 kv=dict(part.split("=",1) for part in lines[0].split("\t")[1:] if "=" in part)
 if kv.get("mode")!=mode:return None,"mode mismatch"
 if kv.get("answer")!=expected:return None,"official label contradiction"
 return dict(status=expected,stats={k:kv.get(k) for k in FIELDS}),""
def affinity(core):
 def setcore():os.sched_setaffinity(0,{core})
 return setcore
def single(mode,cnf,seed,exe,kissat,expected,core):
 start=time.monotonic()
 cmd=command(mode,cnf,seed,exe,kissat)
 ru0=resource.getrusage(resource.RUSAGE_CHILDREN)
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP,
                   preexec_fn=affinity(core),check=False)
  elapsed=time.monotonic()-start
  output,error=decoded(mode,p.stdout,p.returncode,expected)
 except subprocess.TimeoutExpired:
  elapsed=CAP
  output,error=None,""
 except Exception as ex:
  elapsed=time.monotonic()-start
  output,error=None,str(ex)
 ru1=resource.getrusage(resource.RUSAGE_CHILDREN)
 cpu=max(0,(ru1.ru_utime+ru1.ru_stime)-(ru0.ru_utime+ru0.ru_stime))
 if output is not None:status=output["status"]
 elif not error:status="TIMEOUT"
 else:status="ERROR"
 return dict(mode=mode,status=status,wall_s=round(elapsed,6),
  cpu_s=round(cpu,6),stats=output["stats"] if output else {},
  error=error)
def portfolio(cnf,seed,exe,kissat,expected,cores):
 if len(cores)<4:
  return dict(status="SKIPPED_INSUFFICIENT_CORES",available_cores=len(cores),
              lanes=list(PORTFOLIO),fair_comparison=False)
 children=[];done=[];seen=set()
 before=resource.getrusage(resource.RUSAGE_CHILDREN)
 start=time.monotonic();winner=None
 try:
  for mode,core in zip(PORTFOLIO,cores[:4]):
   p=subprocess.Popen(command(mode,cnf,seed,exe,kissat),
       stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
       start_new_session=True,preexec_fn=affinity(core))
   children.append((mode,p,core))
  while time.monotonic()-start<CAP and winner is None:
   for mode,p,core in children:
    if p.pid in seen or p.poll() is None:continue
    out,err=p.communicate();seen.add(p.pid)
    obj,problem=decoded(mode,out,p.returncode,expected)
    rec=dict(mode=mode,status=obj["status"] if obj else "ERROR",
             note=problem,core=core,wall_s=round(time.monotonic()-start,6))
    done.append(rec)
    if obj:winner=rec;break
   if winner is None:time.sleep(0.01)
 finally:
  for mode,p,core in children:
   if p.poll() is None:
    try:os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError:pass
   try:p.communicate(timeout=4)
   except subprocess.TimeoutExpired:
    p.kill();p.communicate()
 wall=min(CAP,time.monotonic()-start)
 after=resource.getrusage(resource.RUSAGE_CHILDREN)
 cpu=max(0,(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime))
 return dict(status="SOLVED" if winner else "TIMEOUT_OR_ERROR",
  winner=winner["mode"] if winner else None,wall_s=round(wall,6),
  cpu_s_total=round(cpu,6),available_cores=len(cores),
  actual_cores=cores[:4],lanes=list(PORTFOLIO),completed=done,
  note="Four CPUs vs single-core; cannot interpret as like-for-like solver speedup")
def main():
 a=argparse.ArgumentParser()
 a.add_argument("--manifest",required=True)
 a.add_argument("--index",type=int,required=True)
 a.add_argument("--exe",required=True)
 a.add_argument("--kissat",required=True)
 a.add_argument("--out",required=True)
 x=a.parse_args()
 assert 0<=x.index<len(CASES)
 mf=Path(x.manifest);manifest=json.loads(mf.read_text())
 assert len(manifest["cases"])==12
 rows={i["id"]:i for i in manifest["cases"]}
 caseid=CASES[x.index];assert caseid in rows,("missing precommitted ID",caseid)
 item=rows[caseid];out=Path(x.out);out.mkdir(parents=True,exist_ok=True)
 cnf=out/(caseid+".cnf")
 try:
  check=download_and_features(caseid,cnf)
  assert check["sha256"]==item["sha256"],"CNF SHA drift"
  assert check["features"]==item["features"],"CNF features drift"
  cores=sorted(os.sched_getaffinity(0))
  seed=(830031+int(item["sha256"][:8],16))%2**32
  exe=Path(x.exe).resolve();kissat=Path(x.kissat).resolve()
  assert exe.is_file() and kissat.is_file()
  plan=list(MODES);random.Random(380031+x.index).shuffle(plan)
  records=[]
  for mode in plan:
   record=single(mode,cnf,seed,exe,kissat,item["official_label"],cores[0])
   records.append(record)
   print("R38_NATIVE",caseid[:8],mode,record["status"],
         record["wall_s"],"CPU",record["cpu_s"],flush=True)
   if record["status"]=="ERROR":raise RuntimeError(str(record))
  racing=portfolio(cnf,seed,exe,kissat,item["official_label"],cores)
  print("R38_PORTFOLIO",caseid[:8],json.dumps(racing,sort_keys=True),flush=True)
  by={r["mode"]:r for r in records}
  # True v9.1 common 256-conflict prefix: the probe must agree on counters.
  early_keys=("v90_learned_256","v90_lbd2_256","v90_props_256",
              "v90_conflicts_256","v90_backtracks_256")
  pair=(by["v91_always_late"],by["v91_never_late"])
  if all(z["status"] not in ("TIMEOUT","ERROR") for z in pair):
   parity=all(pair[0]["stats"].get(k)==pair[1]["stats"].get(k) for k in early_keys)
   # mismatch is a diagnostic limitation, not a priori proof of a bug.
  else:parity=None
  report=dict(case_id=caseid,label=item["official_label"],sha256=item["sha256"],
   features=item["features"],declared_vars=check["variables"],
   declared_clauses=check["clauses"],manifest_sha256=hashlib.sha256(mf.read_bytes()).hexdigest(),
   run_seed=seed,limit_s=CAP,selected_retrospectively=True,
   runner=os.environ.get("RUNNER_NAME"),cores_available=cores,
   pinned_probe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
   pinned_kissat_sha256=hashlib.sha256(kissat.read_bytes()).hexdigest(),
   single_core_modes=records,portfolio=racing,v91_prefix_equal_if_completed=parity)
  (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
  (out/"case-meta.json").write_text(json.dumps({k:v for k,v in report.items() if k not in ("single_core_modes","portfolio")},indent=2))
  print("R38_CASE_PASS",caseid,len(records),"prefix_equal",parity,flush=True)
 finally:cnf.unlink(missing_ok=True)
if __name__=="__main__":main()
