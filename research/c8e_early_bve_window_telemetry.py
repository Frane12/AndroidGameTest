#!/usr/bin/env python3
"""C8E: measure CDCL state immediately before/after real CaDiCaL BVE events.

Uses pinned CaDiCaL 1.7.3 instrumentation and C8C's frozen development SAT
sources. This is a bounded diagnostic, not PAR2 and not blind validation.
At each source's observed first BVE conflict boundary, run fresh processes at
-128, 0, +128, +512 conflicts with identical original bytes. Compare keeping
BVE, candidate/pivot skip ablations, late-candidate negative control, and
--no-elim. Record actual conflicts, propagations, decisions, learned clauses,
learned literals, restarts, BVE counters, vivification counters and glue
progress text. No learned state crosses processes. SAT outputs are replayed
against the original CNF; any UNSAT contradicts the frozen SAT cohort.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, statistics, subprocess, time
import c8c_pivot_causal_audit as c8c
import c7_standard_solver_bve_crosscheck as c7
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO = "DRNAS-C8E-3SHA-FIRST-BVE-4WINDOW-7ARM-2REP-BOUNDED-TELEMETRY-v1"
OUT = pathlib.Path("c8e_out")
REPS = 2
CAP_S = 12.0
OFFSETS = (-128, 0, 128, 512)
ARMS = ("keep", "skip_first_candidate", "skip_first_8_candidates",
        "skip_first_success", "skip_first_8_success",
        "skip_late_8_candidates", "noelim")
METRICS = ("conflicts", "decisions", "propagations", "restarts",
           "learned", "learnedlits", "elimtried", "elimres",
           "eliminated", "elimrounds", "vivifications", "vivifychecks",
           "vivified", "reductions")

def need(ok, msg):
    if not ok:
        raise RuntimeError("C8E_FAIL_CLOSED " + str(msg))

def digest(p):
    return c7.digest(p)

def get_case(i):
    x = c8c.source(i)
    need(c7.digest(x["path"]) == x["sha256"], "frozen original CNF SHA mismatch")
    need(x.get("expected_status", "SAT") == "SAT", "C8E cohort must remain SAT")
    return x

def profile(i):
    p = OUT / f"profile-{i}.json"
    need(p.is_file(), "missing C8C first-event profile")
    x = json.loads(p.read_text())
    c = get_case(i)
    need(x["protocol"] == "DRNAS-C8C-3SHA-CAUSAL-BVE-PIVOT-SKIP-8ARMS-2REPS-25S-v1"
         and x["sha256"] == c["sha256"], "C8C profile/source mismatch")
    need(x["identical_pristine_vs_instrumented_CADICAL_stats"],
         "instrumentation parity control did not pass")
    need(x["first_candidate_conflict"] > 0, "invalid first BVE boundary")
    return x

def skip_map(p):
    x = p["skipped_candidate_order_development_only"]
    need(set(x) >= set(ARMS) - {"noelim"}, "C8C registered skip map incomplete")
    return x

def bounded(i, rep, arm, budget):
    c = get_case(i)
    p = profile(i)
    choices = skip_map(p)
    need(arm in ARMS and rep in range(REPS), "unregistered arm/repetition")
    bin_path = pathlib.Path(c8c.BIN["patched"]).resolve()
    cmd = [str(bin_path), "-c", str(budget), "-v"]
    selected = []
    if arm == "noelim":
        cmd.append("--no-elim")
    elif arm != "keep":
        selected = choices[arm]
    cmd.append(str(pathlib.Path(c["path"]).resolve()))
    env = os.environ.copy()
    env["DRNAS_C8C_TRACE"] = "1"
    env.pop("DRNAS_C8C_SKIP_VARS", None)
    if selected:
        env["DRNAS_C8C_SKIP_VARS"] = ",".join(map(str, selected))
    started = time.perf_counter()
    timed_out = False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                              timeout=CAP_S, check=False, env=env)
        stdout, stderr = proc.stdout, proc.stderr
        status, model = ref.external_parse(proc)
        if status == "SAT":
            cms.verify_model(c["path"], model)
        need(status != "UNSAT", "solver contradicted frozen original SAT source")
        terminal = status
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        if isinstance(stdout, bytes): stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes): stderr = stderr.decode("utf-8", "replace")
        terminal = "WALL_TIMEOUT"
    wall = time.perf_counter() - started
    stats, glue = c8c.c8.parse_stats(stdout)
    events = c8c.parse_c8c(stderr)
    # Keep compact local evidence around the registered checkpoint.
    near = [x for x in events if abs(int(x.get("conflicts", -10**9)) - budget) <= 512]
    if len(near) > 80:
        near = near[:40] + near[-40:]
    need(not timed_out or wall >= CAP_S - 0.05, "timeout accounting mismatch")
    return dict(protocol=PROTO, source_sha256=c["sha256"], gbd=c["gbd"],
        source_index=i, rep=rep, arm=arm, selected_skip_vars=selected,
        event_anchor_conflicts=p["first_candidate_conflict"],
        target_offset=budget-p["first_candidate_conflict"],
        requested_conflict_cap=budget, terminal=terminal, diagnostic_only=True,
        wall_s=round(wall, 6), cap_s=CAP_S, stats=stats,
        glue_progress_samples=glue[:30], trace_event_count=len(events),
        trace_near_window=near, build_sha=os.getenv("GITHUB_SHA", "LOCAL"))

def verify():
    need(len(c8c.sources()) == 3, "C8C source cohort count changed")
    for i in range(3):
        c = get_case(i)
        p = profile(i)
        need(p["first_candidate_conflict"] == int(p["first_candidate_conflict"]),
             "bad anchor type")
        need(set(skip_map(p)) >= set(ARMS)-{"noelim"}, "skip arms changed")
    print("C8E_FROZEN_SOURCE_AND_FIRST_EVENT_PROFILES_PASS",
          json.dumps([dict(gbd=get_case(i)["gbd"],
              sha256=get_case(i)["sha256"],
              first_candidate_conflicts=profile(i)["first_candidate_conflict"],
              first_success_conflicts=profile(i)["first_accepted_conflict"],
              first_success_ids=profile(i)["first_accepted_ids"][:8])
              for i in range(3)], sort_keys=True), flush=True)

def shard(i):
    need(i in range(3), "invalid source shard")
    c, p = get_case(i), profile(i)
    anchor = int(p["first_candidate_conflict"])
    budgets = sorted(set(max(1, anchor+d) for d in OFFSETS))
    OUT.mkdir(exist_ok=True)
    rows = []
    for rep in range(REPS):
        # Fixed deterministic order rotation reduces systematic warm/cold bias.
        schedule = [(b, a) for b in budgets for a in ARMS]
        shift = (rep + i) % len(schedule)
        schedule = schedule[shift:] + schedule[:shift]
        for budget, arm in schedule:
            row = bounded(i, rep, arm, budget)
            rows.append(row)
            (OUT / f"shard-{i}.json").write_text(
                json.dumps(rows, sort_keys=True, indent=2) + "\n")
            print("C8E_PROBE", json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == REPS*len(budgets)*len(ARMS), "probe matrix incomplete")
    print("C8E_SHARD_PASS", i, len(rows), flush=True)

def audit():
    cases = [get_case(i) for i in range(3)]
    rows = []
    for i, c in enumerate(cases):
        path = OUT / f"shard-{i}.json"
        need(path.is_file(), "missing source-paired diagnostics")
        part = json.loads(path.read_text())
        p = profile(i)
        budgets = sorted(set(max(1, int(p["first_candidate_conflict"])+d)
                             for d in OFFSETS))
        need(len(part) == REPS*len(budgets)*len(ARMS), "partial source matrix")
        seen = set()
        for x in part:
            need(x["protocol"] == PROTO and x["gbd"] == c["gbd"]
                 and x["source_sha256"] == c["sha256"]
                 and x["diagnostic_only"] is True
                 and x["requested_conflict_cap"] in budgets
                 and x["target_offset"] in OFFSETS
                 and x["arm"] in ARMS and x["rep"] in range(REPS),
                 "source/protocol/window drift")
            key = (x["rep"], x["requested_conflict_cap"], x["arm"])
            need(key not in seen, "duplicate paired diagnostic")
            seen.add(key)
            need(x["terminal"] in ("SAT", "UNKNOWN", "WALL_TIMEOUT"),
                 "unsupported bounded terminal")
            need(x["terminal"] != "SAT" or x["stats"].get("conflicts", 0) <= x["requested_conflict_cap"]+16,
                 "SAT terminal passed registered conflict window")
            need(all(isinstance(v, int) and v >= 0 for v in x["stats"].values()),
                 "invalid CDCL/BVE counter")
        need(len(seen) == REPS*len(budgets)*len(ARMS), "paired matrix missing")
        rows.extend(part)
    # Pairwise changes at the same original SHA, rep and conflict cap.
    pairs = collections.defaultdict(dict)
    for x in rows:
        pairs[(x["source_sha256"], x["rep"], x["requested_conflict_cap"])][x["arm"]] = x
    comparisons = []
    for key, arms in sorted(pairs.items()):
        need(set(arms) == set(ARMS), "unpaired same-window arms")
        base = arms["keep"]
        for arm in ARMS[1:]:
            test = arms[arm]
            delta = {}
            for m in METRICS:
                a = base["stats"].get(m)
                b = test["stats"].get(m)
                if a is not None and b is not None:
                    delta[m] = b-a
            def rate(row, numerator, denominator):
                n, d = row["stats"].get(numerator), row["stats"].get(denominator)
                return round(n/d, 6) if n is not None and d else None
            comparisons.append(dict(source_sha256=key[0], gbd=base["gbd"],
                rep=key[1], target_conflicts=key[2],
                offset=base["target_offset"], arm=arm,
                keep_terminal=base["terminal"], arm_terminal=test["terminal"],
                delta_vs_keep=delta,
                propagations_per_conflict=dict(keep=rate(base,"propagations","conflicts"),
                    arm=rate(test,"propagations","conflicts")),
                learned_clauses_per_conflict=dict(keep=rate(base,"learned","conflicts"),
                    arm=rate(test,"learned","conflicts")),
                average_learned_clause_literals=dict(
                    keep=rate(base,"learnedlits","learned"),
                    arm=rate(test,"learnedlits","learned")),
                bve_trace_events_near_window=len(test["trace_near_window"])))
    report = dict(protocol=PROTO,
        cohort="three previously studied C8 SAT development sources; no blind claim",
        upstream_cadical="1.7.3 pinned C8C source SHA",
        source_count=3, reps=REPS, offsets=list(OFFSETS), arms=list(ARMS),
        bounded_probes=len(rows), paired_window_comparisons=len(comparisons),
        diagnostic_only_not_PAR2=True, no_learning_state_transfer=True,
        SAT_witness_replay_on_original_when_solved=True,
        UNSAT_independent_LRAT=False, no_auto_promotion=True,
        primary_metrics=["propagations/conflict","decisions","learned clauses/conflict",
          "learned clause average length","restarts","BVE tried/resolvents/eliminated",
          "vivification checks/changes","raw glue progress samples"],
        comparisons=comparisons)
    OUT.mkdir(exist_ok=True)
    (OUT/"report.json").write_text(json.dumps(report, sort_keys=True, indent=2)+"\n")
    print("C8E_FINAL", json.dumps({k:v for k,v in report.items() if k!="comparisons"},
          sort_keys=True), flush=True)
    for x in comparisons:
        print("C8E_DELTA", json.dumps(x, sort_keys=True), flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("verify","shard","audit"))
    ap.add_argument("--shard", type=int, default=0)
    a = ap.parse_args()
    if a.action == "verify": verify()
    elif a.action == "shard": shard(a.shard)
    else: audit()
