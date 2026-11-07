#!/usr/bin/env python3
"""TA8 bounded source-certified XOR pretest on 12 new original SAT2026 CNFs.
Six frozen arms: plain CMS/Kissat, certified R28,
frozen TA3, classify-only certified proof active and shadow. Identical
original SHA bytes, 2 repetitions, 10s end-to-end cap, source-cluster bootstrap.
This is unofficial and not guaranteed globally unseen; standard LRAT checking
of generic CDCL UNSAT is outside this experiment.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, lzma, os, pathlib, random, re
import signal, statistics, subprocess, time, urllib.request

import drnas_ta8_certified_xor_probe as pilot
import r199_unseen_mixed40_crossbackend as r199
import drnas_ta3_adaptive_selector as ta3
import r164_pure_exact_gf2 as exact
import r165_component_benchmark as native

ROOT = pathlib.Path("ta8")
SOURCE = ROOT / "sources"
PROTO = "DRNAS-TA8-2026-NEW12-PROOF-6ARMS-2REPS-10S-v1"
CAP = 10.0
REPS = 2
SHARDS = 3
MODES = ("cms_plain", "kissat_plain", "kissat_r28",
         "ta3_portfolio", "ta8_certified_pretest", "ta8_shadow_pretest")
REFERENCE = {"kissat_r28": "kissat_plain",
             "ta3_portfolio": "cms_plain",
             "ta8_certified_pretest": "ta3_portfolio",
             "ta8_shadow_pretest": "ta3_portfolio"}
R165_BIN_SHA = "f57e68640f576d2fe5ad541e343ba958d861d7ac1e5c7c37e0022ec3d088719e"
r199.ROOT = ROOT
r199.SOURCE = SOURCE
r199.CAP = CAP
r199.PROTO = PROTO
r199.certified.ROOT = ROOT
r199.certified.CAP = CAP

def need(yes, message):
    if not yes:
        raise RuntimeError("TA8_FAIL_CLOSED " + str(message))

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
                 "r200/manifest.json", "ta6/manifest.json",
                 "ta7exclusions/ta7-manifest.json",
                 "ta7h_exclusions/ta7h-manifest.json"):
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
        if len(accepted) >= 12:
            break
        ident = url.rsplit("/", 1)[-1]
        need(bool(re.fullmatch(r"https://benchmark-database\.de/file/[0-9a-f]{32}", url)),
             "unknown official URL")
        if ident in previous_ids:
            skipped.append({"id": ident, "reason": "known_source_id"})
            continue
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "DRNAS-TA8-frozen-2026-source-only/1"})
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
            print("TA8_NEW_SOURCE", ident, h, flush=True)
        except Exception as err:
            skipped.append({"id": ident, "reason": str(err)[:140]})
            print("TA8_SOURCE_SKIP", ident, str(err)[:100], flush=True)
    need(len(accepted) == 12, "not enough eligible new official 2026 sources")
    save(ROOT / "manifest.json", dict(protocol=PROTO, cases=accepted,
        skipped=skipped, selection_uses_results=False,
        sources_disjoint_from_R189_R199_TA3_2026_R200_TA6_TA7_TA7H_and_known_exclusions=True,
        not_globally_blind=True))
    print("TA8_HOLDOUT_FROZEN", json.dumps({
        "cases": len(accepted), "queue_size": len(urls),
        "manifest_sha256": digest(ROOT / "manifest.json"),
        "historical_exclusions": len(previous)}, sort_keys=True), flush=True)

def cases_groups():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    need(manifest["protocol"] == PROTO, "protocol drift")
    cases = manifest["cases"]
    need(len(cases) == 12 and len({c["sha256"] for c in cases}) == 12,
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
    need(all(len(g) == 4 for g in groups), "unbalanced shards")
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
    if mode in ("ta3_portfolio", "ta8_certified_pretest", "ta8_shadow_pretest"):
        signal_timed_out = False
        def alarm(_sig, _frame):
            raise TimeoutError("TA8 bounded source profiling cap")
        prior = signal.signal(signal.SIGALRM, alarm)
        try:
            signal.setitimer(signal.ITIMER_REAL, CAP - .10)
            # Never promote a guessed XOR signature. The classify-only pilot
            # must produce a source-CNF-replayed contradiction before UNSAT.
            if mode != "ta3_portfolio":
                remaining = CAP - (time.perf_counter() - start)
                pilot_result = pilot.classify(src, min(pilot.PILOT_CAP_S,
                                                       max(0., remaining - .3)))
                if mode == "ta8_certified_pretest" and pilot_result["certified"]:
                    status = "UNSAT"
                    proof = "SOURCE_XOR_CONTRADICTION_REPLAYED"
                    selected = "r28_source_only_certified"
                    route = "TA8_verified_source_XOR_before_TA3"
            if status != "UNSAT":
                features = ta3.fast_features(src)
                selected, route = ta3.decision(features, "ta2_portfolio")
        except TimeoutError:
            signal_timed_out = True
            route = "profile_timeout"
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, prior)
        if status != "UNSAT" and not signal_timed_out and time.perf_counter() - start < CAP - .10:
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
        proof=proof,
        pilot_s=round(pilot_result["elapsed_s"],6) if mode != "ta3_portfolio" else 0.0,
        source_certified=bool(pilot_result["certified"]) if mode != "ta3_portfolio" else False)
    print("TA8_TRIAL", json.dumps(row, sort_keys=True), flush=True)
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
    need(len(rows) == 4 * REPS * len(MODES), "partial shard")
    print("TA8_SHARD_PASS", index, len(rows), flush=True)

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
    need(len(rows) == 12*REPS*len(MODES) == 144, "wrong total trials")
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
    # Source-cluster bootstrap, resample 12 complete 2-repetition clusters.
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
    result = dict(protocol=PROTO, status="TA8_AUDIT_PASS", sources=12,
        attempts=len(rows), repetitions=REPS, cap_s=CAP,
        external_new_source_SAT_witness_verified=True,
        original_source_SHA_disjoint_from_known_exclusions=True,
        excluded_prior_R200_TA6_TA7_TA7H_source_manifests=True,
        selector_precommitted_before_new_source_runs=True,
        CDCL_generic_UNSAT_independent_LRAT=False,
        not_globally_blind=True, pilot_cap_s=pilot.PILOT_CAP_S,
        proof_replayed_on_original_CNF=True, modes=metrics, bootstrap95=ci)
    save(ROOT / "report.json", result)
    save(ROOT / "all-trials.json", rows)
    lines = ["# TA8 certified XOR pretest versus unchanged TA3", "",
             "12 new SHA-disjoint official SAT2026 originals, 6 frozen arms, 2 reps, 10s cap.",
             "Same original CNFs, source SHA checked, SAT model verified; generic CDCL UNSAT",
             "is NOT independently LRAT verified. Source set is disjoint from known",
             "prior R200 and TA3 manifests but cannot be called globally blind.", "",
             "| Mode | Solved/24 | PAR-2 seconds | Ratio vs host | W/L/T | 95% bootstrap |",
             "|---|---:|---:|---:|---|---|"]
    for mode in MODES:
        m = metrics[mode]
        base = REFERENCE.get(mode)
        p = m.get("vs_" + base) if base else None
        b = ci.get(mode)
        lines.append("| %s | %d/24 | %.3f | %s | %s | %s |" % (
            mode, m["solved"], m["PAR2_s"],
            ("%.3f×" % p["ratio"]) if p else "reference",
            ("%d/%d/%d" % (p["wins"], p["losses"], p["ties"])) if p else "—",
            ("[%.3f, %.3f]" % (b["low95"], b["high95"])) if b else "—"))
    lines += ["", "Ratio = reference PAR-2 / candidate PAR-2, not CPU-time",
              "speedup on an individual solved instance. A ratio above 1 favors",
              "the candidate. Do not generalize when the bootstrap interval includes 1."]
    (ROOT / "report.md").write_text("\n".join(lines) + "\n")
    print("TA8_FINAL", json.dumps(result, sort_keys=True), flush=True)

def smoke():
    cases, groups = cases_groups()
    r199.certified.deriv.selftest()
    exact.selftest()
    pilot.selftest()
    toy = dict(id="ta8_smoke", sha256="", expected="SAT", real=True,
               family="toy", group="bucket_a")
    path = SOURCE / "ta8_smoke.cnf"
    path.write_text("p cnf 3 2\n1 0\n-1 2 0\n")
    toy["sha256"] = digest(path)
    for mode in MODES:
        row = run_trial(toy, mode, 0, 0)
        need(row["status"] == "SAT", "smoke failed " + mode)
    path.unlink()
    print("TA8_SELFTEST_PASS", len(MODES), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("fetch","smoke","shard","audit"))
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    {"fetch":fetch,"smoke":smoke,"shard":lambda:shard(args.shard),"audit":audit}[args.action]()
