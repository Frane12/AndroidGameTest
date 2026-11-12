#!/usr/bin/env python3
"""DRNAS G1: one-CPU, same-source cross-build SAT E2E comparison.

25 synthetic categories: ATLAS13 10 + WIDE500 15; 4 CNFs/category.
3 repeats with 5s screen cap; independent predetermined 8-case 30s spotlight.
R28/R153 native Kissat fallback DISABLED. SAT verified against original CNF;
R28/R153 UNSAT source-XOR certificates independently replayed; all other
UNSAT is marked unverified. These synthetic cases are NOT a blind official set.
"""
import collections
import hashlib
import json
import os
import pathlib
import resource
import subprocess
import sys
import time

sys.path.insert(0, "research")
import drnas_allnative_competition_bench as B
import drnas_atlas13_generator as G
import drnas_atlas_wide500 as W

STAGE = os.environ.get("G1_STAGE", "screen")
assert STAGE in ("screen", "spotlight")
CAP = 5.0 if STAGE == "screen" else 30.0
REPS = 3 if STAGE == "screen" else 1
ROOT = pathlib.Path("general_g1_" + STAGE)
ARMS = (
    "R28_NATIVE", "R153_NATIVE", "LTM7_NATIVE",
    "LTM8_KEEP50", "LTM9_NATIVE", "REX2_GRAPH",
    "ATLAS39_SHADOW", "ATLAS39_PROTECT",
    "Kissat", "CaDiCaL", "CryptoMiniSat",
)
EXTRA_BIN = {
    "LTM8_KEEP50": "./mre_atlas23/bin/drnas_ltm9",
    "REX2_GRAPH": "./rex2_source/mre_atlas23/bin/drnas_rex2",
    "ATLAS39_SHADOW": "./atlas39_source/mre_atlas23/bin/drnas_atlas39",
    "ATLAS39_PROTECT": "./atlas39_source/mre_atlas23/bin/drnas_atlas39",
}
EXTRA_MODE = {
    "LTM8_KEEP50": "LTM8_KEEP50",
    "REX2_GRAPH": "REX2_GRAPH",
    "ATLAS39_SHADOW": "A39_SHADOW",
    "ATLAS39_PROTECT": "A39_PROTECT",
}
SPOTLIGHT = (
    "pigeonhole_unsat", "color3_unsat", "random3_unsat",
    "random3_uniform", "xor_chain_unsat", "xor_dense_unsat",
    "vertex_cover_sat", "implication_dag",
)

def generate():
    if ROOT.exists():
        raise RuntimeError("G1 output directory already exists: refusing stale data")
    (ROOT / "cnf").mkdir(parents=True)
    all_cases = []
    for family in G.CATEGORIES:
        for index in (231, 232, 233, 234):
            n, clauses, _ = G.build(family, index)
            all_cases.append(("ATLAS13", family, index, n, clauses))
    for family in W.SYNTH:
        for index in (131, 132, 133, 134):
            n, clauses = W.synth_one(family, index)
            all_cases.append(("WIDE500", family, index, n, clauses))
    assert len(G.CATEGORIES) == 10 and len(W.SYNTH) == 15
    assert len(all_cases) == 100
    if STAGE == "spotlight":
        all_cases = [c for c in all_cases if c[1] in SPOTLIGHT and c[2] in (231, 131)]
        assert len(all_cases) == len(SPOTLIGHT) == 8
    cases = []
    for origin, family, idx, n, clauses in all_cases:
        raw = W.canonical(n, clauses)
        sha = hashlib.sha256(raw).hexdigest()
        path = ROOT / "cnf" / (sha + ".cnf")
        path.write_bytes(raw)
        cases.append(dict(
            origin=origin, family=family, index=idx, vars=n,
            clauses=clauses, nclauses=len(clauses), sha256=sha,
            path=str(path.resolve()),
        ))
    assert len({c["sha256"] for c in cases}) == len(cases), "duplicate original CNF SHA"
    return cases

def run_extra(c, arm, rep):
    assert hashlib.sha256(pathlib.Path(c["path"]).read_bytes()).hexdigest() == c["sha256"]
    cmd = [
        EXTRA_BIN[arm], c["path"], "--mode", EXTRA_MODE[arm],
        "--time", str(CAP), "--seed", str(rep + 1), "--policy", "1.0,0.85",
    ]
    def limit():
        resource.setrlimit(resource.RLIMIT_AS, (3 * 1024 ** 3, 3 * 1024 ** 3))
        resource.setrlimit(resource.RLIMIT_CPU, (int(CAP) + 2, int(CAP) + 3))
    t0 = time.monotonic()
    try:
        p = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=CAP + 0.15, preexec_fn=limit,
        )
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        rc, out, err = 124, "", "timeout"
    elapsed = min(CAP, time.monotonic() - t0)
    if rc == 10:
        try:
            valid = B.checked_model(c, out)
        except (ValueError, OverflowError):
            valid = False
        if not valid:
            raise RuntimeError("INVALID ORIGINAL SAT witness " + arm + " " + c["sha256"])
        status = "SAT_VERIFIED"
    elif rc == 20:
        status = "UNSAT_UNVERIFIED"
    elif rc in (0, 124, -9, -15, -24):
        status = "UNKNOWN"
    else:
        raise RuntimeError(
            "solver error: " + arm + " return=" + str(rc) + " " +
            c["sha256"] + " stderr=" + err[-450:]
        )
    return dict(
        arm=arm, origin=c["origin"], family=c["family"], index=c["index"],
        rep=rep, sha256=c["sha256"], status=status, e2e_s=round(elapsed, 6),
        PAR2_verified_s=round(elapsed if status == "SAT_VERIFIED" else 2 * CAP, 6),
        PAR2_reported_s=round(elapsed if status in ("SAT_VERIFIED", "UNSAT_UNVERIFIED") else 2 * CAP, 6),
        standalone_native=True, independent_GF2_UNSAT=False,
        stats=B.metrics(out),
        rex2_stats=next((l for l in out.splitlines() if l.startswith("REX2_STATS ")), "")[:250],
    )

