#!/usr/bin/env python3
"""R54 isolated 70/20/10 RESEARCH PRIORITIES, not solver coefficients.

R53 outcome: R49 -0.0104% vs pinned Kissat (50 cases x3), no solved-case gain.
A deterministic fail-safe R49 policy experiment; XOR and early-conflict
signals are observational only until blind holdout establishes net benefit.
No mutation of frozen R53 or baseline binaries.
"""
import argparse,json,collections,statistics
from pathlib import Path
import r49_pivot_coherence_gate as r49
import r52_prospective_2026_toprefs as r52
import r53_fifty_fresh_triple as r53

PROTO="DRNAS-R54-70-20-10-RESEARCH-20261103-v1"
PRIORITIES={"structural_gate":70,"xor_gf2":20,"early_conflict_stop_continue":10}
# Explicit safe-bounded resource policy, not weights/learning parameters.
MAX_INPUT_BYTES=8*1024*1024
MAX_DERIVED_CLAUSES=40
MAX_PREP_SECONDS=1.0
def inspect(original):
    from time import monotonic
    start=monotonic()
    src=Path(original)
    info=dict(protocol=PROTO,priorities=PRIORITIES,
      file_bytes=src.stat().st_size,
      gate=False,derived=0,pivot_dominance=0.0,
      xor_shadow="not_computed",conflict_signal="not_instrumented",
      stop_continue="continue_clean",fallback="clean_pinned_kissat")
    if info["file_bytes"]>MAX_INPUT_BYTES:
        info["stop_continue"]="stop_structural_probe_large_source"
        return info
    plan=r49.compute_plan(src)
    info["derived"]=plan["derived"]
    info["pivot_dominance"]=plan["dominance"]
    info["gate"]=bool(plan["gate"])
    info["prep_seconds"]=monotonic()-start
    if info["prep_seconds"]>=MAX_PREP_SECONDS:
        info["gate"]=False
        info["stop_continue"]="stop_structural_probe_overhead"
    if info["derived"]>MAX_DERIVED_CLAUSES:
        info["gate"]=False
        info["stop_continue"]="stop_structural_probe_clause_budget"
    # No XOR clauses are injected: R32u/R53 did not establish net benefit.
    # No fake early-conflict indicator: actual Kissat conflict telemetry needed.
    return info

def analyze(a):
    report=json.loads(Path(a.r53).read_text())
    assert report["protocol"]==r53.PROTO
    assert len(report["rows"])==450 and len(report["per_instance"])==50
    rows=report["rows"]
    grouped=collections.defaultdict(list)
    for row in rows:grouped[(row["gbd"],row["mode"])].append(row)
    active=[];inactive=[]
    for g in report["per_instance"]:
        k=sum(r["par2_s"] for r in grouped[g,"kissat_pinned"])
        d=sum(r["par2_s"] for r in grouped[g,"drnas_r49_gate"])
        gate=sum(bool(r["r49_gate"]) for r in grouped[g,"drnas_r49_gate"])
        (active if gate else inactive).append(dict(gbd=g,delta_par2_s=d-k,
             gate_trials=gate,kissat_par2_s=k,drnas_par2_s=d))
    result=dict(protocol=PROTO,priorities=PRIORITIES,
      baseline_r53=dict(solved_kissat=25,solved_drnas=25,
                        drnas_minus_kissat_par2_s=round(
                           report["summary"]["drnas_r49_gate"]["par2_sum_s"]-
                           report["summary"]["kissat_pinned"]["par2_sum_s"],6),
                        ci95_pct=report["cluster_bootstrap_CI95_pct"]["kissat_pinned"]),
      gate_active_cases=len(active),gate_inactive_cases=len(inactive),
      active=active,inactive=inactive,
      next_steps=["R49: paired structural feature ablations and pivot concentration",
                  "XOR: bounded shadow-only certified GF(2) extraction, log overhead",
                  "Early conflict: instrument Kissat conflicts before any adaptive switch"],
      warnings=["R53 improvement statistically unconfirmed",
                "No evidence to claim XOR/early-conflict runtime benefit",
                "R54 analysis is not a fresh blind benchmark"])
    Path(a.out).write_text(json.dumps(result,indent=2)+"\n")
    print("R54_R53_DIAGNOSTIC_PASS",json.dumps({
       "active":len(active),"inactive":len(inactive),
       "baseline":result["baseline_r53"]}),flush=True)

def selftest():
    import tempfile
    r49.selftest()
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/"tiny.cnf"
        p.write_text("p cnf 3 2\n1 2 0\n-1 3 0\n")
        d=inspect(p)
        assert d["derived"]>=1 and d["gate"] is False
        assert d["xor_shadow"]=="not_computed"
        assert d["conflict_signal"]=="not_instrumented"
        assert sum(PRIORITIES.values())==100
    print("R54_SOUNDNESS_FALLBACK_SELFTEST_PASS",flush=True)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("cmd",choices=("selftest","analyze"))
    p.add_argument("--r53");p.add_argument("--out")
    a=p.parse_args()
    if a.cmd=="selftest":selftest()
    else:
        assert a.r53 and a.out
        analyze(a)
if __name__=="__main__":main()
