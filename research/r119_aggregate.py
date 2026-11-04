#!/usr/bin/env python3
"""R119 fail-closed complete-pair aggregation and provenance ledger."""
import csv,hashlib,json,math,pathlib,statistics
from collections import defaultdict,Counter
ROOT=pathlib.Path("r119")
m=json.loads((ROOT/"manifest.json").read_text())
cases={x["id"]:x for x in m["cases"]}
assert len(cases)==192 and len(set(x["sha256"] for x in cases.values()))==192
paths=sorted((ROOT/"collected").rglob("paired.csv"))
assert len(paths)==8,("missing shard artifacts",paths)
rows=[]
for p in paths:
 with p.open(newline="") as f:
  rows.extend(dict(x) for x in csv.DictReader(f))
assert len(rows)==192*2*4,("incomplete benchmark",len(rows))
seen=set()
by=defaultdict(dict)
for r in rows:
 cid=r["id"];assert cid in cases
 c=cases[cid]
 assert r["sha256"]==c["sha256"] and int(r["seed"])==c["seed"]
 assert r["family"]==c["family"]
 assert r["mode"] in ("r28","r118","kissat","cryptominisat")
 assert r["status"] in ("SAT","UNSAT","TIMEOUT")
 if r["status"] in ("SAT","UNSAT"):assert r["status"]==c["expected"],("incorrect result",cid,r)
 k=(cid,int(r["rep"]),r["mode"])
 assert k not in seen,("duplicated measurement",k)
 seen.add(k)
 r["seconds"]=float(r["seconds"]);r["par2"]=float(r["par2"])
 assert 0<=r["seconds"]<=3.5 and 0<=r["par2"]<=6.000001
 by[cid,int(r["rep"])][r["mode"]]=r
assert len(by)==192*2
assert all(len(v)==4 for v in by.values())
for c in cases.values():
 path=ROOT/"cnf"/(c["id"]+".cnf")
 assert hashlib.sha256(path.read_bytes()).hexdigest()==c["sha256"]
result=[]
for fam in m["family_counts"]:
 for mode in ("r28","r118","kissat","cryptominisat"):
  a=[r for r in rows if r["family"]==fam and r["mode"]==mode]
  assert len(a)==m["family_counts"][fam]*2
  result.append(dict(family=fam,solver=mode,attempts=len(a),
    solved=sum(r["status"] in ("SAT","UNSAT") for r in a),
    timeouts=sum(r["status"]=="TIMEOUT" for r in a),
    certified=sum(r["route"].startswith("certified_") for r in a),
    par2_total=round(sum(r["par2"] for r in a),6),
    wall_total=round(sum(r["seconds"] for r in a),6)))
pair=[]
for (id,rep),modes in by.items():
 base=modes["kissat"]
 for mode in ("r28","r118","cryptominisat"):
  r=modes[mode]
  pair.append(dict(formula=id,rep=rep,family=cases[id]["family"],solver=mode,
    solver_status=r["status"],kissat_status=base["status"],
    solver_s=r["seconds"],kissat_s=base["seconds"],
    exact_speedup=(base["seconds"]/r["seconds"] if base["status"]!="TIMEOUT"
       and r["status"]!="TIMEOUT" and r["seconds"] else None),
    censored_lower_bound=(3.0/r["seconds"] if base["status"]=="TIMEOUT"
       and r["status"]!="TIMEOUT" and r["seconds"] else None)))
(ROOT/"aggregate.json").write_text(json.dumps(result,indent=2)+"\n")
with (ROOT/"scatter_pairs.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(pair[0]));w.writeheader();w.writerows(pair)
report=["# R119 circuit-equivalence benchmark", "",
 "**Source type:** 192 freshly generated deterministic digital XOR/AND/OR circuits,",
 "NOT third-party circuit designs and NOT official SAT Competition inputs.",
 "All original CNF SHA256s and generation seeds checked. Two paired repetitions.",
 "Fixed 3-second wall clock per attempt; PAR2 timeout = 6 seconds.",
 "SAT/UNSAT ground truth obtained from exact symbolic parity or exhaustive",
 "Boolean enumeration of 10-input mixed circuits, not solver output.",
 "Proof traces/models of DRNAS direct decisions independently validated.",
 "", "| Family | Solver | Solved | Timeouts | Direct GF2 | PAR2 total (s) |",
 "|---|---|---:|---:|---:|---:|"]
for x in result:
 report.append(f'| {x["family"]} | {x["solver"]} | {x["solved"]}/{x["attempts"]} | {x["timeouts"]} | {x["certified"]} | {x["par2_total"]:.3f} |')
report += ["","**Limits:** Generated sample (not blind industrial circuits),"
 "CPU timings include solver startup and preprocessing; 3-second censoring means",
 "timeout-derived speedups are lower bounds, not exact run-time ratios.",
 "No general P-vs-NP, official ranking, or world-record claim."]
(ROOT/"report.md").write_text("\n".join(report)+"\n")
print("R119_AGGREGATE_SUCCESS",json.dumps(dict(formulas=len(cases),attempts=len(rows),shards=len(paths),family=Counter(r["family"] for r in rows))),flush=True)
print("R119_SUMMARY",json.dumps(result),flush=True)
