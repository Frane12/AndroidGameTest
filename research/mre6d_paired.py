#!/usr/bin/env python3
"""DRNAS MRE6b source-disjoint SAT2026 paired four-arm CPU benchmark.

Always evaluates all four arms, including formulas with NO certified positive
equivalence. Absence of proof causes ABSTENTION (safe baseline) and is counted.
DO NOT choose formula based on detected XOR/equality, and never select a winner
from target runtime. SAT verdicts get independently verified against original
CNF. UNSAT is checked against the published SAT2026 official status, NOT LRAT.

Total cap includes preprocessing, proof replay, rewriting, CMS subprocess,
original-model reconstruction and verification. Native process CPU covers ONLY
cms.solve(), so full CPU lower-bound adds measured Python CPU preprocessing.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,statistics,subprocess,sys,tempfile,time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195
import mre1_cross_representation as mre1
import mre6_principles as m6
import mre5_cpu_watch_cost as m5
import mre6b_blind_freeze as freeze

PROTO="DRNAS-MRE6D-LOCKED7-DIAGNOSTIC-4ARM-2REP-90S-v1"
ROOT=pathlib.Path("mre6b_blind")
MODES=("native_no_xor","quotient_no_xor","all_no_xor","all_xor")
SHARDS=4
REPS=2
CAP=90.0
MAX_PREP_CLAUSES=35000
MAX_DERIVE_S=0.55
SOURCE_CMS_SHA="3b709118fd08eb1d15f25e0e239dbc596f967b60"


def need(ok,reason):
    if not ok:raise RuntimeError("MRE6D_PAIRED_FAIL_CLOSED "+str(reason))

def seed_of(sha,rep):
    return int(hashlib.sha256(("MRE6B-BLIND-LOCKED|"+sha+"|"+str(rep)
         ).encode()).hexdigest()[:8],16)

def find_direct_equalities(original):
    known={mre1.normalize(c) for c in original if len(c)==2}
    out=[]
    # The SOURCE CNF directly contains both (not a OR b) and
    # (a OR not b); each is its own simplest valid certificate.
    for clause in original:
        if len(clause)!=2 or (clause[0]>0)==(clause[1]>0):continue
        a,b=sorted(map(abs,clause))
        if a==b:continue
        c0=mre1.normalize((-a,b))
        c1=mre1.normalize((a,-b))
        if c0 in known and c1 in known:
            out.append((a,b))
    return sorted(set(out))

def choose_certified_principle(original,rows,proofs):
    direct=find_direct_equalities(original)
    candidates=[]
    for a,b in direct:
        candidates.append(dict(principle="certified_equality",
            keep=a,remove=b,
            proof_lemma_a=mre1.normalize((-a,b)),
            proof_lemma_b=mre1.normalize((a,-b)),
            proof_replayed=True,
            proof_type="two_original_CNF_binary_clauses",
            principle_id=hashlib.sha256(("ORIGINAL|%d|%d"%(a,b)).encode()).hexdigest()))
    for row in m6.build_principles(original,rows,proofs):
        p=dict(row)
        p["proof_type"]="MRE1_GF2_OR_RESOLUTION_REPLAYED"
        candidates.append(p)
    if not candidates:return None,0
    occurrences=collections.Counter(abs(lit) for c in original for lit in c)
    # The deterministic structural rule uses ONLY original-CNF variable
    # occurrence counts and proof existence. No CPU labels or solve time.
    chosen=sorted(candidates,key=lambda x:
        (-occurrences[x["remove"]],x["keep"],x["remove"],x["proof_type"]))[0]
    need(chosen["proof_replayed"],"unproven equality candidate")
    if chosen["proof_type"]=="two_original_CNF_binary_clauses":
        known={mre1.normalize(c) for c in original}
        need(tuple(chosen["proof_lemma_a"]) in known
             and tuple(chosen["proof_lemma_b"]) in known,
             "source direct equivalence certificate missing")
    else:
        need(mre1.verify_proofs(original,rows,proofs),
             "MRE1 replay certificate missing")
    return chosen,len({(x["keep"],x["remove"]) for x in candidates})

def build_arm(source,mode,root):
    need(mode in MODES,"invalid arm")
    initial=time.perf_counter()
    cpu_initial=time.process_time()
    stats=dict(gate="no_transform_requested",eligible=False,
        discovered_equalities=0,source_xor_rows=0,
        proof_replayed=False,cnf_before=None,cnf_after=None,
        variable_rewritten=None,replaced_literal_count=0,
        eq_certificate_kind=None,abstain_reason=None,
        preprocessing_cpu_s=0.0,preprocessing_wall_s=0.0)
    src=pathlib.Path(source)
    n=None
    original_count=None
    cnf=src
    rows=[]
    pr=None
    if mode!="native_no_xor":
        n,original=exact.parse_dimacs(src)
        original_count=len(original)
        stats["cnf_before"]=len(original)
        if len(original)>MAX_PREP_CLAUSES:
            stats["abstain_reason"]="large_source_early_guard"
            stats["gate"]="abstain_original_cnf"
        elif mode=="xor":
            rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
            mre1.replay_source_xors(original,rows)
            stats["gate"]="certified_source_XOR_import"
        else:
            source_rows,proofs,dstats=mre1.derive(original,max_s=MAX_DERIVE_S)
            need(dstats["proof_replayed"],
                 "MRE1 mathematical certificate replay missing")
            pr,candidates=choose_certified_principle(original,source_rows,proofs)
            stats["discovered_equalities"]=candidates
            stats["proof_replayed"]=bool(pr)
            if pr is None:
                stats["gate"]="abstain_no_replay_certified_positive_equality"
                stats["abstain_reason"]="no_certified_equality"
                rows=source_rows if mode=="quotient" else []
            else:
                stats["gate"]="certified_equality_quotient"
                stats["eligible"]=True
                cnf_clauses,transformed_rows,evidence=m6.apply_quotient(
                    original,source_rows,pr)
                cnf=root/"quotient.cnf"
                mre1.write_cnf(cnf,n,cnf_clauses,[])
                stats["cnf_after"]=len(cnf_clauses)
                stats["variable_rewritten"]=pr["remove"]
                stats["replaced_literal_count"]=evidence["cnf"]["replaced_occurrences"]
                stats["eq_certificate_kind"]=pr["proof_type"]
                rows=transformed_rows if mode=="quotient" else []
    if original_count is None:
        n,clauses=exact.parse_dimacs(src)
        original_count=len(clauses)
        stats["cnf_before"]=original_count
    stats["cnf_after"]=stats["cnf_after"] or original_count
    rowfile=root/"rows.tsv"
    if rows:
        mre1.write_xors(rowfile,rows)
    else:rowfile.write_text("")
    stats["source_xor_rows"]=len(rows)
    stats["preprocessing_cpu_s"]=round(time.process_time()-cpu_initial,6)
    stats["preprocessing_wall_s"]=round(time.perf_counter()-initial,6)
    return cnf,rowfile,n,stats,pr

def trial(case,rep,mode,binary):
    source=ROOT/case["filename"]
    need(freeze.sha256(source.read_bytes())==case["sha256"],
         "source SHA drift")
    start=time.perf_counter()
    cpu0=time.process_time()
    with tempfile.TemporaryDirectory(prefix="drnas-mre6b-unseen-") as t:
        d=pathlib.Path(t)
        cnf,xor,n,meta,pr=build_arm(source,mode,d)
        empty=d/"empty.tsv"
        empty.write_text("")
        env=os.environ.copy()
        env["DRNAS_TRACE_ENABLED"]=str(1 if rep==0 else 0)
        env["DRNAS_ORIG_COUNT"]=str(meta["cnf_after"])
        env["DRNAS_TAG_0"]=""
        env["DRNAS_TAG_1"]=""
        status="TIMEOUT";native=None;cpu=None;watch=None
        trace=None
        run_s=None
        time_left=CAP-(time.perf_counter()-start)
        if time_left>=0.15:
            t0=time.perf_counter()
            try:
                p=subprocess.run(
                    [str(pathlib.Path(binary).resolve()),str(pathlib.Path(cnf).resolve()),
                     str(rowfile_resolve(xor)),str(empty.resolve()),
                     "source_xor_no_gauss",str(seed_of(case["sha256"],rep))],
                    capture_output=True,text=True,errors="replace",timeout=time_left,
                    env=env,check=False)
            except subprocess.TimeoutExpired:
                p=None
            run_s=time.perf_counter()-t0
            if p is not None:
                need(p.returncode==0,
                     "native CMS invalid witness, missing binary, or runtime error: "+
                     p.stderr[-1000:])
                try:
                    status,model,native,trace,ledger,cpu,watch=m5.parse_native(p.stdout)
                except RuntimeError:
                    # Early root contradiction is valid UNSAT only if it is
                    # independently known from the official published status.
                    status,model,native=r195.parsed_native(p.stdout)
                    need(status=="UNSAT" and
                         case["original_verified_status"]=="UNSAT",
                         "incomplete CMS telemetry or wrong UNSAT result")
                if status=="SAT":
                    if pr is not None:model=(all_eq.reconstruct(model,pr["mapping"]) if "mapping" in pr else m6.reconstruct(model,pr))
                    r195.verify_model(source,model)
                need(status in ("SAT","UNSAT"),"unexpected solver verdict")
                need(status==case["original_verified_status"],
                     "solver result conflicts with official SAT2026 status")
                if cpu is not None:
                    need(cpu["enabled"]==int(rep==0),
                         "misconfigured native watcher telemetry")
                    need(ledger["original_count"]==meta["cnf_after"],
                         "native input clause count mismatch")
                    need(all(v["attached"]==0 for v in trace.values()),
                         "a blind source accidentally inherited tagged test lemma")
        elapsed=time.perf_counter()-start
        if elapsed>=CAP:status="TIMEOUT"
        full_python_cpu=time.process_time()-cpu0
        # Native CPU reports only CMS.solve; load/parse native C++ CPU is
        # not currently measured. Use wall-clock for complete comparison.
        cpu_lower=(full_python_cpu+cpu["process_cpu_s"]) if cpu else None
        out=dict(protocol=PROTO,source_sha256=case["sha256"],
           official_gbd=case["gbd"],official_status=case["original_verified_status"],
           mode=mode,seed=seed_of(case["sha256"],rep),rep=rep,status=status,
           cap_s=CAP,full_wall_s=round(elapsed,6),
           par2_s=round(CAP*2 if status=="TIMEOUT" else elapsed,6),
           prep_wall_s=meta["preprocessing_wall_s"],
           prep_python_cpu_s=meta["preprocessing_cpu_s"],
           python_total_cpu_s=round(full_python_cpu,6),
           native_solve_cpu_s=cpu["process_cpu_s"] if cpu else None,
           known_python_plus_solve_cpu_lower_bound_s=(
               round(cpu_lower,6) if cpu_lower is not None else None),
           native_subprocess_wall_s=(round(run_s,6) if run_s else None),
           native_cdcl_propagations=native.get("propagations") if native else None,
           native_cdcl_decisions=native.get("decisions") if native else None,
           native_cdcl_conflicts=native.get("conflicts") if native else None,
           binary_watcher_visits=watch["visits"] if watch else None,
           binary_watcher_units=watch["units"] if watch else None,
           trace_enabled=bool(rep==0),
           quotient_applied=bool(pr),
           original_sat_model_verified=bool(status=="SAT"),
           UNSAT_independent_LRAT=False,
           original_status_verified_from_official_csv=True,
           cpu_includes_native_DIMACS_load=False,
           original_clauses=case["clauses"],original_vars=case["vars"],
           proof_gate=meta,otf_gauss=False,
           native_CMS_source_commit=SOURCE_CMS_SHA,
           github_sha=os.environ.get("GITHUB_SHA","local"))
        return out

def rowfile_resolve(path):
    return pathlib.Path(path).resolve()

def shard(idx,binary):
    need(0<=idx<SHARDS,"invalid shard")
    freeze.verify()
    mf=json.loads((ROOT/"manifest.json").read_text())
    cases=[x for i,x in enumerate(mf["cases"]) if i%SHARDS==idx]
    need(cases,"shard has no sources")
    out=ROOT/("shard-%d.json"%idx)
    records=[]
    for case in cases:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+case["sha256"]+":"+str(rep)).shuffle(modes)
            for mode in modes:
                row=trial(case,rep,mode,binary)
                records.append(row)
                out.write_text(json.dumps(records,sort_keys=True)+"\n")
                print("MRE6D_PAIRED_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(records)==len(cases)*REPS*len(MODES),
         "shard missing paired cases")
    print("MRE6D_PAIRED_SHARD_PASS",idx,len(cases),len(records),flush=True)

def audit():
    freeze.verify()
    mf=json.loads((ROOT/"manifest.json").read_text())
    records=[]
    for idx in range(SHARDS):
        p=ROOT/("shard-%d.json"%idx)
        need(p.exists(),"missing shard result")
        records+=json.loads(p.read_text())
    need(len(records)==len(mf["cases"])*REPS*len(MODES),
         "incomplete exact paired cohort")
    known={c["sha256"]:c for c in mf["cases"]}
    paired=collections.defaultdict(dict)
    for r in records:
        c=known.get(r["source_sha256"])
        need(c and r["official_gbd"]==c["gbd"] and
             r["official_status"]==c["original_verified_status"],
             "source/official mismatch")
        need(r["protocol"]==PROTO and r["otf_gauss"] is False,
             "protocol or config mismatch")
        need(r["mode"] not in paired[(r["source_sha256"],r["rep"])],
             "paired duplicate")
        paired[(r["source_sha256"],r["rep"])][r["mode"]]=r
        if r["status"]=="SAT":
            need(r["original_sat_model_verified"],"unverified SAT model")
        if r["status"]=="UNSAT":
            need(c["original_verified_status"]=="UNSAT",
                 "UNSAT disagrees with independent official published status")
    need(len(paired)==len(mf["cases"])*REPS,"paired cohort missing source/repetition")
    for p in paired.values():
        need(set(p)==set(MODES),"missing four modes")
        need(len({x["seed"] for x in p.values()})==1,"paired seed mismatch")
        need(len({x["native_CMS_source_commit"] for x in p.values()})==1,
             "native library not identical")
    per_case=[]
    by_mode=collections.defaultdict(list)
    for c in mf["cases"]:
        arms=collections.defaultdict(list)
        for r in records:
            if r["source_sha256"]==c["sha256"]:
                arms[r["mode"]].append(r)
        have_eq=any(r["quotient_applied"] for r in arms["all_no_xor"]+arms["all_xor"])
        entry=dict(gbd=c["gbd"],sha256=c["sha256"],
             official_status=c["original_verified_status"],
             original_clauses=c["clauses"],equality_detected=have_eq,
             modes={})
        for mode in MODES:
            arr=arms[mode]
            by_mode[mode].extend(arr)
            entry["modes"][mode]=dict(attempts=len(arr),
                 solved=sum(r["status"] in ("SAT","UNSAT") for r in arr),
                 par2_s=round(sum(r["par2_s"] for r in arr),6),
                 full_wall_s=round(sum(r["full_wall_s"] for r in arr),6),
                 preprocessing_wall_s=round(sum(r["prep_wall_s"] for r in arr),6),
                 native_solve_cpu_s=round(sum(
                    (r["native_solve_cpu_s"] or 0) for r in arr),6),
                 proof_gate=arr[0]["proof_gate"])
        per_case.append(entry)
    modes={}
    for mode in MODES:
        arr=by_mode[mode]
        modes[mode]=dict(
            attempts=len(arr),
            solved=sum(x["status"] in ("SAT","UNSAT") for x in arr),
            timeouts=sum(x["status"]=="TIMEOUT" for x in arr),
            par2_s=round(sum(x["par2_s"] for x in arr),6),
            full_wall_s=round(sum(x["full_wall_s"] for x in arr),6),
            prep_wall_s=round(sum(x["prep_wall_s"] for x in arr),6),
            solver_cpu_samples=sum(x["native_solve_cpu_s"] is not None for x in arr),
            known_solver_cpu_sum_s=round(sum(
                 (x["native_solve_cpu_s"] or 0) for x in arr),6))
    report=dict(protocol=PROTO,sources=len(mf["cases"]),
        diagnostic_cohort_reused_after_screening=True,
        historical_registry_not_proven_exhaustive=True,
        source_disjoint_from_MRE2_to_MRE6=True,
        original_SHA_verified_all=True,
        official_verified_statuses=mf["statuses"],
        single_source_not_the_cohort=False,
        source_cohort_unchanged=True,
        all_seven_included_without_runtime_selection=True,
        measurements=len(records),modes=modes,per_case=per_case,
        equality_eligible_sources=sum(x["equality_detected"] for x in per_case),
        abstain_sources=sum(not x["equality_detected"] for x in per_case),
        independent_UNSAT_LRAT=False,
        overall_time_includes_preprocessing=True,
        default_deployment_unchanged=True,
        MRE6D_research_methods_not_automatically_enabled=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE6D_PAIRED_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    src=[(-1,2),(1,-2),(-2,3),(2,-3),(1,4)]
    eqs=find_direct_equalities(src)
    need((1,2) in eqs and (2,3) in eqs,"independent direct equality proof broken")
    pr,n=choose_certified_principle(src,[],[])
    need(pr is not None and pr["proof_type"]==
         "two_original_CNF_binary_clauses" and n==2,
         "direct source implication certificate not replayed")
    need(REPS*len(MODES)==8 and CAP==90.0,"holdout protocol changed")
    all_eq.selftest()
    print("MRE6D_PAIRED_PILOT_SELFTEST_PASS",PROTO,flush=True)


import mre6d_all_equalities as all_eq
legacy_build_arm=build_arm

def build_arm(source,mode,root):
    if mode not in ("all_no_xor","all_xor"):
        return legacy_build_arm(source,mode,root)
    t0=time.perf_counter(); cpu0=time.process_time()
    n,original=exact.parse_dimacs(source)
    rows=[]
    # Cheap direct equality scan first. No costly GF2 derivation on this arm.
    transformed,_,mapping,evidence=all_eq.quotient(original)
    if mode=="all_xor" and len(original)<=MAX_PREP_CLAUSES:
        rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
        mre1.replay_source_xors(original,rows)
        transformed,rows,mapping,evidence=all_eq.quotient(original,rows)
    cnf=pathlib.Path(source)
    if mapping:
        cnf=root/"all-quotient.cnf"
        mre1.write_cnf(cnf,n,transformed,[])
    rowfile=root/"rows.tsv"
    mre1.write_xors(rowfile,rows)
    meta=dict(gate="direct_all_classes" if mapping else "abstain_no_direct_equality",
        eligible=bool(mapping),discovered_equalities=evidence["pairs"],
        source_xor_rows=len(rows),proof_replayed=bool(mapping),
        cnf_before=len(original),cnf_after=len(transformed),
        variable_rewritten=None,variables_eliminated=len(mapping),
        equality_classes=evidence["classes"],
        replaced_literal_count=evidence["replaced_occurrences"],
        eq_certificate_kind="two_original_CNF_binary_clauses_transitive_closure" if mapping else None,
        abstain_reason=None if mapping else "no_direct_equality",
        reduction_evidence=evidence,
        preprocessing_cpu_s=round(time.process_time()-cpu0,6),
        preprocessing_wall_s=round(time.perf_counter()-t0,6))
    return cnf,rowfile,n,meta,({"mapping":mapping} if mapping else None)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="mre5/native")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard,a.binary)
    else:audit()

