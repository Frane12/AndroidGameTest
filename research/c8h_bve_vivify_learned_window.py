#!/usr/bin/env python3
"""C8H: isolate BVE attempts from the simplification schedule and trace learned clauses."""
from __future__ import annotations
import collections, hashlib, json, os, pathlib, random, re, subprocess, statistics
import c8c_pivot_causal_audit as c8c
import c7_standard_solver_bve_crosscheck as c7

PROTO = "DRNAS-C8H-3SHA-9ARM-3REP-LEARNED-CLAUSE-WINDOW-v1"
OUT = pathlib.Path("c8h_out")
CAP_S = 25.0
PROBE_CAP_S = 12.0
REPS = 3
PROBE_REPS = 2
E2E_ARMS = (
    "default", "instrumented_control",
    "skip_all_bve", "skip_all_bve_novivify",
    "novivify", "noelim_legacy",
    "skip_first_candidate", "skip_first_8_candidates",
    "skip_late_8_candidates",
)
PROBE_ARMS = (
    "keep", "skip_all_bve", "skip_all_bve_novivify",
    "novivify", "noelim_legacy",
    "skip_first_candidate", "skip_first_8_candidates",
    "skip_late_8_candidates",
)
LEARNED_RE = re.compile(
    r"^C8H_LEARNED conflict=(\d+) learned=(\d+) "
    r"uip_size=(\d+) final_size=(\d+) glue=(\d+)$"
)

def need(ok, msg):
    if not ok:
        raise RuntimeError("C8H_FAIL_CLOSED " + str(msg))

def source_and_profile(i):
    c = c8c.source(i)
    need(c7.digest(c["path"]) == c["sha256"], "source SHA mismatch")
    need(c.get("expected_status", "SAT") == "SAT", "cohort must remain SAT")
    p = c8c.profiles(i)
    need(p["sha256"] == c["sha256"], "C8C profile/source mismatch")
    return c, p

def configure(arm, choices):
    opts, env = [], {}
    binary = "patched"
    key = arm
    if arm in ("default", "noelim_legacy"):
        binary = "plain"
        if arm == "noelim_legacy":
            opts = ["--no-elim"]
    elif arm == "instrumented_control" or arm == "keep":
        pass
    elif arm == "novivify":
        opts = ["--no-vivify"]
    elif arm == "skip_all_bve":
        env["DRNAS_C8C_SKIP_ALL_BVE"] = "1"
    elif arm == "skip_all_bve_novivify":
        env["DRNAS_C8C_SKIP_ALL_BVE"] = "1"
        opts = ["--no-vivify"]
    elif arm in ("skip_first_candidate", "skip_first_8_candidates",
                  "skip_late_8_candidates"):
        selected = choices[key]
        need(bool(selected), "missing source-locked candidate list " + arm)
        env["DRNAS_C8C_SKIP_VARS"] = ",".join(map(str, selected))
    else:
        raise RuntimeError("unregistered C8H arm " + str(arm))
    return binary, opts, env

def parse_learned(stderr):
    rows = []
    for line in stderr.splitlines():
        m = LEARNED_RE.match(line.strip())
        if not m:
            continue
        conflict, learned, uip_size, final_size, glue = map(int, m.groups())
        rows.append(dict(conflicts=conflict, learned=learned,
                         uip_size=uip_size, final_size=final_size, glue=glue))
    return rows

