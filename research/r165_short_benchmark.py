#!/usr/bin/env python3
"""R165: short, paired replay of the immutable R164 native binary.

Development replay only, not blind or SAT Competition ranking. Four original,
SHA-pinned R155 CNFs; clean CDCL and R164 incremental use the *same* native
CaDiCaL binary and CPU within each pair. Pure-exact XOR is a separate Python
solver path, never mislabeled as the native R164 incremental mode.
"""
import argparse
import hashlib
import json
import pathlib
import random
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path("research").resolve()))
import r164_component_benchmark as base
import r164_pure_exact_gf2 as pure

ROOT = pathlib.Path("r165")
base.ROOT = ROOT
base.FROZEN = ROOT / "frozen"
BRANCH_BASE = "2ff07b3af7f98b9d822b9626d348c681297fd174"
MODES = ("clean", "direct_incremental")
PLAN = (("mixed_residual", 2, 90.0), ("complete_xor", 1, 30.0),
        ("xor_plus_units", 1, 30.0))

def require(ok, reason):
    if not ok:
        raise RuntimeError("R165_AUDIT_FAIL: " + reason)

def selected():
    manifest = base.rd(base.FROZEN / "manifest.json")
    require(len(manifest["cases"]) == 25, "original 25-case manifest missing")
    cases = []
    for cohort, count, cap in PLAN:
        subset = sorted((c for c in manifest["cases"] if c["cohort"] == cohort),
                        key=lambda c: c["id"])[:count]
        require(len(subset) == count, "missing original cohort " + cohort)
        for c in subset:
            path = base.FROZEN / (c["id"] + ".cnf")
            require(base.h(path) == c["sha256"], "source SHA mismatch " + c["id"])
            cases.append(dict(c, cap_s=cap))
    require(len(cases) == 4 and len({c["sha256"] for c in cases}) == 4,
            "bad four-formula selection")
    return cases

