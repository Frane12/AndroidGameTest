#!/usr/bin/env python3
"""EQUIV9: preregistered SHA-disjoint original SATComp CNF, single-core seed hedge.

Prospective holdout with fixed 4s/8s cold-restart policies selected on EQUIV8,
never tuned on the new holdout. A separate smoke cohort runs first. SAT witness
verified against original CNF. UNSAT accepted for PAR2 only with original-input
Kissat + CaDiCaL agreement (not independent LRAT). No auto-promotion.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import tempfile
import time

import drnas_equiv8_native_seed_hedge as e8
import drnas_x22_parallel_reducer as x22

ROOT = pathlib.Path("mre_equiv9")
SOURCE = ROOT / "cases"
CAD = pathlib.Path("mre_equiv7/bin/cadical_3_0_1")
NATIVE = pathlib.Path("mre_x4/bin/native")
KISSAT = pathlib.Path("built/bin/kissat_4_0_4")
LIB = pathlib.Path("mre5/lib/libcryptominisat5.so.5.11")
PROTO = "DRNAS-EQUIV9-PROSPECTIVE-SHA-ONECPU-6ARM-2REP-20S-v1"
SALT = "DRNAS-EQUIV9-20261110-SOURCE-ONLY-HOLDOUT-NO-RESELECTION"
ARMS = ("native1", "native_split4", "native_split8", "native_altseed",
        "kissat1", "cadical301_default")
SMOKE = 4
HOLDOUT = 12
TARGET = SMOKE + HOLDOUT
REPS = 2
SHARDS = 6
CAP_SMOKE = 12.0
CAP_HOLDOUT = 20.0
MAX_SCAN = 900
YEARS = ("2021", "2022", "2023")
PRIOR = {
    "x20": pathlib.Path("mre_x20/manifest.json"),
    "x21": pathlib.Path("prior_x22/mre_x22/manifest.json"),
    "equiv6": pathlib.Path("prior_equiv6/mre_equiv6/manifest.json"),
    "equiv7": pathlib.Path("mre_equiv7/manifest.json"),
}
BINARIES = (NATIVE, KISSAT, CAD, LIB)

# Preserve EQUIV8's native/Kissat process launch and SAT model verifier.
# Only add an unmodified CaDiCaL 3.0.1 default arm.
_e8_command = e8.command
def command(arm, source, seed):
    if arm == "cadical301_default":
        return [str(CAD), str(source)]
    return _e8_command(arm, source, seed)
e8.command = command

def need(ok, reason):
    if not ok:
        raise RuntimeError("EQUIV9_FAIL_CLOSED " + str(reason))

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def save(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")

def seedpair(sha, rep):
    need(sha and 0 <= rep < REPS, "bad seed request")
    a = int(hashlib.sha256((sha + "|EQUIV9_BASE|" + str(rep)).encode()).hexdigest()[:7], 16)
    b = int(hashlib.sha256((sha + "|EQUIV9_ALT|" + str(rep)).encode()).hexdigest()[:7], 16)
    need(a != b, "identical seed pair")
    return a, b

def registries():
    old = {}
    excluded_sha, excluded_ids = set(), set()
    expected = {"x20":24, "x21":24, "equiv6":16, "equiv7":48}
    for tag, path in PRIOR.items():
        m = json.loads(path.read_text())
        cases = m["cases"]
        need(len(cases) == expected[tag], "prior registry size " + tag)
        old[tag] = digest(path)
        for case in cases:
            excluded_sha.add(case["sha256"])
            excluded_ids.add(case["gbd"])
    # The single EQUIV8 previously seen formula is not in the 48-source EQUIV7 standard cohort.
    excluded_sha.add(e8.TARGET_SHA)
    excluded_ids.add(e8.TARGET_GBD)
    return excluded_sha, excluded_ids, old

def freeze():
    ROOT.mkdir(parents=True, exist_ok=True)
    SOURCE.mkdir(parents=True, exist_ok=True)
    for p in BINARIES:
        need(p.is_file(), "missing pinned binary " + str(p))
    excluded_sha, excluded_ids, prior_digests = registries()
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as fetch
    candidates, indexes = [], {}
    for year in YEARS:
        ids, mainsha = pool.getids("track=main_" + year)
        easy, easysha = pool.getids("track=main_" + year + " and minisat1m=yes")
        need(len(ids) == 400 and set(easy) <= set(ids), "official index drift " + year)
        indexes[year] = dict(index_sha256=mainsha, easy_sha256=easysha, eligible=len(easy))
        easyset = set(easy)
        candidates.extend((year, gbd, 0) for gbd in easy if gbd not in excluded_ids)
        candidates.extend((year, gbd, 1) for gbd in ids
                          if gbd not in easyset and gbd not in excluded_ids)
    candidates = sorted(set(candidates), key=lambda t: (
        t[2], hashlib.sha256((SALT + "|" + t[0] + "|" + t[1]).encode()).hexdigest()))
    seen, cases, trace = set(), [], []
    for year, gbd, tier in candidates:
        if len(cases) == TARGET:
            break
        if gbd in seen or gbd in excluded_ids:
            continue
        seen.add(gbd)
        need(len(seen) <= MAX_SCAN, "source-only scan cap exhausted")
        path = SOURCE / (gbd + ".cnf")
        record = dict(year=year, gbd=gbd,
                      index_tier="minisat1m_yes" if tier == 0 else "full_main")
        try:
            raw = fetch.get("https://benchmark-database.de/file/" + gbd,
                            12 * 1024 * 1024, seconds=20)
            plain, _ = fetch.prior.r32p.decode(raw)
            need(len(plain) <= 12 * 1024 * 1024, "source size cap")
            n, k = fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(0 < n <= 12000 and 0 < k <= 85000, "source geometry cap")
            sha = hashlib.sha256(plain).hexdigest()
            need(sha not in excluded_sha, "previously seen original SHA")
            path.write_bytes(plain)
            n2, clauses = x22.read_cnf(path)
            need(n2 == n and len(clauses) == k, "original DIMACS mismatch")
            cohort = "smoke" if len(cases) < SMOKE else "holdout"
            cases.append(dict(gbd=gbd, year=year, sha256=sha,
                              filename=path.name, cohort=cohort,
                              vars=n, clauses=k, bytes=len(plain)))
            excluded_sha.add(sha)
            excluded_ids.add(gbd)
            record.update(action="frozen", cohort=cohort, sha256=sha)
        except Exception as ex:
            path.unlink(missing_ok=True)
            record.update(action="excluded_without_solving", reason=str(ex)[:170])
        trace.append(record)
        print("EQUIV9_SOURCE", json.dumps(record, sort_keys=True), flush=True)
        save(ROOT / "selection-progress.json",
             dict(salt=SALT, selected=len(cases), trace=trace))
    need(len(cases) == TARGET, "insufficient SHA-disjoint source CNF")
    need(len({c["sha256"] for c in cases}) == TARGET, "SHA duplicates")
    manifest = dict(protocol=PROTO, source_only_selection=True,
        globally_blind=False, holdout_not_seen_by_equiv9_before_freeze=True,
        no_solver_outcome_selection=True, no_auto_promotion=True,
        exact_original_cnf=True, caps_s=dict(smoke=CAP_SMOKE,holdout=CAP_HOLDOUT),
        single_logical_cpu=True, sequential_children=True,
        previously_tested_equiv8_source_excluded=True,
        no_independent_UNSAT_LRAT=True,
        smoke_count=SMOKE, holdout_count=HOLDOUT, reps=REPS, shards=SHARDS,
        expected_smoke=SMOKE*len(ARMS), expected_holdout=HOLDOUT*REPS*len(ARMS),
        arms=list(ARMS), prior_registry_sha256=prior_digests,
        code_sha256=digest(__file__),
        binary_sha256={str(p):digest(p) for p in BINARIES},
        selection_salt=SALT, official_indexes=indexes,
        selection_trace=trace, cases=cases)
    save(ROOT / "manifest.json", manifest)
    verify()
    print("EQUIV9_FROZEN", json.dumps(dict(smoke=SMOKE, holdout=HOLDOUT,
          unique_sha=TARGET, source_only=True,
          tests=manifest["expected_smoke"]+manifest["expected_holdout"]),
          sort_keys=True),flush=True)

def verify():
    m = json.loads((ROOT / "manifest.json").read_text())
    need(m["protocol"] == PROTO and m["arms"] == list(ARMS)
         and m["smoke_count"] == SMOKE and m["holdout_count"] == HOLDOUT
         and m["reps"] == REPS and m["shards"] == SHARDS
         and len(m["cases"]) == TARGET and
         m["expected_smoke"] == SMOKE*len(ARMS) and
         m["expected_holdout"] == HOLDOUT*REPS*len(ARMS),
         "frozen protocol drift")
    need(m["code_sha256"] == digest(__file__), "code changed since freeze")
    need(m["binary_sha256"] == {str(p):digest(p) for p in BINARIES},
         "binary SHA changed")
    sha, ids, prior = registries()
    need(m["prior_registry_sha256"] == prior, "prior registry SHA drift")
    need(len({c["sha256"] for c in m["cases"]}) == TARGET, "duplicate SHA")
    for i, c in enumerate(m["cases"]):
        need(c["cohort"] == ("smoke" if i < SMOKE else "holdout"),
             "cohort altered")
        need(c["gbd"] not in ids and c["sha256"] not in sha,
             "source overlaps historic registries")
        src = SOURCE / c["filename"]
        need(digest(src) == c["sha256"], "original source SHA drift")
    return m

def trial(case, rep, arm, cap, toy=False):
    need(arm in ARMS and 0 <= rep < REPS, "invalid trial")
    src = SOURCE / case["filename"] if not toy else pathlib.Path(case["filename"])
    need(digest(src) == case["sha256"], "original SHA mismatch")
    n, clauses = x22.read_cnf(src)
    need(n > 0 and len(clauses) > 0, "invalid original CNF")
    base, alt = seedpair(case["sha256"], rep)
    allowed = sorted(os.sched_getaffinity(0))
    need(bool(allowed), "logical CPU unavailable")
    cpu = allowed[0]
    started = time.perf_counter()
    before = x22.child_cpu()
    plan = [(base, cap)]
    if arm == "native_altseed":
        plan = [(alt, cap)]
    if arm == "native_split4":
        plan = [(base, 4.0), (alt, cap)]
    if arm == "native_split8":
        plan = [(base, 8.0), (alt, cap)]
    stages = []
    status = "TIMEOUT"
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        for i, (seed, budget_hint) in enumerate(plan):
            remaining = cap - (time.perf_counter() - started)
            if remaining < 0.07:
                break
            stage = e8.one_stage(arm,src,clauses,seed,cpu,min(budget_hint,remaining),td,i)
            stages.append(stage)
            if stage["status"] in ("SAT","UNSAT"):
                status = stage["status"]
                break
    elapsed = time.perf_counter() - started
    if elapsed >= cap:
        status = "TIMEOUT"
    sat_verified = status == "SAT" and any(
        t["SAT_original_witness_verified"] and t["status"] == "SAT" for t in stages)
    need(status != "SAT" or sat_verified, "original SAT witness invalid")
    return dict(protocol=PROTO,sha256=case["sha256"],gbd=case["gbd"],
       cohort=case["cohort"],rep=rep,arm=arm,cap_s=cap,
       seed_base=base,seed_alt=alt,original_sha256_verified=True,
       pinned_cpu=cpu, child_starts=len(stages),
       SAT_original_witness_verified=sat_verified,UNSAT_independent_LRAT=False,
       status=status,wall_E2E_s=round(elapsed,6),
       child_CPU_s=round(x22.child_cpu()-before,6),stages=stages)

def selftest():
    ROOT.mkdir(parents=True, exist_ok=True)
    for p in BINARIES:
        need(p.is_file(), "missing binary on selftest")
    with tempfile.TemporaryDirectory() as td:
        source = pathlib.Path(td)/"toy.cnf"
        source.write_text("p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n")
        case=dict(filename=str(source),sha256=digest(source),gbd="toy",cohort="smoke")
        for arm in ARMS:
            r=trial(case,0,arm,CAP_SMOKE,toy=True)
            need(r["status"]=="SAT" and r["SAT_original_witness_verified"],
                 "toy SAT original model "+arm)
    print("EQUIV9_SELFTEST_PASS",len(ARMS),flush=True)

def shard(kind, idx):
    m=verify()
    need(kind in ("smoke","holdout"),"invalid cohort")
    if kind=="smoke":
        need(idx == 0,"smoke shard must be zero")
        subset=m["cases"][:SMOKE]
        reps=(0,)
        output=ROOT/"smoke-0.json"
    else:
        need(0<=idx<SHARDS,"bad holdout shard")
        subset=m["cases"][SMOKE+idx::SHARDS]
        need(len(subset)==HOLDOUT//SHARDS,"bad holdout shard balance")
        reps=range(REPS)
        output=ROOT/("holdout-%d.json"%idx)
    rows=[]
    for case in subset:
        for rep in reps:
            arms=list(ARMS)
            random.Random(seedpair(case["sha256"],rep)[0]).shuffle(arms)
            for arm in arms:
                r=trial(case,rep,arm,CAP_SMOKE if kind=="smoke" else CAP_HOLDOUT)
                rows.append(r)
                save(output,rows)
                print("EQUIV9_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    expected=len(subset)*len(reps)*len(ARMS)
    need(len(rows)==expected,"missing shard trial")
    print("EQUIV9_SHARD_PASS",kind,idx,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for p in [ROOT/"smoke-0.json"] + [
           ROOT/("holdout-%d.json"%idx) for idx in range(SHARDS)]:
        need(p.is_file(),"missing shard "+str(p))
        rows.extend(json.loads(p.read_text()))
    cases={c["sha256"]:c for c in m["cases"]}
    expected={(c["sha256"],rep,arm)
       for c in m["cases"]
       for rep in (range(REPS) if c["cohort"]=="holdout" else (0,))
       for arm in ARMS}
    actual={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(actual)==len(rows)==len(expected) and actual==expected,
         "missing / duplicate SHA paired attempts")
    bysha=collections.defaultdict(list)
    for r in rows:
        c=cases[r["sha256"]]
        need(r["protocol"]==PROTO and r["gbd"]==c["gbd"]
             and r["cohort"]==c["cohort"] and
             r["cap_s"]==(CAP_SMOKE if c["cohort"]=="smoke" else CAP_HOLDOUT)
             and r["seed_base"]==seedpair(r["sha256"],r["rep"])[0]
             and r["seed_alt"]==seedpair(r["sha256"],r["rep"])[1]
             and r["original_sha256_verified"]
             and r["child_starts"]==len(r["stages"]) and r["child_starts"]<=2
             and r["wall_E2E_s"]<=r["cap_s"]+0.07,
             "invalid original SHA, seed or CPU budget")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "unverified original SAT")
        bysha[r["sha256"]].append(r)
    consensus=set()
    for sha, rr in bysha.items():
        statuses={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT vs UNSAT mismatch "+sha)
        if any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr) and (
           any(r["arm"]=="cadical301_default" and r["status"]=="UNSAT" for r in rr)):
            consensus.add(sha)
    def accepted(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in consensus)
    scores={}
    for kind in ("smoke","holdout"):
        subset=[r for r in rows if r["cohort"]==kind]
        scores[kind]={}
        for arm in ARMS:
            group=[r for r in subset if r["arm"]==arm]
            scores[kind][arm]=dict(
              attempts=len(group),solved=sum(accepted(r) for r in group),
              SAT_verified=sum(r["status"]=="SAT" for r in group),
              UNSAT_agreement_no_LRAT=sum(r["status"]=="UNSAT" and accepted(r) for r in group),
              UNSAT_not_verified=sum(r["status"]=="UNSAT" and not accepted(r) for r in group),
              timeouts=sum(r["status"]=="TIMEOUT" for r in group),
              PAR2_s=round(sum(r["wall_E2E_s"] if accepted(r) else 2*r["cap_s"]
                               for r in group),6),
              actual_child_CPU_s=round(sum(r["child_CPU_s"] for r in group),6),
              child_process_starts=sum(r["child_starts"] for r in group),
              second_seed_solves=sum(r["status"]=="SAT" and len(r["stages"])==2 for r in group))
        for arm in ARMS:
            scores[kind][arm]["speedup_vs_kissat_PAR2_x"]=round(
               scores[kind]["kissat1"]["PAR2_s"]/scores[kind][arm]["PAR2_s"],6)
            scores[kind][arm]["speedup_vs_native_PAR2_x"]=round(
               scores[kind]["native1"]["PAR2_s"]/scores[kind][arm]["PAR2_s"],6)
            scores[kind][arm]["speedup_vs_cadical_PAR2_x"]=round(
               scores[kind]["cadical301_default"]["PAR2_s"]/scores[kind][arm]["PAR2_s"],6)
    report=dict(protocol=PROTO, source_count=TARGET, smoke_count=SMOKE,
        held_out_count=HOLDOUT, sources_new_to_equiv9=True,
        globally_blind=False, prior_SHA_exclusion_limited_to_loaded_registries=True,
        frozen_source_only_before_solver_trials=True,
        original_SAT_witness_verification=True,
        independent_UNSAT_LRAT=False,UNSAT_reference_agreement_SHA=sorted(consensus),
        one_logical_CPU_per_arm=True,no_parallel_children=True,
        total_trials=len(rows),cap_smoke_s=CAP_SMOKE,cap_holdout_s=CAP_HOLDOUT,
        scores=scores,
        per_sha={sha:dict(gbd=cases[sha]["gbd"],cohort=cases[sha]["cohort"],
            per_arm={arm:dict(statuses=[r["status"] for r in rr if r["arm"]==arm],
                E2E_s=[r["wall_E2E_s"] for r in rr if r["arm"]==arm])
                for arm in ARMS}) for sha,rr in bysha.items()})
    save(ROOT/"report.json",report)
    print("EQUIV9_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("freeze","verify","selftest","shard","audit"))
    parser.add_argument("--kind",choices=("smoke","holdout"),default="holdout")
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="shard":
        shard(args.kind,args.shard)
    else:
        globals()[args.action]()
        if args.action=="verify":
            print("EQUIV9_VERIFY_PASS",flush=True)
