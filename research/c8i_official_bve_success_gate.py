#!/usr/bin/env python3
"""C8I: early BVE-success gate prospective test on frozen official SAT2026 SHA."""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, re, subprocess, time
import c7_standard_solver_bve_crosscheck as c7
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO = "DRNAS-C8I-OFFICIAL2026-12SHA-EARLY-BVE-SUCCESS-GATE16-6ARM-2REP-20S-v1"
ROOT = pathlib.Path("c9c_official")
OUT = pathlib.Path("c8i_out")
MANIFEST = ROOT / "manifest.json"
CAP_S = 20.0
REPS = 2
SHARDS = 4
ARMS = ("cadical", "instrumented_control", "skip_all_bve",
        "gate16", "cadical_noelim", "kissat")
GATE_RE = re.compile(
    r"^C8I_GATE_DECISION candidates=16 early_successes=(\d+) "
    r"disabled=([01]) conflicts=(\d+)$"
)

def need(ok, msg):
    if not ok:
        raise RuntimeError("C8I_FAIL_CLOSED " + str(msg))

def cases():
    need(MANIFEST.is_file(), "missing frozen C9c official source manifest")
    m = json.loads(MANIFEST.read_text())
    need(m.get("protocol") == "DRNAS-C9C-2026-FROZEN-12SHA-PUBLISHED-STATUS-BALANCED-v1",
         "unexpected official-source manifest protocol")
    need(m.get("all_original_SHA_frozen_before_ANY_solver_trial") is True,
         "source freeze was not recorded before solver runs")
    need(len(m.get("cases", [])) == 12 and m.get("original_source_count") == 12,
         "expected exactly 12 source-locked official formulas")
    out = []
    for x in m["cases"]:
        c = dict(gbd=x["gbd"], sha256=x["sha256"], filename=x["filename"],
                 path=ROOT / x["filename"], expected=x["status"],
                 nvars=x["variables"], nclauses=x["clauses"])
        need(c["expected"] in ("SAT", "UNSAT"), "missing official status")
        need(c7.digest(c["path"]) == c["sha256"], "source SHA mismatch " + c["gbd"])
        out.append(c)
    need(len({x["sha256"] for x in out}) == 12, "duplicate official source SHA")
    return out

def parse_gate(stderr):
    for line in stderr.splitlines():
        m = GATE_RE.match(line.strip())
        if m:
            return dict(candidates=16, early_successes=int(m.group(1)),
                        disabled=bool(int(m.group(2))), conflicts=int(m.group(3)))
    return None

def command(arm, source):
    path = str(source["path"].resolve())
    if arm == "cadical":
        return ["c8c/bin/plain", path]
    if arm in ("instrumented_control", "skip_all_bve", "gate16"):
        return ["c8c/bin/instrumented", path]
    if arm == "cadical_noelim":
        return ["c8c/bin/plain", "--no-elim", path]
    if arm == "kissat":
        return ["built/bin/kissat_4_0_4", path]
    raise RuntimeError("unknown C8I arm " + arm)

