#!/usr/bin/env python3
"""30 reproducible 4-XOR CNFs: 15 SAT, 15 UNSAT; 3 runs each.
Deterministic generated suite, NOT blind independent competition.
"""
import json,random,subprocess,time,statistics,os
from pathlib import Path
ROOT=Path("v147-native-results");ROOT.mkdir(exist_ok=True)
def make(seed,unsat):
 r=random.Random(147000+seed);n=24;cl=[]
 # chain of XOR4 equations, with redundant full-support clauses on each block.
 blocks=[(1,2,3,4),(4,5,6,7),(7,8,9,10),(10,11,12,13),(13,14,15,16),(16,17,18,19),(19,20,21,22),(22,23,24,1)]
 model={i:r.randrange(2) for i in range(1,n+1)}
 eq=[(vs,sum(model[x] for x in vs)%2) for vs in blocks]
 if unsat: eq.append((blocks[0],1-eq[0][1]))
 for vs,rhs in eq:
  for mask in range(16):
   if mask.bit_count()%2==rhs:continue
   cl.append([(-v if mask>>j&1 else v) for j,v in enumerate(vs)])
  # duplicate a forbidden pattern, tests redundant clauses on exact support
  cl.append(cl[-1][:])
 r.shuffle(cl)
 p=ROOT/f"case_{seed:02d}_{'unsat' if unsat else 'sat'}.cnf"
 p.write_text(f"p cnf {n} {len(cl)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in cl))
 return p
def run(exe,p,kissat):
 args=[str(exe.resolve()),str(p),str(kissat.resolve()),"1"]
 t=time.perf_counter()
 try:
  x=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=8)
  out=x.stdout
  if '"status":"UNSAT"' in out or "s UNSATISFIABLE" in out:status="UNSAT"
  elif '"status":"SAT"' in out or "s SATISFIABLE" in out:status="SAT"
  else:status="UNKNOWN"
  return {"seconds":time.perf_counter()-t,"status":status,"exit":x.returncode,"fallback":"kissat_direct" in out}
 except subprocess.TimeoutExpired:return {"seconds":8.0,"status":"TIMEOUT"}
def main():
 solvers={"v142":Path("/tmp/v142_xor4"),"v147":Path("/tmp/v147_xor4"),"kissat":Path("/tmp/kissat_solver")}
 for name,p in solvers.items():
  if not p.exists():raise SystemExit(f"Missing {name}: {p}")
 cases=[(make(i,i%2==1),"UNSAT" if i%2 else "SAT") for i in range(30)]
 results=[]
 for p,expected in cases:
  for name,exe in solvers.items():
   reps=[run(exe,p,solvers["kissat"]) for _ in range(3)]
   results.append({"case":p.name,"expected":expected,"solver":name,"repetitions":reps,
    "median_seconds":statistics.median(x["seconds"] for x in reps),
    "correct":all(x["status"]==expected for x in reps)})
 summary={}
 for name in solvers:
  subset=[x for x in results if x["solver"]==name]
  summary[name]={"correct_cases":sum(x["correct"] for x in subset),"total_cases":30,
   "median_seconds":statistics.median(x["median_seconds"] for x in subset),
   "sum_case_medians_seconds":sum(x["median_seconds"] for x in subset)}
 (ROOT/"results.json").write_text(json.dumps({"summary":summary,"results":results},indent=2))
 md=["# DRNAS V14.7 native benchmark (30 generated XOR4 CNFs)","","3 repetitions; same GitHub runner; wall-clock including process startup; deterministic constructed cases, not blind.","","| Solver | Correct cases | Median seconds | Sum of per-case medians (s) |","|---|---:|---:|---:|"]
 for name,s in summary.items():md.append(f"| {name} | {s['correct_cases']}/30 | {s['median_seconds']:.6f} | {s['sum_case_medians_seconds']:.6f} |")
 (ROOT/"results.md").write_text("\n".join(md)+"\n")
 print("\n".join(md))
 if any(s["correct_cases"]!=30 for s in summary.values()):raise SystemExit("At least one solver incorrect; inspect results.json")
if __name__=="__main__":main()
