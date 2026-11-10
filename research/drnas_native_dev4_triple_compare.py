#!/usr/bin/env python3
"""DRNAS standalone R1 vs Kissat 4.0.4 vs CryptoMiniSat 5.17:
TRUE MATCHED SAME-GitHub-RUNNER, SAME LOGICAL CPU, original SHA DEV4.
One process at a time, 3 repeats per SHA per solver, 10s hard nominal
E2E cap; no third-party binary/library linked or called by DRNAS R1.
Reference binaries are only separate standalone benchmark competitors.

This is a selected/nonblind *development* cohort; all source CNFs known SAT.
Never compare earlier runs as if hardware conditions were identical.
"""
import collections, hashlib, json, os, pathlib, random, re
import resource, subprocess, time

import drnas_native_core_r2_test as original

ROOT = pathlib.Path("mre_drnas_native_dev4_triple")
FREEZE = pathlib.Path("experiments/drnas_native_solveset1/FROZEN_DEV4.json")
R1 = ROOT / "bin/drnas_native_core_r1"
KISSAT = pathlib.Path("built/bin/kissat_4_0_4")
CMS = pathlib.Path("mre_equiv12/bin/cryptominisat5")
MIX4 = pathlib.Path("mre_mixab4")
EQ5 = pathlib.Path("mre_equiv10m5")
REPS = 3
CAP = 10.0
ARMS = ("drnas_r1", "kissat_plain", "cms_plain")
PROTOCOL = "DRNAS-NATIVE-DEV4-TRIPLE-SAME-RUNNER-3ARMS-4SHA-3REPS-10S-ONECPU-v1"

def need(ok, msg):
    if not ok: raise RuntimeError("TRIPLE_COMPARE_FAIL_CLOSED " + msg)

def read(p):
    return json.loads(pathlib.Path(p).read_text())

def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def write(p, obj):
    path = pathlib.Path(p)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")

def selected_sources():
    frozen = read(FREEZE)
    need(frozen["protocol"] == "DRNAS-NATIVE-SOLVESET1-FROZEN-DEV4-20261110"
         and frozen["nonblind"] and frozen["original_SHA_count"] == 4,
         "wrong source-locked original DEV4")
    need(len(frozen["selected"]) == 4, "four sources required")
    from_frozen = {v["sha256"]:v for v in frozen["selected"]}
    need(len(from_frozen) == 4, "source SHA duplicate")

    m4 = read(MIX4 / "manifest.json")
    m5 = read(EQ5 / "manifest.json")
    need(len(m4["original_cases"]) == 6 and len(m5["cases"]) == 5,
         "historically frozen source manifest drift")
    cases = {}
    for cohort, records, directory in [
        ("MIXAB4", m4["original_cases"], MIX4 / "cases"),
        ("EQUIV10M5", m5["cases"], pathlib.Path("mre_equiv9/cases"))]:
        for c in records:
            key = c["sha256"]
            if key in from_frozen:
                src = directory / c["filename"]
                need(from_frozen[key]["cohort"] == cohort, "source cohort mismatch")
                need(src.is_file() and sha(src) == key, "source CNF SHA mismatch")
                n, clauses = original.parse_dimacs(src)
                need(n > 0 and len(clauses) > 0, "invalid original CNF")
                cases[key] = dict(cohort=cohort,sha256=key, path=str(src),
                                  vars=n,clauses=len(clauses))
    need(set(cases) == set(from_frozen), "missing frozen SHA")
    return frozen, cases, m4, m5

def binaries(mix4):
    need(all(p.is_file() for p in (R1,KISSAT,CMS)), "missing solver executable")
    require_hashes = mix4["signatures"]
    need(sha(KISSAT) == require_hashes["kissat_bin_sha"],
         "pinned Kissat 4.0.4 binary checksum changed")
    need(sha(CMS) == require_hashes["cms_bin_sha"],
         "pinned CryptoMiniSat 5.17 binary checksum changed")
    need(sha("research/drnas_native_core_r1.cpp")
         == sha(pathlib.Path("research/drnas_native_core_r1.cpp")),
         "own source digest invariant failed")
    return {
      "drnas_r1":sha(R1),
      "kissat_plain":sha(KISSAT),
      "cms_plain":sha(CMS)
    }

def child_cpu():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime

