#!/usr/bin/env python3
"""R200 prospective 24 SAT2026 non-main original CNFs; three CMS arms.
Precommitted candidate queue, source SHA exclusion, 30s total cap,
three repeated source-paired trials, SAT witness validation on original.
CDCL UNSAT independent LRAT is unavailable; do not claim general superiority.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, random, statistics, subprocess, time
import r192_gauss_first_cms_hybrid as old
import r193_certified_gauss_cms as certified

ROOT = pathlib.Path("r200")
SOURCE = pathlib.Path("r200/sources")
PROTO = "DRNAS-R200-CMS-24-SAT2026-NONMAIN-SOURCE-PAIRED-v1"
CAP = 30.0
REPS = 3
SHARDS = 6
MODES = ("cms_plain", "cms_r28", "cms_gf2_hybrid4")
BASES = ("cms_plain",)
certified.ROOT = ROOT
certified.CAP = CAP


def need(ok, msg):
    if not ok:
        raise RuntimeError("R200_FAIL_CLOSED " + str(msg))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def save(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def fetch_holdout():
    """Freeze 24 unused SAT2026 submissions before performing any solving."""
    import lzma, urllib.request
    candidates = json.loads((ROOT / "candidates.json").read_text())
    queue = candidates["cases"]
    groupset = ("xor_crypto", "hardware_software", "industrial_planning", "graph_csp")
    need(len(queue) == 82 and len({c["gbd_id"] for c in queue}) == 82,
         "preregistered source queue changed")
    source_exclude = set(candidates["excluded_source_sha256"])
    old_manifest = json.loads(pathlib.Path("r189/frozen/manifest.json").read_text())
    source_exclude.update(c["sha256"] for c in old_manifest["cases"])
    need(len(source_exclude) >= 79, "missing earlier SHA exclusions")
    SOURCE.mkdir(parents=True, exist_ok=True)
    selected, rejects, selected_sha = [], [], set()
    for group in groupset:
        n = 0
        for c in [x for x in queue if x["group"] == group]:
            if n == 6:
                break
            try:
                req = urllib.request.Request(c["url"],
                    headers={"User-Agent": "DRNAS-R200-prospective-SHA-freeze/1"})
                with urllib.request.urlopen(req, timeout=90) as f:
                    blob = f.read(candidates["max_compressed_bytes"] + 1)
                if len(blob) > candidates["max_compressed_bytes"]:
                    raise ValueError("compressed-size-budget")
                data = lzma.decompress(blob, memlimit=128 * 1024 * 1024)
                if len(data) > candidates["max_original_bytes"]:
                    raise ValueError("original-size-budget")
                if b"p cnf " not in data[:10000]:
                    raise ValueError("not-DIMACS")
                digest = hashlib.sha256(data).hexdigest()
                if digest in source_exclude or digest in selected_sha:
                    raise ValueError("SHA-exposed-or-duplicate")
                case = dict(c)
                case["sha256"] = digest
                case["bytes"] = len(data)
                case["compressed_bytes"] = len(blob)
                (SOURCE / (case["id"] + ".cnf")).write_bytes(data)
                selected.append(case)
                selected_sha.add(digest)
                n += 1
            except Exception as exc:
                rejects.append({"id": c["id"], "reason": str(exc)[:150]})
        need(n == 6, "cannot fill group " + group + " before outcomes")
    need(len(selected) == 24, "not 24 source CNFs")
    manifest = {k:v for k,v in candidates.items() if k != "cases"}
    manifest["cases"] = selected
    manifest["candidate_count"] = len(queue)
    manifest["source_rejections"] = rejects
    manifest["source_exclusion_checked"] = True
    save(ROOT / "manifest.json", manifest)
    save(ROOT / "selection-log.json", {"selected": [
        {"id":c["id"],"sha256":c["sha256"],"bytes":c["bytes"]}
        for c in selected], "rejected": rejects})
    print("R200_HOLDOUT_FROZEN", json.dumps({
        "sources":len(selected),
        "groups":dict(collections.Counter(c["group"] for c in selected)),
        "skipped":len(rejects),
        "status_counts":dict(collections.Counter(c["expected"] for c in selected)),
        "prior_SHA_disjoint":True,
        "manifest_sha256":sha(ROOT / "manifest.json")},sort_keys=True),flush=True)


def cases_and_groups():
    need((ROOT / "manifest.json").exists(), "missing frozen holdout manifest")
    m = json.loads((ROOT / "manifest.json").read_text())
    cases = m["cases"]
    need(len(cases) == 24 and len({c["sha256"] for c in cases}) == 40,
         "expected 24 source-unique frozen original CNFs")
    older = json.loads(pathlib.Path("r189/frozen/manifest.json").read_text())["cases"]
    oldsha = {c["sha256"] for c in older}
    need(not oldsha.intersection(c["sha256"] for c in cases),
         "R189/R194 old formula leaked into holdout")
    groupset = ("xor_crypto", "hardware_software", "industrial_planning", "graph_csp")
    need({c["group"] for c in cases} == set(groupset), "missing holdout cohorts")
    need(all(sum(c["group"] == g for c in cases) == 6 for g in groupset),
         "expected 6 cases per cohort")
    for c in cases:
        need(c["real"] is True and c["expected"] in ("SAT","UNSAT"),
             "invalid external case metadata")
        need(sha(SOURCE / (c["id"] + ".cnf")) == c["sha256"],
             "source file SHA changed: " + c["id"])
    pins = json.loads((ROOT / "pins.json").read_text())
    for path, digest in pins.items():
        need(sha(path) == digest, "R200 pin drift: " + path)
    groups = [[] for _ in range(SHARDS)]
    # Stratified, deterministic, source-disjoint 6-way partition.
    for category in groupset:
        for case in sorted((c for c in cases if c["group"] == category),
                           key=lambda c: c["sha256"]):
            target = min(range(SHARDS),
                         key=lambda s: (sum(c["group"] == category for c in groups[s]),
                                        len(groups[s]), s))
            groups[target].append(case)
    need(sum(map(len, groups)) == 24, "incomplete partition")
    need(len({c["sha256"] for g in groups for c in g}) == 24,
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
            "xor_rows": 0, "covered_clauses": 0, "residual_clauses": 0,
            "source_GF2_contradiction": False}
    route = None
    model = {}
    status = "TIMEOUT"
    proof = "CAP_TIMEOUT"
    if mode.endswith("_gf2_hybrid4"):
        # A non-interruptible Python GF(2) preprocessing loop may otherwise hang
        # the entire shard on unseen large inputs. Enforce the SAME overall cap.
        import signal
        class PreprocessBudgetExceeded(TimeoutError):
            pass
        def expire(_signum, _frame):
            raise PreprocessBudgetExceeded("R200 bounded GF2 preprocessing")
        old_handler = signal.signal(signal.SIGALRM, expire)
        try:
            remaining = max(0.001, CAP - (time.perf_counter() - started) - 0.10)
            signal.setitimer(signal.ITIMER_REAL, remaining)
            work, extra, decision = certified.certified_preprocess(
                source, "r193_hybrid4", rep, shard, started)
            meta.update(extra)
        except PreprocessBudgetExceeded:
            work, decision = source, "TIMEOUT"
            meta["preprocess_budget_exhausted"] = True
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, old_handler)
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
        "xor_rows": meta.get("xor_rows", 0),
        "covered_clauses": meta.get("covered_clauses", 0),
        "residual_clauses": meta.get("residual_clauses", 0),
        "added_total_clauses": meta.get("added_total_clauses", 0),
        "source_GF2_contradiction": meta.get("source_GF2_contradiction", False),
        "preprocess_s": meta.get("preprocess_s", 0),
        "source_original_sha256": case["sha256"],
    }
    print("R200_TRIAL", json.dumps(result, sort_keys=True), flush=True)
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
    print("R200_SHARD_PASS", index, len(results), flush=True)


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
    need(len(records) == 24 * REPS * len(MODES) == 216,
         "not 216 trials")
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
                           ("cms_gf2_hybrid4", "cms_plain")):
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
        "protocol": PROTO, "status": "R200_AUDIT_PASS",
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
        out.write("# R200: DRNAS certified structure across CMS and Kissat\n\n")
        out.write("6 parallel stratified source-disjoint shards, 24 SHA-locked original SAT2026 submissions "
                  "CNFs, 3 paired repeats, 3 arms, 30s total cap, 216 attempts. "
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
        out.write("\n## Two CMS host-vs-DRNAS comparisons (PAR-2)\n\n")
        out.write("| CMS + R28 | CMS + GF2 Hybrid4 |\n")
        out.write("|---|---|\n")
        comparisons = (("cms_r28", "cms_plain"), ("cms_gf2_hybrid4", "cms_plain"))
        tiles = []
        for mode, base in comparisons:
            host = totals["all"]["modes"][base]["PAR2_s"]
            candidate = totals["all"]["modes"][mode]["PAR2_s"]
            gain = 100.0 * (host - candidate) / host if host else 0.0
            tiles.append(("🟢 " if gain > 0.0001 else "🔴 " if gain < -0.0001
                          else "⚪ ") + f"{gain:+.2f}%".replace("++", "+"))
        out.write("| " + " | ".join(tiles) + " |\n\n")
        out.write("Positive means lower PAR-2 than plain host; negative means worse. "
                  "This is NOT a percent speedup on successful runtime alone.\n\n")
        out.write("\nInterpret with solved counts, paired wins/losses and formula-family breakdown, "
                  "not just aggregate PAR2. Do not claim a general win from this prospective cohort.\n")
    print("R200_FINAL", json.dumps({
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
    print("R200_SELFTEST_PASS", flush=True)


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
