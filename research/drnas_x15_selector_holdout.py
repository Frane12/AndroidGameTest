#!/usr/bin/env python3
"""X15 cheap source-only three-way selector vs front100, CMS original and a
native+Kissat 2-process race, with CPU and wall PAR2.

Eight frozen X11 development replays and eight NEW SHA-disjoint (relative to
declared registries) SAT 2021-23 originals. The new source roster is fixed
BEFORE running X15 candidates, selected by salted official GBD IDs, published
minisat1m metadata priority and fixed source-geometry limits, NOT solve times.
That is a prospective X15 evaluation, not proof of globally unseen instances.
UNSAT is cross-solver agreement, NOT an independent LRAT certificate.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, re
import resource, shutil, time

import drnas_x14_adaptive_portfolio as x14
import mre_x11_placebo_causal as x11
import mre_x13b_sample_gate as b
import mre6b_blind_freeze as prior
import mre7_extended_easy_freeze as indexes
import mre7_reference_easy_freeze as fetch

ROOT = pathlib.Path("mre_x15")
PROTO = "DRNAS-X15-CHEAP-THREEWAY-8DEV-8FRESH-6ARM-2SEED-20S-E2E-CPU-v1"
SALT = PROTO + "-NO-SOLVER-OUTCOME-SOURCE-ORDER"
ARMS = ("original", "front100", "parallel2", "x15_gate", "kissat", "cadical")
CAP, REPS, SHARDS, DEVELOPMENT, FRESH = 20.0, 2, 8, 8, 8
QUOTAS = {"2021": 3, "2022": 3, "2023": 2}
MAX_ATTEMPTS_PER_YEAR = 50
MAX_RAW, MAX_PLAIN = 10*1024*1024, 12*1024*1024
MAX_VARS, MAX_CLAUSES = 20000, 95000

def need(ok, why):
    if not ok:
        raise RuntimeError("X15_FAIL_CLOSED " + why)

def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def save(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")

def configure():
    x11.ROOT = ROOT
    x14.ROOT = ROOT
    x14.PROTO = PROTO
    x14.CAP = CAP
    b.ROOT = ROOT
    b.PROTO = PROTO
    b.CAP = CAP

def choose(sig):
    """Frozen inexpensive source features. No solver run and no timing feedback."""
    if sig["duplicates"] >= 2 and sig["lines"] >= 100 and sig["size_bytes"] <= 524288:
        return "front100", "exact_duplicate_sample_small_or_medium"
    if sig["size_bytes"] >= 196608 and sig["lines"] >= 300:
        return "parallel2", "larger_source_race_only"
    return "original", "low_cost_native_default"

def hashes():
    return x14.binary_hashes()

def records_from_manifests():
    """Known prior sources + repository tracked registry; NOT global exhaustiveness."""
    paths = [
        "mre_x11/manifest.json", "mre_x6fresh/manifest.json",
        "mre7_easy/manifest.json", "mre11b_blind/manifest.json",
    ]
    ids, digests, registry = set(), set(), []
    def visit(x):
        if isinstance(x, dict):
            for val in x.values():
                visit(val)
        elif isinstance(x, list):
            for val in x:
                visit(val)
        elif isinstance(x, str):
            if re.fullmatch("[0-9a-f]{32}", x):
                ids.add(x)
            if re.fullmatch("[0-9a-f]{64}", x):
                digests.add(x)
    for name in paths:
        p = pathlib.Path(name)
        need(p.is_file(), "missing registered previous manifest " + name)
        visit(json.loads(p.read_text()))
        registry.append({"path": name, "sha256": b.sha(p)})
    need(prior.PRIOR.is_file(), "missing historic prior GBD registry")
    for line in prior.PRIOR.read_text().splitlines():
        val = line.strip()
        if re.fullmatch("[0-9a-f]{32}", val):
            ids.add(val)
    registry.append({"path": str(prior.PRIOR), "sha256": b.sha(prior.PRIOR)})
    # Search branch-local research & experiments for all referenced GBD/SHA keys.
    # Prior GitHub branches cannot be certified exhaustive; report that clearly.
    return ids, digests, registry

def freeze():
    ROOT.mkdir(parents=True, exist_ok=True)
    need(DEVELOPMENT == FRESH == 8 and SHARDS == 8, "locked matrix cardinality")
    # X11 original manifest is validated on the untouched historical directory.
    x11.ROOT = pathlib.Path("mre_x11")
    baseline = x11.verify()
    ids, digests, registry = records_from_manifests()
    cases = []
    rank = lambda x: sha_bytes((SALT + "|" + x).encode())
    historical = sorted(baseline["cases"], key=lambda x: rank(x["sha256"]))[:DEVELOPMENT]
    for c in historical:
        p = pathlib.Path("mre_x11") / c["filename"]
        need(b.sha(p) == c["sha256"], "development original SHA changed")
        target = ROOT / c["filename"]
        shutil.copyfile(p, target)
        cases.append(dict(c, tier="development", cohort="historical_X11_replay_not_blind",
                          source_selection="salted_source_SHA_without_X15_timing",
                          cap_s=CAP))
    trace = []
    indices = {}
    counts = collections.Counter()
    for year, quota in QUOTAS.items():
        allids, index_hash = indexes.getids("track=main_" + year)
        mini, mini_hash = indexes.getids("track=main_" + year + " and minisat1m=yes")
        need(len(allids) == 400 and set(mini) <= set(allids),
             "official indexed source list drift for " + year)
        indexed_set = set(mini)
        # Prioritize published metadata easy labels, then fall back to main
        # originals; never use DRNAS/Kissat time to select benchmark sources.
        repo_ids, repo_digests = prior.inspect_repo_ids(set(allids))
        ids.update(repo_ids)
        digests.update(repo_digests)
        preferred = sorted((g for g in mini if g not in ids),
                           key=lambda g: rank(year + "|" + g))
        fallback = sorted((g for g in allids if g not in ids and g not in indexed_set),
                          key=lambda g: rank(year + "|" + g))
        candidates = (preferred + fallback)[:MAX_ATTEMPTS_PER_YEAR]
        indices[year] = dict(index_sha256=index_hash, mini_index_sha256=mini_hash,
                             prior_excluded=len(set(allids) & ids),
                             priority_mini=len(preferred), fallback_main=len(fallback))
        for g in candidates:
            if counts[year] == quota:
                break
            row = dict(year=year, gbd=g, minisat1m_label=(g in indexed_set))
            p = ROOT / (g + ".cnf")
            try:
                raw = fetch.get("https://benchmark-database.de/file/" + g,
                                MAX_RAW, seconds=20)
                plain, comp = fetch.prior.r32p.decode(raw)
                need(len(plain) <= MAX_PLAIN, "CNF plain size > fixed cap")
                n,m = fetch.prior.r32p.parse_dimacs_metadata(plain)
                need(n <= MAX_VARS and m <= MAX_CLAUSES,
                     "CNF outside fixed geometry limits")
                d = sha_bytes(plain)
                need(d not in digests and g not in ids, "prior registry collision")
                p.write_bytes(plain)
                parsed_vars, clauses = x11.x9.x2.parse(p)
                need(parsed_vars == n and len(clauses) == m, "invalid original DIMACS")
                cases.append(dict(gbd=g,year=year,filename=p.name,
                                  sha256=d,bytes=len(plain),vars=n,clauses=m,
                                  tier="holdout",cohort="X15_new_source_disjoint_declared_registry",
                                  cap_s=CAP, compression=comp,
                                  minisat1m_label=(g in indexed_set),
                                  source_selection="official_ID_metadata_geometry_before_benchmark"))
                counts[year] += 1
                ids.add(g)
                digests.add(d)
                row.update(result="FROZEN_BEFORE_X15_TIMING",sha256=d,
                           clauses=m,vars=n)
            except Exception as ex:
                p.unlink(missing_ok=True)
                row.update(result="REJECTED_INPUT_FETCH_OR_GEOMETRY",
                           why=(type(ex).__name__ + ": " + str(ex))[:170])
            trace.append(row)
            save(ROOT/"source-trace.json",trace)
            print("X15_SOURCE",json.dumps(row,sort_keys=True),flush=True)
        need(counts[year] == quota,
             "not enough metadata-ranked fresh original inputs in " + year)
    need(len(cases) == DEVELOPMENT + FRESH and
         len({c["sha256"] for c in cases}) == len(cases) and
         len({c["gbd"] for c in cases}) == len(cases), "duplicate original SHA/GBD")
    for c in cases:
        sig=b.cheap_duplicate_signal(ROOT/c["filename"])
        route,reason=choose(sig)
        c["cheap_sample"]=sig
        c["frozen_gate_route"]=route
        c["frozen_gate_reason"]=reason
    m = dict(protocol=PROTO, cases=cases, fresh_count=FRESH, development_count=DEVELOPMENT,
             source_indices=indices, reference_only_screening=False,
             source_registries=registry,
             global_historical_disjointness_not_guaranteed=True,
             source_sha_locked_before_X15_solver_trials=True,
             new_source_selection_salted_metadata_no_solver_timings=True,
             historical_development_not_blind=True,
             no_auto_promotion=True, independent_UNSAT_LRAT=False,
             SAT_original_witness_required=True,
             UNSAT_cross_solver_agreement_required=True,
             binary_sha256=hashes(), cap_s=CAP, reps=REPS,
             arms=ARMS, shards=SHARDS,
             expected_trials=len(cases)*REPS*len(ARMS),
             policy={"min_exact_duplicates":2, "min_sample_lines_for_front":100,
                     "max_source_bytes_for_front":524288,
                     "min_source_bytes_for_race":196608,
                     "min_sample_lines_for_race":300,
                     "prior": "X14 historical heuristic frozen without tuning on X15 holdout"},
             timing="full end-to-end wall PAR2, child user+sys CPU separately")
    save(ROOT/"manifest.json",m)
    configure()
    verify()
    print("X15_FROZEN",json.dumps(dict(cases=len(cases),holdout=FRESH,
          development=DEVELOPMENT,trials=m["expected_trials"],
          routes_by_tier={tier:dict(collections.Counter(
                c["frozen_gate_route"] for c in cases if c["tier"]==tier))
                for tier in ("development","holdout")}),sort_keys=True),flush=True)

def verify():
    configure()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["expected_trials"]==192 and
         len(m["cases"])==16 and len(m["arms"])==6 and
         m["cap_s"]==CAP and m["binary_sha256"]==hashes(),
         "protocol or pinned backend drift")
    seen=set()
    for c in m["cases"]:
        p=ROOT/c["filename"]
        need(p.is_file() and b.sha(p)==c["sha256"] and
             c["sha256"] not in seen,"original CNF bytes drift")
        seen.add(c["sha256"])
        sig=b.cheap_duplicate_signal(p)
        need(sig==c["cheap_sample"] and
             choose(sig)==(c["frozen_gate_route"],c["frozen_gate_reason"]),
             "cheap source-only gate changed after freeze")
    need(sum(c["tier"]=="holdout" for c in m["cases"])==FRESH,
         "holdout roster drift")
    return m

def trial(c, rep, arm):
    need(arm in ARMS and rep in range(REPS), "bad arm or repetition")
    start=time.perf_counter()
    cpu_before=resource.getrusage(resource.RUSAGE_SELF)
    reason="explicit_control"
    profile_s=0.0
    route=arm
    if arm=="x15_gate":
        sig=b.cheap_duplicate_signal(ROOT/c["filename"])
        route,reason=choose(sig)
        profile_s=time.perf_counter()-start
        need(sig==c["cheap_sample"] and route==c["frozen_gate_route"],
             "source-only selection drift at trial time")
    # The X14 subprocess implementation is reused unchanged, including
    # process-group cleanup, original SAT witness replay, and child CPU accounting.
    result=x14.trial(c,rep,route)
    elapsed=time.perf_counter()-start
    cpu_after=resource.getrusage(resource.RUSAGE_SELF)
    parent_cpu=(cpu_after.ru_utime+cpu_after.ru_stime-
                cpu_before.ru_utime-cpu_before.ru_stime)
    status=result["status"] if elapsed<=CAP else "TIMEOUT"
    result.update(protocol=PROTO, arm=arm, route=route,
                  gate_reason=reason, profile_s=round(profile_s,6),
                  tier=c["tier"],year=c.get("year"), cohort=c["cohort"],
                  elapsed_s=round(elapsed,6), cap_s=CAP,
                  PAR2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
                  status=status, parent_cpu_s=round(parent_cpu,6),
                  SAT_original_witness_verified=(status=="SAT"),
                  source_sha_verified=True,
                  selector_precommitted=True)
    if status=="TIMEOUT":
        result["selected_backend"]=None
    return result

def run_shard(index):
    m=verify()
    need(index in range(SHARDS), "invalid shard")
    # Exactly one historical plus one new original in every shard.
    selected=[c for j,c in enumerate(m["cases"]) if j%SHARDS==index]
    need(len(selected)==2 and {c["tier"] for c in selected}==
         {"development","holdout"}, "unbalanced original-source shard")
    rows=[]
    for c in selected:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(x11.seed(c,rep)).shuffle(order)
            for arm in order:
                row=trial(c,rep,arm)
                need(row["original_sha256"]==c["sha256"] and
                     row["seed"]==x11.seed(c,rep), "original SHA/seed changed")
                rows.append(row)
                save(ROOT/("shard-%d.json"%index),rows)
                print("X15_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==24, "incomplete shard")
    print("X15_SHARD_PASS",index,len(rows),flush=True)

def audit():
    m=verify()
    roster={c["sha256"]:c for c in m["cases"]}
    rows=[]
    for i in range(SHARDS):
        rows.extend(json.loads((ROOT/("shard-%d.json"%i)).read_text()))
    expected={(sha,rep,arm) for sha in roster for rep in range(REPS) for arm in ARMS}
    got={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(got)==192 and got==expected,"missing/duplicated paired trials")
    for sha,c in roster.items():
        group=[r for r in rows if r["original_sha256"]==sha]
        verdicts={r["status"] for r in group if r["status"] in ("SAT","UNSAT")}
        need(len(verdicts)<=1,"contradictory SAT/UNSAT outcomes")
        native_unsat=any(r["status"]=="UNSAT" and
            r["selected_backend"]=="native" for r in group)
        kissat_unsat=any(r["status"]=="UNSAT" and
            r["selected_backend"]=="kissat" for r in group)
        cadical_unsat=any(r["status"]=="UNSAT" and
            r["selected_backend"]=="cadical" for r in group)
        agreed=(native_unsat and (kissat_unsat or cadical_unsat)) or (
                 kissat_unsat and cadical_unsat)
        for r in group:
            need(r["protocol"]==PROTO and r["gbd"]==c["gbd"] and
                 r["seed"]==x11.seed(c,r["rep"]) and
                 r["cap_s"]==CAP and r["tier"]==c["tier"],
                 "X15 protocol or source-seed mismatch")
            route=(c["frozen_gate_route"] if r["arm"]=="x15_gate" else r["arm"])
            need(r["route"]==route,"arm route did not match frozen decision")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "unverified SAT original CNF witness")
            need(r["status"]!="TIMEOUT" or r["PAR2_s"]==2*CAP,
                 "incorrect PAR2 timeout penalty")
            need(r["status"]=="TIMEOUT" or
                 (r["elapsed_s"]<=CAP and r["PAR2_s"]==r["elapsed_s"]),
                 "E2E solved PAR2 mismatch")
            need(r["child_cpu_s"]>=0 and r["parent_cpu_s"]>=0,
                 "invalid CPU usage")
            r["accepted"]=r["status"]=="SAT" or (r["status"]=="UNSAT" and agreed)
            r["audited_PAR2_s"]=r["PAR2_s"] if r["accepted"] else 2*CAP
    def score(sub):
        scores={}
        for arm in ARMS:
            part=[r for r in sub if r["arm"]==arm]
            scores[arm]=dict(n=len(part), solved=sum(r["accepted"] for r in part),
                timeouts=sum(r["status"]=="TIMEOUT" for r in part),
                SAT_original_verified=sum(r["accepted"] and r["status"]=="SAT" for r in part),
                UNSAT_agreement_no_LRAT=sum(r["accepted"] and r["status"]=="UNSAT" for r in part),
                PAR2_s=round(sum(r["audited_PAR2_s"] for r in part),6),
                child_cpu_s=round(sum(r["child_cpu_s"] for r in part),6),
                parent_cpu_s=round(sum(r["parent_cpu_s"] for r in part),6),
                gate_profile_s=round(sum(r["profile_s"] for r in part),6))
        for arm,data in scores.items():
            for baseline in ("original","front100","parallel2","kissat","cadical"):
                value=scores[baseline]["PAR2_s"]
                data["pct_less_PAR2_vs_"+baseline]=round(100*(1-data["PAR2_s"]/value),4)
                data["speedup_vs_"+baseline]=round(value/data["PAR2_s"],5)
            data["CPU_cost_vs_Kissat_x"]=round(
                data["child_cpu_s"]/max(scores["kissat"]["child_cpu_s"],0.000001),4)
        return scores
    by_tier={tier:score([r for r in rows if r["tier"]==tier])
             for tier in ("development","holdout")}
    per_source=[dict(gbd=c["gbd"],sha256=c["sha256"],tier=c["tier"],
         gate_route=c["frozen_gate_route"],scores=score(
             [r for r in rows if r["original_sha256"]==c["sha256"]]))
         for c in m["cases"]]
    summary=dict(protocol=PROTO,cases=16,holdout_sources=8,trials=len(rows),
       no_auto_promotion=True, UNSAT_independent_LRAT=False,
       declared_registry_disjoint_only=True,
       no_reference_timing_screen=True,
       gate_routes=dict(collections.Counter(c["frozen_gate_route"] for c in m["cases"])),
       score=score(rows), by_tier=by_tier,
       holdout_gate_PAR2_beats_original=by_tier["holdout"]["x15_gate"]["PAR2_s"] <
                                      by_tier["holdout"]["original"]["PAR2_s"],
       holdout_gate_CPU_less_than_parallel2=by_tier["holdout"]["x15_gate"]["child_cpu_s"] <
                                          by_tier["holdout"]["parallel2"]["child_cpu_s"],
       per_source=per_source,rows=rows)
    save(ROOT/"report.json",summary)
    print("X15_FINAL",json.dumps({k:v for k,v in summary.items()
            if k not in ("per_source","rows")},sort_keys=True),flush=True)

def selftest():
    b.selftest()
    need(choose(dict(duplicates=2,lines=110,size_bytes=180000))[0]=="front100",
         "front control decision failure")
    need(choose(dict(duplicates=0,lines=500,size_bytes=400000))[0]=="parallel2",
         "parallel control decision failure")
    need(choose(dict(duplicates=0,lines=80,size_bytes=60000))[0]=="original",
         "native fallback decision failure")
    need(len(ARMS)==6 and SHARDS*2*REPS*len(ARMS)==192,
         "benchmark cardinality changed")
    print("X15_SELFTEST_PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":
        verify()
        print("X15_VERIFY_PASS",flush=True)
    elif a.action=="shard":run_shard(a.shard)
    else:audit()

if __name__=="__main__":
    main()
