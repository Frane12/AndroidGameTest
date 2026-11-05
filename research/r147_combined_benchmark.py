#!/usr/bin/env python3
"""DRNAS R147: diagnostic 48-CNF SHA-deterministic subset of frozen 400-CNF cohort.
Six-way paired R147 native combined router vs unchanged Kissat/CaDiCaL/R118/R135/R146c.
This is a REUSED EXPOSED cohort, not a new blind validation. No tuning on results.
"""
import collections
import hashlib
import json
import pathlib
import subprocess
import time
import r146c_guarded_portfolio as guard

base = guard.base
base.ROOT = pathlib.Path("r147")
base.R118 = pathlib.Path("r147/r118")
base.PROTO = "DRNAS-R147-COMBINED-SAFE-48-REUSED-400-20261105-v1"
base.MODES = ("kissat", "cadical", "r118", "r135", "r146c", "r147")
base.SHARDS = 4
# Keep the original R135 audit's hardcoded PAR2=30 timeout invariant.
assert base.CAP == 15 and base.REPS == 2
N = 48
R147_BINARY = pathlib.Path("r147/r147")
R132_BINARY = pathlib.Path("r147/r132")

original_sources = base.read_sources

def choose_subset(cases):
    # SHA-only precommitted selection, stratified by original category.
    groups = collections.defaultdict(list)
    for c in cases:
        groups[c["cohort"]].append(c)
    selected = []
    for cat in sorted(groups):
        members = sorted(groups[cat], key=lambda x: x["sha256"])
        quota = max(1, round(N * len(members) / len(cases)))
        selected.extend(members[:quota])
    selected_by_sha = {c["sha256"]: c for c in selected}
    for c in sorted(cases, key=lambda x: x["sha256"]):
        if len(selected_by_sha) >= N:
            break
        selected_by_sha[c["sha256"]] = c
    if len(selected_by_sha) > N:
        # Stable hash balancing after representation by cohort.
        selected_by_sha = dict(sorted(selected_by_sha.items(),
            key=lambda x: hashlib.sha256(("R147-pilot-"+x[0]).encode()).hexdigest())[:N])
    chosen = sorted(selected_by_sha.values(), key=lambda x: x["sha256"])
    assert len(chosen) == N and len({x["sha256"] for x in chosen}) == N
    return chosen

def read_sources():
    manifest, cases = original_sources()
    assert len(cases) == 400
    chosen = choose_subset(cases)
    base.write(base.ROOT / "selected-48.json",
        dict(protocol=base.PROTO, parent_manifest_sha256=manifest,
             cohort="SHA-only deterministic reused 400, 48-case development subset",
             formulas=[dict(sha256=x["sha256"], category=x["cohort"]) for x in chosen]))
    return manifest, chosen

base.read_sources = read_sources
previous_invoke = base.invoke

def invoke(src, mode, rep):
    if mode != "r147":
        return previous_invoke(src, mode, rep)
    begin = time.perf_counter()
    command = [str(R147_BINARY.resolve()), str(src.resolve()),
        str(R132_BINARY.resolve()), str(base.R118.resolve()),
        str(base.KISSAT.resolve()), str(base.CADICAL.resolve())]
    target = "UNKNOWN"
    try:
        p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=base.CAP)
        elapsed = time.perf_counter() - begin
        base.need(p.returncode in (10, 20),
            "R147 unexpected exit " + str(p.returncode) + " " +
            p.stderr[-600:].decode(errors="replace"))
        status = "SAT" if p.returncode == 10 else "UNSAT"
        if elapsed >= base.CAP:
            status = "TIMEOUT"
        for line in p.stdout.splitlines():
            if line.startswith(b"c R147_ROUTE "):
                for item in line.decode(errors="replace").split()[2:]:
                    if item.startswith("route="):
                        target = item.split("=", 1)[1]
                        break
        if target == "UNKNOWN":
            raise RuntimeError("R147 missing route telemetry")
        proof = "timeout"
        if status == "SAT":
            base.witness.check_original_sat(p.stdout, src)
            proof = "source_SAT_witness_verified"
        elif status == "UNSAT":
            proof = "UNSAT_without_independent_LRAT_proof"
    except subprocess.TimeoutExpired:
        elapsed = base.CAP
        status = "TIMEOUT"
        proof = "timeout"
    return dict(mode=mode, repeat=rep, status=status,
        seconds=round(min(elapsed, base.CAP), 6),
        par2=30.0 if status == "TIMEOUT" else round(elapsed, 6),
        proof=proof, selector_target=target, selector_reason="R147_bounded",
        selector_cost_s=None, binary_ratio=None, horn_ratio=None,
        fully_scanned=None)

base.invoke = invoke

def audit():
    guard.audit()
    report_path = base.ROOT / "report.json"
    report = json.loads(report_path.read_text())
    rows = [r for i in range(base.SHARDS) for r in
        json.loads((base.ROOT / ("shard-" + str(i) + ".json")).read_text())["rows"]]
    idx = {(r["sha256"], r["repeat"], r["mode"]): r for r in rows}
    sha = sorted({r["sha256"] for r in rows})
    deltas = [sum(idx[(s, rep, "r147")]["par2"] -
                  idx[(s, rep, "kissat")]["par2"] for rep in range(base.REPS))
              for s in sha]
    report["comparisons"]["r147"] = dict(
        gain_vs_kissat_pct=round(100 *
            (report["summary"]["kissat"]["par2_total_s"] /
             report["summary"]["r147"]["par2_total_s"] - 1), 6),
        faster_formula_pairs=sum(d < -0.00001 for d in deltas),
        slower_formula_pairs=sum(d > 0.00001 for d in deltas),
        regressions_2x=sum(
            sum(idx[(s, rep, "r147")]["par2"] for rep in range(base.REPS)) >=
            2 * sum(idx[(s, rep, "kissat")]["par2"] for rep in range(base.REPS))
            for s in sha))
    report["r147_route_counts"] = dict(collections.Counter(
        r["selector_target"] for r in rows if r["mode"] == "r147"))
    report["evaluation_status"] = "REUSED_EXPOSED_48_OF_FROZEN_400_NOT_BLIND"
    report["verdict"] = "EXPLORATORY_ONLY_NO_PROMOTION"
    base.write(report_path, report)
    print("R147_FINAL_AUDIT", json.dumps(report, sort_keys=True), flush=True)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("run", "audit"))
    ap.add_argument("--shard", type=int, default=0)
    args = ap.parse_args()
    if args.command == "run":
        base.run(args.shard)
    else:
        audit()
