#!/usr/bin/env python3
"""DRNAS source-only R3 heap + event-indexed GF2: no foreign SAT libraries.
Compares own R1, R2B GF2 and optimized R3 plain/GF2 on
two preselected original MIXAB3 SHA, unchanged from previous NOVEL2C screening.
"""
import argparse,hashlib,json,os,pathlib,random,re,subprocess,tempfile,time
import drnas_native_core_r2_test as checks
ROOT=pathlib.Path("mre_drnas_native_core_r3")
BINS={"r1":ROOT/"bin/drnas_native_core_r1",
      "r2b_gf2":ROOT/"bin/drnas_native_core_r2b",
      "r3_plain":ROOT/"bin/drnas_native_core_r3",
      "r3_gf2":ROOT/"bin/drnas_native_core_r3"}
SELECTED=[
"daa0360a834fbd9f49437d2b3fd6b372d331774100d913d55c57c0de547eb623",
"e3e6b2c71ca07f5f17491a38490b29fb63045be258ad6837bcc4530b31438162"
]
CAP=6.0
def need(ok,msg):
    if not ok:raise RuntimeError("R3_FAIL_CLOSED "+str(msg))
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def execute(path,arm,cap):
    need(arm in BINS,"unknown own solver")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    start=time.perf_counter()
    mode=("plain" if arm=="r3_plain" else "gf2")
    cmd=([str(BINS[arm].resolve()),str(path.resolve()),"--time",str(cap)] if arm=="r1" else
         [str(BINS[arm].resolve()),str(path.resolve()),"--mode",mode,"--time",str(cap)])
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+1.5)
    wall=time.perf_counter()-start
    need(p.returncode in (0,10,20),"own solver exit "+str(p.returncode)+p.stderr[-500:])
    prefix=("DRNAS_NATIVE_R1_RESULT" if arm=="r1" else
           "DRNAS_NATIVE_R2B_RESULT" if arm=="r2b_gf2" else
           "DRNAS_NATIVE_R3_RESULT")
    m=re.search(r"^c "+prefix+r" (.+)$",p.stdout,re.M)
    need(m is not None,"missing native telemetry "+arm)
    kv=dict(x.split("=",1) for x in m.group(1).split() if "=" in x)
    status=kv["status"]
    need(p.returncode=={"SAT":10,"UNSAT":20,"UNKNOWN":0}[status],
         "exit status mismatch")
    need(kv["third_party_solver_calls"]=="0",
         "unexpected foreign solver call")
    n,clauses=checks.parse_dimacs(path)
    if status=="SAT":
        witness={}
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                for v in map(int,line[2:].split()):
                    if v:witness[abs(v)]=(v>0)
        need(len(witness)==n and checks.satisfied(clauses,witness),
             "original SAT witness invalid")
    return dict(status=status,solver_s=round(float(kv["solver_s"]),6),
       E2E_s=round(wall,6),verified_SAT=status=="SAT",
       UNSAT_independent_LRAT=False,
       native_conflicts=int(kv["conflicts"]),
       native_decisions=int(kv["decisions"]),
       certified_xor_candidates=int(kv.get("xor_certified_candidates",0)),
       active_xor_rows=int(kv.get("xor_source_rows",0)),
       derived_rows=int(kv.get("xor_derived_rows",0)),
       derived_implications=int(kv.get("xor_derived_implications",0)),
       xor_reasons=int(kv.get("xor_reasons",0)),
       xor_conflicts=int(kv.get("xor_conflicts",0)),
       xor_budget_off=int(kv.get("xor_budget_off",0)),
       xor_checks=int(kv.get("xor_checks",0)),
       xor_events_processed=int(kv.get("xor_events_processed",0)),
       heap_pops=int(kv.get("heap_pops",0)),
       heap_pushes=int(kv.get("heap_pushes",0)),
       cpu_id=min(os.sched_getaffinity(0)))
