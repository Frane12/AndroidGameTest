#!/usr/bin/env python3
"""DRNAS SEARCH2: DIRECT CaDiCaL CDCL initial VMTF+EVSIDS seeding, original CNF.
Experimentally patched pinned CaDiCaL 3.0.1 vs patched-no-op, unpatched
original, inverse, SOURCE-AND-REP salted random placebo and Kissat.
12 PREVIOUSLY SEEN official EQUIV13 SHA, 2 reps; NOT BLIND.
Unchanged SHA and independent original-SAT witness; original reference
Kissat+unpatched CaDiCaL UNSAT agreement only (NO independent LRAT).
Mechanism measured: true internal CDCL conflicts/decisions/propagations,
not just bounded preprocessor/renamed-CNF timings.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,tempfile,time
import drnas_equiv13_structural_router as e13
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_x22_parallel_reducer as x22
import drnas_search1_guided_e2e as search1

ROOT=pathlib.Path("mre_search2")
DRIVER=ROOT/"bin/search2_cadical"
PRIORITY=ROOT/"bin/search1_relabel"
PROTO="DRNAS-SEARCH2-NATIVE-CDCL-INITIAL-VMTF-EVSIDS-12SHA-7ARM-2REP-15S-v1"
ARMS=("cadical_orig","cadical_noop","cadical_guided","cadical_reverse",
      "cadical_placebo","cadical_unpatched","kissat1")
CAP=15.0
PILOT_CAP=6.0
SHARDS=6
REPS=2
COUNT=12
PILOT=4
EXPECTED=COUNT*REPS*len(ARMS)
TAG="SEARCH2-CADICAL-3.0.1-CONTROLLED-SOURCE-PROBE-v1"

def need(cond,why):
    if not cond:raise RuntimeError("SEARCH2_FAIL_CLOSED "+str(why))
def digest(p):return e9.digest(p)
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def cases():
    cs=e13.verify()["cases"]
    need(len(cs)==COUNT and len({c["sha256"] for c in cs})==COUNT,
         "EQUIV13 frozen source count")
    return cs
def hashes():
    return dict(cadical_search2=digest(DRIVER),
       priority_generator=digest(PRIORITY),
       cadical_original=digest(e9.CAD),kissat_original=digest(e9.KISSAT))
def seed(sha,rep):
    return int(hashlib.sha256((TAG+"|"+sha+"|"+str(rep)).encode()).hexdigest()[:15],16)
def cohort_pilot(cs):
    # Source-ONLY stratified four SHA, before looking at ANY SEARCH2 outcome.
    by_xor=sorted(cs,key=lambda c:(-c["signals"]["xor3_complete_patterns"],
                                    c["sha256"]))[:2]
    rest=[c for c in cs if c not in by_xor]
    by_binary=sorted(rest,key=lambda c:(-c["signals"]["binary_ratio"],
                                         c["sha256"]))[:2]
    chosen={c["sha256"] for c in by_xor+by_binary}
    need(len(chosen)==PILOT,"pilot disjoint SHA")
    return sorted(chosen)
def freeze():
    ROOT.mkdir(exist_ok=True,parents=True)
    cs=cases()
    for p in (DRIVER,PRIORITY,e9.CAD,e9.KISSAT):
        need(p.is_file(),"missing solver or prep binary "+str(p))
    m=dict(protocol=PROTO,sources=cs,source_count=COUNT,
      code_SHA=digest(__file__),
      patch_SHA=digest("research/drnas_search2_patch_cadical.py"),
      driver_source_SHA=digest("research/drnas_search2_cadical_driver.cpp"),
      source_manifest_SHA=digest(e13.ROOT/"manifest.json"),
      priority_cpp_SHA=digest("research/drnas_search1_guided_relabel.cpp"),
      binaries=hashes(),arms=list(ARMS),trial_count=EXPECTED,
      reps=REPS,cap_s=CAP,shards=SHARDS,pilot_cap_s=PILOT_CAP,
      pilot_SHA=cohort_pilot(cs),
      upstream_cadical_commit="c60730422e758ef1cebe7aeddf2dda31c996bf04",
      direct_native_VMTF_initial_priority=True,
      direct_native_EVSIDS_initial_activity=True,
      original_source_DIMACS_given_to_all_solver_variants=True,
      source_feature_generator_charged_to_E2E=True,
      no_op_control_generates_same_priority_map_but_does_not_apply=True,
      previous_search1_was_not_direct_CDCL=True,
      no_parallel_solver_children=True,one_logical_cpu=True,
      original_SHA_unchanged=True, SAT_original_verified=True,
      UNSAT_two_reference_agreement_only=True,UNSAT_independent_LRAT=False,
      source_history="Previously seen EQUIV13 source-only selected SHA; not globally blind",
      no_auto_promotion=True)
    save(ROOT/"manifest.json",m)
    verify()
    print("SEARCH2_FROZEN "+json.dumps(dict(source_count=COUNT,arms=len(ARMS),
         trials=EXPECTED,pilot_trials=PILOT*len(ARMS),
         pilot_source_SHA=m["pilot_SHA"],
         direct_native_CDCL=True,not_blind=True,independent_UNSAT_LRAT=False),
         sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    cs=cases()
    need(m["protocol"]==PROTO and m["sources"]==cs and
         m["source_count"]==COUNT and m["trial_count"]==EXPECTED
         and m["arms"]==list(ARMS) and m["shards"]==SHARDS
         and m["cap_s"]==CAP and m["reps"]==REPS
         and m["pilot_SHA"]==cohort_pilot(cs),"frozen protocol drift")
    need(m["code_SHA"]==digest(__file__)
         and m["patch_SHA"]==digest("research/drnas_search2_patch_cadical.py")
         and m["driver_source_SHA"]==digest("research/drnas_search2_cadical_driver.cpp")
         and m["priority_cpp_SHA"]==digest("research/drnas_search1_guided_relabel.cpp")
         and m["source_manifest_SHA"]==digest(e13.ROOT/"manifest.json")
         and m["binaries"]==hashes(),"code/build/registry SHA drift")
    for c in cs:
        src=e9.SOURCE/c["filename"]
        need(digest(src)==c["sha256"],"original SHA drift")
    return m

def read_sat(output,original):
    assignment={}
    for line in output.splitlines():
        if not line.startswith("v "):continue
        for lit in map(int,line.split()[1:]):
            if lit==0:continue
            need(abs(lit) not in assignment or assignment[abs(lit)]==(lit>0),
                 "inconsistent original model")
            assignment[abs(lit)]=(lit>0)
    need(bool(assignment) and x22.holds(original,assignment),
         "model did not satisfy original CNF")
    return len(assignment)

def score_file(src,mode,repseed,tmp,original):
    target=pathlib.Path(tmp)/"unused_renamed.cnf"
    mapping=pathlib.Path(tmp)/"decision_order.map"
    p=subprocess.run([str(PRIORITY.resolve()),mode,str(src.resolve()),
        str(target),str(mapping),str(repseed)],
        text=True,capture_output=True,timeout=4)
    need(p.returncode==0,"priority generator failure "+p.stderr[-250:])
    n=len({abs(l) for c in original for l in c})
    orig_n,original2=x22.read_cnf(src)
    m=search1.permutation(mapping,orig_n)
    rewritten_n,rewritten=x22.read_cnf(target)
    need(orig_n==rewritten_n,"priority generator changed var space")
    search1.verify_relabel(original,rewritten,m)
    return mapping,p.stderr

def one(c,rep,arm,cap):
    need(arm in ARMS and rep in range(REPS) and cap in (CAP,PILOT_CAP),
         "trial key/clock")
    src=e9.SOURCE/c["filename"]
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    start=time.perf_counter();before=x22.child_cpu();parent_start=time.process_time()
    need(digest(src)==c["sha256"],"source mutated at entry")
    original_n,original=x22.read_cnf(src)
    need(original_n>0 and bool(original),"invalid original geometry")
    mode=arm.split("_",1)[1] if arm.startswith("cadical_") else "baseline"
    ispatched=arm not in ("kissat1","cadical_unpatched")
    mapping_telemetry={}
    metrics=None
    status="TIMEOUT";witness=False
    parse_time=0.0;selected_seed=seed(c["sha256"],rep)
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        priority="NONE"
        if mode in ("guided","reverse","placebo","noop"):
            path,out=score_file(src,"guided" if mode=="noop" else mode,
                                selected_seed,temp,original)
            mapping_telemetry=[line for line in out.splitlines()
                               if line.startswith("SEARCH1_RENAME ")]
            need(len(mapping_telemetry)==1,"priority feature telemetry absent")
            mapping_telemetry=json.loads(mapping_telemetry[0][len("SEARCH1_RENAME "):])
            if mode!="noop":priority=str(path.resolve())
        parse_time=time.perf_counter()-start
        remaining=cap-parse_time
        need(remaining>.15,"preprocessing exhausted E2E budget")
        if ispatched:
            # Original CNF always supplied to the patched CDCL, never the
            # intermediate byproduct generated for source feature ranking.
            command=[str(DRIVER.resolve()),str(src.resolve()),priority,
                     str(max(.15,remaining-.08))]
        elif arm=="kissat1":
            command=e9.command("kissat1",src,e9.seedpair(c["sha256"],rep)[0])
        else:
            command=e9.command("cadical301_default",src,e9.seedpair(c["sha256"],rep)[0])
        child=x22.launch("search2",command,cpu,temp)
        try:
            while child["p"].poll() is None and time.perf_counter()-start<cap-.025:
                time.sleep(.003)
            if child["p"].poll() is not None:
                output,stderr=x22.read_output(child)
                rc=child["p"].returncode
                need(rc in (0,10,20),"solver crashed "+arm+":"+str(rc)+":"+stderr[-500:])
                if ispatched:
                    diag=[line[len("SEARCH2_METRICS "):]
                          for line in output.splitlines()
                          if line.startswith("SEARCH2_METRICS ")]
                    need(len(diag)==1,"native CDCL telemetry absent")
                    metrics=json.loads(diag[0])
                    need(metrics["source_is_original_DIMACS"],"solver not original source")
                    need(metrics["initial_internal_priority_seed_count"]==
                         (0 if priority=="NONE" else original_n),
                         "priority map not directly passed to CDCL")
                if rc in (10,20):
                    need(("s SATISFIABLE" if rc==10 else "s UNSATISFIABLE") in
                         [line.strip() for line in output.splitlines()],
                         "solver exit and verdict mismatch")
                    if rc==10:
                        read_sat(output,original);witness=True;status="SAT"
                    else:status="UNSAT"
                else:status="TIMEOUT"
        finally:
            x22.cleanup([child])
    wall=time.perf_counter()-start
    if wall>=cap:status="TIMEOUT";witness=False
    need(digest(src)==c["sha256"],"original source changed during CDCL")
    need(status!="SAT" or witness,"SAT original witness missing")
    return dict(protocol=PROTO,arm=arm,rep=rep,gbd=c["gbd"],
       sha256=c["sha256"],status=status,cap_s=cap,
       original_SHA_verified=True,one_logical_cpu=cpu,
       no_parallel_solver_children=True,
       true_native_CDCL_seed=ispatched and mode in ("guided","reverse","placebo"),
       SAT_original_model_verified=bool(witness),
       UNSAT_independent_LRAT=False,
       source_XOR3=c["signals"]["xor3_complete_patterns"],
       source_binary_ratio=c["signals"]["binary_ratio"],
       prep_E2E_s=round(parse_time,6),
       wall_E2E_s=round(wall,6),
       child_CPU_s=round(x22.child_cpu()-before,6),
       parent_CPU_s=round(time.process_time()-parent_start,6),
       actual_CDCL_telemetry=metrics,
       priority_features=mapping_telemetry)

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(DRIVER.is_file() and PRIORITY.is_file(),"experimental compiled binaries missing")
    import random
    rng=random.Random(129717)
    toy=0;verified=0
    with tempfile.TemporaryDirectory() as tmp:
        src=pathlib.Path(tmp)/"toy.cnf"
        for n in range(2,7):
            for k in range(3):
                clauses=[tuple(rng.choice((-1,1))*rng.randint(1,n)
                        for _ in range(rng.randint(1,4)))
                        for _ in range(rng.randint(2,14))]
                src.write_text("p cnf %d %d\n"%(n,len(clauses))+
                     "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
                true_sat=any(x22.holds(clauses,{v:bool(i&(1<<(v-1)))
                          for v in range(1,n+1)}) for i in range(1<<n))
                for mode in ("orig","noop","guided","reverse","placebo"):
                    with tempfile.TemporaryDirectory(dir=ROOT) as td:
                        rank="NONE"
                        if mode!="orig":
                            rankpath,_=score_file(src,"guided" if mode=="noop"
                                                   else mode,10+k,td,clauses)
                            if mode!="noop":rank=str(rankpath.resolve())
                        p=subprocess.run([str(DRIVER.resolve()),str(src.resolve()),
                             rank,"2.0"],text=True,capture_output=True,timeout=5)
                        need(p.returncode in (10,20),"toy solver bad exit "+p.stderr[-300:])
                        need((p.returncode==10)==true_sat,"toy exact SAT/UNSAT mismatch")
                        if p.returncode==10:
                            read_sat(p.stdout,clauses);verified+=1
                        diag=[l for l in p.stdout.splitlines()
                              if l.startswith("SEARCH2_METRICS ")]
                        need(len(diag)==1,"toy native telemetry absent")
                        x=json.loads(diag[0][len("SEARCH2_METRICS "):])
                        need(x["conflicts"]>=0 and x["decisions"]>=0
                             and x["search_propagations"]>=0,
                             "toy actual CDCL metrics invalid")
                        toy+=1
    print("SEARCH2_SELFTEST_PASS "+json.dumps(dict(
      toy_trials=toy,original_SAT_models_verified=verified,
      native_CDCL_priorities_seeded=True,
      numerical_conflicts_decisions_propagations=True,
      exhaustive_small_truth_comparison=True),sort_keys=True),flush=True)

def pilot():
    m=verify();pilot_SHA=set(m["pilot_SHA"])
    cs=[c for c in cases() if c["sha256"] in pilot_SHA]
    need(len(cs)==PILOT,"pilot sample drift")
    rows=[]
    for c in cs:
        for arm in ARMS:
            r=one(c,0,arm,PILOT_CAP)
            rows.append(r);save(ROOT/"pilot.json",rows)
            print("SEARCH2_PILOT_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==PILOT*len(ARMS),"pilot trials incomplete")
    print("SEARCH2_PILOT_PASS "+json.dumps(dict(
       SHA=PILOT,trials=len(rows),SAT_verified=sum(r["status"]=="SAT" for r in rows),
       true_native_CDCL_metrics=sum(r["actual_CDCL_telemetry"] is not None for r in rows)),
       sort_keys=True),flush=True)

def shard(i):
    m=verify()
    need(i in range(SHARDS),"bad shard")
    cs=[c for j,c in enumerate(cases()) if j%SHARDS==i]
    need(len(cs)==COUNT//SHARDS,"unequal shard")
    rows=[]
    for c in cs:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(seed(c["sha256"],rep)).shuffle(arms)
            for arm in arms:
                r=one(c,rep,arm,CAP)
                r["shard"]=i;rows.append(r)
                need(r["wall_E2E_s"]<=CAP+.1,"cap exceeded")
                save(ROOT/("shard-%d.json"%i),rows)
                print("SEARCH2_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==COUNT//SHARDS*REPS*len(ARMS),"shard incomplete")
    print("SEARCH2_SHARD_PASS "+json.dumps(dict(
         shard=i,SHA=len(cs),trials=len(rows)),sort_keys=True),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        x=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(x)==COUNT//SHARDS*REPS*len(ARMS),"shard incomplete")
        rows.extend(x)
    expected={(c["sha256"],rep,a) for c in m["sources"]
              for rep in range(REPS) for a in ARMS}
    actual={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(actual)==len(expected)==EXPECTED and
         actual==expected,"pairing mismatch or duplicates")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP
           and r["original_SHA_verified"] and r["no_parallel_solver_children"]
           and r["wall_E2E_s"]<=CAP+.1 and
           r["status"] in ("SAT","UNSAT","TIMEOUT") and
           (r["status"]!="SAT" or r["SAT_original_model_verified"]),
           "trial invalid")
        if r["arm"] not in ("kissat1","cadical_unpatched"):
            tele=r["actual_CDCL_telemetry"]
            need(isinstance(tele,dict)
                 and tele["conflicts"]>=0 and tele["decisions"]>=0
                 and tele["search_propagations"]>=0,
                 "no native CDCL instrumentation")
            mode=r["arm"].split("_",1)[1]
            need((tele["initial_internal_priority_seed_count"]>0)==
                  (mode in ("guided","reverse","placebo")),
                  "native CDCL priority setting not causal")
        bysha[r["sha256"]].append(r)
    agreed=set()
    for sha,rr in bysha.items():
        statuses={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"solver SAT/UNSAT disagreement on original "+sha)
        if (any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr)
           and any(r["arm"]=="cadical_unpatched" and r["status"]=="UNSAT" for r in rr)):
            agreed.add(sha)
    def passed(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and
                                       r["sha256"] in agreed)
    def par(r):return r["wall_E2E_s"] if passed(r) else CAP*2
    def summary(rr):
        tele=[r["actual_CDCL_telemetry"] for r in rr if r["actual_CDCL_telemetry"]]
        return dict(trials=len(rr),
          solved=sum(passed(r) for r in rr),
          SAT_original_verified=sum(r["status"]=="SAT" for r in rr),
          UNSAT_original_ref_agreed_no_LRAT=sum(r["status"]=="UNSAT" and passed(r) for r in rr),
          UNSAT_unverified=sum(r["status"]=="UNSAT" and not passed(r) for r in rr),
          TIMEOUT=sum(r["status"]=="TIMEOUT" for r in rr),
          PAR2_s=round(sum(par(r) for r in rr),6),
          wall_E2E_total_s=round(sum(r["wall_E2E_s"] for r in rr),6),
          child_CPU_s=round(sum(r["child_CPU_s"] for r in rr),6),
          parent_CPU_s=round(sum(r["parent_CPU_s"] for r in rr),6),
          source_prep_wall_s=round(sum(r["prep_E2E_s"] for r in rr),6),
          observed_CDCL_conflicts=sum(t["conflicts"] for t in tele),
          observed_CDCL_decisions=sum(t["decisions"] for t in tele),
          observed_CDCL_search_propagations=sum(t["search_propagations"] for t in tele))
    score={a:summary([r for r in rows if r["arm"]==a]) for a in ARMS}
    for arm in ARMS:
        ref="kissat1" if arm=="kissat1" else "cadical_unpatched"
        score[arm]["speedup_vs_reference_PAR2_x"]=round(
            score[ref]["PAR2_s"]/score[arm]["PAR2_s"],6)
        score[arm]["speedup_vs_cadical_noop_PAR2_x"]=round(
            score["cadical_noop"]["PAR2_s"]/score[arm]["PAR2_s"],6)
    differences={}
    for arm in ARMS:
        if arm in ("kissat1","cadical_unpatched"):continue
        dif=[]
        for sha,rr in bysha.items():
            for rep in range(REPS):
                a=next(r for r in rr if r["arm"]==arm and r["rep"]==rep)
                b=next(r for r in rr if r["arm"]=="cadical_unpatched" and r["rep"]==rep)
                dif.append(par(a)-par(b))
        differences[arm]=dict(wins=sum(x<-.02 for x in dif),
            ties=sum(abs(x)<=.02 for x in dif),
            losses=sum(x>.02 for x in dif),
            best_gain_s=round(min(dif),6),
            worst_regression_s=round(max(dif),6))
    report=dict(protocol=PROTO,source_count=COUNT,trials=EXPECTED,
        all_original_SHA=True,not_globally_blind=True,
        true_native_CDCL_activities=True,source_only_priority=True,
        patched_and_unpatched_CaDiCaL_pinned=True,
        independent_original_SAT_witness_validation=True,
        no_independent_UNSAT_LRAT=True,
        accepted_UNSAT_reference_sha=sorted(agreed),
        no_auto_promotion=True,
        scores=score,paired_vs_unpatched=differences,
        per_shard={str(i):{a:summary([r for r in rows if r["shard"]==i and r["arm"]==a])
                          for a in ARMS} for i in range(SHARDS)},
        per_SHA={sha:dict(
            gbd=next(c["gbd"] for c in m["sources"] if c["sha256"]==sha),
            XOR3=rr[0]["source_XOR3"],
            binary_ratio=rr[0]["source_binary_ratio"],
            arms={a:[dict(rep=r["rep"],status=r["status"],
                  E2E_s=r["wall_E2E_s"],tele=r["actual_CDCL_telemetry"])
                  for r in rr if r["arm"]==a] for a in ARMS})
                 for sha,rr in bysha.items()})
    save(ROOT/"report.json",report)
    print("SEARCH2_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","pilot","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        {"selftest":selftest,"freeze":freeze,"verify":verify,
         "pilot":pilot,"audit":audit}[a.action]()
        if a.action=="verify":print("SEARCH2_VERIFY_PASS",flush=True)