def execute(source, arm, cap, clauses):
    need(arm in ARMS and cap == CAP, "benchmark arm or cap changed")
    allowed = os.sched_getaffinity(0)
    need(allowed, "no logical CPU affinity available")
    cpu = min(allowed)
    os.sched_setaffinity(0,{cpu})
    src = pathlib.Path(source).resolve()
    cmd = {
      "drnas_r1":[str(R1.resolve()), str(src), "--time", str(max(.01,cap-.10))],
      "kissat_plain":[str(KISSAT.resolve()), str(src)],
      "cms_plain":[str(CMS.resolve()), "--verb", "0", "-t", "1", str(src)],
    }[arm]
    env=os.environ.copy()
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
               LD_LIBRARY_PATH=(str(pathlib.Path("mre_equiv12/lib").resolve()) + ":" +
                                str(pathlib.Path("mre5/lib").resolve()) + ":" +
                                env.get("LD_LIBRARY_PATH","")))
    beginning=time.perf_counter()
    cpu_before=child_cpu()
    timed_out=False
    try:
        p=subprocess.run(cmd, capture_output=True, text=True, env=env,
                         timeout=cap-0.075, check=False)
    except subprocess.TimeoutExpired:
        p=None
        timed_out=True
    child_wall=time.perf_counter()-beginning
    cpu_delta=max(0.0,child_cpu()-cpu_before)
    status="TIMEOUT"
    backend="TIMEOUT"
    checked=False
    inner_solver_s=None
    if p is not None:
        need(p.returncode in (0,10,20),
             f"{arm} unexpected exit {p.returncode}: {p.stderr[-850:]}")
        if p.returncode in (10,20):
            backend = "SAT" if p.returncode == 10 else "UNSAT"
            expected = "s SATISFIABLE" if p.returncode == 10 else "s UNSATISFIABLE"
            need(expected in {line.strip() for line in p.stdout.splitlines()},
                 f"{arm} status/exit mismatch")
            if backend == "UNSAT":
                # These original sources have earlier independently checked
                # *SAT witnesses*; an UNSAT reply means a solver bug.
                raise RuntimeError(f"TRIPLE_COMPARE_FAIL_CLOSED {arm} UNSAT on known SAT")
            assignment={}
            for ln in p.stdout.splitlines():
                if not ln.startswith("v "): continue
                for lit in map(int,ln.split()[1:]):
                    if not lit:continue
                    v=abs(lit)
                    need(v not in assignment or assignment[v] == (lit>0),
                         "conflicting model variable in reference output")
                    assignment[v] = lit > 0
            need(assignment and original.satisfied(clauses,assignment),
                 f"{arm} SAT model fails original CNF witness replay")
            checked=True
            status="SAT"
        if arm=="drnas_r1":
            match=re.search(r"^c DRNAS_NATIVE_R1_RESULT (.+)$",p.stdout,re.M)
            need(match is not None,"own native solver metrics missing")
            kv=dict(x.split("=",1) for x in match.group(1).split() if "=" in x)
            need(kv.get("third_party_solver_calls")=="0",
                 "foreign solver call inside DRNAS")
            inner_solver_s=float(kv["solver_s"])
    e2e=time.perf_counter()-beginning
    if e2e>=cap: status="TIMEOUT";checked=False
    need(e2e <= cap + .50, "hard E2E cap unexpectedly exceeded")
    return dict(arm=arm, status=status, backend_status=backend,
        original_SAT_witness_verified=checked,
        UNSAT_independent_original_LRAT=False,
        cap_s=cap, child_process_wall_s=round(child_wall,6),
        inner_native_solver_s=inner_solver_s,
        child_CPU_s=round(cpu_delta,6),
        wall_E2E_with_original_model_check_s=round(e2e,6),
        external_timeout=timed_out,cpu_id=cpu,
        logical_cores_per_solver=1,
        foreign_solver_calls_inside_DRNAS=0 if arm=="drnas_r1" else None)

