#!/usr/bin/env python3
"""DRNAS MRE14 structural synergy: proof-replayed D96->Cdepth2 + exact X3 Spread100 + selective No Vivify.

* D96: each novel binary lemma is independently replayed as two ORIGINAL binary implications.
* Cdepth2: each deleted disjunct has an independently replayed implication path to a RETAINED disjunct.
* Spread100: exact raw clause multiset preserved; only original/certified duplicate positions change.
* No Vivify: solver search heuristic only, controlled by frozen structural rule; no source labels used.
* SAT model always checked on untouched original CNF. No globally blind or independent UNSAT proof claims.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import io
import itertools
import json
import os
import pathlib
import random
import shutil
import subprocess
import tempfile
import time

import mre13_abcd_parallel as m13
import mre12_exact_quotient as m12
import c15d_benchmark as c15d

PROTO = "DRNAS-MRE14-D96-C2-SPREAD100-SELECTIVE-20SHA-6ARM-2SEED-12S-v1"
SALT = "DRNAS-MRE14-FROZEN-20261109-NO-TUNING-v1"
ROOT = pathlib.Path("mre14_sources")
OUT = pathlib.Path("mre14_out")
CAP = 12.0
REPS = 2
SHARDS = 4
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_CLAUSES = 175000
MAX_SOURCE_VARIABLES = 30000
MAX_WORKING_CLAUSES = 125000
ARMS = ("baseline", "spread100", "cd", "cd_spread",
        "cd_spread_no_vivify", "cd_spread_selective")
FRESH_TARGET = {"SAT": 2, "UNSAT": 2}

def need(ok, message):
    if not ok:
        raise RuntimeError("MRE14_FAIL_CLOSED " + str(message))

def hashbytes(raw):
    return hashlib.sha256(raw).hexdigest()

def digest(path):
    return m12.digest(path)

def save(path, content):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, sort_keys=True, indent=2) + "\n", encoding="utf-8")

def source_copy(raw, gbd, status, cohort, origin, existing_shas):
    sha = hashbytes(raw)
    if sha in existing_shas:
        return False
    need(status in ("SAT", "UNSAT"), "source reference status invalid")
    n, m = c15d.h.r32p.parse_dimacs_metadata(raw)
    # Historical source inclusion must not be confused with candidate eligibility.
    # Preserve larger frozen originals unchanged; per-arm metadata guard safely
    # abstains before costly transformation. New official sources have tighter caps.
    if origin == "official2026-database":
        need(0 < n <= MAX_SOURCE_VARIABLES and 0 < m <= MAX_SOURCE_CLAUSES
             and len(raw) <= MAX_SOURCE_BYTES, "fresh official resource cap")
    else:
        need(0 < n <= 200000 and 0 < m <= 500000 and len(raw) <= 50 * 1024 * 1024,
             "previously frozen original exceeds maximum transport cap")
    filename = sha[:24] + ".cnf"
    target = ROOT / filename
    target.write_bytes(raw)
    need(digest(target) == sha, "copied original source hash mismatch")
    existing_shas[sha] = dict(filename=filename, gbd=gbd, sha256=sha,
                              status=status, cohort=cohort,
                              nvars=n, nclauses=m, bytes=len(raw), origin=origin)
    return True

def freeze():
    need(not ROOT.exists() or not (ROOT / "manifest.json").exists(),
         "frozen MRE14 manifest already exists; refuse refreeze")
    ROOT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    existing = {}
    for c in c15d.cases():
        original = (c15d.SRC / c["filename"]).read_bytes()
        need(hashbytes(original) == c["sha256"], "C15D original SHA drift")
        group = "historical_" + c["cohort"]
        need(source_copy(original, c["gbd"], c["status"], group,
                         "C15D-42541912605", existing), "duplicate C15D source")
    x3manifest = json.loads(pathlib.Path("mre_x3/manifest.json").read_text())
    need(len(x3manifest["cases"]) == 5, "X3 original 5 source manifest missing")
    x3paths = list(pathlib.Path("mre_x").glob("*.cnf"))
    x3bys = {digest(p): p for p in x3paths}
    x3_added, x3_overlap = 0, 0
    for c in x3manifest["cases"]:
        sha = c["sha256"]
        need(sha in x3bys, "X3 original SHA source unavailable")
        raw = x3bys[sha].read_bytes()
        need(hashbytes(raw) == sha, "X3 original source altered")
        if source_copy(raw, c["gbd"], c["reference_status"],
                       "historical_x3_duplicate_order", "MRE-X3-42524524856", existing):
            x3_added += 1
        else:
            x3_overlap += 1

    # Freeze genuinely different original SHA from the two reused input manifests.
    # NOT globally unseen to all prior research: no claim of exhaustive history exclusion.
    helper = c15d.h
    index = helper.r52.fetch_bytes(helper.r52.URI, 100000)
    ids = [x.strip().rsplit("/", 1)[-1] for x in index.decode().splitlines()
           if x.strip()]
    need(len(ids) == len(set(ids)) == 400, "SAT2026 official index changed")
    score_bytes = helper.r52.fetch_bytes(helper.r52.SCORES, 32 * 1024 * 1024)
    statuses = {x["instanceid"]: helper.STATUS.get(x["status"])
                for x in csv.DictReader(io.StringIO(score_bytes.decode()))
                if x.get("solverid") == "biere_cadical3[main]"}
    old_gbd = {v["gbd"] for v in existing.values()}
    candidates = sorted((g for g in ids if g not in old_gbd),
                        key=lambda g: hashbytes((SALT + "|" + g).encode()))
    counts = collections.Counter()
    attempts = []
    for gbd in candidates:
        if all(counts[k] >= v for k, v in FRESH_TARGET.items()):
            break
        status = statuses.get(gbd)
        if status not in FRESH_TARGET or counts[status] >= FRESH_TARGET[status]:
            continue
        entry = dict(gbd=gbd, expected=status)
        try:
            raw, _ = helper.r32p.request_url(
                "https://benchmark-database.de/file/" + gbd,
                12 * 1024 * 1024, seconds=25)
            decoded, _ = helper.r32p.decode(raw)
            if not source_copy(decoded, gbd, status, "fresh_to_MRE14_official",
                               "official2026-database", existing):
                raise RuntimeError("source SHA duplicated reused cohort")
            counts[status] += 1
            entry["accepted"] = True
            entry["sha256"] = hashbytes(decoded)
        except Exception as exc:
            entry["accepted"] = False
            entry["reason"] = (type(exc).__name__ + ": " + str(exc))[:160]
        attempts.append(entry)
        print("MRE14_OFFICIAL_FREEZE_SCAN " + json.dumps(entry, sort_keys=True), flush=True)
        need(len(attempts) < 100, "too many failed official source downloads")
    need(dict(counts) == FRESH_TARGET,
         "did not freeze both SAT and UNSAT source quotas")
    cases = list(existing.values())
    need(len(cases) == len(existing), "source duplicate")
    need(x3_added >= 3 and x3_overlap <= 2, "X3 duplicate-bearing cohort missing")
    # Deterministic order independent of filesystem and fetch ordering.
    cases = sorted(cases, key=lambda c: (c["cohort"], c["sha256"]))
    manifest = dict(protocol=PROTO, cases=cases, x3_added=x3_added, x3_overlap=x3_overlap,
                    provenance={"c15d_run": 42541912605, "mre_x3_run": 42524524856},
                    fresh_quota=dict(counts), source_count=len(cases),
                    total_trials=len(cases) * REPS * len(ARMS),
                    original_SHA_locked=True, global_blind_claim=False,
                    fresh_only_disjoint_from_reused_manifests=True,
                    no_source_timing_screen=True, salt=SALT,
                    index_sha256=hashbytes(index), reference_csv_sha256=hashbytes(score_bytes),
                    official_attempts=attempts)
    save(ROOT / "manifest.json", manifest)
    print("MRE14_FREEZE_PASS " + json.dumps({
        "source_count": len(cases), "fresh": sum(counts.values()),
        "x3_added": x3_added, "x3_overlap": x3_overlap,
        "expected_trials": manifest["total_trials"],
        "manifest_sha256": digest(ROOT / "manifest.json")}, sort_keys=True), flush=True)

def cases():
    p = ROOT / "manifest.json"
    need(p.is_file(), "frozen MRE14 manifest absent")
    m = json.loads(p.read_text())
    need(m["protocol"] == PROTO and m["original_SHA_locked"] is True,
         "frozen source protocol drift")
    cc = m["cases"]
    need(len(cc) == len({c["sha256"] for c in cc})
         and len(cc) == m["source_count"]
         and m["total_trials"] == len(cc) * REPS * len(ARMS), "source/trial drift")
    for c in cc:
        need(digest(ROOT / c["filename"]) == c["sha256"], "MRE14 original SHA changed")
    return cc

def identical_spread100(clauses):
    """Exact MRE X3 Spread100 algorithm: move existing canonical duplicates evenly."""
    seen = set()
    duplicate_indices = []
    for i, c in enumerate(clauses):
        key = tuple(sorted(set(c)))
        if key in seen:
            duplicate_indices.append(i)
        else:
            seen.add(key)
    amount = len(duplicate_indices)
    if amount == 0:
        return list(clauses), 0
    chosen = set(duplicate_indices)
    retained = [c for i, c in enumerate(clauses) if i not in chosen]
    moved = [clauses[i] for i in duplicate_indices]
    gaps = [((i + 1) * (len(retained) + 1)) // (amount + 1) for i in range(amount)]
    buckets = [[] for _ in range(len(retained) + 1)]
    for gap, c in zip(gaps, moved):
        buckets[gap].append(c)
    result = []
    for i in range(len(retained) + 1):
        result.extend(buckets[i])
        if i < len(retained):
            result.append(retained[i])
    need(len(result) == len(clauses)
         and collections.Counter(result) == collections.Counter(clauses),
         "X3 Spread100 raw clause multiset changed")
    return result, amount

def verify_d96_original(clauses, enriched):
    need(len(enriched) >= len(clauses) and enriched[:len(clauses)] == clauses,
         "D96 modified or removed original clauses")
    graph, _, _ = m12.edge_graph(clauses)
    added = enriched[len(clauses):]
    for lemma in added:
        need(len(lemma) == 2, "D96 produced nonbinary lemma")
        left, right = lemma
        start = -left
        need(any(right in graph.get(via, ()) for via in graph.get(start, ())),
             "D96 binary implication not certified from two original clauses")
    return len(added)

def path_in_graph(graph, start, targets, max_depth=8):
    # Used as independent replay of Cdepth2 removal, never as a heuristic proof guess.
    frontier = collections.deque([(start, (start,))])
    visited = {start}
    while frontier:
        current, path = frontier.popleft()
        if current in targets and current != start:
            return path
        if len(path) > max_depth:
            continue
        for nxt in graph.get(current, ()):
            if nxt not in visited:
                visited.add(nxt)
                frontier.append((nxt, path + (nxt,)))
    return None

def verify_cdepth2(enriched, shortened):
    need(len(enriched) == len(shortened), "Cdepth2 must retain clause positions")
    graph, _, original_edges = m12.edge_graph(enriched)
    count = 0
    for old, new in zip(enriched, shortened):
        if old == new:
            continue
        need(new and len(new) < len(old), "Cdepth2 invalid clause strengthening")
        need(collections.Counter(new) <= collections.Counter(old),
             "Cdepth2 introduced a new literal")
        survivors = set(new)
        removed = set(old) - survivors
        for x in removed:
            path = path_in_graph(graph, x, survivors)
            need(path and len(path) >= 2, "Cdepth2 removed unproven literal")
            for a, b in zip(path, path[1:]):
                need(frozenset((-a, b)) in original_edges,
                     "Cdepth2 implication edge not in certified source+lemmas")
            count += 1
    return count

def cert_cd(original):
    # Directly retain the proven MRE13 intervention, with a separate independent replay.
    enriched, lemmas = m13.binary_lemmas(original, 96, seconds=0.10)
    need(lemmas == verify_d96_original(original, enriched),
         "D96 original-CNF proof count mismatch")
    shortened, removed, certs = m13.clause_dominance(
        enriched, depth=2, limit=192, seconds=0.13)
    replayed = verify_cdepth2(enriched, shortened)
    need(replayed == removed == certs,
         "Cdepth2 independent proof replay/count mismatch")
    return shortened, lemmas, removed

def preprocess(case, arm):
    original_path = ROOT / case["filename"]
    metadata = dict(applied=False, skip_reason="", original_clauses=case["nclauses"],
                    transformed_clauses=case["nclauses"], d96_lemmas=0,
                    c2_literals_removed=0, duplicates_moved=0, structural_gate=False,
                    source_size_guard=False, multiset_verified=True,
                    original_logical_meaning_preserved=True)
    if arm == "baseline":
        metadata["skip_reason"] = "baseline_untouched"
        return None, metadata, False
    if (case["nclauses"] > MAX_WORKING_CLAUSES or
        case["nvars"] > MAX_SOURCE_VARIABLES or
        case["bytes"] > MAX_SOURCE_BYTES):
        metadata["skip_reason"] = "metadata_size_guard_before_parse"
        metadata["source_size_guard"] = True
        return None, metadata, False
    nvars, original = m12.parse_dimacs(original_path)
    need(nvars == case["nvars"] and len(original) == case["nclauses"],
         "original DIMACS metadata inconsistent")
    clauses = list(original)
    if arm not in ("spread100",):
        clauses, lemmas, removed = cert_cd(original)
        metadata["d96_lemmas"] = lemmas
        metadata["c2_literals_removed"] = removed
    if arm in ("spread100", "cd_spread", "cd_spread_no_vivify", "cd_spread_selective"):
        clauses, moved = identical_spread100(clauses)
        metadata["duplicates_moved"] = moved
    # No oracle: fixed, unsupervised structural gate using proof counts and raw duplicates.
    # NOT a validated predictor. Never use case SHA, status, GBD, elapsed or benchmark labels.
    gate = ((metadata["d96_lemmas"] >= 32 and metadata["c2_literals_removed"] >= 8)
            or (metadata["duplicates_moved"] >= 32 and
                metadata["c2_literals_removed"] >= 4))
    metadata["structural_gate"] = bool(gate)
    disable_vivify = (arm == "cd_spread_no_vivify" or
                      (arm == "cd_spread_selective" and gate))
    metadata["applied"] = bool(metadata["d96_lemmas"] or
                               metadata["c2_literals_removed"] or
                               metadata["duplicates_moved"])
    metadata["transformed_clauses"] = len(clauses)
    if not metadata["applied"]:
        metadata["skip_reason"] = "no_replay_certified_effect"
        return None, metadata, disable_vivify
    return (nvars, clauses), metadata, disable_vivify

def smoke():
    with tempfile.TemporaryDirectory(prefix="mre14-smoke-") as temp:
        p = pathlib.Path(temp) / "smoke.cnf"
        p.write_text("p cnf 3 3\n1 2 0\n-1 2 0\n1 -3 0\n")
        binary = pathlib.Path("c8c/bin/instrumented").resolve()
        need(binary.is_file(), "pinned instrumented CaDiCaL missing")
        for seed in (173, 271):
            cmd = [str(binary), "--seed=" + str(seed), str(p.resolve())]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            need(proc.returncode == 10, "pinned CaDiCaL cannot set independent solver seed")
            status, model = c15d.h.ref.external_parse(proc)
            need(status == "SAT", "CaDiCaL smoke failed status")
            c15d.h.cms.verify_model(p, model)
        print("MRE14_SEED_SMOKE_PASS 2", flush=True)

def trial(case, rep, arm, position, paired_seed):
    path = ROOT / case["filename"]
    started = time.perf_counter()
    need(digest(path) == case["sha256"], "pretrial source SHA drift")
    with tempfile.TemporaryDirectory(prefix="drnas-mre14-") as d:
        transformed, meta, disable_vivify = preprocess(case, arm)
        effective = path
        if transformed is not None:
            nv, clauses = transformed
            effective = pathlib.Path(d) / "candidate.cnf"
            effective.write_text(m12.encode(nv, clauses), encoding="utf-8")
        prep_s = time.perf_counter() - started
        binary = pathlib.Path("c8c/bin/instrumented")
        need(binary.exists(), "frozen binary missing")
        cmd = [str(binary.resolve()), "--seed=" + str(paired_seed)]
        if disable_vivify:
            cmd.append("--no-vivify")
        cmd.append(str(effective.resolve()))
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("DRNAS_C8", "DRNAS_C14", "DRNAS_C15"))}
        status, verified = "TIMEOUT", False
        native_exit = None
        remaining = CAP - (time.perf_counter() - started)
        if remaining > 0.05:
            try:
                p = subprocess.run(cmd, env=env, text=True, capture_output=True,
                                   errors="replace", timeout=remaining)
                native_exit = p.returncode
                need(p.returncode in (10, 20), "solver did not terminate with SAT/UNSAT")
                status, model = c15d.h.ref.external_parse(p)
                need(status == case["status"], "solver verdict contradicts frozen reference")
                if status == "SAT":
                    c15d.h.cms.verify_model(path, model)
                    verified = True
                if time.perf_counter() - started > CAP:
                    status, verified = "TIMEOUT", False
            except subprocess.TimeoutExpired:
                status = "TIMEOUT"
        elapsed = time.perf_counter() - started
        if elapsed > CAP and status != "TIMEOUT":
            status, verified = "TIMEOUT", False
        return dict(protocol=PROTO, arm=arm, source_sha256=case["sha256"],
                    gbd=case["gbd"], cohort=case["cohort"], source_ref=case["status"],
                    rep=rep, order_position=position, paired_seed=paired_seed,
                    independent_solver_seed=True, cap_s=CAP, status=status,
                    elapsed_s=round(elapsed, 6),
                    PAR2_s=round(elapsed if status != "TIMEOUT" else 2 * CAP, 6),
                    prep_s=round(prep_s, 6), no_vivify=disable_vivify,
                    SAT_original_verified=verified, UNSAT_independent_LRAT=False,
                    UNSAT_reference_agreement=status == "UNSAT",
                    binary_sha256=digest(binary),
                    original_sha_unchanged=True, native_exit=native_exit, **meta)

def shard(index):
    need(0 <= index < SHARDS, "bad shard index")
    cc = cases()
    rows = []
    OUT.mkdir(exist_ok=True)
    for case in cc[index::SHARDS]:
        for rep in range(REPS):
            paired_seed = int(hashbytes((PROTO + "|" + case["sha256"] +
                                        "|" + str(rep)).encode())[:8], 16)
            # Real numerical CaDiCaL seeds are independently changed across repeat 0/1.
            need(paired_seed <= 0xffffffff, "bad seed")
            order = list(ARMS)
            random.Random(paired_seed).shuffle(order)
            for position, arm in enumerate(order):
                row = trial(case, rep, arm, position, paired_seed)
                rows.append(row)
                save(OUT / ("shard-%d.json" % index), rows)
                print("MRE14_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    print("MRE14_SHARD_PASS %d %d" % (index, len(rows)), flush=True)

def audit():
    cc = cases()
    rows = []
    for i in range(SHARDS):
        p = OUT / ("shard-%d.json" % i)
        need(p.is_file(), "missing complete shard")
        rows += json.loads(p.read_text())
    expected = {(c["sha256"], arm, rep) for c in cc for arm in ARMS for rep in range(REPS)}
    keys = [(r["source_sha256"], r["arm"], r["rep"]) for r in rows]
    need(len(rows) == len(expected) == len(set(keys))
         and set(keys) == expected, "unpaired source-arm-seed audit")
    mapping = {c["sha256"]: c for c in cc}
    bins = set()
    seed_groups = collections.defaultdict(dict)
    for r in rows:
        c = mapping[r["source_sha256"]]
        need(r["protocol"] == PROTO and r["cohort"] == c["cohort"] and
             r["source_ref"] == c["status"] and r["original_sha_unchanged"]
             and r["cap_s"] == CAP, "source provenance/limit drift")
        need(r["status"] in ("SAT", "UNSAT", "TIMEOUT"), "invalid solver result")
        need(r["original_logical_meaning_preserved"] and r["multiset_verified"],
             "missing transformation meaning invariant")
        need(r["independent_solver_seed"], "external seed not changed")
        key = (r["source_sha256"], r["rep"])
        seed_groups[key][r["arm"]] = r["paired_seed"]
        if r["status"] == "TIMEOUT":
            need(r["PAR2_s"] == 2 * CAP, "timeout incorrectly charged")
        else:
            need(r["status"] == c["status"] and
                 (r["status"] != "SAT" or r["SAT_original_verified"]),
                 "non-timeout verdict or witness invalid")
        bins.add(r["binary_sha256"])
        if r["arm"] == "baseline":
            need(not r["applied"] and not r["no_vivify"], "baseline altered")
        if r["arm"] == "cd_spread_selective":
            need(r["no_vivify"] == r["structural_gate"], "unfrozen selective gate")
        if r["arm"] == "cd_spread":
            need(not r["no_vivify"], "control had no-vivify")
        if r["arm"] == "cd_spread_no_vivify":
            need(r["no_vivify"], "no-vivify ablation not activated")
    need(len(bins) == 1, "binary SHA differed across arms")
    need(len(seed_groups) == len(cc) * REPS
         and all(set(z) == set(ARMS) and len(set(z.values())) == 1
                 for z in seed_groups.values()), "solver seed pairing broken")
    need(all(seed_groups[(c["sha256"], 0)]["baseline"] !=
             seed_groups[(c["sha256"], 1)]["baseline"] for c in cc),
         "solver repetitions are not independent seeds")
    def summarize(values):
        out = {}
        for arm in ARMS:
            rr = [x for x in values if x["arm"] == arm]
            out[arm] = dict(trials=len(rr),
                            solved=sum(x["status"] != "TIMEOUT" for x in rr),
                            SAT=sum(x["status"] == "SAT" for x in rr),
                            UNSAT=sum(x["status"] == "UNSAT" for x in rr),
                            PAR2_s=round(sum(x["PAR2_s"] for x in rr), 6),
                            prep_s=round(sum(x["prep_s"] for x in rr), 6),
                            transformations=sum(x["applied"] for x in rr),
                            d_lemmas=sum(x["d96_lemmas"] for x in rr),
                            c_removed=sum(x["c2_literals_removed"] for x in rr),
                            duplicates_moved=sum(x["duplicates_moved"] for x in rr),
                            selective_triggered=sum(x["structural_gate"] for x in rr
                                                    if arm == "cd_spread_selective"))
        return out
    report = dict(protocol=PROTO, source_count=len(cc), trials=len(rows),
                  seed_reps=REPS, cap_s=CAP, experimental_not_global_blind=True,
                  fresh_only_sha_disjoint_from_reused_manifest=True,
                  actual_solver_seeds_independent=True,
                  original_CNF_witness_verified=True,
                  independent_UNSAT_LRAT=False, no_auto_promotion=True,
                  scores=summarize(rows),
                  by_cohort={group: summarize([r for r in rows if r["cohort"] == group])
                             for group in sorted({r["cohort"] for r in rows})},
                  by_source={c["gbd"]: summarize([r for r in rows
                                                   if r["source_sha256"] == c["sha256"]])
                             for c in cc})
    save(OUT / "report.json", report)
    print("MRE14_FINAL " + json.dumps({k: v for k, v in report.items()
                                     if k != "by_source"}, sort_keys=True), flush=True)

def selftest():
    rng = random.Random(141414)
    suites = [
        (3, [(1, 2), (-1, 2), (1, 2), (2, 3), (-2, 3)]),
        (3, [(1, -2), (-1, 2), (-2, 3), (1, 3), (1, -3), (1, 3)]),
        (4, [(1, 2), (-2, 3), (1, 4), (-1, 4), (-3, 4), (1, 2)]),
        (3, [(1,), (-1,), (1, 2), (1, 2)]),
        (2, [(), (1, 2), (1, 2)]),
    ]
    for n in range(2, 6):
        pool = [tuple(v * s for v, s in zip(vs, signs))
                for length in (1, 2, 3) if length <= n
                for vs in itertools.combinations(range(1, n + 1), length)
                for signs in itertools.product((-1, 1), repeat=length)]
        for _ in range(60):
            clauses = rng.choices(pool, k=rng.randrange(2, 18))
            suites.append((n, clauses))
    checked, moved_any, c_any, d_any = 0, False, False, False
    for n, original in suites:
        cd, d_count, c_count = cert_cd(original)
        c_any |= bool(c_count)
        d_any |= bool(d_count)
        spread, moved = identical_spread100(cd)
        moved_any |= bool(moved)
        spread_only, _ = identical_spread100(original)
        for assignment in range(1 << n):
            model = {v: bool(assignment & (1 << (v - 1))) for v in range(1, n + 1)}
            truth = m12.model_satisfies(original, model)
            for altered in (cd, spread, spread_only):
                need(m12.model_satisfies(altered, model) == truth,
                     "SAT truth changes in proof-preserving pipeline")
            checked += 1
    need(moved_any and c_any and d_any, "selftest did not exercise all components")
    print("MRE14_EXACT_SELFTEST_PASS " +
          json.dumps({"sources": len(suites), "assignments": checked,
                      "spread_used": moved_any, "C_used": c_any, "D_used": d_any,
                      "same_original_truth_table": True}, sort_keys=True), flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("selftest", "freeze", "verify", "smoke", "shard", "audit"))
    p.add_argument("--shard", type=int, default=0)
    a = p.parse_args()
    if a.action == "selftest": selftest()
    elif a.action == "freeze": freeze()
    elif a.action == "verify":
        cc = cases()
        print("MRE14_FROZEN_SHA_VERIFIED " + str(len(cc)), flush=True)
    elif a.action == "smoke": smoke()
    elif a.action == "shard": shard(a.shard)
    elif a.action == "audit": audit()
