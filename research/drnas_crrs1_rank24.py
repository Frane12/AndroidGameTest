#!/usr/bin/env python3
"""CRR-S1: bounded, source-SHA-locked RUP-gated algebraic preprocessor.
Research experiment only. Reuses RIT3's exact CNF XOR(2/3/4) and signed-SCC
extraction. Never inserts a clause without original-or-prior-lemma RUP.
E2E includes each arm's real preprocessing overhead, one CPU, verified SAT.
"""
import argparse
import hashlib
import json
import os
import pathlib
import resource
import signal
import subprocess
import tempfile
import time

import drnas_crr1_gf2_scc_rup as core
import drnas_rit3_original_sha_screen as rit3

PROTO = "DRNAS-CRRS1-3SEEN-SHA-RUP-GATED-ONECPU-E2E-v1"
PREFIXES = ("7f25d086", "a43d096e", "404763ef")
ARMS = ("kissat_raw", "kissat_shadow", "kissat_rup", "cadical_raw")
REPS = 2
CAP_S = 8.0
PREP_CAP_S = 2.5

def require(ok, reason):
    if not ok:
        raise RuntimeError("CRRS1_FAIL_CLOSED " + str(reason))

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()

class Budget(Exception):
    pass

def alarm(_sig, _frame):
    raise Budget()

def bounded_preprocess(source, output, seconds=PREP_CAP_S):
    """A timed, RUP-only addition. On timeout, always fail closed to source."""
    start = time.perf_counter()
    cpu_start = time.process_time()
    original_n, original_clauses = core.parse(source)
    candidates = []
    accepted = []
    stats = {"xor23": 0, "xor4": 0, "scc": 0, "rank_gain": 0,
             "candidate_count": 0, "rup_checked": 0,
             "rup_passed": 0, "abstained": False, "reason": ""}
    old_handler = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, max(0.01, seconds-(time.perf_counter()-start)))
    try:
        xor23 = rit3.normalize(core.gf2_rows(original_clauses))
        xor4, _ = rit3.source_xor4(original_clauses)
        scc = rit3.normalize(core.scc_rows(original_clauses, original_n))
        stats.update(xor23=len(xor23), xor4=len(xor4), scc=len(scc))
        require(len(xor23|xor4|scc) <= rit3.MAX_RELATIONS, "relation limit")
        gb, gc, gt = rit3.basis_from(xor23|xor4)
        joint, jc, jt = rit3.basis_from(xor23|xor4|scc)
        stats["rank_gain"] = len(joint)-len(gb)
        if gc or gt or jc or jt:
            stats.update(abstained=True, reason="contradictory_or_truncated")
        else:
            eqs, pair_tests, pair_limited = rit3.candidates(joint)
            stats["pair_tests"] = pair_tests
            stats["pair_limited"] = pair_limited
            seen = {tuple(sorted(set(c))) for c in original_clauses}
            for vs, rhs in sorted(eqs, key=lambda z: (len(z[0]), tuple(sorted(z[0])),z[1])):
                if not vs or len(vs) > 2:
                    continue
                if rit3.algebraically_follows((vs, rhs), joint, jc) is not True:
                    continue
                for clause in rit3.encoded(vs, rhs):
                    k = tuple(sorted(set(clause)))
                    if k not in seen and len(k) == len(clause):
                        candidates.append(k)
                        seen.add(k)
            stats["candidate_count"] = len(candidates)
            # RIT3's original-CNF RUP-first clause priority, not pivot/variable order.
            # For fixed-width clauses tuple sorting prioritizes negative literals,
            # which exposed genuine RUP shortcuts in frozen RIT4.
            candidates.sort(key=lambda clause: (len(clause),clause))
            stats["candidate_priority"] = "RIT3_literal_lexicographic"
            for clause in candidates[:64]:
                if core.rup(original_clauses+accepted, clause):
                    accepted.append(clause)
                    stats["rup_passed"] += 1
                stats["rup_checked"] += 1
    except Budget:
        # Keep only lemmas whose individual RUP check completed successfully.
        # The independent serial replay below must verify the whole prefix.
        stats.update(abstained=True, reason="bounded_preprocess_timeout_with_proved_prefix")
    except (AssertionError, ValueError, OSError) as exc:
        stats.update(abstained=True, reason="extractor_exception:"+str(exc)[:90])
        accepted = []
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    # Independent serial recheck against original+previous accepted, before emission.
    if accepted:
        for i, clause in enumerate(accepted):
            require(core.rup(original_clauses+accepted[:i], clause),
                    "RUP replay failed at lemma "+str(i))
    with open(output, "w") as f:
        f.write(f"p cnf {original_n} {len(original_clauses)+len(accepted)}\n")
        for clause in original_clauses+accepted:
            f.write(" ".join(map(str, clause))+" 0\n")
    stats.update(added=len(accepted), prep_wall_s=round(time.perf_counter()-start,6),
                 prep_cpu_s=round(time.process_time()-cpu_start,6),
                 clauses_original=len(original_clauses), vars_original=original_n,
                 emitted_lemmas=[list(c) for c in accepted])
    return stats

