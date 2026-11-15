#!/usr/bin/env python3
"""Prospective, source-paired original SAT2026 E2E/PAR2 audit.

Core per-trial runner and independent proof verifiers are imported, unchanged,
from research/math4/benchmark_unseen15.py. Distinct structural and strict DRAT
scores remain explicit; structural proofs do NOT imply Main Track acceptance.
"""
import argparse
import collections
import hashlib
import json
import os
import platform
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/math4"))
import benchmark_unseen15 as core

CAP = 20.0
REPS = 3
SHARDS = 6
ARMS = ("CF7_OFF", "HALL3_ON", "MATH4_ON", "Kissat", "CaDiCaL")
OUT = ROOT / "maxpar2_results"
SELECTION = ROOT / "research/maxpar2/selection.json"
MANIFEST = ROOT / "maxpar2_inputs/manifest.json"

def sha(path):
    return core.sha(path)

def save(path, obj):
    return core.save(path, obj)

def emit(tag, obj):
    return core.emit(tag, obj)

def manifest():
    return json.loads(MANIFEST.read_text())

def choose_cpu():
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    assert len(os.sched_getaffinity(0)) == 1
    return cpu

def prepare():
    cpu = choose_cpu()
    sel = json.loads(SELECTION.read_text())
    m = manifest()
    assert m["selection_sha256"] == sha(SELECTION)
    assert m["selected_count"] == 27 and m["downloaded_count"] == len(m["sources"])
    assert len(m["sources"]) >= 12
    assert sel["cap_s"] == CAP and sel["repetitions"] == REPS
    assert sel["arms"] == list(ARMS) and sel["shards"] == SHARDS
    assert m["no_outcome_reselection"] and m["selection_frozen_before_results"]
    for source in m["sources"]:
        assert sha(ROOT / source["path"]) == source["sha256"], source["id"]
    names = sorted(set(core.BIN.values()) | {"build/drat-trim"})
    checks = ["research/pcmax_capacity/check_clause_hall.py",
              "research/pcmax_capacity/check_capacity.py",
              "research/math4/check_xor_units.py",
              "research/drnas_x55_cpu_real36.py",
              "research/math4/benchmark_unseen15.py",
              "research/maxpar2/benchmark.py"]
    protocol = dict(name=sel["protocol"], cap_s=CAP, repetitions=REPS,
        shards=SHARDS, arms=ARMS, selected_sources=27,
        frozen_sources=len(m["sources"]), excluded_sources=len(m["excluded_or_failed"]),
        expected_trials=len(m["sources"]) * REPS * len(ARMS),
        one_logical_cpu=True, cpu=cpu, host=platform.platform(),
        model=platform.processor(), input_sha256=sha(MANIFEST),
        selection_sha256=sha(SELECTION),
        binary_sha256={n:sha(ROOT / n) for n in names},
        verifier_sha256={n:sha(ROOT / n) for n in checks},
        proof_verification="independent MODEL, DRAT-trim, Hall/BDD/GF2 original-clause",
        strict_verification="MODEL or DRAT only (separate score)",
        time="single job sequential one-CPU; solver wall + checker wall must fit cap",
        proof_limit_bytes=256*1024*1024,
        size_proxy_not_hardness=True, no_automatic_promotion=True)
    save(OUT / "protocol.json", protocol)
    emit("MAXPAR2_READY", protocol)

def shard(index):
    cpu = choose_cpu()
    assert 0 <= index < SHARDS
    protocol = json.loads((OUT / "protocol.json").read_text())
    assert protocol["input_sha256"] == sha(MANIFEST)
    assert protocol["selection_sha256"] == sha(SELECTION)
    for name, checksum in protocol["binary_sha256"].items():
        assert sha(ROOT/name) == checksum, name
    for name, checksum in protocol["verifier_sha256"].items():
        assert sha(ROOT/name) == checksum, name
    sources = [s for s in manifest()["sources"] if s["id"] % SHARDS == index]
    folder = OUT / ("shard-" + str(index))
    folder.mkdir(exist_ok=False, parents=True)
    rows = []
    with (folder/"trials.jsonl").open("w") as log:
        for source in sources:
            for rep in range(REPS):
                order = list(ARMS)
                random.Random(20261115 + source["id"]*173 + rep*47).shuffle(order)
                for arm in order:
                    r = core.trial(source, arm, rep,
                         folder / (f'{source["id"]:02d}-r{rep}-{arm}'), cap=CAP)
                    r["cohort"] = source["cohort"]
                    r["size_tier"] = source["size_tier"]
                    r["variables"] = source["variables"]
                    r["clauses"] = source["clauses"]
                    rows.append(r)
                    log.write(json.dumps(r, sort_keys=True) + "\n")
                    log.flush()
            verified = {r["status"] for r in rows
                if r["id"] == source["id"] and r["verified"]}
            assert len(verified) <= 1, ("contradictory_verified_results", source["id"])
    save(folder / "meta.json", dict(index=index, cpu=cpu,
         trials=len(rows), source_ids=[s["id"] for s in sources]))
    emit("MAXPAR2_SHARD_PASS", dict(index=index, cpu=cpu, trials=len(rows),
         verified=sum(bool(x["accepted"]) for x in rows)))

