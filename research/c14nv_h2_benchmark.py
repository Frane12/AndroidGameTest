#!/usr/bin/env python3
"""C14NV H2: source-disjoint official2026 replication of frozen C14 no-vivify."""
import argparse, collections, csv, hashlib, io, json, os, pathlib, random, shutil, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import c14_factorial as c14
h = c14.helpers
PROTO = "DRNAS-C14NV-H2-NEW12-5ARM-2REP-30S-v1"
SALT = "DRNAS-C14NV-H2-SHA-DISJOINT-20261109-FROZEN-v1"
SRC, OUT = pathlib.Path("c14nv_sources"), pathlib.Path("c14nv_out")
ARMS = ("c14_no_vivify", "matched_default", "noelim", "upstream_default", "kissat")
CAP, REPS, SHARDS = 30.0, 2, 6
C8H_IDS = ("fdfcd52a21824b7181d66672f283ba04",
           "695d8f6a2ee6e89e5a4f5d94abc3aca6",
           "037d21e060a2e3eab8b080aa84ceee75")
C11B_IDS = ("776ff89b72b0f6290d69af6f95e13182", "2563ea83d8508d635cc034d80014cd72",
            "5cae5c0629ce1c724746af890410cfc1", "808d66b11c602eb1d5728f3f8e90aaef",
            "3ed56242f55e3653dbceeb4a70221787")
need, digest = c14.need, h.digest
def save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2, sort_keys=True) + "\n")
def digest_bytes(b):
    return hashlib.sha256(b).hexdigest()
def add_case(cases, gbd, data, status, cohort, expected_sha=None):
    sha = digest_bytes(data)
    need(expected_sha is None or sha == expected_sha, "original source SHA drift")
    need(all(x["sha256"] != sha for x in cases), "duplicate source")
    n, m = h.r32p.parse_dimacs_metadata(data)
    filename = gbd + ".cnf"
    (SRC / filename).write_bytes(data)
    cases.append(dict(gbd=gbd, sha256=sha, filename=filename, status=status,
                      nvars=n, nclauses=m, bytes=len(data), cohort=cohort))
def prepare():
    """Freeze 12 new official source CNFs before any timed solver invocation."""
    SRC.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    old_ids, old_shas, provenance = h.prior()
    old_ids.update(C11B_IDS)
    # Explicitly exclude C13, all C14/C8H/C15D controls, and C15D new official
    # sources. This is indexed SHA-disjoint, not a claim of global blindness.
    prior_files = ("c13_sources/manifest.json",
                   "prior_c15d/c15d_sources/manifest.json")
    for item in prior_files:
        path = pathlib.Path(item)
        need(path.is_file(), "required historical manifest missing: " + item)
        doc = json.loads(path.read_text())
        need(len(doc.get("cases", [])) >= 12, "empty historical exclusion registry")
        for x in doc["cases"]:
            old_ids.add(x["gbd"]); old_shas.add(x["sha256"])
        provenance[item] = digest(path)
    reg_path = pathlib.Path("prior_c8h/c7_source/dedup/manifest.json")
    registry = json.loads(reg_path.read_text())["sources"]
    for x in registry.values():
        old_ids.add(x["gbd"]); old_shas.add(x["original_sha256"])
    provenance[str(reg_path)] = digest(reg_path)
    index = h.r52.fetch_bytes(h.r52.URI, 100000)
    ids = [x.strip().rsplit("/", 1)[-1] for x in index.decode().splitlines() if x.strip()]
    need(len(ids) == len(set(ids)) == 400, "official source index drift")
    score_bytes = h.r52.fetch_bytes(h.r52.SCORES, 32*1024*1024)
    statuses = {x["instanceid"]: h.STATUS.get(x["status"])
                for x in csv.DictReader(io.StringIO(score_bytes.decode()))
                if x.get("solverid") == "biere_cadical3[main]"}
    need(len(statuses) == 400, "official status index incomplete")
    ranked = sorted((g for g in ids if g not in old_ids),
                    key=lambda g: digest_bytes((SALT + "|" + g).encode()))
    cases, attempts, counts = [], [], collections.Counter()
    h.r32p.CNF_LIMIT = 15 * 1024 * 1024
    for gbd in ranked:
        if len(cases) == 12:
            break
        status = statuses.get(gbd)
        if status not in ("SAT", "UNSAT") or counts[status] >= 6:
            continue
        record = dict(gbd=gbd, published_status=status)
        try:
            raw, _ = h.r32p.request_url("https://benchmark-database.de/file/" + gbd,
                                       12*1024*1024, seconds=25)
            data, _ = h.r32p.decode(raw)
            n, m = h.r32p.parse_dimacs_metadata(data)
            need(len(data) <= 15*1024*1024 and 100 <= n <= 30000 and
                 0 < m <= 300000, "precommitted size bound")
            sha = digest_bytes(data)
            need(sha not in old_shas, "historically seen SHA collision")
            add_case(cases, gbd, data, status, "new_official", sha)
            counts[status] += 1
            record.update(accepted=True, sha256=sha, nvars=n, nclauses=m)
        except Exception as exc:
            record.update(accepted=False,
                          reason=(type(exc).__name__ + ":" + str(exc))[:180])
        attempts.append(record)
        print("C14NV_SOURCE_SCAN " + json.dumps(record, sort_keys=True), flush=True)
    need(len(cases) == 12 and counts == {"SAT": 6, "UNSAT": 6},
         "precommitted 6 SAT / 6 UNSAT quota unmet; no benchmark allowed")
    manifest = dict(protocol=PROTO, cases=cases, salt=SALT, cap_s=CAP,
                    repetitions=REPS, controls=list(ARMS),
                    candidate="same frozen CaDiCaL binary with --no-vivify",
                    candidate_frozen_before_new_timing=True,
                    original_cnf_unchanged=True, independent_UNSAT_LRAT=False,
                    global_blind_claim=False,
                    disjoint_from_indexed_prior_manifests=True,
                    selection_only_status_size_and_salted_GBD=True,
                    index_sha256=digest_bytes(index),
                    status_file_sha256=digest_bytes(score_bytes),
                    historical_provenance=provenance,
                    scan_attempts=attempts)
    save(SRC / "manifest.json", manifest)
    print("C14NV_FROZEN " + json.dumps(dict(cases=12, sat=6, unsat=6,
          manifest_sha256=digest(SRC / "manifest.json")), sort_keys=True), flush=True)

