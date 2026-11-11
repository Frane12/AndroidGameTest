#!/usr/bin/env python3
"""GENERALIST2 family diagnostic from frozen ATLAS40 original-CNF results.

Offline analysis only: per-family performance is descriptive, not prospective
learning or standalone generalization. Never label unverified UNSAT as solved.
"""
import collections
import json
from pathlib import Path

ROOT = Path("audits")
COHORTS = ("regression", "extension", "hard")
ARMS = ("A36_75", "A39_PROTECT", "A40_TREE", "KISSAT")
rows = []
for cohort in COHORTS:
    for shard in (0, 1):
        matches = list((ROOT / ("GENERALIST2-%s-%s" % (cohort, shard))).rglob("result_%s.json" % shard))
        assert len(matches) == 1, (cohort, shard, matches)
        data = json.loads(matches[0].read_text())
        rows += data["rows"]

pairs = collections.defaultdict(dict)
source_meta = {}
for r in rows:
    k = (r["sha256"], r["rep"])
    assert r["arm"] in ARMS and r["arm"] not in pairs[k]
    assert r["status"] != "SAT_VERIFIED" or r["original_SAT_witness_verified"]
    pairs[k][r["arm"]] = r
    s = r["sha256"]
    label = (r["family"], r["cohort"])
    assert s not in source_meta or source_meta[s] == label
    source_meta[s] = label
assert len(rows) == 208 and len(pairs) == 52
assert all(set(d) == set(ARMS) for d in pairs.values())

families = collections.defaultdict(list)
for (sha, rep), paired in pairs.items():
    family, cohort = source_meta[sha]
    families[(cohort, family)].append(paired)

summaries = []
for (cohort, family), group in sorted(families.items()):
    a39 = sum(d["A39_PROTECT"]["PAR2_verified_s"] for d in group)
    a40 = sum(d["A40_TREE"]["PAR2_verified_s"] for d in group)
    kissat = sum(d["KISSAT"]["PAR2_verified_s"] for d in group)
    confirmed_sat = {arm: sum(d[arm]["status"] == "SAT_VERIFIED" for d in group) for arm in ARMS}
    wins = sum(d["A40_TREE"]["PAR2_verified_s"] < d["A39_PROTECT"]["PAR2_verified_s"] for d in group)
    losses = sum(d["A40_TREE"]["PAR2_verified_s"] > d["A39_PROTECT"]["PAR2_verified_s"] for d in group)
    tie = len(group) - wins - losses
    changed = sum(d["A40_TREE"]["telemetry"]["atlas39_changed_rank"] for d in group)
    conflicts39 = sum(d["A39_PROTECT"]["telemetry"]["conflicts"] for d in group)
    conflicts40 = sum(d["A40_TREE"]["telemetry"]["conflicts"] for d in group)
    report = dict(cohort=cohort, family=family,
                  unique_sha=len({r["A40_TREE"]["sha256"] for r in group}),
                  trials_per_arm=len(group), a39_verified_par2_s=round(a39, 6),
                  a40_verified_par2_s=round(a40, 6),
                  kissat_verified_par2_s=round(kissat, 6),
                  a40_vs_a39_ratio=round(a39/a40, 6) if a40 else None,
                  paired_wins=wins, paired_losses=losses, paired_ties=tie,
                  a39_conflicts=conflicts39, a40_conflicts=conflicts40,
                  changed_clause_ranks=changed, sat_verified=confirmed_sat,
                  recommendation="DO_NOT_TRAIN: 26 source SHA total, retrospective cohort")
    summaries.append(report)
    print("GENERALIST2_FAMILY " + json.dumps(report, sort_keys=True), flush=True)

global_result = {"families": len(summaries), "original_sha": len(source_meta),
                 "paired_repetitions": len(pairs),
                 "selector_trained": False,
                 "independent_unsat_proof_verified": False}
print("GENERALIST2_FAMILY_AUDIT " + json.dumps(global_result, sort_keys=True), flush=True)
Path("generalist2_family_report.json").write_text(
    json.dumps({"summary": global_result, "families": summaries}, indent=2) + "\n")
