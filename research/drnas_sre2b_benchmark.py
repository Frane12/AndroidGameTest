#!/usr/bin/env python3
"""SRE2B native 5 arms x 5 source instances x 2 repetitions = 50 oneCPU trials.
Small development formulas: independent exhaustive SAT/UNSAT, no blind claim.
"""
import importlib.util,json,pathlib,re,subprocess,time,os
spec=importlib.util.spec_from_file_location("sre1","research/drnas_sre1_benchmark.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=pathlib.Path("mre_sre2b");root.mkdir(exist_ok=True)
binary=root/"bin/drnas_sre2b"
def symmetry():
 return 6,[[1,2],[-1,-2],[3,4],[-3,-4],[5,6],[-5,-6],
           [-1,3],[-2,4],[-3,1],[-4,2]]
def main():
 cases=[("radio_sat",m.radio(False)),("radio_unsat",m.radio(True)),
        ("circuit_sat",m.circuit(False)),("parity_sat",m.parity(False)),
        ("symmetry_sat",symmetry())]
 modes=("plain","sre1","sre2a","sre2b","sre2b_shadow")
 rows=[]
 for label,(n,cls) in cases:
  path=root/(label+".cnf");path.write_text(m.dimacs(n,cls))
  expected=m.truth(n,cls)
  for mode in modes:
   for rep in range(2):
    start=time.perf_counter()
    proc=subprocess.run([str(binary.resolve()),str(path.resolve()),
        "--mode",mode,"--time","3"],capture_output=True,text=True,timeout=5)
    elapsed=time.perf_counter()-start
    if proc.returncode not in (0,10,20):
     raise RuntimeError("native failed "+proc.stderr)
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[proc.returncode]
    if status!=expected:raise RuntimeError(f"wrong truth {label} {mode} {status} expected {expected}")
    line=re.search(r"^SRE2B_TRIAL (.*)$",proc.stdout,re.M)
    if line is None:raise RuntimeError("missing telemetry "+proc.stdout)
    metrics=dict(x.split("=",1) for x in line.group(1).split() if "=" in x)
    if status=="SAT":
     literals=[int(x) for l in proc.stdout.splitlines() if l.startswith("v ")
               for x in l[2:].split() if x!="0"]
     values={abs(x):x>0 for x in literals}
     if len(values)!=n or not all(any(values[abs(l)]==(l>0) for l in c) for c in cls):
      raise RuntimeError("original CNF witness invalid")
    row=dict(source=label,mode=mode,rep=rep,status=status,
      original_exhaustive_truth=expected,E2E_s=round(elapsed,6),metrics=metrics)
    rows.append(row)
    print("SRE2B_TRIAL_JSON "+json.dumps(row,sort_keys=True),flush=True)
 summary={}
 for mode in modes:
  sub=[x for x in rows if x["mode"]==mode]
  summary[mode]=dict(solved=len(sub),
    PAR2_s=round(sum(x["E2E_s"] for x in sub),6),
    symmetry_leaders=sum(int(x["metrics"]["symmetry_leader_added"]) for x in sub),
    detected_symmetries=sum(int(x["metrics"]["symmetry_shadow_found"]) for x in sub),
    GF2_pair_relations=sum(int(x["metrics"]["sre_gf2_pairs"]) for x in sub),
    clique_used=sum(int(x["metrics"]["clique_used"]) for x in sub))
 audit=dict(protocol="DRNAS-SRE2B-5SOURCES-5ARMS-2REPS-ONECPU-v1",
  original_sources=5,matched_trials=len(rows),one_logical_cpu=True,
  source_truth_independent_exhaustive=True,original_SAT_witness_independent=True,
  original_UNSAT_independent_LRAT=False,synthetic_nonblind=True,
  no_foreign_solver=True,scores=summary,rows=rows)
 (root/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
 print("SRE2B_FINAL "+json.dumps({k:v for k,v in audit.items() if k!="rows"},sort_keys=True),flush=True)
if __name__=="__main__":main()