def trial(source, arm, rep, order_index, order_seed):
    need(c7.digest(source["path"]) == source["sha256"], "source changed before trial")
    cmd = command(arm, source)
    cmd[0] = str(pathlib.Path(cmd[0]).resolve())
    env = os.environ.copy()
    for key in ("DRNAS_C8C_TRACE", "DRNAS_C8C_SKIP_VARS",
                "DRNAS_C8C_SKIP_ALL_BVE", "DRNAS_C8H_LEARNED_TRACE",
                "DRNAS_C8H_MIN_CONFLICT", "DRNAS_C8I_EARLY_GATE16",
                "DRNAS_C8I_GATE_TRACE"):
        env.pop(key, None)
    if arm == "skip_all_bve":
        env["DRNAS_C8C_SKIP_ALL_BVE"] = "1"
    if arm == "gate16":
        env["DRNAS_C8I_EARLY_GATE16"] = "1"
        env["DRNAS_C8I_GATE_TRACE"] = "1"
    start = time.perf_counter()
    proc = None
    partial_stderr = ""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                              timeout=CAP_S, check=False, env=env)
    except subprocess.TimeoutExpired as exc:
        partial_stderr = (exc.stderr.decode("utf-8", "replace")
                          if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
    wall = time.perf_counter() - start
    status = "TIMEOUT"
    verified = False
    if proc is not None:
        status, model = ref.external_parse(proc)
        need(status in ("SAT", "UNSAT", "UNKNOWN", "TIMEOUT"),
             "unrecognized terminal status")
        if status == "SAT":
            cms.verify_model(source["path"], model)
            verified = True
        if status in ("SAT", "UNSAT"):
            need(status == source["expected"],
                 "solver contradicted official reference status for " + source["gbd"])
    gate = parse_gate(proc.stderr if proc is not None else partial_stderr) if arm == "gate16" else None
    if gate is not None:
        need(gate["disabled"] == (gate["early_successes"] == 0),
             "gate decision disagrees with early BVE success count")
    if wall > CAP_S or status not in ("SAT", "UNSAT"):
        status = "TIMEOUT"
        verified = False
    return dict(protocol=PROTO, gbd=source["gbd"], source_sha256=source["sha256"],
                source_nvars=source["nvars"], source_nclauses=source["nclauses"],
                official_reference_status=source["expected"], arm=arm, rep=rep,
                order_index=order_index, order_seed=order_seed,
                independent_seed_applied=False, cap_s=CAP_S,
                full_solver_process_wall_included=True,
                original_source_SHA_unmodified=True,
                selected_binary=cmd[0], status=status,
                SAT_original_witness_verified=verified,
                UNSAT_published_status_agreement=(status == "UNSAT"),
                independent_UNSAT_LRAT=False, gate_decision=gate,
                wall_s=round(wall, 6),
                PAR2_s=round(wall if status in ("SAT", "UNSAT") else 2 * CAP_S, 6))

def shard(i):
    need(i in range(SHARDS), "invalid shard index")
    OUT.mkdir(exist_ok=True)
    selected = [(j, c) for j, c in enumerate(cases()) if j % SHARDS == i]
    need(len(selected) == 3, "expected three frozen source formulas per shard")
    rows = []
    for index, source in selected:
        for rep in range(REPS):
            seed = int(hashlib.sha256(
                (PROTO + "|" + source["sha256"] + "|" + str(rep)).encode()
            ).hexdigest()[:8], 16)
            order = list(ARMS)
            random.Random(seed).shuffle(order)
            for pos, arm in enumerate(order):
                row = trial(source, arm, rep, pos, seed)
                rows.append(row)
                print("C8I_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == 3 * len(ARMS) * REPS, "incorrect shard trial count")
    (OUT / ("shard-%d.json" % i)).write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print("C8I_SHARD_PASS %d %d" % (i, len(rows)), flush=True)

def audit():
    paths = sorted(OUT.glob("shard-*.json"))
    rows = [x for p in paths for x in json.loads(p.read_text())]
    expected = 12 * len(ARMS) * REPS
    need(len(rows) == expected, "incomplete official-source factorial")
    need(len({x["source_sha256"] for x in rows}) == 12, "source SHA coverage mismatch")
    need(all(x["full_solver_process_wall_included"] and
             x["original_source_SHA_unmodified"] for x in rows),
         "timing or original-source scope mismatch")
    need(all(x["SAT_original_witness_verified"] for x in rows
             if x["status"] == "SAT"), "SAT model witness not checked")
    need(all(x["UNSAT_published_status_agreement"] for x in rows
             if x["status"] == "UNSAT"), "UNSAT status agreement missing")
    by_arm = collections.defaultdict(list)
    by_case = collections.defaultdict(list)
    for x in rows:
        by_arm[x["arm"]].append(x)
        by_case[(x["gbd"], x["arm"])].append(x)
    scores = {}
    for arm in ARMS:
        xs = by_arm[arm]
        need(len(xs) == 24, "missing per-arm trials " + arm)
        scores[arm] = dict(PAR2_s=round(sum(x["PAR2_s"] for x in xs), 6),
                           actual_wall_s=round(sum(x["wall_s"] for x in xs), 6),
                           solved=sum(x["status"] in ("SAT", "UNSAT") for x in xs),
                           timeouts=sum(x["status"] == "TIMEOUT" for x in xs),
                           trials=len(xs))
    baseline = scores["cadical"]["PAR2_s"]
    for s in scores.values():
        s["speedup_vs_cadical_x"] = round(baseline / s["PAR2_s"], 6)
    gate_decisions = collections.defaultdict(list)
    per_formula = []
    for source in sorted({x["gbd"] for x in rows}):
        values = {}
        for arm in ARMS:
            xs = by_case[(source, arm)]
            need(len(xs) == REPS, "missing paired repeats for " + source + "/" + arm)
            values[arm] = dict(PAR2_s=round(sum(x["PAR2_s"] for x in xs), 6),
                               solved=sum(x["status"] in ("SAT", "UNSAT") for x in xs))
            if arm == "gate16":
                decisions = [x["gate_decision"] for x in xs if x["gate_decision"]]
                if decisions:
                    need(len({(d["early_successes"], d["disabled"]) for d in decisions}) == 1,
                         "deterministic gate class differed between repetitions " + source)
                    gate_decisions[source] = decisions
        per_formula.append(dict(gbd=source, arms=values,
                                gate_decisions=gate_decisions.get(source, [])))
    gate_closed = sum(bool(ds) and ds[0]["disabled"] for ds in gate_decisions.values())
    gate_open = sum(bool(ds) and not ds[0]["disabled"] for ds in gate_decisions.values())
    gate_unobserved = 12 - gate_closed - gate_open
    gate_rows = by_arm["gate16"]
    report = dict(protocol=PROTO,
                  cohort="12 original SHA-frozen official SAT2026 sources from C9c; source cohort was previously tested with other arms, C8I gate not previously tested",
                  source_count=12, statuses_balanced=True, cap_s=CAP_S, repeats=REPS,
                  full_trials=len(rows), arms=list(ARMS),
                  independent_external_seeds=False, independent_UNSAT_LRAT=False,
                  SAT_original_witnesses_checked=True,
                  gate_rule="In each BVE round, attempt the first 16 candidates; if none eliminates a variable, skip the remaining candidates in that round while preserving the simplification schedule. Only the first decision is summarized.",
                  gate_decisions=dict(formulas_gate_closed=gate_closed,
                                      formulas_gate_open=gate_open,
                                      formulas_without_captured_first_decision=gate_unobserved,
                                      trials_with_decision=sum(x["gate_decision"] is not None for x in gate_rows)),
                  scores=scores, per_formula=per_formula,
                  no_auto_promotion=True, global_blind_claim=False)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\\n")
    print("C8I_FINAL " + json.dumps(dict(scores=scores, gate_decisions=report["gate_decisions"]),
                                    sort_keys=True), flush=True)
    for x in per_formula:
        print("C8I_CASE " + json.dumps(x, sort_keys=True), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("shard", "audit"))
    parser.add_argument("--shard", type=int)
    args = parser.parse_args()
    if args.command == "shard":
        shard(args.shard)
    else:
        audit()

if __name__ == "__main__":
    main()
