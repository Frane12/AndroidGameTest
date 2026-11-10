#!/usr/bin/env python3
"""Four official SAT Competition 2025 submitted Round-Robin benchmark CNFs.
One CPU, 40 seconds each solver, source SHA audit, original SAT model check.
UNSAT only independently certified when proof verification is available.
"""
import pathlib,hashlib,subprocess,time,json,re,shutil,os
OUT=pathlib.Path("mre_factor4_official");OUT.mkdir(exist_ok=True)
BASE="https://raw.githubusercontent.com/Aeacu2/RR-Benchmarks/main/"
FILES=["RoundRobin_n15_d13.cnf","RoundRobin_n16_d14.cnf",
       "RoundRobin_n17_d15.cnf","RoundRobin_n18_d16.cnf"]
CAP=40
def read_source(name):
 path=OUT/name
 subprocess.run(["curl","-fLsS","--retry","3","--max-time","120",BASE+name,"-o",str(path)],check=True)
 raw=path.read_bytes()
 assert raw.startswith((b"c",b"p",b"\n")),name
 sha=hashlib.sha256(raw).hexdigest()
 n=None;m=None
 for line in raw.decode().splitlines():
  if line.startswith("p cnf "):
   _,_,n,m=line.split()[:4];n=int(n);m=int(m);break
 assert n and m
 return path,sha,n,m
def check_sat(path,stdout):
 lits=[]
 for line in stdout.splitlines():
  if line.startswith("v ") or line.startswith("v\t"):
   lits.extend(int(x) for x in line[1:].split() if x!="0")
 if not lits:return False
 values={abs(x):x>0 for x in lits}
 clause=[]
 for line in path.read_text().splitlines():
  if line.startswith(("c","p")) or not line.strip():continue
  for token in line.split():
   lit=int(token)
   if lit:
    clause.append(lit)
   else:
    if not any(values.get(abs(x))==(x>0) for x in clause):return False
    clause=[]
 return not clause
def run(cmd,path,solver,source):
 start=time.perf_counter()
 try:
  p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    text=True,timeout=CAP,preexec_fn=lambda:os.sched_setaffinity(0,{min(os.sched_getaffinity(0))}))
  elapsed=time.perf_counter()-start
  output=p.stdout
  sat=bool(re.search(r"^s SATISFIABLE\s*$",output,re.M))
  unsat=bool(re.search(r"^s UNSATISFIABLE\s*$",output,re.M))
  status="SAT" if sat else "UNSAT" if unsat else "UNKNOWN"
  if status=="SAT" and not check_sat(path,output):
   raise RuntimeError(f"invalid or absent original SAT witness: {solver} {path.name}")
  if status=="UNSAT" and p.returncode not in (0,20):
   raise RuntimeError(f"invalid UNSAT exit code {solver} {p.returncode}")
 except subprocess.TimeoutExpired:
  elapsed=CAP;status="TIMEOUT";output=""
 row=dict(file=path.name,sha256=source,solver=solver,status=status,
   E2E_s=round(elapsed,6),PAR2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
   SAT_original_model_verified=status=="SAT",UNSAT_independent_LRAT=False)
 print("FACTOR4_OFFICIAL_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
 return row
sources=[];rows=[]
for name in FILES:
 path,sha,n,m=read_source(name)
 sources.append(dict(name=name,sha256=sha,vars=n,clauses=m,url=BASE+name))
 commands={
 "DRNAS_CDCL":["mre_factor4/bin/drnas_factor4",str(path),"--mode","A","--time",str(CAP)],
 "DRNAS_FACTOR4":["mre_factor4/bin/drnas_factor4",str(path),"--mode","C","--time",str(CAP)],
 "Kissat":["kissat",str(path)],
 "CryptoMiniSat":["cryptominisat5","--verb","0",str(path)],
 "CaDiCaL":["cadical",str(path)]
 }
 for solver,cmd in commands.items():
  if shutil.which(cmd[0]) is None:raise RuntimeError("missing solver "+cmd[0])
  rows.append(run(cmd,path,solver,sha))
summary={}
for solver in ("DRNAS_CDCL","DRNAS_FACTOR4","Kissat","CryptoMiniSat","CaDiCaL"):
 sub=[r for r in rows if r["solver"]==solver]
 summary[solver]=dict(solved=sum(r["status"] in ("SAT","UNSAT") for r in sub),
  PAR2_s=round(sum(r["PAR2_s"] for r in sub),6),
  elapsed_s=round(sum(r["E2E_s"] for r in sub),6),
  timeout=sum(r["status"]=="TIMEOUT" for r in sub))
audit=dict(protocol="FACTOR4-OFFICIAL-SAT2025-4-SOURCES-5-SOLVERS-40SEC-ONECPU",
 source_origin="SAT Competition 2025 Round-Robin submitted benchmark family",
 cap_s=CAP,one_logical_cpu=True,source_selection_fixed_before_timings=True,
 original_SAT_models_verified=True,UNSAT_independent_LRAT=False,
 sources=sources,rows=rows,summary=summary)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
print("FACTOR4_OFFICIAL_FINAL "+json.dumps({k:v for k,v in audit.items() if k not in ("rows","sources")},sort_keys=True))