def report(rows):
    data = {}
    for arm in ARMS:
        rr = [r for r in rows if r["arm"] == arm]
        data[arm] = dict(
            trials=len(rr),
            SAT_verified=sum(r["status"] == "SAT_VERIFIED" for r in rr),
            UNSAT_GF2_verified=sum(r["status"] == "UNSAT_GF2_VERIFIED" for r in rr),
            UNSAT_unverified=sum(r["status"] == "UNSAT_UNVERIFIED" for r in rr),
            abstain=sum(r["status"] == "ABSTAIN" for r in rr),
            unknown=sum(r["status"] == "UNKNOWN" for r in rr),
            solved_reported=sum(r["status"] in ("SAT_VERIFIED", "UNSAT_GF2_VERIFIED", "UNSAT_UNVERIFIED") for r in rr),
            solved_verified=sum(r["status"] in ("SAT_VERIFIED", "UNSAT_GF2_VERIFIED") for r in rr),
            PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in rr), 5),
            PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in rr), 5),
            E2E_s=round(sum(r["e2e_s"] for r in rr), 5),
        )
    return data

def main():
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    os.environ.update(DRNAS_LTM8_MEMORY="", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    B.CAP = CAP
    cases = generate()
    manifest = dict(
        stage=STAGE, source="deterministic synthetic ATLAS13 + WIDE500; not official CNFs",
        categories=25, cases=len(cases), reps=REPS, cap_s=CAP,
        arms=ARMS, cpu=cpu, one_logical_cpu=True,
        source_disjoint_with_tests_not_claimed=True,
        R28_R153_external_fallback_disabled=True,
        original_CNF_SAT_witness_verified=True,
        independent_UNSAT_proof_only_for_R28_R153_GF2=True,
        samples=[{k:c[k] for k in ("origin", "family", "index", "sha256", "vars", "nclauses")} for c in cases],
    )
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("G1_START " + json.dumps({k:manifest[k] for k in ("stage", "cases", "reps", "cap_s", "arms")}), flush=True)
    rows = []
    verdicts = {}
    with (ROOT / "trials.jsonl").open("w") as fd:
        for ci, c in enumerate(cases):
            for rep in range(REPS):
                shift = (ci + rep) % len(ARMS)
                for arm in ARMS[shift:] + ARMS[:shift]:
                    row = (run_extra(c, arm, rep) if arm in EXTRA_BIN else B.run(c, arm, rep))
                    row["shard"] = ci // 20
                    rows.append(row)
                    verdict = "SAT" if row["status"] == "SAT_VERIFIED" else (
                        "UNSAT" if row["status"] in ("UNSAT_GF2_VERIFIED", "UNSAT_UNVERIFIED") else None
                    )
                    if verdict:
                        old = verdicts.setdefault(c["sha256"], verdict)
                        if old != verdict:
                            raise RuntimeError("CROSS-SOLVER SAT/UNSAT CONTRADICTION " + c["sha256"])
                    fd.write(json.dumps(row, sort_keys=True) + "\n")
                    fd.flush()
                    print("G1_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    total = report(rows)
    assert all(x["trials"] == len(cases) * REPS for x in total.values()), "unequal trials"
    families = {family:report([r for r in rows if r["family"] == family]) for family in sorted({c["family"] for c in cases})}
    shards = {str(s):report([r for r in rows if r["shard"] == s]) for s in sorted({r["shard"] for r in rows})}
    ratios = {
        arm: {reference: round(total[reference]["PAR2_reported_s"] / max(1e-9, total[arm]["PAR2_reported_s"]), 4)
              for reference in ("Kissat", "CaDiCaL", "CryptoMiniSat")}
        for arm in ARMS if arm not in ("Kissat", "CaDiCaL", "CryptoMiniSat")
    }
    result = dict(manifest=manifest, total=total, families=families, shards=shards,
                  ratios_reported_PAR2=ratios)
    (ROOT / "summary.json").write_text(json.dumps(result, indent=2))
    print("G1_FINAL " + json.dumps(dict(stage=STAGE, total=total, ratios=ratios), sort_keys=True), flush=True)
    print("G1_AUDIT synthetic=true original_CNF_SHA=true SAT_model_verified=true "
          "UNSAT_GF2_replayed=true other_UNSAT_unverified=true "
          "single_cpu=true paired=true no_external_R28_fallback=true", flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fd:
            fd.write("## DRNAS GENERAL G1 — " + STAGE + "\n\n")
            fd.write("Synthetic only; 25 categories; E2E single logical CPU; original SHA tracked. "
                     "All UNSAT except GF(2) replayed source certificates remain unverified.\n\n")
            fd.write("| Arm | Reported solved | Verified SAT+GF2 UNSAT | Unverified UNSAT | PAR2 reported s | PAR2 verified s |\n")
            fd.write("|---|---:|---:|---:|---:|---:|\n")
            for name, x in sorted(total.items(), key=lambda a:a[1]["PAR2_reported_s"]):
                fd.write("| " + name + " | " + str(x["solved_reported"]) + "/" + str(x["trials"]) + " | " +
                         str(x["solved_verified"]) + " | " + str(x["UNSAT_unverified"]) + " | " +
                         str(x["PAR2_reported_s"]) + " | " + str(x["PAR2_verified_s"]) + " |\n")
            fd.write("\nDetailed 25-family results, five consecutive shards, and ratios are in summary.json.\n")

if __name__ == "__main__":
    main()