def bounded_probe(c, p, choices, arm, rep, trace=True):
    binary, opts, extra = configure(arm, choices)
    budget = int(p["first_candidate_conflict"]) + 512
    cmd = [str(pathlib.Path(c8c.BIN[binary]).resolve()),
           "-c", str(budget), "-v", *opts,
           str(pathlib.Path(c["path"]).resolve())]
    env = os.environ.copy()
    for name in ("DRNAS_C8C_TRACE", "DRNAS_C8C_SKIP_VARS",
                 "DRNAS_C8C_SKIP_ALL_BVE", "DRNAS_C8H_LEARNED_TRACE",
                 "DRNAS_C8H_MIN_CONFLICT"):
        env.pop(name, None)
    env.update(extra)
    env["DRNAS_C8C_TRACE"] = "1"
    env["DRNAS_C8H_LEARNED_TRACE"] = "1" if trace else "0"
    env["DRNAS_C8H_MIN_CONFLICT"] = str(max(0, p["first_candidate_conflict"] - 128))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              errors="replace", timeout=PROBE_CAP_S,
                              check=False, env=env)
    except subprocess.TimeoutExpired:
        return dict(arm=arm, rep=rep, trace=trace, budget=budget,
                    timed_out=True, status="WALL_TIMEOUT", stats={},
                    learned_events=[], bve_candidates=0,
                    skipped_candidates=0, vivify_events=0)
    status, model = c8c.ref.external_parse(proc)
    if status == "SAT":
        c8c.cms.verify_model(c["path"], model)
    need(status != "UNSAT", "instrumented solver contradicted original SAT")
    stats, _ = c8c.c8.parse_stats(proc.stdout)
    events = c8c.parse_c8c(proc.stderr)
    candidates = [x for x in events if x.get("kind") == "C8C_CANDIDATE"]
    learned = parse_learned(proc.stderr) if trace else []
    if arm in ("skip_all_bve", "skip_all_bve_novivify"):
        need(bool(candidates), "skip-all probe observed no scheduled BVE candidates")
        need(all(x.get("skip") == 1 for x in candidates),
             "skip-all control allowed a BVE candidate attempt")
        need(stats.get("eliminated", 0) == 0,
             "skip-all control unexpectedly eliminated a variable")
    return dict(arm=arm, rep=rep, trace=trace, budget=budget,
                timed_out=False, status=status, stats=stats,
                learned_events=learned,
                bve_candidates=len(candidates),
                skipped_candidates=sum(x.get("skip") == 1 for x in candidates),
                vivify_events=sum(x.get("kind") == "C8C_VIVIFY_END"
                                  for x in events))

def quantile(xs, q):
    if not xs:
        return None
    values = sorted(xs)
    return values[min(len(values)-1, int((len(values)-1)*q))]

def summarize_window(events, lo, hi):
    xs = [x for x in events if lo <= x["conflicts"] <= hi]
    glue = [x["glue"] for x in xs]
    final = [x["final_size"] for x in xs]
    raw = [x["uip_size"] for x in xs]
    removed = [a-b for a, b in zip(raw, final)]
    return dict(learned_clauses=len(xs),
                mean_glue=round(statistics.mean(glue), 4) if glue else None,
                median_glue=quantile(glue, 0.5),
                mean_final_size=round(statistics.mean(final), 4) if final else None,
                median_final_size=quantile(final, 0.5),
                p90_final_size=quantile(final, 0.9),
                mean_uip_size=round(statistics.mean(raw), 4) if raw else None,
                mean_literals_removed=round(statistics.mean(removed), 4)
                    if removed else None,
                glue_le_2=sum(x <= 2 for x in glue),
                glue_3_to_5=sum(3 <= x <= 5 for x in glue),
                glue_6_to_10=sum(6 <= x <= 10 for x in glue),
                glue_gt_10=sum(x > 10 for x in glue))

def clause_profile(events, anchor):
    windows = {
        "pre_event_128": (max(0, anchor-128), anchor-1),
        "event_to_plus128": (anchor, anchor+128),
        "plus128_to_plus512": (anchor+129, anchor+512),
    }
    return {name:summarize_window(events, lo, hi)
            for name,(lo,hi) in windows.items()}

def diagnostic(shard):
    c, p = source_and_profile(shard)
    choices = p["skipped_candidate_order_development_only"]
    OUT.mkdir(exist_ok=True)
    # Observability check: toggling C8H stderr telemetry must not change CDCL counters.
    off = bounded_probe(c, p, choices, "keep", 0, trace=False)
    on = bounded_probe(c, p, choices, "keep", 0, trace=True)
    need(not off["timed_out"] and not on["timed_out"],
         "instrumentation parity control timed out")
    need(off["stats"] == on["stats"] and off["status"] == on["status"],
         "learned-clause logging changed solver behavior")
    parity = dict(stats_identical=off["stats"] == on["stats"],
                  status_identical=off["status"] == on["status"],
                  traced_learned_clauses=len(on["learned_events"]))
    rows = []
    for rep in range(PROBE_REPS):
        for arm in PROBE_ARMS:
            row = bounded_probe(c, p, choices, arm, rep, trace=True)
            need(not row["timed_out"], "bounded learned-clause window timed out")
            rows.append(row)
            print("C8H_PROBE " + json.dumps(
                dict(gbd=c["gbd"], arm=arm, rep=rep, status=row["status"],
                     conflicts=row["stats"].get("conflicts"),
                     learned=row["stats"].get("learned"),
                     propagations=row["stats"].get("propagations"),
                     eliminated=row["stats"].get("eliminated"),
                     vivifychecks=row["stats"].get("vivifychecks"),
                     vivified=row["stats"].get("vivified"),
                     bve_candidates=row["bve_candidates"],
                     skipped_candidates=row["skipped_candidates"],
                     learned_events=len(row["learned_events"])),
                sort_keys=True), flush=True)
    payload = dict(protocol=PROTO, gbd=c["gbd"], source_sha256=c["sha256"],
                   event_anchor_conflicts=p["first_candidate_conflict"],
                   instrumentation_parity=parity, probes=rows)
    (OUT / ("telemetry-%d.json" % shard)).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("C8H_DIAGNOSTIC_PASS %d %d" % (shard, len(rows)), flush=True)