def run_native(c, mode, prep, binary):
    src = base.FROZEN / (c["id"] + ".cnf")
    tsv = ROOT / ("full-" + c["id"] + ".tsv")
    require(base.h(src) == c["sha256"], "source changed during trial")
    require(base.h(tsv) == prep["full_tsv_sha"], "GF2 certified rows changed")
    charge = 0.0 if mode == "clean" else prep["preprocessing_s"]
    cap = c["cap_s"]
    require(cap > charge + 5.0, "insufficient time budget")
    start = time.perf_counter()
    proc = subprocess.run(
        [str(binary.resolve()), mode, str(src.resolve()),
         str(tsv.resolve()), str(cap - charge)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=cap + 15)
    elapsed = time.perf_counter() - start + charge
    require(proc.returncode in (0, 10, 20),
            "native process error " + proc.stderr.decode(errors="replace")[-600:])
    txt, native, stats, source_rows, derived_rows = base.parse_native(proc.stdout, mode)
    status = {"SAT": "SAT", "UNSAT": "UNSAT", "UNKNOWN": "TIMEOUT"}[native["status"]]
    require(proc.returncode == {"SAT": 10, "UNSAT": 20, "TIMEOUT": 0}[status],
            "result and exit mismatch")
    require(source_rows == (0 if mode == "clean" else prep["full_rows"]),
            "native GF2 row count mismatch")
    require(abs(float(native["solver_s"]) - (elapsed - charge)) < 0.75,
            "native/wall stopwatch drift")
    if status == "SAT":
        require(native.get("source_sat_witness_checked") == "1",
                "native original SAT witness not checked")
        base.sat_check(src, txt)
    for field in ("conflicts", "decisions", "propagations"):
        require(stats[field] is not None, "missing CaDiCaL telemetry " + field)
    return {
        "id": c["id"], "sha256": c["sha256"], "cohort": c["cohort"],
        "family": c["family"], "cap_s": cap, "mode": mode, "status": status,
        "elapsed_s": round(elapsed, 6), "charged_preprocess_s": charge,
        "PAR2_s": round(2*cap if status == "TIMEOUT" else min(cap, elapsed), 6),
        "conflicts": stats["conflicts"], "decisions": stats["decisions"],
        "propagations": stats["propagations"],
        "gf2_proposals": int(native["direct_proposals"]),
        "gf2_reason_clauses": int(native["reason_clauses_completed"]),
        "incremental_row_events": int(native["incremental_row_events"]),
        "proof": "SOURCE_SAT_INDEPENDENT_CHECK" if status == "SAT" else
                 "UNSAT_UNVERIFIED_LRAT" if status == "UNSAT" else "TIMEOUT",
        "source_rows": source_rows, "derived_rows": derived_rows
    }

def shard(index, binary):
    cases = selected()
    require(0 <= index < len(cases), "invalid shard")
    pin = base.rd(ROOT / "build-pin.json")
    require(base.h(binary) == pin["binary_sha256"], "original R164 binary drift")
    require(pin["commit"] == BRANCH_BASE, "original R164 source commit drift")
    c = cases[index]
    prep = base.prepare(c)
    # Alternate order deterministically across formulas; one repeat only.
    modes = list(MODES)
    random.Random("R165-V1-" + c["sha256"]).shuffle(modes)
    rows = []
    for mode in modes:
        result = run_native(c, mode, prep, binary)
        rows.append(result)
        base.wr(ROOT / ("shard-%d.json" % index), rows)
        print("R165_TRIAL", json.dumps(result, sort_keys=True), flush=True)
    pure_result = None
    if c["cohort"] in ("complete_xor", "xor_plus_units"):
        v = pure.solve(base.FROZEN / (c["id"] + ".cnf"))
        require(v["source_sha256"] == c["sha256"], "pure source mismatch")
        pure_result = {
            "id": c["id"], "status": v["status"],
            "pure_exact": v["pure_exact"], "elapsed_s": v["elapsed_s"],
            "xor_rows": v["xor_rows"],
        }
        base.wr(ROOT / ("pure-%d.json" % index), pure_result)
        print("R165_PURE_EXACT", json.dumps(pure_result, sort_keys=True), flush=True)
    result = {"pin": pin, "case": c, "prep": prep, "rows": rows, "pure": pure_result}
    base.wr(ROOT / ("result-%d.json" % index), result)
    print("R165_SHARD_PASS", index, c["id"], flush=True)

def audit():
    cases = selected()
    report_rows = []
    pure_rows = []
    for i, c in enumerate(cases):
        item = base.rd(ROOT / ("result-%d.json" % i))
        require(item["case"]["sha256"] == c["sha256"], "audit source SHA drift")
        require(item["pin"]["commit"] == BRANCH_BASE, "audit pinned source drift")
        require(len(item["rows"]) == 2 and
                {z["mode"] for z in item["rows"]} == set(MODES),
                "missing clean/incremental pair")
        for z in item["rows"]:
            require(z["sha256"] == c["sha256"], "wrong source in audit")
            report_rows.append(z)
        if item["pure"] is not None:
            require(item["pure"]["id"] == c["id"], "bad pure match")
            pure_rows.append(item["pure"])
    pins = [base.rd(ROOT / ("result-%d.json" % i))["pin"]["binary_sha256"]
            for i in range(4)]
    require(len(set(pins)) == 1, "binary SHA mismatch across paired jobs")
    require(len(report_rows) == 8, "expected 8 native trials")
    pairs = []
    for c in cases:
        arr = [r for r in report_rows if r["id"] == c["id"]]
        d = {z["mode"]: z for z in arr}
        clean, inc = d["clean"], d["direct_incremental"]
        require(not (clean["status"] in ("SAT", "UNSAT") and
                     inc["status"] in ("SAT", "UNSAT") and
                     clean["status"] != inc["status"]), "contradictory SAT/UNSAT")
        ratio = None
        if clean["status"] != "TIMEOUT" and inc["status"] != "TIMEOUT":
            ratio = round(clean["elapsed_s"] / max(inc["elapsed_s"], 1e-9), 4)
        pairs.append({"id": c["id"], "cohort": c["cohort"], "cap_s": c["cap_s"],
                      "clean": clean, "incremental": inc, "paired_speedup": ratio})
    total = {}
    for mode in MODES:
        rows = [r for r in report_rows if r["mode"] == mode]
        total[mode] = {
            "solved": sum(z["status"] != "TIMEOUT" for z in rows),
            "trials": len(rows),
            "PAR2_s": round(sum(z["PAR2_s"] for z in rows), 5),
            "conflicts": sum(z["conflicts"] for z in rows),
            "decisions": sum(z["decisions"] for z in rows),
        }
    out = {"status": "RESEARCH_REPLAY_NO_PROMOTION", "formulas": 4,
           "native_trials": 8, "same_binary_sha256": pins[0],
           "reference": "CaDiCaL 2.1.0 clean in identical R164 binary",
           "not_blind": True, "single_repeat": True,
           "total": total, "pairs": pairs, "pure_exact": pure_rows,
           "caveats": ["Development originals, not unseen or independent competition",
                        "A TIMEOUT cannot establish a speedup; use PAR2 penalty",
                        "Pure Python GF2 is separate from the native incremental path",
                        "Independent UNSAT LRAT/FRAT proof is not available"]}
    base.wr(ROOT / "short-report.json", out)
    lines = ["# DRNAS R165 quick paired R164 replay", "",
             "4 SHA-pinned original CNFs, 2 native modes, 1 repeat, "
             "90s mixed / 30s controls; same precompiled R164 binary.", "",
             "| Original CNF | Clean | Incremental | Cap | Both solved speedup |",
             "|---|---:|---:|---:|---:|"]
    for p in pairs:
        def fmt(z):
            return z["status"] + (" (" + str(z["elapsed_s"]) + "s)" if
                                  z["status"] != "TIMEOUT" else "")
        lines.append("| " + p["id"][:10] + " (" + p["cohort"] + ") | " +
                     fmt(p["clean"]) + " | " + fmt(p["incremental"]) + " | " +
                     str(p["cap_s"]) + "s | " +
                     (str(p["paired_speedup"]) + "x" if p["paired_speedup"] else "n/a") + " |")
    lines.extend(["", "| Native mode | Solved | PAR2 s | Conflicts | Decisions |",
                  "|---|---:|---:|---:|---:|"])
    for mode in MODES:
        d = total[mode]
        lines.append("| " + mode + " | " + str(d["solved"]) + "/4 | " +
                     str(d["PAR2_s"]) + " | " + str(d["conflicts"]) + " | " +
                     str(d["decisions"]) + " |")
    lines.extend(["", "Pure-exact GF2 (separate path): " +
                  json.dumps(pure_rows, sort_keys=True),
                  "", "RESEARCH ONLY. NOT BLIND. One repeat; UNSAT unverified LRAT."])
    (ROOT / "short-summary.md").write_text("\n".join(lines) + "\n")
    print("R165_FINAL", json.dumps(out, sort_keys=True), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--binary", default="r165/r164-native")
    args = parser.parse_args()
    if args.action == "shard":
        shard(args.shard, pathlib.Path(args.binary))
    else:
        audit()
