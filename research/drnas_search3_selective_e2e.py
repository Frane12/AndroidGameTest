#!/usr/bin/env python3
"""DRNAS SEARCH3 -- native selective SEARCH2 CDCL structure-guided ablation.

Source cohort: 16 SHA frozen during EQUIV6, strictly disjoint from SEARCH2
original SHA. This cohort was previously benchmarked by EQUIV6 and is therefore
NOT globally blind. Gate preregistered before SEARCH3 outcomes: source-only
binary_ratio in [0.40,0.85], 500<=vars<=10000 activates both. All original
CNFs are fed to every solver untouched. VMTF and EVSIDS are independently
seeded inside a pinned CaDiCaL 3.0.1 C++ engine (no renaming of solver CNF).
Independent original SAT witness verification, original reference double UNSAT
agreement only (no independent LRAT). Single logical CPU for each child.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,tempfile,time
import drnas_x22_parallel_reducer as x22
import drnas_search2_direct_cdcl_e2e as s2
import drnas_equiv9_prospective_seed_holdout as e9
ROOT=pathlib.Path("mre_search3")
SOURCE=pathlib.Path("mre_equiv6/cases")
E6MAN=pathlib.Path("mre_equiv6/manifest.json")
SEARCH2MAN=pathlib.Path("prior_search2/mre_equiv13/manifest.json")
DRIVER=ROOT/"bin/search3_cadical"
PRIORITY=pathlib.Path("mre_search2/bin/search1_relabel")
CAD=pathlib.Path("mre_equiv6/bin/cadical_3_0_1")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
PROTO="DRNAS-SEARCH3-SOURCEONLY-SELECTIVE-VMTF-EVSIDS-16SHA-10ARMS-2REPS-10S-v1"
ARMS=("cadical_unpatched","cadical_orig","cadical_preponly","cadical_vmtf",
      "cadical_evsids","cadical_both","cadical_reverse",
      "cadical_placebo","cadical_gate","kissat_orig")
REPS=2
SHARDS=8
COUNT=16
CAP=10.
PILOT_CAP=5.
PILOT_COUNT=4
EXPECTED=COUNT*REPS*len(ARMS)
SALT="DRNAS-SEARCH3-PRECOMMITTED-SELECTIVE-GATE-20261110-v1"

def need(x,why):
    if not x:raise RuntimeError("SEARCH3_FAIL_CLOSED "+str(why))
def dig(p):return e9.digest(p)
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def gate(c):
    f=c["source_signals"]
    # This hypothesis is motivated by SEARCH2's sole winning SHA and NOT
    # trained from outcomes of the 16 EQUIV6 sources.
    return (0.40 <= f["binary_ratio"] <= 0.85 and
            500 <= f["vars"] <= 10000)
def cases():
    m=json.loads(E6MAN.read_text())
    need(len(m["cases"])==COUNT and len({c["sha256"] for c in m["cases"]})==COUNT,
         "EQUIV6 original-source frozen manifest drift")
    prior=json.loads(SEARCH2MAN.read_text())["cases"]
    excluded={c["sha256"] for c in prior}
    result=m["cases"]
    need(not excluded.intersection(c["sha256"] for c in result),
         "SEARCH2 SHA reused in SEARCH3!")
    for c in result:
        src=SOURCE/c["filename"]
        need(dig(src)==c["sha256"],"EQUIV6 source SHA changed")
    return result
def hashes():
    return dict(driver=dig(DRIVER),features=dig(PRIORITY),
                unpatched=dig(CAD),kissat=dig(KISSAT))
def pilot_SHA(cs):
    # Four independent source-only strata, no solver outcome filtering.
    selected=[]
    for fn in (lambda c:-c["source_signals"]["binary_ratio"],
               lambda c:c["source_signals"]["binary_ratio"],
               lambda c:abs(c["source_signals"]["binary_ratio"]-.6),
               lambda c:abs(c["source_signals"]["binary_ratio"]-.1)):
        remainder=[c for c in cs if c["sha256"] not in selected]
        ranked=sorted(remainder,key=lambda c:(fn(c),c["sha256"]))
        selected.append(ranked[0]["sha256"])
    need(len(set(selected))==PILOT_COUNT,"source-only selection duplicated")
    return sorted(selected)
def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    cs=cases()
    for f in (DRIVER,PRIORITY,CAD,KISSAT):need(f.is_file(),"binary missing "+str(f))
    m=dict(protocol=PROTO,source_count=COUNT,
      sources=cs, source_artifact_run_id=42614287853,
      prior_search2_frozen_sha=dig(SEARCH2MAN),
      EQUIV6_frozen_manifest_sha=dig(E6MAN),
      source_exclusion="No original CNF SHA overlap with SEARCH2 EQUIV13 12 SHA",
      globally_blind=False,never_used_in_SEARCH2=True,
      original_sources_previously_tested_in_EQUIV6=True,
      source_gate_precommitted=True,
      selective_rule="0.4<=binary_ratio<=0.85 and 500<=vars<=10000 => both VMTF+EVSIDS; otherwise none",
      eligible_SHA=sorted(c["sha256"] for c in cs if gate(c)),
      pilot_SHA=pilot_SHA(cs),pilot_cap_s=PILOT_CAP,
      code_SHA=dig(__file__),
      patch_code_SHA=dig("research/drnas_search3_patch_modes.py"),
      base_patch_SHA=dig("research/drnas_search2_patch_cadical.py"),
      driver_cpp_SHA=dig("research/drnas_search3_cadical_driver.cpp"),
      feature_cpp_SHA=dig("research/drnas_search1_guided_relabel.cpp"),
      bins=hashes(),upstream="arminbiere/cadical rel-3.0.1 pinned commit c60730422e758ef1cebe7aeddf2dda31c996bf04",
      arms=list(ARMS),reps=REPS,shards=SHARDS,cap_s=CAP,
      expected_trials=EXPECTED,one_logical_CPU_per_child=True,
      no_parallel_children=True,
      source_structure_probe_paid_in_E2E=True,
      independent_original_SAT_witness=True,
      independent_UNSAT_LRAT=False,
      UNSAT_original_Kissat_CaDiCaL_agreement_only=True,
      no_auto_promotion=True)
    save(ROOT/"manifest.json",m);verify()
    print("SEARCH3_FROZEN "+json.dumps(dict(
       source_count=COUNT,trials=EXPECTED,pilot_count=PILOT_COUNT,
       pilot_trials=PILOT_COUNT*len(ARMS),
       eligible_SHA=m["eligible_SHA"],reference_no_overlap=True,
       not_globally_blind=True),sort_keys=True),flush=True)
def verify():
    m=json.loads((ROOT/"manifest.json").read_text());cs=cases()
    need(m["protocol"]==PROTO and m["sources"]==cs
         and m["source_count"]==COUNT and m["expected_trials"]==EXPECTED
         and m["arms"]==list(ARMS) and m["reps"]==REPS
         and m["shards"]==SHARDS and m["cap_s"]==CAP
         and m["pilot_SHA"]==pilot_SHA(cs)
         and m["eligible_SHA"]==sorted(c["sha256"] for c in cs if gate(c)),
         "protocol/selection changed")
    need(m["prior_search2_frozen_sha"]==dig(SEARCH2MAN)
         and m["EQUIV6_frozen_manifest_sha"]==dig(E6MAN)
         and m["code_SHA"]==dig(__file__)
         and m["patch_code_SHA"]==dig("research/drnas_search3_patch_modes.py")
         and m["base_patch_SHA"]==dig("research/drnas_search2_patch_cadical.py")
         and m["driver_cpp_SHA"]==dig("research/drnas_search3_cadical_driver.cpp")
         and m["feature_cpp_SHA"]==dig("research/drnas_search1_guided_relabel.cpp")
         and m["bins"]==hashes(),"frozen code/solver/CNF SHA drift")
    return m
def seed(sha,rep):
    return int(hashlib.sha256((SALT+sha+"|"+str(rep)).encode()).hexdigest()[:15],16)
def arm_mode(arm,c):
    if arm=="cadical_vmtf":return "guided",1
    if arm=="cadical_evsids":return "guided",2
    if arm=="cadical_both":return "guided",3
    if arm=="cadical_reverse":return "reverse",3
    if arm=="cadical_placebo":return "placebo",3
    if arm=="cadical_gate":return "guided",3 if gate(c) else 0
    if arm=="cadical_preponly":return "guided",0
    return None,0
def one(c,rep,arm,cap):
    need(arm in ARMS and rep in range(REPS) and cap in (CAP,PILOT_CAP),
         "trial schema error")
    src=SOURCE/c["filename"]
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    started=time.perf_counter();cpu_start=time.process_time()
    children=x22.child_cpu()
    need(dig(src)==c["sha256"],"original CNF changed")
    n,clauses=x22.read_cnf(src)
    need(n>0 and bool(clauses),"source invalid")
    prep_mode,mask=arm_mode(arm,c)
    obs=None;diag=None;status="TIMEOUT";verified=False
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        rank="NONE"
        if prep_mode:
            rpath,summary=s2.score_file(src,prep_mode,seed(c["sha256"],rep),
                                        tmp,clauses)
            messages=[x for x in summary.splitlines()
                      if x.startswith("SEARCH1_RENAME ")]
            need(len(messages)==1,"missing source-only feature telemetry")
            diag=json.loads(messages[0][len("SEARCH1_RENAME "):])
            if mask:rank=str(rpath.resolve())
        prep_s=time.perf_counter()-started
        left=cap-prep_s
        need(left>.2,"source preprocessing exhausted cap")
        if arm=="cadical_unpatched":
            command=[str(CAD),str(src)]
        elif arm=="kissat_orig":
            command=e9.command("kissat1",src,e9.seedpair(c["sha256"],rep)[0])
        else:
            command=[str(DRIVER.resolve()),str(src.resolve()),rank,
                     str(max(.15,left-.08)),str(mask)]
        child=x22.launch("search3",command,cpu,tmp)
        try:
            while child["p"].poll() is None and time.perf_counter()-started<cap-.025:
                time.sleep(.004)
            if child["p"].poll() is not None:
                output,err=x22.read_output(child)
                rc=child["p"].returncode
                need(rc in (0,10,20),"native child error "+arm+" "+str(rc)+" "+err[-450:])
                if arm not in ("cadical_unpatched","kissat_orig"):
                    texts=[x[len("SEARCH3_METRICS "):] for x in output.splitlines()
                           if x.startswith("SEARCH3_METRICS ")]
                    need(len(texts)==1,"real CDCL telemetry absent")
                    obs=json.loads(texts[0])
                    need(obs["source_is_original_DIMACS"] and
                         obs["priority_mode_mask"]==mask and
                         obs["initial_vmtf_seed"]==int(bool(mask&1)) and
                         obs["initial_evsids_seed"]==int(bool(mask&2)) and
                         obs["initial_internal_priority_seed_count"]==(n if mask else 0),
                         "invalid actual CDCL mode or rank")
                if rc in (10,20):
                    need(("s SATISFIABLE" if rc==10 else "s UNSATISFIABLE") in
                         [line.strip() for line in output.splitlines()],
                         "verdict inconsistency")
                    if rc==10:
                        s2.read_sat(output,clauses);status="SAT";verified=True
                    else:status="UNSAT"
        finally:
            x22.cleanup([child])
    wall=time.perf_counter()-started
    if wall>=cap:status="TIMEOUT";verified=False
    need(dig(src)==c["sha256"],"source changed after solver")
    need(status!="SAT" or verified,"original model not verified")
    return dict(protocol=PROTO,arm=arm,rep=rep,sha256=c["sha256"],
      gbd=c["gbd"],original_sha_verified=True,cap_s=cap,
      status=status,SAT_original_model_verified=verified,
      UNSAT_independent_LRAT=False,
      one_logical_CPU=cpu,no_parallel_children=True,
      source_binary_ratio=c["source_signals"]["binary_ratio"],
      source_reciprocal_edges=c["source_signals"]["reciprocal_binary_edges"],
      source_selected_gate=gate(c),mode_mask=mask,
      original_DIMACS_fed_to_CDCL=True,
      preparation_E2E_s=round(prep_s,6),wall_E2E_s=round(wall,6),
      child_CPU_s=round(x22.child_cpu()-children,6),
      parent_CPU_s=round(time.process_time()-cpu_start,6),
      actual_CDCL_telemetry=obs,source_feature_diags=diag)

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(DRIVER.is_file() and PRIORITY.is_file(),"missing native binary")
    rng=random.Random(1130026);count=0;sat_verified=0
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"toy.cnf"
        for n in range(2,7):
            for rep in range(4):
                clauses=[tuple(rng.choice((-1,1))*rng.randint(1,n)
                          for _ in range(rng.randint(1,4)))
                          for _ in range(rng.randint(2,18))]
                p.write_text("p cnf %d %d\n"%(n,len(clauses))+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
                truth=any(x22.holds(clauses,{v:bool(i&(1<<(v-1)))
                           for v in range(1,n+1)}) for i in range(1<<n))
                for mode,mask in (("guided",0),("guided",1),("guided",2),
                                  ("guided",3),("reverse",3),("placebo",3)):
                    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
                        path,_=s2.score_file(p,mode,100+rep,tmp,clauses)
                        rank="NONE" if mask==0 else str(path.resolve())
                        r=subprocess.run([str(DRIVER.resolve()),str(p.resolve()),
                              rank,"2.0",str(mask)],capture_output=True,text=True,
                              timeout=5)
                        need(r.returncode in (10,20),
                             "toy status error "+r.stderr[-200:])
                        need((r.returncode==10)==truth,"toy satisfiability mismatch")
                        if truth:s2.read_sat(r.stdout,clauses);sat_verified+=1
                        row=[x for x in r.stdout.splitlines()
                             if x.startswith("SEARCH3_METRICS ")]
                        need(len(row)==1,"toy telemetry absent")
                        tele=json.loads(row[0][len("SEARCH3_METRICS "):])
                        need(tele["priority_mode_mask"]==mask and
                             tele["conflicts"]>=0 and tele["decisions"]>=0
                             and tele["search_propagations"]>=0,
                             "toy native CDCL mode mismatch")
                        count+=1
    print("SEARCH3_SELFTEST_PASS "+json.dumps(dict(
        attempts=count,SAT_original_verified=sat_verified,
        VMTF_only=True,EVSIDS_only=True,BOTH=True,placebo=True,
        original_truth_table_equivalence=True),sort_keys=True),flush=True)
def pilot():
    m=verify();cs=[c for c in cases() if c["sha256"] in m["pilot_SHA"]]
    need(len(cs)==PILOT_COUNT,"pilot source count drift")
    rows=[]
    for c in cs:
        for arm in ARMS:
            row=one(c,0,arm,PILOT_CAP)
            rows.append(row);save(ROOT/"pilot.json",rows)
            print("SEARCH3_PILOT_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==PILOT_COUNT*len(ARMS),"pilot not complete")
    print("SEARCH3_PILOT_PASS "+json.dumps(dict(
        sha=len(cs),trials=len(rows),
        verified_SAT=sum(r["status"]=="SAT" for r in rows)),sort_keys=True),flush=True)
def shard(i):
    m=verify()
    need(0<=i<SHARDS,"invalid shard")
    cs=[c for j,c in enumerate(cases()) if j%SHARDS==i]
    need(len(cs)==2,"shard misbalanced")
    rows=[]
    for c in cs:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(seed(c["sha256"],rep)).shuffle(order)
            for arm in order:
                row=one(c,rep,arm,CAP);row["shard"]=i
                need(row["wall_E2E_s"]<=CAP+.1,"E2E cap exceeded")
                rows.append(row);save(ROOT/("shard-%d.json"%i),rows)
                print("SEARCH3_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cs)*REPS*len(ARMS),"missing trial")
    print("SEARCH3_SHARD_PASS "+json.dumps(dict(
        shard=i,SHA=len(cs),trials=len(rows)),sort_keys=True),flush=True)
def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        p=ROOT/("shard-%d.json"%i)
        subset=json.loads(p.read_text())
        need(len(subset)==2*REPS*len(ARMS),"shard incomplete "+str(i))
        rows+=subset
    expected={(c["sha256"],rep,a) for c in m["sources"]
              for rep in range(REPS) for a in ARMS}
    found={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(found)==len(expected)==EXPECTED and
         found==expected,"pairing missing, duplicated or unexpected")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
          r["original_sha_verified"] and r["original_DIMACS_fed_to_CDCL"]
          and r["no_parallel_children"] and r["wall_E2E_s"]<=CAP+.1
          and r["status"] in ("SAT","UNSAT","TIMEOUT") and
          (r["status"]!="SAT" or r["SAT_original_model_verified"]) and
          r["source_selected_gate"]==gate(next(c for c in m["sources"]
                                             if c["sha256"]==r["sha256"])),
          "inconsistent outcome or features")
        if r["arm"] not in ("cadical_unpatched","kissat_orig"):
            tele=r["actual_CDCL_telemetry"]
            need(isinstance(tele,dict) and
                 tele["priority_mode_mask"]==r["mode_mask"] and
                 tele["initial_internal_priority_seed_count"]==
                  (next(c["source_signals"]["vars"] for c in m["sources"]
                   if c["sha256"]==r["sha256"]) if r["mode_mask"] else 0),
                 "CDCL mode not causal")
        bysha[r["sha256"]].append(r)
    agreed=set()
    for sha,rw in bysha.items():
        verdicts={r["status"] for r in rw if r["status"]!="TIMEOUT"}
        need(len(verdicts)<=1,"SAT/UNSAT original source contradiction "+sha)
        if any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rw) and \
           any(r["arm"]=="cadical_unpatched" and r["status"]=="UNSAT" for r in rw):
            agreed.add(sha)
    def ok(r):return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agreed)
    def p2(r):return r["wall_E2E_s"] if ok(r) else 2*CAP
    def stat(rr):
        tele=[r["actual_CDCL_telemetry"] for r in rr
              if r["actual_CDCL_telemetry"] is not None]
        return dict(n=len(rr),solved=sum(ok(r) for r in rr),
          SAT_original_verified=sum(r["status"]=="SAT" for r in rr),
          UNSAT_original_backend_agreement_no_LRAT=sum(r["status"]=="UNSAT" and ok(r) for r in rr),
          UNSAT_unverified=sum(r["status"]=="UNSAT" and not ok(r) for r in rr),
          TIMEOUT=sum(r["status"]=="TIMEOUT" for r in rr),
          PAR2_s=round(sum(p2(r) for r in rr),6),
          wall_total_s=round(sum(r["wall_E2E_s"] for r in rr),6),
          CPU_child_s=round(sum(r["child_CPU_s"] for r in rr),6),
          CPU_parent_s=round(sum(r["parent_CPU_s"] for r in rr),6),
          prep_wall_s=round(sum(r["preparation_E2E_s"] for r in rr),6),
          CDCL_conflicts=sum(x["conflicts"] for x in tele),
          CDCL_decisions=sum(x["decisions"] for x in tele),
          CDCL_search_propagations=sum(x["search_propagations"] for x in tele),
          active_seed_count=sum(r["mode_mask"]!=0 for r in rr))
    scores={a:stat([r for r in rows if r["arm"]==a]) for a in ARMS}
    for a in ARMS:
        scores[a]["PAR2_speedup_vs_unpatched_x"]=round(
            scores["cadical_unpatched"]["PAR2_s"]/scores[a]["PAR2_s"],6)
        scores[a]["PAR2_speedup_vs_prepcontrol_x"]=round(
            scores["cadical_preponly"]["PAR2_s"]/scores[a]["PAR2_s"],6)
    paired={}
    for a in ARMS:
        if a=="cadical_unpatched":continue
        delta=[]
        for sha,rs in bysha.items():
            for rep in range(REPS):
                v=next(r for r in rs if r["arm"]==a and r["rep"]==rep)
                base=next(r for r in rs if r["arm"]=="cadical_unpatched" and r["rep"]==rep)
                delta.append(p2(v)-p2(base))
        paired[a]=dict(wins=sum(x<-.02 for x in delta),
              losses=sum(x>.02 for x in delta),
              ties=sum(abs(x)<=.02 for x in delta),
              best_gain_s=round(min(delta),6),
              worst_regression_s=round(max(delta),6))
    eligible={c["sha256"] for c in m["sources"] if gate(c)}
    out=dict(protocol=PROTO,sources=COUNT,trials=EXPECTED,
        source_SHA_disjoint_SEARCH2=True,
        EQUIV6_previously_seen_not_globally_blind=True,
        one_logical_CPU=True,original_CNF_untouched=True,
        actual_native_VMTF_EVSIDS_isolated=True,
        independent_UNSAT_LRAT=False,
        UNSAT_original_ref_agreement=sorted(agreed),
        independent_original_SAT_witness=True,
        no_auto_promotion=True,gate_eligible_sha=sorted(eligible),
        scores=scores,paired_vs_unpatched=paired,
        per_shard={str(i):{a:stat([r for r in rows if r["shard"]==i and r["arm"]==a])
                           for a in ARMS} for i in range(SHARDS)},
        gate_class={k:{a:stat([r for r in rows if r["arm"]==a and
                            (r["sha256"] in eligible)==yes])
                       for a in ARMS}
                   for k,yes in (("eligible",True),("ineligible",False))},
        per_SHA={sha:dict(gbd=next(c["gbd"] for c in m["sources"]
                                  if c["sha256"]==sha),
          signals=next(c["source_signals"] for c in m["sources"]
                       if c["sha256"]==sha),
          arms={a:[dict(rep=r["rep"],status=r["status"],
                        E2E_s=r["wall_E2E_s"],mode=r["mode_mask"],
                        telemetry=r["actual_CDCL_telemetry"])
                   for r in rs if r["arm"]==a]
                for a in ARMS}) for sha,rs in bysha.items()})
    save(ROOT/"report.json",out)
    print("SEARCH3_FINAL "+json.dumps(out,sort_keys=True),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","verify","pilot","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    a=parser.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        {"selftest":selftest,"freeze":freeze,"verify":verify,
         "pilot":pilot,"audit":audit}[a.action]()
        if a.action=="verify":print("SEARCH3_VERIFY_PASS",flush=True)