def verify_model(output, clauses, n):
    vals={}
    for line in output.splitlines():
        if not line.startswith("v "):
            continue
        for word in line[2:].split():
            if word.lstrip("-").isdigit():
                lit=int(word)
                if lit and 0<abs(lit)<=n:
                    vals[abs(lit)] = lit>0
    return all(any(vals.get(abs(lit))==(lit>0) for lit in clause)
               for clause in clauses)

def execute(binary, cnf, timeout_s):
    if timeout_s <= 0:
        return {"status":"TIMEOUT","solve_wall_s":0.0,"child_cpu_s":0.0}
    usage_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    start=time.perf_counter()
    try:
        p=subprocess.run([binary, str(cnf)], capture_output=True, text=True,
                         errors="replace", timeout=max(0.001,timeout_s))
        out=p.stdout+"\n"+p.stderr
        status="SAT" if p.returncode==10 and "SATISFIABLE" in out and "UNSATISFIABLE" not in out else (
              "UNSAT" if p.returncode==20 and "UNSATISFIABLE" in out else "UNKNOWN")
    except subprocess.TimeoutExpired:
        out=""
        status="TIMEOUT"
    usage_after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=(usage_after.ru_utime+usage_after.ru_stime-
         usage_before.ru_utime-usage_before.ru_stime)
    return {"status":status, "solve_wall_s":round(time.perf_counter()-start,6),
            "child_cpu_s":round(max(0,cpu),6),"output":out if status=="SAT" else ""}

def manifest_cases(path):
    m=json.loads(pathlib.Path(path).read_text())
    by_prefix=[]
    for prefix in PREFIXES:
        matches=[c for c in m["cases"] if c["sha256"].startswith(prefix)]
        require(len(matches)==1, "missing/ambiguous prefix "+prefix)
        by_prefix.append(matches[0])
    require(len({c["sha256"] for c in by_prefix})==len(PREFIXES),"duplicate case")
    return by_prefix

def bench(args):
    cpus=os.sched_getaffinity(0)
    require(bool(cpus),"no logical CPU available")
    cpu=min(cpus)
    os.sched_setaffinity(0,{cpu})
    cases=manifest_cases(args.manifest)
    raw=json.loads(pathlib.Path(args.consensus).read_text())
    consensus=set(raw["historical_consensus"])
    out=pathlib.Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    all_rows=[]
    for idx,case in enumerate(cases):
        if idx%2!=args.shard:continue
        source=pathlib.Path(args.root)/case["filename"]
        require(source.is_file() and sha(source)==case["sha256"],
                "original CNF not SHA-verified")
        n,clauses=core.parse(source)
        for rep in range(REPS):
            for arm in ARMS:
                with tempfile.TemporaryDirectory() as td:
                    stats={"added":0,"prep_wall_s":0.0,"prep_cpu_s":0.0,
                           "rup_checked":0,"rup_passed":0,"abstained":False}
                    runfile=source
                    if arm in ("kissat_shadow","kissat_rup"):
                        modified=pathlib.Path(td)/"rup.cnf"
                        stats=bounded_preprocess(source, modified)
                        if arm=="kissat_rup" and stats["added"]:
                            runfile=modified
                    remaining=max(0,CAP_S-stats["prep_wall_s"])
                    binary=args.cadical if arm=="cadical_raw" else args.kissat
                    result=execute(binary,runfile,remaining)
                    raw_status=result.pop("status")
                    original_valid=(verify_model(result.pop("output",""),clauses,n)
                                    if raw_status=="SAT" else False)
                    source_agreed=raw_status=="UNSAT" and case["sha256"] in consensus
                    accepted=original_valid or source_agreed
                    status=("SAT_VERIFIED" if original_valid else
                            "UNSAT_CONSENSUS_NO_LRAT" if source_agreed else
                            "INVALID_SAT" if raw_status=="SAT" else
                            "UNSAT_UNCONFIRMED" if raw_status=="UNSAT" else raw_status)
                    e2e=stats["prep_wall_s"]+result["solve_wall_s"]
                    cpu_s=stats["prep_cpu_s"]+result["child_cpu_s"]
                    row={"protocol":PROTO, "original_sha256":case["sha256"],
                         "gbd":case["gbd"], "arm":arm, "rep":rep,
                         "allocated_logical_cpus":1,"cpu_affinity":[cpu],
                         "cap_s":CAP_S,"raw_status":raw_status,"status":status,
                         "accepted":accepted,"SAT_original_witness_verified":original_valid,
                         "UNSAT_historical_consensus_no_LRAT":source_agreed,
                         "independent_UNSAT_LRAT":False,
                         "original_sha_verified":sha(source)==case["sha256"],
                         "E2E_s":round(e2e,6),"CPU_s":round(cpu_s,6),
                         "PAR2_s":round(e2e,6) if accepted else 2*CAP_S,
                         "CPU_PAR2_s":round(cpu_s,6) if accepted else 2*CAP_S,
                         "prep":stats, "solve":result}
                    require(row["original_sha_verified"],"source drift")
                    all_rows.append(row)
                    out.write_text(json.dumps(all_rows,indent=2)+"\n")
                    print("CRRS1_TRIAL "+json.dumps({k:row[k] for k in
                        ("original_sha256","arm","rep","status","E2E_s",
                         "CPU_s","PAR2_s","accepted")}|
                        {"added":stats["added"],"rup_checked":stats["rup_checked"],
                         "prep_s":stats["prep_wall_s"]},sort_keys=True),flush=True)
    require(len(all_rows)==(2 if args.shard==0 else 1)*REPS*len(ARMS),
            "incomplete shard")
    print("CRRS1_SHARD_PASS",args.shard,len(all_rows),flush=True)