def cases():
    d = json.loads((SRC / "manifest.json").read_text())
    need(d["protocol"] == PROTO and d["candidate_frozen_before_new_timing"] and
         d["selection_only_status_size_and_salted_GBD"], "manifest drift")
    cc = d["cases"]
    need(len(cc) == len({x["sha256"] for x in cc}) == 12, "source count mismatch")
    for x in cc:
        need(digest(SRC / x["filename"]) == x["sha256"], "source hash changed")
    return cc
def command(arm, path):
    need(arm in ARMS, "unknown arm")
    binary = pathlib.Path("built/bin/kissat_4_0_4" if arm == "kissat" else
                          "c8c/bin/plain" if arm == "upstream_default" else "c8c/bin/instrumented")
    env = {k:v for k,v in os.environ.items() if not k.startswith(("DRNAS_C8", "DRNAS_C14", "DRNAS_C15"))}
    options = ["--no-vivify"] if arm == "c14_no_vivify" else (["--no-elim"] if arm == "noelim" else [])
    return [str(binary.resolve()), *options, str(path.resolve())], env, binary
def smoke():
    OUT.mkdir(exist_ok=True)
    p = OUT / "smoke.cnf"; p.write_text("p cnf 2 2\n1 2 0\n-1 2 0\n")
    for arm in ARMS:
        cmd, env, _ = command(arm, p)
        proc = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=5)
        need(proc.returncode == 10, "smoke failed: " + arm)
        state, model = h.ref.external_parse(proc)
        need(state == "SAT", "smoke parse failed")
        h.cms.verify_model(p, model)
    print("C14NV_SMOKE_PASS", flush=True)
