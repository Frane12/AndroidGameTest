#!/usr/bin/env python3
"""DRNAS MRE7: medium real SAT2026, full 35s solve (not a short conflict probe).

Source-paired 6 originals: 2 reused and known CMS-solvable anchors and 4
reference-time selected 2-15s official 2026 originals (no DRNAS screening).
Four modes: no-XOR CMS, original CMS+certified XOR, proof-based MRE6b quotient
without XOR, and cheap direct-CNF-equivalence CPU guard with CMS+XOR fallback.
All costs including Python prep, source rewrite and witness verification are
charged inside the 35-second full wall; native CPU is measured by pinned MRE5.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,sys,tempfile,time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195
import mre1_cross_representation as mre1
import mre5_cpu_watch_cost as mre5
import mre6_principles as m6
import mre6b_blind_pilot as m6b
import mre7_medium_freeze as cohort

PROTO="DRNAS-MRE7-MEDIUM-REAL2026-2KNOWN+4REF-4ARM-2REP-FULL35S-v1"
ROOT=pathlib.Path("mre7_medium")
MODES=cohort.MODES
CAP=cohort.CAP
REPS=cohort.REPS
SHARDS=3
CMS_SOURCE_SHA="3b709118fd08eb1d15f25e0e239dbc596f967b60"

def need(ok,msg):
    if not ok:raise RuntimeError("MRE7_PAIRED_FAIL_CLOSED "+str(msg))

def seed_of(sha,rep):
    return int(hashlib.sha256((PROTO+"|"+sha+"|"+str(rep)).encode()).hexdigest()[:8],16)

def direct_cpu_gate(source,tmp):
    """Cheap source-native exact CNF certificate; no proof search and no CPU oracle.

    Probe original binary clauses only. If CNF contains both (-a v b)
    and (a v -b), they PROVE a=b; optional safe quotient avoids extra
    watched clauses. If none, original CMS+certified source XOR fallback.
    """
    p=pathlib.Path(source)
    started=time.perf_counter()
    cpu0=time.process_time()
    n,original=exact.parse_dimacs(p)
    pairs=m6b.find_direct_equalities(original)
    trace=dict(policy="only_direct_positive_equality_in_original_binary_CNF",
               proof_type="no_derived_lemma_unless_both_original_clauses_present",
               direct_pairs=len(pairs),gate="fallback_CMS_XOR",
               certificate_verified=False,source_rows=0,
               replaced_literals=0,original_clauses=len(original),
               transformed_clauses=len(original))
    if pairs:
        # This is a fixed structural choice BEFORE timing CMS.
        occur=collections.Counter(abs(l) for c in original for l in c)
        a,b=sorted(pairs,key=lambda ab:(-occur[ab[1]],ab[0],ab[1]))[0]
        known={mre1.normalize(c) for c in original}
        need(mre1.normalize((-a,b)) in known
             and mre1.normalize((a,-b)) in known,
             "direct certified quotient lacks original two clauses")
        pr=dict(principle="certified_equality",keep=a,remove=b,
                proof_replayed=True,proof_type="exact_original_two_binary_clauses")
        clauses,ignored_xor,meta=m6.apply_quotient(original,[],pr)
        cnf=tmp/"direct-certified-quotient.cnf"
        mre1.write_cnf(cnf,n,clauses,[])
        xor=tmp/"no-source-xor.tsv";xor.write_text("")
        trace.update(gate="direct_proved_equivalence_quotient_no_XOR",
               certificate_verified=True,replaced_literals=meta["cnf"]["replaced_occurrences"],
               transformed_clauses=len(clauses))
    else:
        pr=None;cnf=p
        rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
        mre1.replay_source_xors(original,rows)
        xor=tmp/"fallback-certified-xor.tsv"
        mre1.write_xors(xor,rows)
        trace.update(source_rows=len(rows))
    trace["prep_s"]=round(time.perf_counter()-started,6)
    trace["prep_cpu_s"]=round(time.process_time()-cpu0,6)
    return cnf,xor,trace,pr

def prepare(case,mode,tmp):
    source=ROOT/case["name"]
    if mode=="mre7_cpu_guard":
        return direct_cpu_gate(source,tmp)
    m={"cms_native":"native_no_xor","cms_source_xor":"xor",
       "mre6b_proof_quotient":"quotient_no_xor"}.get(mode)
    need(m is not None,"unexpected arm")
    cnf,xor,n,meta,pr=m6b.build_arm(source,m,tmp)
    return pathlib.Path(cnf),pathlib.Path(xor),meta,pr

def trial(case,rep,mode,binary):
    source=ROOT/case["name"]
    need(r195.digest(source)==case["sha256"],"original input SHA mismatch")
    began=time.perf_counter()
    cpu0=time.process_time()
    meta={}
    status="TIMEOUT";native={};cpu=None;watch=None
    subprocess_s=None;original_model_verified=False
    with tempfile.TemporaryDirectory(prefix="mre7-medium-real-") as temp:
        tmp=pathlib.Path(temp)
        cnf,xor,meta,pr=prepare(case,mode,tmp)
        prep_s=time.perf_counter()-began
        src=tmp/"empty.tsv";src.write_text("")
        env=os.environ.copy()
        env.update(DRNAS_TRACE_ENABLED="0",
                   DRNAS_ORIG_COUNT=str(meta.get("transformed_clauses") or meta.get("cnf_after")),
                   DRNAS_TAG_0="",DRNAS_TAG_1="")
        leftover=CAP-(time.perf_counter()-began)
        if leftover>=0.15:
            t=time.perf_counter()
            try:
                out=subprocess.run(
                  [str(pathlib.Path(binary).resolve()),
                   str(cnf.resolve()),str(xor.resolve()),str(src.resolve()),
                   "source_xor_no_gauss",str(seed_of(case["sha256"],rep))],
                  capture_output=True,text=True,errors="replace",check=False,
                  env=env,timeout=leftover)
            except subprocess.TimeoutExpired:
                out=None
            subprocess_s=time.perf_counter()-t
            if out is not None:
                need(out.returncode==0,
                     "native CMS failure: "+out.stderr[-1000:])
                try:
                    status,model,native,tag,ledger,cpu,watch=mre5.parse_native(out.stdout)
                    need(cpu["enabled"]==0,"CPU trace toggle mismatch")
                except RuntimeError:
                    status,model,native=r195.parsed_native(out.stdout)
                    need(status=="UNSAT","missing native counters in SAT solution")
                need(status in ("SAT","UNSAT"),"no final solver verdict")
                need(status==case["expected"],
                     "CMS disagrees with externally verified SAT/UNSAT source")
                if status=="SAT":
                    if pr is not None:
                        model=m6.reconstruct(model,pr)
                    r195.verify_model(source,model)
                    original_model_verified=True
        elapsed=time.perf_counter()-began
        if elapsed>=CAP:status="TIMEOUT"
    return dict(protocol=PROTO,case=case["name"],cohort=case["cohort"],
        sha256=case["sha256"],expected=case["expected"],
        published_reference_s=case["published_reference_s"],
        mode=mode,rep=rep,seed=seed_of(case["sha256"],rep),status=status,
        full_wall_s=round(elapsed,6),
        par2_s=round(2*CAP if status=="TIMEOUT" else elapsed,6),
        full_python_cpu_s=round(time.process_time()-cpu0,6),
        preprocessing_wall_s=round(prep_s,6),
        solve_native_cpu_s=cpu["process_cpu_s"] if cpu else None,
        solve_native_wall_s=cpu["solve_wall_s"] if cpu else None,
        all_process_cpu_lower_bound_s=(
          round(time.process_time()-cpu0+cpu["process_cpu_s"],6)
          if cpu else None),
        subprocess_wall_s=round(subprocess_s,6) if subprocess_s is not None else None,
        decisions=native.get("decisions"),conflicts=native.get("conflicts"),
        propagations=native.get("propagations"),proof_gate=meta,
        SAT_original_model_verified=original_model_verified,
        UNSAT_independent_LRAT=False,
        UNSAT_official_published_status_crosscheck=(status=="UNSAT"),
        source_SHA_verified=True,otf_gauss=False,
        native_CMS_sha=CMS_SOURCE_SHA,
        github_run=os.environ.get("GITHUB_RUN_ID","local"))

def shard(k,binary):
    need(k in range(SHARDS),"shard out of range")
    cohort.verify()
    m=json.loads((ROOT/"manifest.json").read_text())
    cases=m["cases"][k::SHARDS]
    need(len(cases)==2,"shard cohort changed")
    rows=[]
    for c in cases:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                row=trial(c,rep,mode,binary)
                rows.append(row)
                (ROOT/("shard-%d.json"%k)).write_text(
                    json.dumps(rows,sort_keys=True)+"\n")
                print("MRE7_MEDIUM_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cases)*REPS*len(MODES)==16,"shard trial count")
    print("MRE7_MEDIUM_SHARD_PASS",k,len(rows),flush=True)

def audit():
    cohort.verify()
    m=json.loads((ROOT/"manifest.json").read_text())
    data=[]
    for k in range(SHARDS):
        data+=json.loads((ROOT/("shard-%d.json"%k)).read_text())
    need(len(data)==6*REPS*len(MODES)==48,"missing paired results")
    sources={c["sha256"]:c for c in m["cases"]}
    paired=collections.defaultdict(dict)
    for z in data:
        c=sources.get(z["sha256"])
        need(c is not None and z["expected"]==c["expected"] and
             z["case"]==c["name"] and z["cohort"]==c["cohort"],"source mismatch")
        need(z["protocol"]==PROTO and z["otf_gauss"] is False
             and z["native_CMS_sha"]==CMS_SOURCE_SHA
             and z["source_SHA_verified"],"native/source confound")
        if z["status"]=="SAT":
            need(z["SAT_original_model_verified"],"unverified SAT witness")
        if z["status"]=="UNSAT":
            need(c["expected"]=="UNSAT"
                 and z["UNSAT_official_published_status_crosscheck"],
                 "unverified UNSAT official verdict")
        key=(z["sha256"],z["rep"])
        need(z["mode"] not in paired[key],"duplicate")
        paired[key][z["mode"]]=z
    need(len(paired)==12,"not 12 paired source/seeds")
    for z in paired.values():
        need(set(z)==set(MODES),"missing arm")
        need(len({v["seed"] for v in z.values()})==1,"seed mismatch")
    group=collections.defaultdict(list)
    for x in data:group[(x["cohort"],x["mode"])].append(x)
    totals={}
    for cohort_name in ("REUSED_known_solved_diagnostic","NEW_official_reference_medium"):
        totals[cohort_name]={}
        for mode in MODES:
            vals=group[(cohort_name,mode)]
            solved=[x for x in vals if x["status"]!="TIMEOUT"]
            totals[cohort_name][mode]=dict(
                attempts=len(vals),solved=len(solved),timeouts=len(vals)-len(solved),
                par2_s=round(sum(x["par2_s"] for x in vals),6),
                full_wall_s=round(sum(x["full_wall_s"] for x in vals),6),
                prep_total_s=round(sum(x["preprocessing_wall_s"] for x in vals),6),
                native_solve_cpu_s=round(sum(
                    (x["solve_native_cpu_s"] or 0) for x in vals),6))
    per_source=[]
    for c in m["cases"]:
        vals=[x for x in data if x["sha256"]==c["sha256"]]
        per_source.append(dict(name=c["name"],cohort=c["cohort"],
           expected=c["expected"],official_reference_s=c["published_reference_s"],
           arms={mode:dict(solved=sum(x["status"]!="TIMEOUT" for x in vals
                                     if x["mode"]==mode),
                 par2_s=round(sum(x["par2_s"] for x in vals if x["mode"]==mode),6),
                 mean_pre_s=round(sum(x["preprocessing_wall_s"] for x in vals
                                     if x["mode"]==mode)/REPS,6),
                 gates=[x["proof_gate"].get("gate") for x in vals if x["mode"]==mode])
                 for mode in MODES}))
    summary=dict(protocol=PROTO,measurement_count=48,source_count=6,
        anchor_count=2,official_new_reference_count=4,
        real_SAT2026_all=True,reference_difficulty_range_s=[2,15],
        full_35s_wall_per_attempt=True,
        source_new_cohort_preselected_by_published_reference_not_DRNAS=True,
        known_anchor_cohort_reused_not_blind=True,
        new_historical_source_disjoint_not_exhaustive=True,
        no_post_hoc_excluding_timed_out_cases=True,
        native_CPU_missing_on_timeout=True,
        all_SAT_models_original_verified=True,
        official_UNSAT_verdict_crosscheck_not_LRAT=True,
        solved_any=sum(x["status"]!="TIMEOUT" for x in data),
        by_cohort=totals,per_source=per_source,
        production_policy_not_promoted=True)
    (ROOT/"report.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("MRE7_MEDIUM_FINAL",json.dumps(summary,sort_keys=True),flush=True)

def selftest():
    need(len(MODES)==4 and len(cohort.ANCHORS)==2 and CAP==35
         and REPS==2,"medium protocol error")
    # Full direct equivalence proof must be present in original CNF.
    original=[(-1,2),(1,-2),(2,3),(-2,-3)]
    pairs=m6b.find_direct_equalities(original)
    need((1,2) in pairs,"safe original equality certificate not detected")
    print("MRE7_MEDIUM_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--binary",default="mre5/native")
    a=ap.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard,a.binary)
    else:audit()