def verify():
    ROOT.mkdir(exist_ok=True)
    p=subprocess.run([str(BINS["r3_gf2"].resolve()),"--selftest"],
                     capture_output=True,text=True,timeout=70)
    need(p.returncode==0 and "DRNAS_NATIVE_R3_GF2_SELFTEST_PASS" in p.stdout
         and "DRNAS_NATIVE_R3_SELFTEST_PASS" in p.stdout,
         "R3 exhaustive tests fail: "+p.stderr[-750:])
    print(p.stdout.strip(),flush=True)
    rng=random.Random(0xD2B2026)
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        path=pathlib.Path(td)/"test.cnf"
        exercised=0
        for i in range(240):
            n=rng.randint(1,9)
            clauses=[]
            for _ in range(rng.randrange(0,5*n+5)):
                clauses.append([rng.choice((-1,1))*rng.randint(1,n)
                  for __ in range(rng.randrange(0,min(n+4,7)))])
            path.write_text(checks.content(n,clauses))
            expected=checks.independent_truth(n,clauses)
            for arm in ("r3_plain","r3_gf2"):
                result=execute(path,arm,1.4)
                need(result["status"]==expected,
                     "original truth mismatch random "+str(i)+" "+arm)
        for i in range(120):
            a,b,c,d=rng.sample([1,2,3,4],4)
            rhs1,rhs2=rng.randrange(2),rng.randrange(2)
            assigned=rng.randrange(2)
            clauses=checks.xor_cnf((a,b,c),rhs1)+checks.xor_cnf((a,b,d),rhs2)
            clauses.append([c if assigned else -c])
            if i&1:
                implies=rhs1^rhs2^assigned
                clauses.append([-d if implies else d])
            path.write_text(checks.content(4,clauses))
            expected=checks.independent_truth(4,clauses)
            result=execute(path,"r3_gf2",1.4)
            need(result["status"]==expected,"positive XOR proof mismatch")
            need(result["derived_rows"]>=1 and
                 result["derived_implications"]+result["xor_conflicts"]>=1,
                 "R3 GF2 genuine inference missing")
            exercised+=1
    print("DRNAS_NATIVE_R3_CHECKS_PASS "+
          json.dumps(dict(random_CNF=240,positive_xor_CNF=120,
                          independent_small_CNF_checks=600,
                          gf2_native_activations=exercised,
                          third_party_solver_calls=0)),flush=True)
def originals():
    ROOT.mkdir(exist_ok=True)
    m=json.loads(pathlib.Path("mre_mixab3/manifest.json").read_text())
    roster={c["sha256"]:c for c in m["original_cases"]}
    need(len(roster)==12,"source-frozen MIXAB3 cohort changed")
    records=[]
    for sha in SELECTED:
        need(sha in roster,"source-only selected SHA not in roster")
        path=pathlib.Path("mre_mixab3/cases")/roster[sha]["filename"]
        need(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==sha,
             "original CNF SHA drift")
        for rep in range(2):
            arms=list(BINS)
            random.Random(sha+str(rep)+"NATIVE_R3").shuffle(arms)
            for arm in arms:
                result=execute(path,arm,CAP)
                result.update(sha256=sha,arm=arm,rep=rep,cap_s=CAP,
                              cohort="MIXAB3_previous_source_only")
                records.append(result)
                save(ROOT/"original-trials.json",records)
                print("DRNAS_NATIVE_R3_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    need(len(records)==16,"paired trial count not 16")
    result={}
    for arm in BINS:
        v=[x for x in records if x["arm"]==arm]
        result[arm]=dict(attempts=len(v),SAT_verified=sum(x["verified_SAT"] for x in v),
            raw_UNSAT_without_LRAT=sum(x["status"]=="UNSAT" for x in v),
            timeout=sum(x["status"]=="UNKNOWN" for x in v),
            strict_PAR2_s=round(sum(x["E2E_s"] if x["verified_SAT"] else 2*CAP for x in v),6),
            GF2_derived_rows_max=max(x["derived_rows"] for x in v),
            GF2_derived_implications=sum(x["derived_implications"] for x in v),
            GF2_reasons=sum(x["xor_reasons"] for x in v),
            GF2_row_checks=sum(x["xor_checks"] for x in v),
            GF2_indexed_events=sum(x["xor_events_processed"] for x in v),
            branch_heap_pops=sum(x["heap_pops"] for x in v),
            total_E2E_s=round(sum(x["E2E_s"] for x in v),6))
    audit=dict(protocol="DRNAS-NATIVE-R3-HEAP-EVENT-XOR-2SHA-4ARMS-2REPS-6S",
      samples=2,repetitions=2,attempts=16,one_cpu_per_trial=True,
      previously_seen_not_blind=True,proof_checked_UNSAT=False,arms=result)
    save(ROOT/"audit.json",audit)
    print("DRNAS_NATIVE_R3_FINAL "+json.dumps(audit,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("task",choices=("verify","original"))
    args=p.parse_args()
    if args.task=="verify":verify()
    else:originals()