def bootstrap_interval(values, seed):
    if not values:
        return [None, None]
    rng = random.Random(seed)
    n = len(values)
    draws = sorted(sum(rng.choice(values) for _ in range(n))/n for _ in range(10000))
    return [round(draws[250], 6), round(draws[9749], 6)]

def report():
    m = manifest()
    rows = []
    for index in range(SHARDS):
        file = OUT / f"shard-{index}" / "trials.jsonl"
        assert file.is_file(), file
        rows.extend(json.loads(line) for line in file.read_text().splitlines())
    expected = {(s["id"], rep, arm) for s in m["sources"]
                for rep in range(REPS) for arm in ARMS}
    actual = [(r["id"], r["rep"], r["arm"]) for r in rows]
    assert len(actual) == len(expected) and set(actual) == expected, "incomplete_or_duplicate_trials"
    for s in m["sources"]:
        group = [r for r in rows if r["id"] == s["id"]]
        assert len(group) == REPS * len(ARMS)
        assert all(r["source_sha256"] == s["sha256"] for r in group)
        valid = {r["status"] for r in group if r["verified"]}
        assert len(valid) <= 1, ("conflicting_certificates", s["id"])
    totals = []
    for arm in ARMS:
        rr = [r for r in rows if r["arm"] == arm]
        totals.append(dict(arm=arm, trials=len(rr),
            accepted=sum(bool(r["accepted"]) for r in rr),
            solved_sources=len({r["id"] for r in rr if r["accepted"]}),
            structural=sum(bool(r["accepted"]) and
                str(r["certificate_kind"]).startswith("STRUCTURAL") for r in rr),
            strict_accepted=sum(bool(r["strict_accepted"]) for r in rr),
            PAR2_verified_sum_s=round(sum(r["PAR2_verified_s"] for r in rr), 6),
            PAR2_verified_mean_s=round(sum(r["PAR2_verified_s"] for r in rr)/len(rr), 6),
            PAR2_strict_sum_s=round(sum(r["PAR2_strict_drat_s"] for r in rr), 6)))
    pairs = []
    for s in m["sources"]:
        group = [r for r in rows if r["id"] == s["id"]]
        means = {arm:sum(r["PAR2_verified_s"] for r in group
                if r["arm"] == arm)/REPS for arm in ARMS}
        strict_means = {arm:sum(r["PAR2_strict_drat_s"] for r in group
                if r["arm"] == arm)/REPS for arm in ARMS}
        best_ref = min(means["Kissat"], means["CaDiCaL"])
        pairs.append(dict(id=s["id"], family=s["family"], cohort=s["cohort"],
             file_id=s["file_id"], size_tier=s["size_tier"],
             clauses=s["clauses"], variables=s["variables"],
             PAR2_mean_by_arm_s={k:round(v,6) for k,v in means.items()},
             strict_by_arm_s={k:round(v,6) for k,v in strict_means.items()},
             best_ref_minus_MATH4_s=round(best_ref-means["MATH4_ON"],6)))
    by_group = {}
    for keyname in ("family", "cohort", "size_tier"):
        out = {}
        for groupname in sorted({x[keyname] for x in pairs}):
            subset = [p for p in pairs if p[keyname] == groupname]
            out[groupname] = dict(sources=len(subset),
                verified_PAR2_mean_by_arm_s={a:round(
                    sum(p["PAR2_mean_by_arm_s"][a] for p in subset)/len(subset),6)
                    for a in ARMS},
                best_reference_minus_MATH4_mean_s=round(
                    sum(p["best_ref_minus_MATH4_s"] for p in subset)/len(subset),6))
        by_group[keyname] = out
    ref_confidence = {}
    for arm in ("Kissat", "CaDiCaL"):
        d = [p["PAR2_mean_by_arm_s"][arm]-p["PAR2_mean_by_arm_s"]["MATH4_ON"]
             for p in pairs]
        ref_confidence[arm] = dict(mean_delta_ref_minus_MATH4_s=round(sum(d)/len(d),6),
             source_cluster_bootstrap_95_s=bootstrap_interval(d, 20261115+len(arm)))
    best_d = [p["best_ref_minus_MATH4_s"] for p in pairs]
    best_ci = bootstrap_interval(best_d, 2026111509)
    t = {x["arm"]:x for x in totals}
    ref_best = min(t["Kissat"]["PAR2_verified_sum_s"],t["CaDiCaL"]["PAR2_verified_sum_s"])
    delta_pct = round(100*(ref_best-t["MATH4_ON"]["PAR2_verified_sum_s"])/ref_best,4)
    summary = dict(status="COMPLETE", protocol=m["protocol"],
        frozen_sources=len(m["sources"]), selected_sources=27,
        excluded_sources=len(m["excluded_or_failed"]), trials=len(rows),
        cap_s=CAP, repetitions=REPS, totals=totals,
        MATH4_vs_best_fixed_reference_pct=delta_pct,
        per_source_best_reference_delta_mean_s=round(sum(best_d)/len(best_d),6),
        per_source_best_reference_delta_CI95_s=best_ci,
        reference_paired_bootstrap=ref_confidence, by_group=by_group,
        biggest_source_wins=sorted(pairs,key=lambda p:p["best_ref_minus_MATH4_s"],
                                   reverse=True)[:5],
        biggest_source_losses=sorted(pairs,key=lambda p:p["best_ref_minus_MATH4_s"])[:5],
        pairs=pairs, structural_is_not_DPR_GRAT_or_VeriPB=True,
        not_official_sat_competition_ranking=True, automatic_promotion=False,
        point_estimate_wins_vs_both=t["MATH4_ON"]["PAR2_verified_sum_s"] <
          min(t["Kissat"]["PAR2_verified_sum_s"],t["CaDiCaL"]["PAR2_verified_sum_s"]),
        strict_point_estimate_wins_vs_both=t["MATH4_ON"]["PAR2_strict_sum_s"] <
          min(t["Kissat"]["PAR2_strict_sum_s"],t["CaDiCaL"]["PAR2_strict_sum_s"]))
    save(OUT/"summary.json", summary)
    (OUT/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n"
                                       for r in rows))
    lines = [
        "# DRNAS MAXPAR2 original SAT Competition 2026 — frozen prospective holdout",
        "",
        f"Fixed 27 source IDs; {len(m['sources'])} original SHA-frozen CNFs passed"
        f" size/download gates; {len(m['excluded_or_failed'])} excluded, not replaced.",
        f"{REPS} source-paired repetitions; {CAP:g} s each; sequential one logical CPU.",
        "Both SAT models and UNSAT certificates independently checked. E2E includes checker.",
        "**Structural Hall/BDD/GF2 certificates are separate from strict MODEL/DRAT"
        " and are not an official SAT Competition 2026 proof format.**",
        "Size tiers are CNF-size proxies, not demonstrated runtime complexity.",
        "", "| Arm | Verified source successes | Verified trials | Structural |"
        " E2E PAR2 mean (s) | E2E PAR2 sum (s) | Strict MODEL/DRAT sum (s) |",
        "|---|---:|---:|---:|---:|---:|---:|"
    ]
    for a in totals:
        lines.append(f'| {a["arm"]} | {a["solved_sources"]} | {a["accepted"]} |'
                     f' {a["structural"]} | {a["PAR2_verified_mean_s"]:.4f} |'
                     f' {a["PAR2_verified_sum_s"]:.4f} | {a["PAR2_strict_sum_s"]:.4f} |')
    lines.extend(["", f"MATH4 point-estimate gain vs better fixed reference: {delta_pct:+.3f}%.",
        f"Mean per-source delta vs min(Kissat,CaDiCaL): {summary['per_source_best_reference_delta_mean_s']:.4f}s;"
        f" source-cluster bootstrap 95% interval {best_ci}.",
        "", "## By predeclared cohort"])
    for name,d in by_group["cohort"].items():
        lines.append(f"- {name}: {d['sources']} sources; mean PAR2 MATH4 "
            f"{d['verified_PAR2_mean_by_arm_s']['MATH4_ON']:.3f}s,"
            f" Kissat {d['verified_PAR2_mean_by_arm_s']['Kissat']:.3f}s,"
            f" CaDiCaL {d['verified_PAR2_mean_by_arm_s']['CaDiCaL']:.3f}s.")
    lines += ["", "## Biggest penalized paired gains (seconds/source)"]
    for p in summary["biggest_source_wins"]:
        lines.append(f"- {p['family']} {p['file_id']}: {p['best_ref_minus_MATH4_s']:+.4f}")
    lines += ["", "## Biggest penalized paired losses (seconds/source)"]
    for p in summary["biggest_source_losses"]:
        lines.append(f"- {p['family']} {p['file_id']}: {p['best_ref_minus_MATH4_s']:+.4f}")
    lines += ["", "Not a competition ranking, not a family-unseen blind experiment;"
        " no source-dependent solver tuning, no automatic promotion."]
    (OUT/"README.md").write_text("\n".join(lines)+"\n")
    emit("MAXPAR2_FINAL", {k:summary[k] for k in ("status","frozen_sources",
         "trials","MATH4_vs_best_fixed_reference_pct",
         "per_source_best_reference_delta_CI95_s",
         "point_estimate_wins_vs_both","strict_point_estimate_wins_vs_both","totals")})

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("prepare","shard","report"))
    p.add_argument("--index", type=int)
    a = p.parse_args()
    {"prepare":prepare,"shard":lambda: shard(a.index),"report":report}[a.action]()