def main():
    ROOT.mkdir(exist_ok=True,parents=True)
    frozen,cases,m4,m5=selected_sources()
    signature=binaries(m4)
    frozen_benchmark=dict(protocol=PROTOCOL,selected_SHA=[x["sha256"] for x in frozen["selected"]],
         fixed_source_SHA_in_git_before_this_run=True,development_nonblind=True,
         original_source_manifest_sha={"mix4":sha(MIX4/"manifest.json"),
                                      "equiv10m5":sha(EQ5/"manifest.json")},
         binary_sha=signature,benchmark_arms=list(ARMS),
         source_qualifier="prior native original SAT witness verified",
         repetitions=REPS, cap_s=CAP, one_logical_CPU_per_solver=True,
         all_trials_serial_same_runner=True,
         no_third_party_backends_inside_DRNAS=True,
         strict_PAR2_SAT_original_witness_only=True)
    write(ROOT/"frozen-comparison.json",frozen_benchmark)
    print("DRNAS_TRIPLE_FROZEN "+json.dumps(frozen_benchmark,sort_keys=True),flush=True)
    all_trials=[]
    for frozen_case in frozen["selected"]:
        key=frozen_case["sha256"]
        source=pathlib.Path(cases[key]["path"])
        n, original_clauses=original.parse_dimacs(source)
        need(n==cases[key]["vars"],"source vars changed")
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(key+"|DRNAS-TRIPLE|"+str(rep)).shuffle(arms)
            for arm in arms:
                result=execute(source,arm,CAP,original_clauses)
                result.update(original_sha256=key,cohort=cases[key]["cohort"],
                              rep=rep,source_SHA_verified=(sha(source)==key))
                need(result["source_SHA_verified"],"source altered during run")
                all_trials.append(result)
                write(ROOT/"paired-trials.json",all_trials)
                print("DRNAS_TRIPLE_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    expected={(key,rep,arm) for key in cases for rep in range(REPS) for arm in ARMS}
    actual=[(r["original_sha256"],r["rep"],r["arm"]) for r in all_trials]
    need(len(actual)==36 and len(set(actual))==36 and set(actual)==expected,
         "not all 36 original SHA paired attempts complete")
    scores={}
    per_sha={}
    for arm in ARMS:
        rows=[r for r in all_trials if r["arm"]==arm]
        good=[r for r in rows if r["status"]=="SAT" and
              r["original_SAT_witness_verified"]]
        scores[arm]=dict(trials=len(rows),verified_original_SAT=len(good),
            raw_UNSAT_no_proof=sum(r["backend_status"]=="UNSAT" for r in rows),
            timeout=sum(r["status"]=="TIMEOUT" for r in rows),
            process_wall_total_s=round(sum(r["child_process_wall_s"] for r in rows),6),
            child_CPU_total_s=round(sum(r["child_CPU_s"] for r in rows),6),
            strict_E2E_PAR2_s=round(sum(
                r["wall_E2E_with_original_model_check_s"] if r in good else 2*CAP
                for r in rows),6))
    baseline=scores["drnas_r1"]["strict_E2E_PAR2_s"]
    for arm in ARMS:
        scores[arm]["PAR2_speedup_vs_DRNAS_x"]=round(
            baseline/scores[arm]["strict_E2E_PAR2_s"],6)
    for item in frozen["selected"]:
        sha_value=item["sha256"]
        per_sha[sha_value]={}
        for arm in ARMS:
            rows=sorted((r for r in all_trials if
                         r["original_sha256"]==sha_value and r["arm"]==arm),
                        key=lambda r:r["rep"])
            per_sha[sha_value][arm]=dict(
                status=[r["status"] for r in rows],
                E2E_s=[r["wall_E2E_with_original_model_check_s"] for r in rows],
                child_process_wall_s=[r["child_process_wall_s"] for r in rows],
                child_CPU_s=[r["child_CPU_s"] for r in rows],
                avg_E2E_s=round(sum(
                    r["wall_E2E_with_original_model_check_s"] for r in rows)/REPS,6),
                avg_child_process_wall_s=round(sum(
                    r["child_process_wall_s"] for r in rows)/REPS,6))
    audit=dict(protocol=PROTOCOL,trials=len(all_trials),original_sha=sorted(cases),
               matched_same_runner=True,not_blind=True,one_logical_CPU=True,
               cap_s=CAP,summary=scores,per_original_sha=per_sha,
               frozen_protocol=frozen_benchmark)
    write(ROOT/"final-report.json",audit)
    print("DRNAS_TRIPLE_FINAL "+json.dumps(
       {k:v for k,v in audit.items() if k not in ("per_original_sha","frozen_protocol")},
       sort_keys=True),flush=True)
    for key in sorted(per_sha):
        print("DRNAS_TRIPLE_PER_SHA "+json.dumps(
            dict(sha=key,arms=per_sha[key]),sort_keys=True),flush=True)
    print("DRNAS_TRIPLE_AUDIT_PASS 36",flush=True)

if __name__=="__main__":
    main()
