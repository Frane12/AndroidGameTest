#!/usr/bin/env python3
"""SRE2-A 3 graph source instances, 4 native modes, 3 repeats,
strict original SAT witness and independently enumerated UNSAT.
No claim of blind competitive benchmark.
"""
import importlib.util,json,pathlib,subprocess,time,re
spec=importlib.util.spec_from_file_location("sre1","research/drnas_sre1_benchmark.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=pathlib.Path("mre_sre2a");out.mkdir(exist_ok=True)
binary=out/"bin/drnas_sre2a"
def run():
 cases=[]
 for label,make in [("radio_sat",lambda:m.radio(False)),
                    ("radio_unsat",lambda:m.radio(True)),
                    ("circuit_sat",lambda:m.circuit(False)),
                    ("parity_sat",lambda:m.parity(False))]:
  n,cls=make()
  path=out/(label+".cnf");path.write_text(m.dimacs(n,cls))
  cases.append((label,path,n,cls,m.truth(n,cls)))
 rows=[]
 for label,path,n,clauses,expected in cases:
  for mode in ("plain","sre1","sre2a","sre2a_shadow"):
   for rep in range(3):
    t=time.perf_counter()
    p=subprocess.run([str(binary.resolve()),str(path.resolve()),"--mode",mode,"--time","3"],
        text=True,capture_output=True,timeout=5)
    wall=time.perf_counter()-t
    if p.returncode not in (10,20,0):raise RuntimeError(p.stderr)
    status={10:"SAT",20:"UNSAT",0:"UNKNOWN"}[p.returncode]
    if status!=expected:raise RuntimeError(f"mismatch {label} {mode}: {status} vs {expected}")
    line=re.search(r"^SRE2A_TRIAL (.*)$",p.stdout,re.M)
    if not line:raise RuntimeError(p.stdout)
    vals=dict(x.split("=",1) for x in line.group(1).split() if "=" in x)
    if status=="SAT":
     lits=[int(x) for l in p.stdout.splitlines() if l.startswith("v ")
           for x in l[2:].split() if x!="0"]
     assignments={abs(l):l>0 for l in lits}
     if len(assignments)!=n or not all(any(assignments[abs(l)]==(l>0) for l in c)
         for c in clauses):raise RuntimeError("independent original SAT model invalid")
    rows.append(dict(source=label,mode=mode,rep=rep,status=status,
         E2E_s=round(wall,6),original_truth_exhaustively_verified=True,
         native_metrics=vals))
    print("SRE2A_TRIAL_JSON "+json.dumps(rows[-1],sort_keys=True),flush=True)
 modes={}
 for mode in ("plain","sre1","sre2a","sre2a_shadow"):
  r=[x for x in rows if x["mode"]==mode]
  modes[mode]=dict(solved=len(r),PAR2_s=round(sum(x["E2E_s"] for x in r),6),
    exact_one_groups=sum(int(x["native_metrics"]["groups"]) for x in r),
    clique_used=sum(int(x["native_metrics"]["clique_used"]) for x in r))
 result=dict(protocol="DRNAS-SRE2A-SYNTHETIC-4CASES-4ARMS-3REPS-ONECPU-v1",
    trials=len(rows),sources=len(cases),one_logical_cpu_per_solver=True,
    independently_exhaustive_source_truth=True,
    independently_checked_original_SAT_witness=True,
    UNSAT_original_LRAT=False,nonblind_synthetic_development=True,
    no_foreign_solver=True,modes=modes,rows=rows)
 (out/"audit.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
 print("SRE2A_FINAL "+json.dumps({k:v for k,v in result.items() if k!="rows"},sort_keys=True))
if __name__=="__main__":run()
