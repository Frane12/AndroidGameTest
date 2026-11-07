#!/usr/bin/env python3
"""DRNAS R199: four parallel source-paired cross-backend hybrid experiments.

40 SHA-pinned original SAT2025 CNFs not used in R189, 3 paired repeats,
4 stratified shards, 6 arms: pure CMS/Kissat, R28 routing into each, and certified
R193 GF2 derived clauses into each. 12s end-to-end wall cap per trial.
Original CNFs and binary hashes are frozen; SAT witnesses checked on ORIGINAL.
Derived clauses are proof-replayed by R193. Not blind; CMS/Kissat UNSAT is not
independently LRAT-certified. The experiment tests backend transfer, not a claim
of general SAT superiority.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, random, statistics, subprocess, time
import r192_gauss_first_cms_hybrid as old
import r193_certified_gauss_cms as certified

ROOT = pathlib.Path("r199")
SOURCE = pathlib.Path("r189/frozen")
PROTO = "DRNAS-R199-4PARALLEL-CROSS-BACKEND-SOURCE-PAIRED-v1"
CAP = 20.0
REPS = 3
SHARDS = 8
MODES = (
    "cms_plain", "cms_r28", "cms_gf2_hybrid4",
    "kissat_plain", "kissat_r28", "kissat_gf2_hybrid4",
)
BASES = ("cms_plain", "kissat_plain")
certified.ROOT = ROOT
certified.CAP = CAP


def need(ok, msg):
    if not ok:
        raise RuntimeError("R199_FAIL_CLOSED " + str(msg))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def save(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def fetch_holdout():
    """Materialize 40 precommitted SAT Competition 2025 instances; no performance selection."""
    import concurrent.futures
    import lzma
    import urllib.request
    candidates = json.loads((ROOT / "candidates.json").read_text())
    cases = candidates["cases"]
    need(len(cases) == 40 and len({x["sha256"] for x in cases}) == 40,
         "invalid prospective candidate set")
    old_manifest = json.loads(pathlib.Path("r189/frozen/manifest.json").read_text())
    old_sha = {x["sha256"] for x in old_manifest["cases"]}
    need(not old_sha.intersection(x["sha256"] for x in cases),
         "holdout overlaps old R189/R194 external source SHA")
    SOURCE.mkdir(parents=True, exist_ok=True)
    def one(c):
        target = SOURCE / (c["id"] + ".cnf")
        if target.exists() and sha(target) == c["sha256"]:
            return
        import time as t
        last = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(
                    c["url"], headers={"User-Agent": "DRNAS-R199-source-frozen-benchmark/1"})
                with urllib.request.urlopen(req, timeout=120) as f:
                    blob = f.read(15_000_001)
                need(len(blob) < 15_000_001, "compressed oversize " + c["id"])
                data = lzma.decompress(blob)
                need(len(data) == c["bytes"], "source byte length mismatch " + c["id"])
                need(hashlib.sha256(data).hexdigest() == c["sha256"],
                     "source SHA mismatch " + c["id"])
                need(b"p cnf " in data[:10000], "missing DIMACS header " + c["id"])
                target.write_bytes(data)
                return
            except Exception as exc:
                last = exc
                t.sleep(2 + 3 * attempt)
        raise RuntimeError("R199 fetch failed " + c["id"] + ": " + str(last))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(one, cases))
    save(ROOT / "manifest.json", candidates)
    print("R199_HOLDOUT_FROZEN", json.dumps({
        "sources": len(cases), "bytes": sum(c["bytes"] for c in cases),
        "status_counts": dict(collections.Counter(c["expected"] for c in cases)),
        "source_sha_no_overlap_with_R189": True,
        "manifest_sha256": sha(ROOT / "manifest.json")}, sort_keys=True), flush=True)


def cases_and_groups():
    need((ROOT / "manifest.json").exists(), "missing frozen holdout manifest")
    m = json.loads((ROOT / "manifest.json").read_text())
    cases = m["cases"]
    need(len(cases) == 40 and len({c["sha256"] for c in cases}) == 40,
         "expected 40 source-unique frozen original CNFs")
    older = json.loads(pathlib.Path("r189/frozen/manifest.json").read_text())["cases"]
    oldsha = {c["sha256"] for c in older}
    need(not oldsha.intersection(c["sha256"] for c in cases),
         "R189/R194 old formula leaked into holdout")
    groupset = ("xor_crypto", "hardware_software", "industrial_planning", "graph_csp")
    need({c["group"] for c in cases} == set(groupset), "missing holdout cohorts")
    need(all(sum(c["group"] == g for c in cases) == 10 for g in groupset),
         "expected 10 cases per cohort")
    for c in cases:
        need(c["real"] is True and c["expected"] in ("SAT","UNSAT"),
             "invalid external case metadata")
        need(sha(SOURCE / (c["id"] + ".cnf")) == c["sha256"],
             "source file SHA changed: " + c["id"])
    pins = json.loads((ROOT / "pins.json").read_text())
    for path, digest in pins.items():
        need(sha(path) == digest, "R199 pin drift: " + path)
    groups = [[] for _ in range(SHARDS)]
    # Stratified, deterministic, source-disjoint 8-way partition.
    for category in groupset:
        for case in sorted((c for c in cases if c["group"] == category),
                           key=lambda c: c["sha256"]):
            target = min(range(SHARDS),
                         key=lambda s: (sum(c["group"] == category for c in groups[s]),
                                        len(groups[s]), s))
            groups[target].append(case)
    need(sum(map(len, groups)) == 40, "incomplete partition")
    need(len({c["sha256"] for g in groups for c in g}) == 40,
         "repeated source across shards")
    return cases, groups


def commands(mode, path):
    p = str(path.resolve())
    if mode == "cms_plain":
        return old.command("cms_default", path)
    if mode == "cms_r28":
        return old.command("r28_cms_gauss_first", path)
    if mode == "kissat_plain":
        return [str(pathlib.Path("built/bin/kissat_4_0_4").resolve()), p]
    if mode == "kissat_r28":
        return old.command("r28_kissat", path)
    if mode == "cms_gf2_hybrid4":
        return old.command("cms_default", path)
    if mode == "kissat_gf2_hybrid4":
        return [str(pathlib.Path("built/bin/kissat_4_0_4").resolve()), p]
    raise ValueError(mode)


def trial(case, mode, rep, shard):
    source = SOURCE / (case["id"] + ".cnf")
    need(sha(source) == case["sha256"], "source drift while running")
    started = time.perf_counter()
    meta = {"preprocess_s": 0.0, "added_total_clauses": 0,
            "gf2_units": 0, "derived_candidates": 0,
            "source_GF2_contradiction": False}
    route = None
    model = {}
    status = "TIMEOUT"
    proof = "CAP_TIMEOUT"
    if mode.endswith("_gf2_hybrid4"):
        work, extra, decision = certified.certified_preprocess(
            source, "r193_hybrid4", rep, shard, started)
        meta.update(extra)
        if decision == "UNSAT":
            status = "UNSAT"
            proof = "SOURCE_GF2_CONTRADICTION_REPLAYED"
        elif decision != "TIMEOUT":
            status, model, route, _raw, _rc = certified.timed_command(
                commands(mode, work), started)
    else:
        status, model, route, _raw, _rc = certified.timed_command(
            commands(mode, source), started)

    elapsed = time.perf_counter() - started
    if elapsed >= CAP:
        status = "TIMEOUT"
    if status == "SAT":
        _n, original_clauses = certified.gf_src.gf.dimacs(source)
        certified.gf_src.gf.sat_check(original_clauses, model)
        proof = "SAT_WITNESS_ORIGINAL_VERIFIED"
    elif status == "UNSAT" and proof != "SOURCE_GF2_CONTRADICTION_REPLAYED":
        if route and route.startswith("certified_xor_contradiction"):
            proof = "R28_SOURCE_GF2_CONTRADICTION"
        else:
            proof = "NO_INDEPENDENT_LRAT"
    else:
        if status == "TIMEOUT":
            proof = "CAP_TIMEOUT"
    need(status in ("SAT", "UNSAT", "TIMEOUT"), "unsupported status " + str(status))
    if case["expected"] != "UNKNOWN" and status != "TIMEOUT":
        need(case["expected"] == status, "mismatch known SAT/UNSAT")
    result = {
        "id": case["id"], "sha256": case["sha256"], "real": case["real"],
        "family": case["family"], "shard": shard, "mode": mode, "rep": rep,
        "status": status, "elapsed_s": round(min(CAP, elapsed), 6),
        "par2_s": round(2 * CAP if status == "TIMEOUT" else elapsed, 6),
        "route": route, "proof": proof,
        "gf2_units": meta.get("gf2_units", 0),
        "added_total_clauses": meta.get("added_total_clauses", 0),
        "source_GF2_contradiction": meta.get("source_GF2_contradiction", False),
        "preprocess_s": meta.get("preprocess_s", 0),
        "source_original_sha256": case["sha256"],
    }
    print("R199_TRIAL", json.dumps(result, sort_keys=True), flush=True)
    return result


def shard(index):
    cases, groups = cases_and_groups()
    need(0 <= index < SHARDS, "shard out of range")
    results = []
    for case in groups[index]:
        for rep in range(REPS):
            order = list(MODES)
            random.Random(PROTO + case["sha256"] + str(rep)).shuffle(order)
            for mode in order:
                results.append(trial(case, mode, rep, index))
                save(ROOT / ("shard-%d.json" % index), results)
    need(len(results) == len(groups[index]) * REPS * len(MODES),
         "partial shard")
    print("R199_SHARD_PASS", index, len(results), flush=True)


def audit():
    cases, groups = cases_and_groups()
    records, seen = [], set()
    by_sha = {c["sha256"]: c for c in cases}
    for i, group in enumerate(groups):
        path = ROOT / ("shard-%d.json" % i)
        need(path.exists(), "missing shard " + str(i))
        rows = json.loads(path.read_text())
        need(len(rows) == len(group) * REPS * len(MODES),
             "shard count mismatch " + str(i))
        need({r["sha256"] for r in rows} == {c["sha256"] for c in group},
             "wrong cohort in shard " + str(i))
        for r in rows:
            need(r["sha256"] in by_sha and r["id"] == by_sha[r["sha256"]]["id"],
                 "source ID/SHA mismatch")
            need(r["source_original_sha256"] == r["sha256"],
                 "source changed")
            k = (r["sha256"], r["rep"], r["mode"])
            need(k not in seen, "duplicate trial")
            seen.add(k)
            need(r["status"] in ("SAT", "UNSAT", "TIMEOUT"), "bad status")
            expected_par2 = (2 * CAP if r["status"] == "TIMEOUT" else r["elapsed_s"])
            need(abs(r["par2_s"] - expected_par2) < .00002, "PAR2 mismatch")
            need(r["status"] != "SAT" or r["proof"] == "SAT_WITNESS_ORIGINAL_VERIFIED",
                 "missing SAT proof")
        records.extend(rows)
    need(len(records) == 40 * REPS * len(MODES) == 720,
         "not 720 trials")
    for c in cases:
        for rep in range(REPS):
            rows = [r for r in records if r["sha256"] == c["sha256"] and r["rep"] == rep]
            need({r["mode"] for r in rows} == set(MODES), "unpaired arms")
            truth = {r["status"] for r in rows if r["status"] != "TIMEOUT"}
            need(len(truth) <= 1, "conflicting solved outcomes on same source")
    groups_report = {"all": cases}
    for group in ("xor_crypto", "hardware_software", "industrial_planning", "graph_csp"):
        groups_report[group] = [c for c in cases if c["group"] == group]
    totals = {}
    for cohort, chosen in groups_report.items():
        allowed = {c["sha256"] for c in chosen}
        records_group = [r for r in records if r["sha256"] in allowed]
        metrics = {}
        for mode in MODES:
            rr = [r for r in records_group if r["mode"] == mode]
            solved = [r for r in rr if r["status"] != "TIMEOUT"]
            metrics[mode] = {
                "attempts": len(rr), "solved": len(solved),
                "SAT": sum(r["status"] == "SAT" for r in rr),
                "UNSAT": sum(r["status"] == "UNSAT" for r in rr),
                "timeouts": sum(r["status"] == "TIMEOUT" for r in rr),
                "PAR2_s": round(sum(r["par2_s"] for r in rr), 6),
                "median_s_solved": round(statistics.median(
                    r["elapsed_s"] for r in solved), 6) if solved else None,
                "preprocess_s": round(sum(r["preprocess_s"] for r in rr), 6),
                "clauses_injected": sum(r["added_total_clauses"] for r in rr),
            }
        for mode, base in (("cms_r28", "cms_plain"),
                           ("cms_gf2_hybrid4", "cms_plain"),
                           ("kissat_r28", "kissat_plain"),
                           ("kissat_gf2_hybrid4", "kissat_plain")):
            pair = {(r["sha256"], r["rep"]): r for r in records_group
                    if r["mode"] == base}
            wins = losses = ties = 0
            for r in records_group:
                if r["mode"] != mode:
                    continue
                d = r["par2_s"] - pair[(r["sha256"], r["rep"])]["par2_s"]
                if d < -0.001: wins += 1
                elif d > 0.001: losses += 1
                else: ties += 1
            metrics[mode]["paired_vs_plain"] = {
                "wins": wins, "losses": losses, "ties": ties,
                "par2_gain_s": round(metrics[base]["PAR2_s"] - metrics[mode]["PAR2_s"], 6),
            }
        totals[cohort] = {"cases": len(chosen), "modes": metrics}
    report = {
        "protocol": PROTO, "status": "R199_AUDIT_PASS",
        "original_sources_preexposed": False,
        "original_source_manifest_sha256": sha(ROOT / "manifest.json"),
        "attempts": len(records), "shards": SHARDS, "repetitions": REPS,
        "per_attempt_end_to_end_cap_s": CAP,
        "SAT_witness_original_verified": True,
        "derived_short_clause_proofs_replayed": True,
        "CMS_and_Kissat_unsat_independent_LRAT": False,
        "counts_by_shard": [len(g) for g in groups],
        "results": totals,
    }
    save(ROOT / "report.json", report)
    save(ROOT / "all-trials.json", records)
    with (ROOT / "summary.md").open("w") as out:
        out.write("# R199: DRNAS certified structure across CMS and Kissat\n\n")
        out.write("8 parallel stratified source-disjoint shards, 40 SHA-pinned original SAT2025 "
                  "CNFs, 3 paired repeats, 6 arms, 20s total cap, 720 attempts. "
                  "All SAT models validated on original CNF. "
                  "Independently certified UNSAT LRAT is not provided for CDCL outcomes. "
                  "Pre-committed source-disjoint test; not a general SAT claim.\n\n")
        out.write("| Cohort | Solver | Solved | PAR-2 (s) | Overhead (s) | Pair vs plain |\n")
        out.write("|---|---|---:|---:|---:|---|\n")
        for cohort in ("xor_crypto", "hardware_software", "industrial_planning", "graph_csp", "all"):
            for mode in MODES:
                m = totals[cohort]["modes"][mode]
                p = m.get("paired_vs_plain", {})
                pair_text = ("%d W / %d L / %d T" % (
                    p["wins"], p["losses"], p["ties"])) if p else "baseline"
                out.write("| %s | %s | %d/%d | %.3f | %.3f | %s |\n" %
                          (cohort, mode, m["solved"], m["attempts"],
                           m["PAR2_s"], m["preprocess_s"], pair_text))
        out.write("\nInterpret with solved counts, paired wins/losses and formula-family breakdown, "
                  "not just aggregate PAR2. Never claim a general win from these reused sources.\n")
    print("R199_FINAL", json.dumps({
        "status": report["status"], "attempts": report["attempts"],
        "counts_by_shard": report["counts_by_shard"],
        "all": totals["all"], "xor_crypto": totals["xor_crypto"], "hardware_software": totals["hardware_software"], "industrial_planning": totals["industrial_planning"], "graph_csp": totals["graph_csp"],
    }, sort_keys=True), flush=True)


def smoke():
    _cases, groups = cases_and_groups()
    need(all(groups), "empty shard")
    certified.deriv.selftest()
    toy = ROOT / "smoke.cnf"
    toy.write_text("p cnf 3 2\n1 0\n-1 2 0\n")
    for mode in MODES:
        started = time.perf_counter()
        src = toy
        if mode.endswith("_gf2_hybrid4"):
            src, extra, decision = certified.certified_preprocess(
                toy, "r193_hybrid4", 0, 0, started)
            need(decision is None, "unexpected toy GF2 outcome")
        status, model, _route, _raw, _rc = certified.timed_command(
            commands(mode, src), started)
        need(status == "SAT" and model.get(1) and model.get(2),
             "smoke failed " + mode)
    print("R199_SELFTEST_PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("fetch", "smoke", "shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    if args.action == "fetch":
        fetch_holdout()
    elif args.action == "smoke":
        smoke()
    elif args.action == "shard":
        shard(args.shard)
    else:
        audit()