def full_config(arm, choices):
    return configure(arm, choices)

def benchmark(shard):
    c, p = source_and_profile(shard)
    choices = p["skipped_candidate_order_development_only"]
    OUT.mkdir(exist_ok=True)
    rows = []
    seed = int(hashlib.sha256((PROTO + "|" + c["sha256"]).encode()).hexdigest()[:8], 16)
    for rep in range(REPS):
        order = list(E2E_ARMS)
        order_seed = seed ^ (rep * 0x9E3779B1)
        random.Random(order_seed).shuffle(order)
        for order_index, arm in enumerate(order):
            binary, opts, env = full_config(arm, choices)
            result = c8c.run_bin(c, binary, opts=opts, env_extra=env,
                                 verbose=False, cap=CAP_S)
            row = dict(protocol=PROTO, source_index=shard, gbd=c["gbd"],
                       source_sha256=c["sha256"], arm=arm, rep=rep,
                       order_index=order_index, run_order_seed=order_seed,
                       independent_seed_applied=False, cap_s=CAP_S,
                       solver_process_wall_included=True,
                       external_router_header_used=False,
                       binary=binary, options=opts,
                       selected_skip_variables=choices.get(arm, [])
                           if arm in ("skip_first_candidate",
                                      "skip_first_8_candidates",
                                      "skip_late_8_candidates") else [],
                       status=result["status"],
                       original_SAT_witness_verified=
                           result["original_sat_model_verified"],
                       wall_s=result["wall_s"], PAR2_s=result["PAR2_s"])
            rows.append(row)
            print("C8H_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == len(E2E_ARMS) * REPS, "incorrect full trial count")
    (OUT / ("full-%d.json" % shard)).write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print("C8H_BENCH_SHARD_PASS %d %d" % (shard, len(rows)), flush=True)

def audit():
    full_paths = sorted(OUT.glob("full-*.json"))
    rows = [row for path in full_paths for row in json.loads(path.read_text())]
    need(len(rows) == 3 * len(E2E_ARMS) * REPS,
         "incomplete C8H full-solve factorial")
    need(len({x["source_sha256"] for x in rows}) == 3, "source hash set mismatch")
    need(not any(x["status"] == "UNSAT" for x in rows),
         "SAT source contradicted by an ablation")
    need(all(x["original_SAT_witness_verified"] for x in rows
             if x["status"] == "SAT"), "unverified SAT witness")
    need(all(x["solver_process_wall_included"] and
             not x["external_router_header_used"] for x in rows),
         "incorrect end-to-end timing scope")
    per_arm = collections.defaultdict(list)
    per_source_arm = collections.defaultdict(list)
    for x in rows:
        per_arm[x["arm"]].append(x)
        per_source_arm[(x["gbd"], x["arm"])].append(x)
    scores = {}
    base = None
    for arm in E2E_ARMS:
        xs = per_arm[arm]
        need(len(xs) == 9, "missing 3x3 source/repeat cells " + arm)
        scores[arm] = dict(PAR2_s=round(sum(x["PAR2_s"] for x in xs), 6),
                           actual_wall_s=round(sum(x["wall_s"] for x in xs), 6),
                           solved=sum(x["status"] == "SAT" for x in xs),
                           timeouts=sum(x["status"] != "SAT" for x in xs),
                           trials=len(xs))
    base = scores["default"]["PAR2_s"]
    for x in scores.values():
        x["speedup_vs_default_x"] = round(base / x["PAR2_s"], 6)
    per_source = []
    for gbd in sorted({x["gbd"] for x in rows}):
        arms = {}
        for arm in E2E_ARMS:
            xs = per_source_arm[(gbd, arm)]
            need(len(xs) == 3, "source missing one or more repetitions")
            arms[arm] = dict(PAR2_s=round(sum(x["PAR2_s"] for x in xs), 6),
                             actual_wall_s=round(sum(x["wall_s"] for x in xs), 6),
                             solved=sum(x["status"] == "SAT" for x in xs),
                             timeouts=sum(x["status"] != "SAT" for x in xs))
        per_source.append(dict(gbd=gbd, arms=arms))

    tel_paths = sorted(OUT.glob("telemetry-*.json"))
    telemetry = [json.loads(path.read_text()) for path in tel_paths]
    need(len(telemetry) == 3, "missing learned-clause telemetry sources")
    need(all(x["instrumentation_parity"]["stats_identical"] and
             x["instrumentation_parity"]["status_identical"] for x in telemetry),
         "learned telemetry instrumentation changed solver counters")
    learned_profiles = []
    skipall_checks = []
    for x in sorted(telemetry, key=lambda y:y["gbd"]):
        anchor = x["event_anchor_conflicts"]
        source_profile = dict(gbd=x["gbd"], source_sha256=x["source_sha256"],
                              anchor_conflicts=anchor,
                              instrumentation_parity=x["instrumentation_parity"],
                              arms={})
        by_arm = collections.defaultdict(list)
        for probe in x["probes"]:
            by_arm[probe["arm"]].append(probe)
        for arm in PROBE_ARMS:
            ps = by_arm[arm]
            need(len(ps) == PROBE_REPS, "missing learned-probe repeat " + arm)
            source_profile["arms"][arm] = [
                dict(rep=p["rep"], stats={k:p["stats"].get(k) for k in
                     ("conflicts","learned","propagations","decisions",
                      "elimtried","eliminated","vivifychecks","vivified")},
                     bve_candidates=p["bve_candidates"],
                     skipped_candidates=p["skipped_candidates"],
                     clause_windows=clause_profile(p["learned_events"], anchor))
                for p in ps]
        for p in by_arm["skip_all_bve"]:
            skipall_checks.append(dict(
                gbd=x["gbd"], rep=p["rep"],
                every_scheduled_candidate_skipped=(
                    p["bve_candidates"] == p["skipped_candidates"]),
                eliminated=p["stats"].get("eliminated", 0),
                vivifychecks=p["stats"].get("vivifychecks", 0),
                vivified=p["stats"].get("vivified", 0)))
        learned_profiles.append(source_profile)
    report = dict(protocol=PROTO,
                  cohort="three previously studied C8 development SAT originals; no blind claim",
                  source_count=3, cap_s=CAP_S, repeats=REPS,
                  full_trials=len(rows), full_E2E_PAR2_includes_solver_process_wall=True,
                  external_router_header_used=False, original_SAT_models_checked=True,
                  independent_solver_seeds=False, independent_UNSAT_LRAT=False,
                  bounded_learned_clause_probes_per_source=len(PROBE_ARMS)*PROBE_REPS,
                  bounded_probes_are_not_PAR2=True,
                  learned_clause_fields=["first-UIP size","minimized final size",
                                          "glue/LBD","conflict index"],
                  skipall_control="suppresses each BVE candidate attempt while leaving the elimination/subsumption schedule active",
                  noelim_legacy_is_confounded=True, no_auto_promotion=True,
                  scores=scores, per_source=per_source,
                  skipall_vivify_checks=skipall_checks,
                  learned_clause_window_profiles=learned_profiles)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("C8H_FINAL " + json.dumps(dict(full_trials=len(rows), scores=scores,
        skipall_vivify_checks=skipall_checks), sort_keys=True), flush=True)
    for x in per_source:
        print("C8H_CASE " + json.dumps(x, sort_keys=True), flush=True)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("diagnostic","bench","audit"))
    parser.add_argument("--shard", type=int)
    args = parser.parse_args()
    if args.command in ("diagnostic","bench"):
        need(args.shard in (0,1,2), "invalid source shard")
        if args.command == "diagnostic":
            diagnostic(args.shard)
        else:
            benchmark(args.shard)
    else:
        audit()

if __name__ == "__main__":
    main()
