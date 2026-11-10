#!/usr/bin/env python3
"""DRNAS SEARCH1 — experimental CDCL search guidance via BIJECTIVE variable IDs.
12 previously seen EQUIV13 original SHA, two paired repetitions, 15s E2E.
Not true native decision-heuristic integration: guided, reverse and random
renumbering perturb solver internal search. No variable elimination or invented
model; SAT is lifted to the exact original SHA and independently checked.
UNSAT counts only original Kissat+CaDiCaL agreement (no independent LRAT).
Separate 4-source source-only pilot of 32 trials at 6s before 192 full E2E.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,subprocess,tempfile,time
import drnas_equiv13_structural_router as e13
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_search1")
BIN=ROOT/"bin/search1_relabel"
PROTO="DRNAS-SEARCH1-SOURCE-SCC-XOR3-PERMUTE-12SHA-8ARM-2REP-15SEC-v1"
ARMS=("kissat_orig","kissat_guided","kissat_reverse","kissat_placebo",
      "cadical_orig","cadical_guided","cadical_reverse","cadical_placebo")
SHARDS=6
CAP=15.0
PILOT_CAP=6.0
REPS=2
SOURCES=12
PILOT=4
EXPECTED=SOURCES*REPS*len(ARMS)
SALT="DRNAS-SEARCH1-SOURCE-BIN-SCC-XOR3-PILOT-20261110-v1"

def need(v,msg):
    if not v:raise RuntimeError("SEARCH1_FAIL_CLOSED "+str(msg))

def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def hashfile(path):return e9.digest(path)

def cases():
    m=e13.verify()
    cs=m["cases"]
    need(len(cs)==SOURCES and len({c["sha256"] for c in cs})==SOURCES,
         "source cohort invalid")
    return cs

def binaries():
    return dict(relabel=hashfile(BIN),
                kissat=hashfile(e9.KISSAT),
                cadical=hashfile(e9.CAD))

def source_signals(c):
    src=e9.SOURCE/c["filename"]
    need(hashfile(src)==c["sha256"],"original source changed")
    n,clauses=x22.read_cnf(src)
    s=e13.source_signals(n,clauses)
    need(s==c["signals"],"original features changed")
    return s

def pilot_sources(cs):
    # Entirely source-only, SHA-frozen before any SEARCH1 solver trial:
    # 2 highest exact-XOR3 sources and 2 highest binary ratio other sources.
    left=sorted(cs,key=lambda c:(-c["signals"]["xor3_complete_patterns"],
                                  c["sha256"]))[:2]
    other=[c for c in cs if c not in left]
    right=sorted(other,key=lambda c:(-c["signals"]["binary_ratio"],
                                       c["sha256"]))[:2]
    ids={c["sha256"] for c in left+right}
    need(len(ids)==PILOT,"pilot source geometry selection")
    return [c for c in cs if c["sha256"] in ids]

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    cs=cases()
    need(BIN.is_file(),"C++ relabeler missing")
    picked=pilot_sources(cs)
    m=dict(protocol=PROTO,source_count=SOURCES,trial_count=EXPECTED,
      arms=list(ARMS),shards=SHARDS,repetitions=REPS,cap_s=CAP,
      pilot_count=PILOT,pilot_cap_s=PILOT_CAP,
      pilot_SHA=sorted(c["sha256"] for c in picked),
      source_selection="existing EQUIV13 previously seen originals; NOT BLIND",
      no_fresh_holdout_claim=True,original_CNF_SHA_locked=True,
      source_only_variables_scored_before_search=True,
      ranking="xor3 complete motifs + signed binary implication SCC sizes + binary degree + occurrence",
      implementation="exact bijective original CNF variable renaming, NOT a direct CDCL heuristic",
      negative_control="reverse exact score order",
      placebo_control="source SHA and rep keyed uniform random permutation",
      proof="all clauses verified under variable bijection; exact original SAT model verified",
      UNSAT_strict="original Kissat + original CaDiCaL agreement only, no independent LRAT",
      one_logical_CPU=True,no_parallel_solving=True,
      no_auto_promotion=True,
      sources=[dict(sha256=c["sha256"],gbd=c["gbd"],filename=c["filename"],
                    signals=c["signals"]) for c in cs],
      source_manifest_SHA=hashfile(e13.ROOT/"manifest.json"),
      code_SHA=hashfile(__file__),
      cpp_SHA=hashfile("research/drnas_search1_guided_relabel.cpp"),
      binaries=binaries())
    save(ROOT/"manifest.json",m)
    verify()
    print("SEARCH1_FROZEN "+json.dumps(dict(sources=SOURCES,
      pilot_SHA=m["pilot_SHA"],pilot_trials=PILOT*len(ARMS),
      full_trials=EXPECTED,not_blind=True,
      original_SHA_unchanged=True),sort_keys=True),flush=True)

def verify():
    cs=cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["source_count"]==SOURCES
         and m["trial_count"]==EXPECTED
         and m["arms"]==list(ARMS) and m["shards"]==SHARDS
         and m["repetitions"]==REPS and m["cap_s"]==CAP
         and m["pilot_count"]==PILOT and m["pilot_cap_s"]==PILOT_CAP,
         "protocol drift")
    need(m["pilot_SHA"]==sorted(c["sha256"] for c in pilot_sources(cs)),
         "pilot cohort changed")
    need(m["source_manifest_SHA"]==hashfile(e13.ROOT/"manifest.json")
         and m["code_SHA"]==hashfile(__file__)
         and m["cpp_SHA"]==hashfile("research/drnas_search1_guided_relabel.cpp")
         and m["binaries"]==binaries(),"code, binary or frozen registry drift")
    for c in cs:
        need(hashfile(e9.SOURCE/c["filename"])==c["sha256"],"original SHA drift")
        source_signals(c)
    return m

def permutation(path,n):
    lines=pathlib.Path(path).read_text().splitlines()
    need(lines and lines[0].split()==["p","perm",str(n)]
         and len(lines)==n+1,"permutation header")
    perm={}
    for i,line in enumerate(lines[1:],1):
        old,new=map(int,line.split())
        need(old==i and 1<=new<=n and new not in perm.values(),
             "invalid bijection")
        perm[old]=new
    need(len(perm)==n and len(set(perm.values()))==n,"non-bijection")
    return perm

def verify_relabel(original,changed,perm):
    need(len(original)==len(changed),"CNF clause count not preserved")
    for x,y in zip(original,changed):
        witness=tuple((1 if l>0 else -1)*perm[abs(l)] for l in x)
        need(witness==tuple(y),"CNF rewrite not exact bijective literal relabel")

def read_model(stdout,transformed,original,perm):
    values={}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for l in map(int,line.split()[1:]):
                if l==0:continue
                need(abs(l) not in values or values[abs(l)]==(l>0),
                     "SAT witness contradictory assignment")
                values[abs(l)]=(l>0)
    need(x22.holds(transformed,values),"renamed SAT model falsifies permuted CNF")
    original_assignment={old:values.get(new,False) for old,new in perm.items()}
    need(x22.holds(original,original_assignment),"lifted SAT model falsifies ORIGINAL CNF")
    return len(values)

def seed_for(sha,rep):
    return int(hashlib.sha256((sha+"|SEARCH1-RENAME|"+str(rep)).encode()).hexdigest()[:15],16)

def experiment(c,rep,arm,cap):
    need(arm in ARMS and rep in range(REPS) and cap in (CAP,PILOT_CAP),
         "trial schema")
    backend,mode=arm.split("_",1)
    src=e9.SOURCE/c["filename"]
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    started=time.perf_counter();main_cpu_start=time.process_time()
    children_cpu_start=x22.child_cpu()
    original_sha=hashfile(src)
    need(original_sha==c["sha256"],"original source SHA changed")
    n,original=x22.read_cnf(src)
    need(n>0 and bool(original),"empty source")
    source_n_vars=n
    features=source_signals(c)
    pseed=seed_for(c["sha256"],rep)
    mapped={v:v for v in range(1,n+1)}
    diag=dict(mode=mode)
    status="TIMEOUT";sat_verify=False
    preprocess=0.0;raw_conflicts=None
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        target=src
        transformed=original
        if mode!="orig":
            target=pathlib.Path(tmp)/"mapped.cnf"
            mapfile=pathlib.Path(tmp)/"permutation.map"
            proc=subprocess.run([str(BIN.resolve()),mode,str(src.resolve()),
                                 str(target),str(mapfile),str(pseed)],
                                 capture_output=True,text=True,timeout=max(.5,cap/2))
            need(proc.returncode==0,"relabel C++ failed "+proc.stderr[-600:])
            telemetry=[line for line in proc.stderr.splitlines()
                       if line.startswith("SEARCH1_RENAME ")]
            need(len(telemetry)==1,"relabel telemetry absent")
            diag=json.loads(telemetry[0].split("SEARCH1_RENAME ",1)[1])
            mapped=permutation(mapfile,n)
            n2,transformed=x22.read_cnf(target)
            need(n2==n,"variable count altered")
            verify_relabel(original,transformed,mapped)
        preprocess=time.perf_counter()-started
        left=cap-preprocess
        need(left>.10,"source-only prep exhausted cap")
        base_seed=e9.seedpair(c["sha256"],rep)[0]
        solver_arm="kissat1" if backend=="kissat" else "cadical301_default"
        command=e9.command(solver_arm,target,base_seed)
        child=x22.launch(backend,command,cpu,tmp)
        try:
            solver_started=time.perf_counter()
            while child["p"].poll() is None and time.perf_counter()-started<cap-.025:
                time.sleep(.004)
            if child["p"].poll() is not None:
                out,err=x22.read_output(child)
                rc=child["p"].returncode
                if rc in (10,20):
                    expected="s SATISFIABLE" if rc==10 else "s UNSATISFIABLE"
                    need(expected in [s.strip() for s in out.splitlines()],
                         "solver exit/verdict discrepancy")
                    if rc==10:
                        read_model(out,transformed,original,mapped)
                        status="SAT";sat_verify=True
                    else:
                        status="UNSAT"
                else:
                    need(False,"unexpected solver exit "+str(rc)+":"+err[-250:])
                # Solver text metrics are diagnostics, not bounded-CDCL success.
                for l in out.splitlines():
                    mc=re.search(r"conflicts:\s*([0-9]+)",l,re.I)
                    if mc:raw_conflicts=int(mc.group(1))
        finally:
            x22.cleanup([child])
    elapsed=time.perf_counter()-started
    if elapsed>=cap:status="TIMEOUT";sat_verify=False
    need(hashfile(src)==original_sha,"original CNF SHA mutated")
    need(status!="SAT" or sat_verify,"SAT model not verified")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],rep=rep,
        arm=arm,status=status,cap_s=cap,
        SAT_original_witness_verified=bool(sat_verify),
        UNSAT_independent_LRAT=False,source_sha_verified=True,
        one_logical_cpu=cpu,no_parallel_children=True,
        variables=source_n_vars,original_clauses=len(original),
        source_binary_ratio=features["binary_ratio"],
        source_xor3_patterns=features["xor3_complete_patterns"],
        mapping_checked_exact_original_clauses=True,
        permutation_mode=mode,source_independent_placebo_seed=pseed if mode=="placebo" else None,
        preparation_E2E_s=round(preprocess,6),
        wall_E2E_s=round(elapsed,6),
        CPU_child_total_s=round(x22.child_cpu()-children_cpu_start,6),
        CPU_parent_s=round(time.process_time()-main_cpu_start,6),
        conflicts_diagnostic=raw_conflicts,
        renamer=diag)

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(BIN.is_file(),"missing compiled native renamer")
    rng=random.Random(1337026);count=0
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)
        for n in range(2,7):
            for it in range(10):
                clauses=[]
                for j in range(rng.randint(1,20)):
                    clauses.append(tuple(rng.choice((-1,1))*rng.randint(1,n)
                           for k in range(rng.randint(1,4))))
                src=root/"in.cnf"
                src.write_text("p cnf %d %d\n"%(n,len(clauses))+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
                orig_n,orig=x22.read_cnf(src)
                truth=any(x22.holds(orig,{v:bool(mask&(1<<(v-1)))
                                         for v in range(1,n+1)}) for mask in range(1<<n))
                for mode in ("guided","reverse","placebo"):
                    transformed=root/"out.cnf";mpath=root/"p.map"
                    p=subprocess.run([str(BIN.resolve()),mode,str(src.resolve()),
                        str(transformed),str(mpath),str(213+it)],
                        capture_output=True,text=True,timeout=3)
                    need(p.returncode==0,"toy native exit "+p.stderr[-220:])
                    newn,new=x22.read_cnf(transformed)
                    need(newn==orig_n,"toy changed variable count")
                    perm=permutation(mpath,n)
                    verify_relabel(orig,new,perm)
                    sat=any(x22.holds(new,{v:bool(mask&(1<<(v-1)))
                                         for v in range(1,n+1)}) for mask in range(1<<n))
                    need(truth==sat,"toy brute-force SAT equivalence failed")
                    count+=1
    print("SEARCH1_SELFTEST_PASS "+json.dumps(dict(
       exhaustive_small_formula_renamings=count,
       exact_original_clause_replay=True,original_SAT_equivalence=True,
       guidance_is_not_direct_CDCL_engine_modification=True),sort_keys=True),flush=True)

def pilot():
    m=verify();selected=pilot_sources(cases());rows=[]
    for c in selected:
        for arm in ARMS:
            r=experiment(c,0,arm,PILOT_CAP)
            rows.append(r);save(ROOT/"pilot.json",rows)
            print("SEARCH1_PILOT_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==PILOT*len(ARMS),"pilot incomplete")
    print("SEARCH1_PILOT_PASS "+json.dumps(dict(
        trials=len(rows),SHA=PILOT,solved_SAT=sum(r["status"]=="SAT" for r in rows),
        UNSAT_unverified=sum(r["status"]=="UNSAT" for r in rows)),
        sort_keys=True),flush=True)

def shard(idx):
    m=verify();need(idx in range(SHARDS),"invalid shard")
    cs=cases()
    group=[c for i,c in enumerate(cs) if i%SHARDS==idx]
    need(len(group)==2,"shard case imbalance")
    rows=[]
    for c in group:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(seed_for(c["sha256"],rep)).shuffle(arms)
            for arm in arms:
                r=experiment(c,rep,arm,CAP)
                r["shard"]=idx
                need(r["wall_E2E_s"]<=CAP+.1,"E2E cap violated")
                rows.append(r);save(ROOT/f"shard-{idx}.json",rows)
                print("SEARCH1_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(group)*REPS*len(ARMS),"shard incomplete")
    print("SEARCH1_SHARD_PASS "+json.dumps(dict(
         idx=idx,SHA=len(group),trials=len(rows)),sort_keys=True),flush=True)

def audit():
    m=verify();cs=cases()
    allrows=[]
    for idx in range(SHARDS):
        rows=json.loads((ROOT/f"shard-{idx}.json").read_text())
        need(len(rows)==32,"missing shard attempts")
        allrows.extend(rows)
    expected={(c["sha256"],rep,arm) for c in cs
              for rep in range(REPS) for arm in ARMS}
    observed={(r["sha256"],r["rep"],r["arm"]) for r in allrows}
    need(len(allrows)==len(observed)==len(expected)==EXPECTED
         and observed==expected,"SHA pairing or duplicates")
    per_sha=collections.defaultdict(list)
    for r in allrows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["source_sha_verified"] and r["mapping_checked_exact_original_clauses"]
             and r["no_parallel_children"] and r["wall_E2E_s"]<=CAP+.1
             and r["status"] in ("SAT","UNSAT","TIMEOUT")
             and (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "invalid audited trial")
        per_sha[r["sha256"]].append(r)
    agreed=set()
    for sha,rows in per_sha.items():
        verdicts={r["status"] for r in rows if r["status"]!="TIMEOUT"}
        need(len(verdicts)<=1,"SAT/UNSAT contradiction on original SHA")
        if (any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rows)
            and any(r["arm"]=="cadical_orig" and r["status"]=="UNSAT" for r in rows)):
            agreed.add(sha)
    def success(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agreed)
    def p2(r):
        return r["wall_E2E_s"] if success(r) else 2*CAP
    def summary(rows):
        return dict(attempts=len(rows),solved=sum(success(r) for r in rows),
          SAT_original_verified=sum(r["status"]=="SAT" for r in rows),
          UNSAT_ref_agreed_no_LRAT=sum(r["status"]=="UNSAT" and success(r) for r in rows),
          UNSAT_unverified=sum(r["status"]=="UNSAT" and not success(r) for r in rows),
          TIMEOUT=sum(r["status"]=="TIMEOUT" for r in rows),
          PAR2_s=round(sum(p2(r) for r in rows),6),
          wall_total_s=round(sum(r["wall_E2E_s"] for r in rows),6),
          child_CPU_total_s=round(sum(r["CPU_child_total_s"] for r in rows),6),
          parent_CPU_total_s=round(sum(r["CPU_parent_s"] for r in rows),6),
          preprocessing_wall_s=round(sum(r["preparation_E2E_s"] for r in rows),6))
    scores={arm:summary([r for r in allrows if r["arm"]==arm]) for arm in ARMS}
    paired={}
    for backend in ("kissat","cadical"):
        reference=scores[backend+"_orig"]["PAR2_s"]
        placebo=scores[backend+"_placebo"]["PAR2_s"]
        for mode in ("orig","guided","reverse","placebo"):
            name=backend+"_"+mode
            scores[name]["speedup_vs_original_PAR2_x"]=round(
                reference/scores[name]["PAR2_s"],6)
            scores[name]["speedup_vs_placebo_PAR2_x"]=round(
                placebo/scores[name]["PAR2_s"],6)
            if mode=="orig":continue
            delta=[]
            for sha,rows in per_sha.items():
                for rep in range(REPS):
                    arm=next(r for r in rows if r["arm"]==name and r["rep"]==rep)
                    orig=next(r for r in rows if r["arm"]==backend+"_orig" and r["rep"]==rep)
                    delta.append(round(p2(arm)-p2(orig),6))
            paired[name]=dict(wins=sum(x<-.02 for x in delta),
                losses=sum(x>.02 for x in delta),
                ties=sum(abs(x)<=.02 for x in delta),
                biggest_gain_s=min(delta),
                biggest_regression_s=max(delta))
    report=dict(protocol=PROTO,source_count=SOURCES,trial_count=EXPECTED,
      not_blind=True,not_direct_CDCL_heuristic=True,
      one_logical_CPU=True,no_parallel_solver_children=True,
      original_CNFs_SHA_locked=True,
      exact_clause_bijection_independently_verified=True,
      SAT_model_lift_verified_original=True,
      UNSAT_original_reference_agreement_SHA=sorted(agreed),
      no_independent_UNSAT_LRAT=True,
      no_auto_promotion=True,scores=scores,paired_vs_orig=paired,
      per_shard={str(i):{a:summary([r for r in allrows if r["shard"]==i
                                   and r["arm"]==a]) for a in ARMS}
                 for i in range(SHARDS)},
      per_source={sha:dict(gbd=next(c["gbd"] for c in cs if c["sha256"]==sha),
           xor3=rows[0]["source_xor3_patterns"],
           binary_ratio=rows[0]["source_binary_ratio"],
           arms={a:[dict(status=r["status"],rep=r["rep"],
                         E2E_s=r["wall_E2E_s"]) for r in rows if r["arm"]==a]
                 for a in ARMS}) for sha,rows in per_sha.items()})
    save(ROOT/"report.json",report)
    print("SEARCH1_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","verify","pilot","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    a=parser.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        {"selftest":selftest,"freeze":freeze,"verify":verify,
         "pilot":pilot,"audit":audit}[a.action]()
        if a.action=="verify":print("SEARCH1_VERIFY_PASS",flush=True)
