#!/usr/bin/env python3
"""Audit five retrospective official R38 probes, not a blind speedup claim."""
import argparse,collections,hashlib,json,statistics
from pathlib import Path
from r38_portfolio_probe import CASES,MODES,PORTFOLIO,CAP
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--root",required=True);p.add_argument("--manifest",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args()
 mfile=Path(a.manifest);manifest=json.loads(mfile.read_text())
 expected={c["id"]:c for c in manifest["cases"]}
 assert len(expected)==12
 cases=[];pins=set();kissats=set()
 for i,id in enumerate(CASES):
  path=Path(a.root)/("case-"+str(i))/"results"/"report.json"
  row=json.loads(path.read_text())
  assert row["case_id"]==id and id in expected
  src=expected[id]
  assert row["sha256"]==src["sha256"] and row["label"]==src["official_label"]
  assert row["features"]==src["features"]
  assert row["manifest_sha256"]==hashlib.sha256(mfile.read_bytes()).hexdigest()
  assert row["selected_retrospectively"] is True and float(row["limit_s"])==CAP
  assert len(row["single_core_modes"])==len(MODES)
  by={s["mode"]:s for s in row["single_core_modes"]}
  assert len(by)==len(MODES) and set(by)==set(MODES)
  for mode,r in by.items():
   assert r["status"] in ("SAT","UNSAT","TIMEOUT"),(id,mode,r)
   if r["status"] in ("SAT","UNSAT"):assert r["status"]==src["official_label"]
   assert r["wall_s"]>=0 and r["cpu_s"]>=0
  pins.add(row["pinned_probe_sha256"]);kissats.add(row["pinned_kissat_sha256"])
  port=row["portfolio"]
  assert tuple(port["lanes"])==PORTFOLIO
  assert port["status"] in ("SOLVED","TIMEOUT_OR_ERROR","SKIPPED_INSUFFICIENT_CORES")
  if port["status"]=="SOLVED":
   assert port["winner"] in PORTFOLIO
   assert 0<port["wall_s"]<=CAP+0.3
  r=lambda mode:by[mode]["wall_s"] if by[mode]["status"] in ("SAT","UNSAT") else 2*CAP
  best_mode=min(MODES,key=r)
  best_par2=r(best_mode)
  baseline=r("ca_plain");kissat=r("kissat_pinned")
  port_par2=port["wall_s"] if port["status"]=="SOLVED" else 2*CAP
  cases.append(dict(id=id,label=src["official_label"],features=row["features"],
     vars=row["declared_vars"],clauses=row["declared_clauses"],
     baseline_par2=baseline,kissat_par2=kissat,
     best_mode=best_mode,best_par2=best_par2,
     mode_times={mode:dict(status=by[mode]["status"],wall=by[mode]["wall_s"],
        cpu=by[mode]["cpu_s"]) for mode in MODES},
     matched_v91_prefix=row["v91_prefix_equal_if_completed"],
     pre256_telemetry={mode:by[mode]["stats"] for mode in
      ("v91_always_late","v91_never_late","v90_quality_guided","v90_quality_no_hints")},
     portfolio=port,portfolio_par2=port_par2,
     portfolio_vs_ca_wall=baseline/port_par2 if port_par2 else None,
     strongest_single_vs_ca=baseline/best_par2 if best_par2 else None))
 assert len(cases)==5 and len(pins)==1 and len(kissats)==1
 by_mode={}
 for mode in MODES:
  d=[(c["mode_times"][mode]["wall"] if c["mode_times"][mode]["status"] in ("SAT","UNSAT") else 2*CAP) for c in cases]
  by_mode[mode]=dict(mean_PAR2_s=statistics.mean(d),
                     solved=sum(c["mode_times"][mode]["status"] in ("SAT","UNSAT") for c in cases),
                     timeout=5-sum(c["mode_times"][mode]["status"] in ("SAT","UNSAT") for c in cases))
 head={"protocol":"R38 targeted retrospective 2026 official formula portfolio; no R37 120 re-run",
     "cases":len(cases),"native_single_core_attempts":len(cases)*len(MODES),
     "portfolio_attempts":len(cases),
     "portfolio_lanes":list(PORTFOLIO),"timeout_s":CAP,
     "pinned_probe_sha256":next(iter(pins)),"pinned_kissat_sha256":next(iter(kissats)),
     "v91_confirmed_common_prefix_count":sum(c["matched_v91_prefix"] is True for c in cases),
     "v91_mismatched_common_prefix_count":sum(c["matched_v91_prefix"] is False for c in cases),
     "unverified_prefix_count":sum(c["matched_v91_prefix"] is None for c in cases),
     "limitations":"Retrospectively chosen cases, one seed/case, 5 formulas, variable CI load. 4-core portfolio uses 4x hardware. No proven generalization, no world record."}
 report={"summary":head,"modes":by_mode,"cases":cases}
 Path(a.out).write_text(json.dumps(report,indent=2)+"\n")
 print("R38_AUDIT_PASS",json.dumps(head,sort_keys=True),flush=True)
 print("| Case | CaDiCaL 1 CPU PAR2 | Best selected mode | Best PAR2 | 4-core portfolio PAR2 | v91 checkpoint same? |")
 print("|---|---:|---|---:|---:|---|")
 for c in cases:print("|",c["id"][:8],"|",round(c["baseline_par2"],4),
  "|",c["best_mode"],"|",round(c["best_par2"],4),"|",round(c["portfolio_par2"],4),
  "|",c["matched_v91_prefix"],"|")
 print("R38_MODE_MEANS",json.dumps(by_mode,sort_keys=True))
if __name__=="__main__":main()
