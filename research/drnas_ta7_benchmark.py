#!/usr/bin/env python3
"""TA7 prospective cross-version confirmation on 24 new official SAT2026 CNFs.
Eight frozen arms: CMS plain, Kissat plain/R28, frozen TA3, frozen TA6 guarded,
TA7 guarded, explore and shadow, all on identical original SHA sources. All on identical
original SHA bytes, 3 repetitions, 20s end-to-end cap, source-cluster bootstrap.
This is unofficial and not guaranteed globally unseen; standard LRAT checking
of generic CDCL UNSAT is outside this experiment.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, lzma, os, pathlib, random, re
import signal, statistics, subprocess, time, urllib.request

import drnas_ta7_stratified_selector as router
import drnas_ta6_router as ta6_router
import r199_unseen_mixed40_crossbackend as r199
import drnas_ta3_adaptive_selector as ta3
import r164_pure_exact_gf2 as exact
import r165_component_benchmark as native

ROOT = pathlib.Path("ta7")
SOURCE = ROOT / "sources"
PROTO = "DRNAS-TA7-2026-DISJOINT24-8ARMS-3REPS-20S-v1"
CAP = 20.0
REPS = 3
SHARDS = 8
MODES = ("cms_plain", "kissat_plain", "kissat_r28",
         "ta3_portfolio", "ta6_guarded",
         "ta7_guarded", "ta7_explore", "ta7_shadow")
REFERENCE = {"kissat_r28": "kissat_plain",
             "ta3_portfolio": "cms_plain",
             "ta6_guarded": "ta3_portfolio",
             "ta7_guarded": "ta3_portfolio",
             "ta7_explore": "ta3_portfolio",
             "ta7_shadow": "ta3_portfolio"}
R165_BIN_SHA = "f57e68640f576d2fe5ad541e343ba958d861d7ac1e5c7c37e0022ec3d088719e"
r199.ROOT = ROOT
r199.SOURCE = SOURCE
r199.CAP = CAP
r199.PROTO = PROTO
r199.certified.ROOT = ROOT
r199.certified.CAP = CAP

def need(yes, message):
    if not yes:
        raise RuntimeError("TA7_FAIL_CLOSED " + str(message))

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")

def existing():
    known = set()
    ids = set()
    for path in ("r189/frozen/manifest.json", "r199/candidates.json",
                 "ta3_2026/manifest.json", "ta3/candidates.json",
                 "r200/manifest.json", "ta6/manifest.json"):
        p = pathlib.Path(path)
        if not p.exists():
            if path == "ta3/candidates.json":
                continue
            need(False, "missing prior manifest " + path)
        for case in json.loads(p.read_text())["cases"]:
            known.add(case["sha256"])
            ids.add(case["id"].split("-")[0])
    exclusions = json.loads(pathlib.Path("ta3_2026/excluded_hashes.json").read_text())
    known.update(exclusions["sha256"])
    return known, ids

def fetch():
    """Selection uses only frozen original-source queue, sizes and exclusions."""
    queue = json.loads(pathlib.Path("ta3_2026/preregistration.json").read_text())
    urls = queue["source_queue"]
    need(len(urls) == 400 and len(set(urls)) == 400,
         "official SAT2026 queue not frozen at 400")
    previous, previous_ids = existing()
    cap_comp = queue["max_compressed_bytes"]
    cap_raw = queue["max_original_bytes"]
    SOURCE.mkdir(parents=True, exist_ok=True)
    accepted, skipped = [], []
    for url in urls:
        if len(accepted) >= 24:
            break
        ident = url.rsplit("/", 1)[-1]
        need(bool(re.fullmatch(r"https://benchmark-database\.de/file/[0-9a-f]{32}", url)),
             "unknown official URL")
        if ident in previous_ids:
            skipped.append({"id": ident, "reason": "known_source_id"})
            continue
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "DRNAS-TA7-frozen-2026-source-only/1"})
            with urllib.request.urlopen(request, timeout=45) as response:
                size = int(response.headers.get("Content-Length") or "0")
                need(size <= cap_comp, "compressed source too large")
                compressed = response.read(cap_comp + 1)
            need(0 < len(compressed) <= cap_comp, "compressed file size")
            decoder = lzma.LZMADecompressor()
            raw = decoder.decompress(compressed, max_length=cap_raw + 1)
            need(decoder.eof and 0 < len(raw) <= cap_raw, "raw source size/completeness")
            header = re.search(rb"(?m)^p\s+cnf\s+(\d+)\s+(\d+)\s*$", raw[:8192])
            need(header is not None, "no DIMACS original CNF")
            variables, clauses = int(header[1]), int(header[2])
            need(0 < variables <= 150000 and 0 < clauses <= 160000,
                 "source limits exceeded")
            h = hashlib.sha256(raw).hexdigest()
            need(h not in previous, "historical SHA overlap")
            need(h not in {x["sha256"] for x in accepted}, "duplicate source SHA")
            (SOURCE / (ident + ".cnf")).write_bytes(raw)
            accepted.append(dict(id=ident, url=url, sha256=h, bytes=len(raw),
                variables=variables, clauses=clauses, expected="UNKNOWN", real=True,
                family="official-2026-" + ident[:12],
                group="bucket_" + "abcd"[len(accepted) % 4]))
            print("TA7_NEW_SOURCE", ident, h, flush=True)
        except Exception as err:
            skipped.append({"id": ident, "reason": str(err)[:140]})
            print("TA7_SOURCE_SKIP", ident, str(err)[:100], flush=True)
    need(len(accepted) == 24, "not enough eligible new official 2026 sources")
    save(ROOT / "manifest.json", dict(protocol=PROTO, cases=accepted,
        skipped=skipped, selection_uses_results=False,
        sources_disjoint_from_R189_R199_TA3_2026_R200_TA6_and_known_exclusions=True,
        not_globally_blind=True))
    print("TA7_HOLDOUT_FROZEN", json.dumps({
        "cases": len(accepted), "queue_size": len(urls),
        "manifest_sha256": digest(ROOT / "manifest.json"),
        "historical_exclusions": len(previous)}, sort_keys=True), flush=True)

def cases_groups():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    need(manifest["protocol"] == PROTO, "protocol drift")
    cases = manifest["cases"]
    need(len(cases) == 24 and len({c["sha256"] for c in cases}) == 24,
         "24 unique original sources required")
    old, _ = existing()
    need(not old.intersection(c["sha256"] for c in cases), "source leakage")
    for c in cases:
        need(digest(SOURCE / (c["id"] + ".cnf")) == c["sha256"],
             "original source drift")
    pins = json.loads((ROOT / "pins.json").read_text())
    for path, h in pins.items():
        need(digest(path) == h, "binary/source pin drift " + path)
    groups = [[] for _ in range(SHARDS)]
    for i, c in enumerate(sorted(cases, key=lambda x:x["sha256"])):
        groups[i % SHARDS].append(c)
    need(all(len(g) == 3 for g in groups), "unbalanced shards")
    return cases, groups

def run_trial(case, mode, rep, shard):
    if mode in r199.MODES:
        row = r199.trial(case, mode, rep, shard)
        row["group"] = case["group"]
        return row
    src = SOURCE / (case["id"] + ".cnf")
    need(digest(src) == case["sha256"], "trial SHA drift")
    start = time.perf_counter()
    status, proof, selected, route = "TIMEOUT", "CAP_TIMEOUT", mode, None
    region_stats = None
    if mode in ("ta3_portfolio", "ta6_guarded", "ta7_guarded", "ta7_explore", "ta7_shadow"):
        signal_timed_out = False
        def alarm(_sig, _frame):
            raise TimeoutError("TA7 bounded source profiling cap")
        prior = signal.signal(signal.SIGALRM, alarm)
        try:
            signal.setitimer(signal.ITIMER_REAL, CAP - .10)
            features = ta3.fast_features(src)
            if mode == "ta3_portfolio":
                selected, route = ta3.decision(features, "ta2_portfolio")
            elif mode == "ta6_guarded":
                selected, route = ta6_router.route(features, mode)
            else:
                selected, route, region_stats = router.select(src, features, mode)
        except TimeoutError:
            signal_timed_out = True
            route = "profile_timeout"
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, prior)
        if not signal_timed_out and time.perf_counter() - start < CAP - .10:
            status, model, backend_route, _raw, _rc = r199.certified.timed_command(
                ta3.command(selected, src), start)
            if status == "SAT":
                _n, clauses = r199.certified.gf_src.gf.dimacs(src)
                r199.certified.gf_src.gf.sat_check(clauses, model)
                proof = "SAT_WITNESS_ORIGINAL_VERIFIED"
            elif status == "UNSAT":
                proof = ("R28_SOURCE_GF2_CONTRADICTION" if backend_route and
                         backend_route.startswith("certified_xor_contradiction")
                         else "NO_INDEPENDENT_LRAT")
    else:
        need(False, "unknown benchmark arm")
    elapsed = min(CAP, time.perf_counter() - start)
    if elapsed >= CAP:
        status, proof = "TIMEOUT", "CAP_TIMEOUT"
    need(status in ("SAT", "UNSAT", "TIMEOUT"), "invalid status")
    row = dict(protocol=PROTO, id=case["id"], sha256=case["sha256"],
        source_original_sha256=case["sha256"], family=case["family"],
        group=case["group"], real=True, mode=mode, selected=selected,
        route=route, rep=rep, shard=shard, status=status,
        elapsed_s=round(elapsed, 6),
        par2_s=round(2 * CAP if status == "TIMEOUT" else elapsed, 6),
        proof=proof)
    if region_stats is not None:
        row["region_profile"] = region_stats
    print("TA7_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    return row

def shard(index):
    _cases, groups = cases_groups()
    need(0 <= index < SHARDS, "invalid shard")
    if hasattr(os, "sched_getaffinity"):
        mask = os.sched_getaffinity(0)
        if mask:
            os.sched_setaffinity(0, {min(mask)})
    rows = []
    for case in groups[index]:
        for rep in range(REPS):
            order = list(MODES)
            random.Random(PROTO + case["sha256"] + str(rep)).shuffle(order)
            for mode in order:
                row = run_trial(case, mode, rep, index)
                rows.append(row)
                save(ROOT / ("shard-%d.json" % index), rows)
    need(len(rows) == 3 * REPS * len(MODES), "partial shard")
    print("TA7_SHARD_PASS", index, len(rows), flush=True)

def audit():
    cases, groups = cases_groups()
    seen, rows = set(), []
    for idx, group in enumerate(groups):
        path = ROOT / ("shard-%d.json" % idx)
        need(path.is_file(), "missing shard")
        subset = json.loads(path.read_text())
        need(len(subset) == len(group) * REPS * len(MODES), "incomplete shard")
        need({r["sha256"] for r in subset} == {c["sha256"] for c in group},
             "shard source drift")
        for row in subset:
            k = (row["sha256"], row["rep"], row["mode"])
            need(k not in seen, "duplicate paired trial")
            seen.add(k)
            need(row["source_original_sha256"] == row["sha256"],
                 "trial SHA mismatch")
            need(row["status"] in ("SAT", "UNSAT", "TIMEOUT"), "invalid result")
            expected = 2*CAP if row["status"] == "TIMEOUT" else row["elapsed_s"]
            need(abs(expected - row["par2_s"]) <= .00002, "PAR2 rule violated")
            need(row["status"] != "SAT" or "VERIFIED" in row["proof"] or
                 "MODEL_CHECKED" in row["proof"], "SAT witness not verified")
        rows.extend(subset)
    need(len(rows) == 24*REPS*len(MODES) == 576, "wrong total trials")
    for c in cases:
        for rep in range(REPS):
            pair = [r for r in rows if r["sha256"] == c["sha256"] and r["rep"] == rep]
            need({r["mode"] for r in pair} == set(MODES), "missing mode")
            need(len({r["status"] for r in pair if r["status"] != "TIMEOUT"}) <= 1,
                 "contradicting solver verdicts")
    metrics = {}
    for mode in MODES:
        s = [r for r in rows if r["mode"] == mode]
        metrics[mode] = dict(
            PAR2_s=round(sum(r["par2_s"] for r in s), 6),
            solved=sum(r["status"] != "TIMEOUT" for r in s),
            SAT=sum(r["status"] == "SAT" for r in s),
            UNSAT=sum(r["status"] == "UNSAT" for r in s),
            timeouts=sum(r["status"] == "TIMEOUT" for r in s),
            attempts=len(s))
    by_key = {(r["sha256"], r["rep"], r["mode"]):r for r in rows}
    for mode, base in REFERENCE.items():
        wins = losses = ties = 0
        for c in cases:
            for rep in range(REPS):
                delta = by_key[c["sha256"],rep,mode]["par2_s"] - by_key[c["sha256"],rep,base]["par2_s"]
                if delta < -.001: wins += 1
                elif delta > .001: losses += 1
                else: ties += 1
        metrics[mode]["vs_" + base] = dict(wins=wins, losses=losses, ties=ties,
            ratio=round(metrics[base]["PAR2_s"]/metrics[mode]["PAR2_s"], 6),
            gain_s=round(metrics[base]["PAR2_s"]-metrics[mode]["PAR2_s"], 6))
    # Source-cluster bootstrap, resample 24 complete 3-repetition clusters.
    rng = random.Random(20261107)
    ci = {}
    for mode, base in REFERENCE.items():
        per_case = [(sum(by_key[c["sha256"],rep,base]["par2_s"] for rep in range(REPS)),
                     sum(by_key[c["sha256"],rep,mode]["par2_s"] for rep in range(REPS)))
                    for c in cases]
        dist = []
        for _ in range(2000):
            chosen = [per_case[rng.randrange(len(per_case))] for _ in cases]
            candidate = sum(pair[1] for pair in chosen)
            if candidate > 0:
                dist.append(sum(pair[0] for pair in chosen)/candidate)
        dist.sort()
        ci[mode] = dict(baseline=base, low95=round(dist[int(.025*len(dist))], 5),
                        high95=round(dist[int(.975*len(dist))], 5))
    selector_routes = {}
    for mode in ("ta3_portfolio", "ta6_guarded", "ta7_guarded",
                 "ta7_explore", "ta7_shadow"):
        rs = [row for row in rows if row["mode"] == mode]
        selector_routes[mode] = dict(
            selected={k:sum(row["selected"]==k for row in rs)
                      for k in ("cms_plain", "cms_r28", "kissat_plain", "kissat_r28")},
            route_reasons=dict(collections.Counter(row.get("route") for row in rs)),
            mean_region_scan_ms=round(
                sum(row.get("region_profile", {}).get("scan_ms", 0) for row in rs)
                / len(rs), 5))
    old = {(row["sha256"],row["rep"]):row["selected"]
           for row in rows if row["mode"]=="ta3_portfolio"}
    decision_changes = {
        mode:sum(row["selected"]!=old[row["sha256"],row["rep"]]
                 for row in rows if row["mode"]==mode)
        for mode in ("ta6_guarded", "ta7_guarded", "ta7_explore", "ta7_shadow")}
    result = dict(protocol=PROTO, status="TA7_AUDIT_PASS", sources=24,
        selector_routes=selector_routes, changed_decisions_from_TA3=decision_changes,
        attempts=len(rows), repetitions=REPS, cap_s=CAP,
        external_new_source_SAT_witness_verified=True,
        original_source_SHA_disjoint_from_known_exclusions=True,
        excluded_prior_R200_and_TA6_source_manifests=True,
        selector_precommitted_before_new_source_runs=True,
        CDCL_generic_UNSAT_independent_LRAT=False,
        not_globally_blind=True, modes=metrics, bootstrap95=ci)
    save(ROOT / "report.json", result)
    save(ROOT / "all-trials.json", rows)
    lines = ["# TA7 three-region structural selector vs TA3, TA6, and plain solvers", "",
             "24 next source-disjoint official SAT2026 originals, 8 frozen arms, 3 reps, 20s cap.",
             "Same original CNFs, source SHA checked, SAT model verified; generic CDCL UNSAT",
             "is NOT independently LRAT verified. Source set is disjoint from known",
             "prior R200, TA6 and TA3 manifests; it is not globally blind.", "",
             "| Mode | Solved/72 | PAR-2 seconds | Ratio vs host | W/L/T | 95% bootstrap |",
             "|---|---:|---:|---:|---|---|"]
    for mode in MODES:
        m = metrics[mode]
        base = REFERENCE.get(mode)
        p = m.get("vs_" + base) if base else None
        b = ci.get(mode)
        lines.append("| %s | %d/72 | %.3f | %s | %s | %s |" % (
            mode, m["solved"], m["PAR2_s"],
            ("%.3f×" % p["ratio"]) if p else "reference",
            ("%d/%d/%d" % (p["wins"], p["losses"], p["ties"])) if p else "—",
            ("[%.3f, %.3f]" % (b["low95"], b["high95"])) if b else "—"))
    lines += ["", "Ratio = reference PAR-2 / candidate PAR-2, not CPU-time",
              "speedup on an individual solved instance. A ratio above 1 favors",
              "the candidate. Do not generalize when the bootstrap interval includes 1."]
    (ROOT / "report.md").write_text("\n".join(lines) + "\n")
    print("TA7_FINAL", json.dumps(result, sort_keys=True), flush=True)

def smoke():
    cases, groups = cases_groups()
    r199.certified.deriv.selftest()
    exact.selftest()
    ta6_router.selftest()
    router.selftest()
    toy = dict(id="ta7_smoke", sha256="", expected="SAT", real=True,
               family="toy", group="bucket_a")
    path = SOURCE / "ta7_smoke.cnf"
    path.write_text("p cnf 3 2\n1 0\n-1 2 0\n")
    toy["sha256"] = digest(path)
    for mode in MODES:
        row = run_trial(toy, mode, 0, 0)
        need(row["status"] == "SAT", "smoke failed " + mode)
    path.unlink()
    print("TA7_SELFTEST_PASS", len(MODES), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("fetch","smoke","shard","audit"))
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    {"fetch":fetch,"smoke":smoke,"shard":lambda:shard(args.shard),"audit":audit}[args.action]()
