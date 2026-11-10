#!/usr/bin/env python3
"""FACTOR2 A/B: both native arms same binary, source, process and one CPU."""
import importlib.util,json,pathlib,re,subprocess,time,statistics
spec=importlib.util.spec_from_file_location("factor1","research/drnas_factor1_ab.py")
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
OUT=pathlib.Path("mre_factor2");OUT.mkdir(exist_ok=True)
BIN=OUT/"bin/drnas_factor2"
rows=[]
for seed in range(24):
 n,clauses,_,_=f.case(seed)
 truth=f.exact(clauses,n)
 expected="SAT" if truth is not None else "UNSAT"
 path=OUT/f"factor_{seed:02}.cnf";path.write_text(f.dimacs(clauses,n))
 for rep in range(3):
  for arm in ("A","B"):
   p=subprocess.run([str(BIN.resolve()),str(path.resolve()),"--mode",arm,"--time","2"],
                    capture_output=True,text=True,timeout=5)
   if p.returncode not in (10,20):raise RuntimeError(f"native failed {seed} {arm}: {p.stdout} {p.stderr}")
   line=re.search(r"^FACTOR2_TRIAL (.*)$",p.stdout,re.M)
   if not line:raise RuntimeError(p.stdout)
   metrics=dict(x.split("=",1) for x in line.group(1).split() if "=" in x)
   status=metrics["status"]
   if status!=expected:raise RuntimeError(f"wrong status {seed} {arm}: {status}")
   if status=="SAT":
    lits=[int(x) for l in p.stdout.splitlines() if l.startswith("v ") for x in l[2:].split() if x!="0"]
    model={abs(l):l>0 for l in lits}
    if len(model)!=n or not all(any(model[abs(l)]==(l>0) for l in c) for c in clauses):
     raise RuntimeError("invalid original witness")
   row=dict(seed=seed,arm=arm,rep=rep,status=status,E2E_s=float(metrics["e2e_s"]),
            sep=int(metrics["sep"]),components=int(metrics["components"]),
            local_checks=int(metrics["local_checks"]),fallback=int(metrics["fallback"]),
            decisions=int(metrics["decisions"]),conflicts=int(metrics["conflicts"]))
   rows.append(row)
   print("FACTOR2_MEASURE "+json.dumps(row,sort_keys=True),flush=True)
summary={}
for arm in ("A","B"):
 sub=[r for r in rows if r["arm"]==arm]
 summary[arm]=dict(solved=len(sub),PAR2_s=round(sum(x["E2E_s"] for x in sub),7),
                    median_s=round(statistics.median(x["E2E_s"] for x in sub),7),
                    fallback=sum(x["fallback"] for x in sub),
                    decisions=sum(x["decisions"] for x in sub))
audit=dict(protocol="FACTOR2-24-SYNTHETIC-2NATIVE-ARMS-3REPS-ONECPU",
           sources=24,trials=len(rows),same_binary=True,automatic_separator=True,
           original_truth_exhaustively_checked=True,original_SAT_models_verified=True,
           UNSAT_independent_LRAT=False,nonblind_synthetic=True,
           original_separator_not_supplied_to_B=True,
           summary=summary,rows=rows)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
print("FACTOR2_FINAL "+json.dumps({k:v for k,v in audit.items() if k!="rows"},sort_keys=True))