def trial(x, arm, rep, position, order_seed):
    p = SRC / x["filename"]
    need(digest(p) == x["sha256"], "pre-trial SHA mismatch")
    cmd, env, binary = command(arm, p)
    started = time.perf_counter(); verified = False
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                              errors="replace", timeout=CAP)
        wall = time.perf_counter() - started
        need(proc.returncode in (10, 20), "unexpected solver exit " + str(proc.returncode))
        status, model = h.ref.external_parse(proc)
        need(status == x["status"], "reference contradiction")
        if status == "SAT":
            h.cms.verify_model(p, model); verified = True
        stats = c14.stats_lines(proc.stdout)
        if wall > CAP: status, verified = "TIMEOUT", False
    except subprocess.TimeoutExpired as exc:
        wall, status = time.perf_counter() - started, "TIMEOUT"
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stats = c14.stats_lines(stdout)
    return dict(protocol=PROTO, source_sha256=x["sha256"], gbd=x["gbd"], cohort=x["cohort"],
                arm=arm, rep=rep, order_position=position, order_seed=order_seed,
                status=status, reference=x["status"], SAT_original_witness_verified=verified,
                UNSAT_published_agreement=status == "UNSAT", UNSAT_independent_LRAT=False,
                wall_s=round(wall, 6), PAR2_s=round(wall if status != "TIMEOUT" else 2*CAP, 6),
                binary_sha256=digest(binary), cap_s=CAP, native_stats=stats,
                timing_excludes_model_check=True, independent_solver_seed=False,
                commit_sha=os.environ.get("GITHUB_SHA", "local"))
def shard(index):
    need(index in range(SHARDS), "bad shard index")
    cc = [x for i,x in enumerate(cases()) if i % SHARDS == index]
    need(len(cc) == 2, "source partition changed")
    rows = []
    for x in cc:
        for rep in range(REPS):
            seed = int(digest_bytes((PROTO + x["sha256"] + str(rep)).encode())[:8], 16)
            order = list(ARMS); random.Random(seed).shuffle(order)
            for position, arm in enumerate(order):
                r = trial(x, arm, rep, position, seed); rows.append(r)
                save(OUT / ("shard-%d.json" % index), rows)
                print("C14NV_TRIAL " + json.dumps(r, sort_keys=True), flush=True)
    need(len(rows) == 2 * REPS * len(ARMS), "incomplete shard")
    print("C14NV_SHARD_PASS %d %d" % (index, len(rows)), flush=True)
def audit():
    cc, rows = cases(), []
    for i in range(SHARDS):
        part = json.loads((OUT / ("shard-%d.json" % i)).read_text())
        need(len(part) == 2 * REPS * len(ARMS), "missing trials"); rows.extend(part)
    expected = {(x["sha256"], a, rep) for x in cc for a in ARMS for rep in range(REPS)}
    keys = [(r["source_sha256"], r["arm"], r["rep"]) for r in rows]
    need(len(keys) == len(set(keys)) == len(expected) and set(keys) == expected, "paired keys mismatch")
    bysha = {x["sha256"]:x for x in cc}
    for r in rows:
        x = bysha[r["source_sha256"]]
        need(r["protocol"] == PROTO and r["cap_s"] == CAP and r["cohort"] == x["cohort"], "row metadata drift")
        need(r["status"] in ("SAT", "UNSAT", "TIMEOUT"), "unknown status")
        if r["status"] != "TIMEOUT":
            need(r["status"] == x["status"] and r["PAR2_s"] == r["wall_s"], "bad solved result")
            need(r["status"] != "SAT" or r["SAT_original_witness_verified"], "missing SAT witness")
        else: need(r["PAR2_s"] == 2*CAP, "bad timeout PAR2")
    need(len({r["binary_sha256"] for r in rows if r["arm"] in ("c14_no_vivify", "matched_default", "noelim")}) == 1,
         "candidate and matched default binary mismatch")
    def scores(group):
        result = {}
        for a in ARMS:
            rr = [r for r in group if r["arm"] == a]
            result[a] = dict(attempts=len(rr), solved=sum(r["status"] != "TIMEOUT" for r in rr),
                             PAR2_s=round(sum(r["PAR2_s"] for r in rr),6))
        return result
    per_case = {x["gbd"]:dict(cohort=x["cohort"], scores=scores([r for r in rows if r["gbd"] == x["gbd"]])) for x in cc}
    report = dict(protocol=PROTO, trials=len(rows), cap_s=CAP, global_blind_claim=False,
                  adaptive_policy=False, independent_solver_seeds=False,
                  candidate="C14 no-vivify replicated on fresh indexed-SHA-disjoint official CNFs", independent_UNSAT_LRAT=False,
                  scores=scores(rows), by_cohort={c:scores([r for r in rows if r["cohort"] == c])
                  for c in sorted({x["cohort"] for x in cc})}, per_case=per_case)
    save(OUT / "report.json", report)
    print("C14NV_FINAL " + json.dumps(report, sort_keys=True), flush=True)
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "smoke", "shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    a = parser.parse_args()
    if a.action == "prepare": prepare()
    elif a.action == "smoke": smoke()
    elif a.action == "shard": shard(a.shard)
    else: audit()
