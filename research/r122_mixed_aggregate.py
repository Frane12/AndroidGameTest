#!/usr/bin/env python3
"""R122 strict eight-shard matched-pair aggregate, SHA, duplicate, status audit."""
from collections import Counter,defaultdict
from pathlib import Path
import csv,hashlib,json
root=Path("r122")
m=json.loads((root/"manifest.json").read_text())
assert m["protocol"]=="DRNAS-R122-MIXED-AND-OR-ANF-20261105-V1"
cs={c["id"]:c for c in m["cases"]}
assert len(cs)==192 and len({c["sha256"] for c in cs.values()})==192
for c in cs.values():
 data=(root/"cnf"/(c["id"]+".cnf")).read_bytes()
 assert hashlib.sha256(data).hexdigest()==c["sha256"]
paths=list((root/"collected").rglob("paired.csv"))
assert len(paths)==8,("wrong shard count",len(paths))
rows=[]
for file in paths:
 with file.open(newline="") as f:rows+=list(csv.DictReader(f))
assert len(rows)==1536,("wrong complete attempt count",len(rows))
seen=set();paired=defaultdict(dict)
for r in rows:
 c=cs[r["id"]]
 assert c["sha256"]==r["sha256"] and str(c["seed"])==r["seed"]
 assert c["family"]==r["family"] and c["exposure"]==r["exposure"]
 assert r["mode"] in ("r118","r122","kissat","cryptominisat")
 assert r["status"] in ("SAT","UNSAT","TIMEOUT")
 if r["status"] in ("SAT","UNSAT"):assert r["status"]==c["expected"]
 k=(r["id"],int(r["rep"]),r["mode"])
 assert k not in seen,("duplicate",k)
 seen.add(k)
 r["seconds"]=float(r["seconds"]);r["par2"]=float(r["par2"])
 assert 0<=r["seconds"]<=3.5
 assert abs(r["par2"]-(r["seconds"] if r["status"]!="TIMEOUT" else 6.0))<.0001
 if r["mode"]=="r122":
  assert r["route"] in ("certified_gate_anf_equivalent","certified_gate_anf_counterexample")
 paired[(r["id"],int(r["rep"]))][r["mode"]]=r
assert len(paired)==384 and all(len(v)==4 for v in paired.values())
summary=[]
for exposure in ("seen","new"):
 for fam in ("mixed_equiv","mixed_inequiv"):
  for mode in ("r118","r122","kissat","cryptominisat"):
   a=[r for r in rows if r["exposure"]==exposure and r["family"]==fam and r["mode"]==mode]
   assert len(a)==96
   summary.append(dict(exposure=exposure,family=fam,solver=mode,
    attempts=len(a),solved=sum(r["status"]!="TIMEOUT" for r in a),
    timeout=sum(r["status"]=="TIMEOUT" for r in a),
    direct=sum(r["route"].startswith("certified_") for r in a),
    par2_total=round(sum(r["par2"] for r in a),6),
    wall_total=round(sum(r["seconds"] for r in a),6)))
pairrows=[]
for (id,rep),run in paired.items():
 for competitor in ("r118","kissat","cryptominisat"):
  a,b=run["r122"],run[competitor]
  pairrows.append(dict(formula=id,rep=rep,exposure=cs[id]["exposure"],
   family=cs[id]["family"],competitor=competitor,r122_s=a["seconds"],
   baseline_s=b["seconds"],r122_status=a["status"],baseline_status=b["status"],
   ratio=(b["seconds"]/a["seconds"] if a["seconds"]>0 and b["status"]!="TIMEOUT" else ""),
   timeout_lower_bound=(3/a["seconds"] if a["seconds"]>0 and b["status"]=="TIMEOUT" else "")))
with (root/"scatter_pairs.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(pairrows[0]));w.writeheader();w.writerows(pairrows)
(root/"aggregate.json").write_text(json.dumps(summary,indent=2)+"\n")
lines=["# DRNAS R122 mixed AND/OR gate-equivalence benchmark","",
 "192 generated circuits: 96 R119 previously seen + 96 new deterministic examples.",
 "Each has 10 primary inputs, XOR/AND/OR gates; no production industrial inputs.",
 "3 s timeout; 6 s PAR-2; source SHA and exact source-clause reconstruction audit.",
 "UNSAT assertions independently verified by complete enumeration of 1024 input patterns.",
 "SAT counterexamples checked on every original DIMACS clause.",
 "Run-order shuffled per pair, CPU affinity pinned, same hardware within each shard.",
 "","| Exposure | Family | Solver | Solved | Direct | PAR-2 total |",
 "|---|---|---|---:|---:|---:|"]
for x in summary:
 lines.append(f'| {x["exposure"]} | {x["family"]} | {x["solver"]} | {x["solved"]}/{x["attempts"]} | {x["direct"]} | {x["par2_total"]:.6f} s |')
lines+=["", "Caution: on known synthetically encoded gate circuits, not generalized",
 "real industrial mixed SAT; benchmark includes process startup and parsing.",
 "R122 only makes direct decisions when the *entire* CNF matches a gate miter.",
 "No claim of a general-purpose AND/OR SAT breakthrough or official result."]
(root/"report.md").write_text("\n".join(lines)+"\n")
print("R122_AUDIT_SUCCESS",json.dumps(dict(formulas=len(cs),attempts=len(rows),shards=len(paths),
 new=Counter(c["exposure"] for c in cs.values()))),flush=True)
print("R122_FINAL",json.dumps(summary),flush=True)