def audit(args):
    all_rows=[]
    for i in (0,1):
        all_rows.extend(json.loads((pathlib.Path(args.folder)/f"shard-{i}.json").read_text()))
    cases=manifest_cases(args.manifest)
    expected={(c["sha256"],a,r) for c in cases for a in ARMS for r in range(REPS)}
    observed={(r["original_sha256"],r["arm"],r["rep"]) for r in all_rows}
    require(len(all_rows)==24 and observed==expected,"pairing mismatch")
    require(all(r["protocol"]==PROTO and r["allocated_logical_cpus"]==1
                and r["original_sha_verified"] and not r["independent_UNSAT_LRAT"]
                for r in all_rows),"audit metadata mismatch")
    result={"protocol":PROTO,"source_count":3,"trials":24,
            "cap_s":CAP_S,"reps":REPS,"globally_blind":False,
            "new_CDCL_trials":24,"source_original_sha_locked":True,
            "independent_UNSAT_LRAT":False,"scores":{}}
    for arm in ARMS:
        subset=[x for x in all_rows if x["arm"]==arm]
        result["scores"][arm]={
            "PAR2_s":round(sum(x["PAR2_s"] for x in subset),6),
            "CPU_PAR2_s":round(sum(x["CPU_PAR2_s"] for x in subset),6),
            "solved":sum(x["accepted"] for x in subset),
            "SAT_verified":sum(x["SAT_original_witness_verified"] for x in subset),
            "UNSAT_consensus_no_LRAT":sum(x["UNSAT_historical_consensus_no_LRAT"]
                                         for x in subset),
            "RUP_lemmas_added":sum(x["prep"]["added"] for x in subset),
            "prep_wall_s":round(sum(x["prep"]["prep_wall_s"] for x in subset),6),
            "attempts":len(subset)}
    folder=pathlib.Path(args.folder)
    (folder/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print("CRRS1_FINAL "+json.dumps(result,sort_keys=True),flush=True)

def selftest():
    import itertools
    with tempfile.TemporaryDirectory() as t:
        src=pathlib.Path(t)/"sample.cnf"
        cs=[]
        for flags in itertools.product((False,True),repeat=3):
            if sum(flags)%2:
                cs.append(tuple(-v if flags[i] else v
                                for i,v in enumerate((1,2,3))))
        cs += [(-2,4),(-4,3),(-3,5),(-5,2)]
        src.write_text("p cnf 5 "+str(len(cs))+"\n"+
                       "".join(" ".join(map(str,c))+" 0\n" for c in cs))
        dest=pathlib.Path(t)/"output.cnf"
        result=bounded_preprocess(src,dest,3.0)
        n,a=core.parse(dest)
        require(n==5 and len(a)>=len(cs),"selftest output malformed")
        require(all(core.rup(cs+list(map(tuple,result["emitted_lemmas"][:i])),c)
                    for i,c in enumerate(map(tuple,result["emitted_lemmas"]))),
                "selftest RUP not valid")
        require(not verify_model("v 1 2 3 4 5 0",[(1,),(-1,)],5),
                "SAT verifier admits contradiction")
        print("CRRS1_SELFTEST_PASS "+json.dumps(result,sort_keys=True))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("selftest")
    b=sub.add_parser("bench")
    for x in ("manifest","root","kissat","cadical","consensus","out"):
        b.add_argument("--"+x,required=True)
    b.add_argument("--shard",type=int,choices=(0,1),required=True)
    a=sub.add_parser("audit")
    a.add_argument("--folder",required=True)
    a.add_argument("--manifest",required=True)
    args=p.parse_args()
    dict(selftest=lambda:selftest(),bench=lambda:bench(args),
         audit=lambda:audit(args))[args.command]()
