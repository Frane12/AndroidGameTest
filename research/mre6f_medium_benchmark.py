#!/usr/bin/env python3
"""DRNAS MRE6f: medium-real SAT2026 full-solve certified equality benchmark.

The exact six original CNF SHAs from completed MRE7 (2 reused diagnostic
anchors + 4 officially reference-time-selected originals) are reused WITHOUT
resampling or any post hoc inclusion changes. Each attempt has 35s FULL wall,
including parsing, proof check, rewriting, solve and original witness check.

Compare identical pinned CMS 5.11.15 backend and native seeds across:
  native: original CNF, no optional XOR import;
  xor: original CNF + proof-verified source GF(2) imports (eligible sizes);
  all_no_xor: simultaneously quotient all provable positive equality classes;
  all_xor: same quotient plus transported, proof-verified source XOR rows.

All equality edges must appear as both complementary implication clauses
in the ORIGINAL CNF. A union-find closure then yields a certified bijective
model lifting. Disabled OTF Gaussian; no UNSAT LRAT is claimed. This is a
development diagnostic cohort, NOT a new blind holdout.
"""
from __future__ import annotations
import argparse,collections,json,os,pathlib,random,subprocess,sys,tempfile,time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195
import mre1_cross_representation as mre1
import mre5_cpu_watch_cost as mre5
import mre6d_all_equalities as all_eq
import mre7_medium_freeze as frozen
import mre7_medium_pilot as previous

PROTO="DRNAS-MRE6F-REAL-SAT2026-MEDIUM-6SHA-4ARM-2REP-35S-v1"
ROOT=pathlib.Path("mre6f")
INPUT=pathlib.Path("mre7_medium")
CAP=35.0
REPS=2
SHARDS=3
MODES=("native_no_xor","source_xor","all_eq_no_xor","all_eq_plus_xor")
MAX_PREP_CLAUSES=35000
CMS_SOURCE_SHA="3b709118fd08eb1d15f25e0e239dbc596f967b60"

def need(cond,reason):
    if not cond:raise RuntimeError("MRE6F_FAIL_CLOSED "+str(reason))

def prepare(source,mode,tmp):
    start=time.perf_counter()
    cpu0=time.process_time()
    n,original=exact.parse_dimacs(source)
    original_count=len(original)
    need(mode in MODES,"unknown arm")
    rows=[]
    proof_map={}
    cnf=pathlib.Path(source)
    gating="native"
    evidence=dict(pairs=0,merges=0,classes=0,replaced_occurrences=0)
    if mode!="native_no_xor":
        if original_count>MAX_PREP_CLAUSES:
            gating="early_size_abstain"
        elif mode=="source_xor":
            rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
            mre1.replay_source_xors(original,rows)
            gating="verified_source_xor" if rows else "no_verified_source_xor"
        else:
            if mode=="all_eq_plus_xor":
                rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
                mre1.replay_source_xors(original,rows)
            # all_eq.quotient asserts every original-CNF positive equality edge
            # via the two exact original implication clauses.
            rewritten,translated_rows,proof_map,evidence=all_eq.quotient(original,rows)
            if proof_map:
                cnf=tmp/"certified-all-equality-quotient.cnf"
                mre1.write_cnf(cnf,n,rewritten,[])
                rows=translated_rows
                gating="all_certified_equivalence_classes"
            else:
                gating="no_original_positive_equality"
    xor=tmp/"source.tsv"
    mre1.write_xors(xor,rows)
    metadata=dict(gate=gating,
        source_clauses=original_count,
        input_clauses=(len(rewritten) if proof_map else original_count),
        imported_xors=len(rows),
        applied=bool(proof_map),
        eliminated_variables=len(proof_map),
        evidence=evidence,
        original_proof_edges_replayed=bool(proof_map),
        preprocessing_wall_s=round(time.perf_counter()-start,6),
        preprocessing_cpu_s=round(time.process_time()-cpu0,6))
    return cnf,xor,metadata,proof_map

def trial(case,rep,mode,binary):
    original=INPUT/case["name"]
    need(r195.digest(original)==case["sha256"],"original SHA mismatch")
    start=time.perf_counter()
    cpu0=time.process_time()
    status="TIMEOUT"
    native={}
    cpu=None
    watch=None
    model_ok=False
    child_wall=None
    metadata={}
    with tempfile.TemporaryDirectory(prefix="drnas-mre6f-") as td:
        tmp=pathlib.Path(td)
        cnf,xor,metadata,proof_map=prepare(original,mode,tmp)
        empty=tmp/"empty.tsv";empty.write_text("")
        env=os.environ.copy()
        env.update(DRNAS_TRACE_ENABLED="0",
                   DRNAS_ORIG_COUNT=str(metadata["input_clauses"]),
                   DRNAS_TAG_0="",DRNAS_TAG_1="")
        remaining=CAP-(time.perf_counter()-start)
        if remaining>0.15:
            t0=time.perf_counter()
            try:
                p=subprocess.run(
                    [str(pathlib.Path(binary).resolve()),
                     str(cnf.resolve()),str(xor.resolve()),str(empty.resolve()),
                     "source_xor_no_gauss",str(previous.seed_of(case["sha256"],rep))],
                    text=True,capture_output=True,errors="replace",timeout=remaining,
                    env=env,check=False)
            except subprocess.TimeoutExpired:p=None
            child_wall=time.perf_counter()-t0
            if p is not None:
                need(p.returncode==0,"native CMS exit/error: "+p.stderr[-950:])
                try:
                    status,model,native,tags,ledger,cpu,watch=mre5.parse_native(p.stdout)
                    need(cpu["enabled"]==0,"expected trace-off identical native backend")
                    need(ledger["original_count"]==metadata["input_clauses"],
                         "native CNF was not the certified input")
                    need(all(k["attached"]==0 for k in tags.values()),
                         "unexpected tagged clause in MRE6f")
                except RuntimeError:
                    status,model,native=r195.parsed_native(p.stdout)
                    need(status=="UNSAT" and case["expected"]=="UNSAT",
                         "early root-level UNSAT missing native telemetry")
                need(status in ("SAT","UNSAT"),"unexpected native final status")
                need(status==case["expected"],"official original verdict mismatch")
                if status=="SAT":
                    if proof_map:
                        model=all_eq.reconstruct(model,proof_map)
                    r195.verify_model(original,model)
                    model_ok=True
        elapsed=time.perf_counter()-start
        if elapsed>=CAP:
            # A verdict completed after an overrun is not scored as solved.
            status="TIMEOUT"
            model_ok=False
    out=dict(protocol=PROTO,original_sha256=case["sha256"],source=case["name"],
        source_cohort=case["cohort"],expected=case["expected"],
        official_reference_s=case["published_reference_s"],mode=mode,
        rep=rep,seed=previous.seed_of(case["sha256"],rep),
        status=status,full_wall_s=round(elapsed,6),
        par2_s=round(2*CAP if status=="TIMEOUT" else elapsed,6),
        python_cpu_s=round(time.process_time()-cpu0,6),
        native_solve_cpu_s=(cpu["process_cpu_s"] if cpu else None),
        native_solve_wall_s=(cpu["solve_wall_s"] if cpu else None),
        child_wall_s=round(child_wall,6) if child_wall is not None else None,
        native_conflicts=native.get("conflicts"),
        native_decisions=native.get("decisions"),
        native_propagations=native.get("propagations"),
        gate=metadata,
        certified_quotient_applied=bool(proof_map),
        source_original_SAT_witness_verified=model_ok,
        official_UNSAT_status_crosschecked=(status=="UNSAT"),
        independent_UNSAT_LRAT=False,
        full_cost_includes_proof_and_reconstruction=True,
        cpu_does_not_include_child_DIMACS_load=True,
        otf_gauss=False,
        same_pinned_CMS_source_sha=CMS_SOURCE_SHA,
        github_sha=os.environ.get("GITHUB_SHA","local"))
    return out

def shard(i,binary):
    need(0<=i<SHARDS,"shard outside precommitted cohort")
    frozen.verify(INPUT)
    manifest=json.loads((INPUT/"manifest.json").read_text())
    need(len(manifest["cases"])==6,"source cohort not MRE7 frozen six")
    selected=manifest["cases"][i::SHARDS]
    need(len(selected)==2,"shard workload drift")
    ROOT.mkdir(parents=True,exist_ok=True)
    done=[]
    for case in selected:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+case["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                z=trial(case,rep,mode,binary)
                done.append(z)
                (ROOT/("shard-%d.json"%i)).write_text(
                    json.dumps(done,sort_keys=True)+"\n")
                print("MRE6F_TRIAL",json.dumps(z,sort_keys=True),flush=True)
    need(len(done)==16,"incomplete shard")
    print("MRE6F_SHARD_PASS",i,len(done),flush=True)

def audit():
    frozen.verify(INPUT)
    manifest=json.loads((INPUT/"manifest.json").read_text())
    records=[]
    for i in range(SHARDS):
        file=ROOT/("shard-%d.json"%i)
        need(file.exists(),"missing shard")
        records+=json.loads(file.read_text())
    need(len(records)==6*REPS*len(MODES)==48,"expected 48 paired results")
    permitted={c["sha256"]:c for c in manifest["cases"]}
    pairing=collections.defaultdict(dict)
    for r in records:
        c=permitted.get(r["original_sha256"])
        need(c and c["name"]==r["source"] and c["cohort"]==r["source_cohort"],
             "source pairing drift")
        need(r["protocol"]==PROTO and r["same_pinned_CMS_source_sha"]==CMS_SOURCE_SHA
             and r["otf_gauss"] is False and r["full_cost_includes_proof_and_reconstruction"],
             "configuration drift")
        if r["status"]=="SAT":
            need(r["source_original_SAT_witness_verified"] and r["expected"]=="SAT",
                 "missing verified original SAT model")
        if r["status"]=="UNSAT":
            need(c["expected"]=="UNSAT" and r["official_UNSAT_status_crosschecked"],
                 "UNSAT not crosschecked")
        pair=(r["original_sha256"],r["rep"])
        need(r["mode"] not in pairing[pair],"duplicate pair")
        pairing[pair][r["mode"]]=r
    need(len(pairing)==12,"missing source-rep pair")
    for z in pairing.values():
        need(set(z)==set(MODES),"four-arm pair incomplete")
        need(len({a["seed"] for a in z.values()})==1,
             "different native solver seeds")
    bycohort={}
    for cohort in ("REUSED_known_solved_diagnostic","NEW_official_reference_medium"):
        bycohort[cohort]={}
        for mode in MODES:
            rows=[r for r in records if r["mode"]==mode and r["source_cohort"]==cohort]
            bycohort[cohort][mode]=dict(
                n=len(rows),
                solved=sum(r["status"] in ("SAT","UNSAT") for r in rows),
                timeouts=sum(r["status"]=="TIMEOUT" for r in rows),
                par2_s=round(sum(r["par2_s"] for r in rows),6),
                full_wall_s=round(sum(r["full_wall_s"] for r in rows),6),
                prep_s=round(sum(r["gate"]["preprocessing_wall_s"] for r in rows),6),
                cpu_solve_samples=sum(r["native_solve_cpu_s"] is not None for r in rows),
                solver_cpu_s=round(sum(r["native_solve_cpu_s"] or 0 for r in rows),6),
                certified_merges=sum(r["gate"]["eliminated_variables"] for r in rows))
    allmodes={}
    for mode in MODES:
        rows=[r for r in records if r["mode"]==mode]
        allmodes[mode]=dict(
            solved=sum(r["status"] in ("SAT","UNSAT") for r in rows),
            attempts=len(rows),
            par2_s=round(sum(r["par2_s"] for r in rows),6),
            prep_s=round(sum(r["gate"]["preprocessing_wall_s"] for r in rows),6),
            equality_active_sources=len({r["source"] for r in rows if r["certified_quotient_applied"]}),
            timeouts=sum(r["status"]=="TIMEOUT" for r in rows))
    per_source=[]
    for c in manifest["cases"]:
        found=[r for r in records if r["original_sha256"]==c["sha256"]]
        per_source.append(dict(source=c["name"],cohort=c["cohort"],
            status=c["expected"],external_reference_s=c["published_reference_s"],
            per_mode={m:dict(
                solved=sum(r["status"]!="TIMEOUT" for r in found if r["mode"]==m),
                par2_s=round(sum(r["par2_s"] for r in found if r["mode"]==m),6),
                gates=[r["gate"]["gate"] for r in found if r["mode"]==m],
                eliminated_variables=[r["gate"]["eliminated_variables"]
                                    for r in found if r["mode"]==m])
                for m in MODES}))
    report=dict(protocol=PROTO,sources=6,
       repeats=2,attempts=48,cap_s=CAP,
       anchors_reused=2,externally_selected_new_sources=4,
       comparison_design="same MRE7 pre-frozen 6 original SHA paired across all 4 arms and seeds",
       official_source_disjoint_new_not_exhaustively_verified=True,
       cohort_is_not_new_blind_test=False,
       entire_35s_wall_charged=True,
       all_SAT_models_checked_on_original=True,
       UNSAT_independent_LRAT=False,
       no_unsolved_CDCL_counter_claims=True,
       by_cohort=bycohort,modes=allmodes,per_source=per_source,
       no_policy_promoted_without_new_source_validation=True)
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE6F_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    all_eq.selftest()
    need(len(MODES)==4 and CAP==35.0 and REPS==2 and SHARDS==3,
         "frozen MRE6f cohort/modes/cap changed")
    a=[(-1,2),(1,-2),(-2,3),(2,-3)]
    r,_,m,st=all_eq.quotient(a)
    need(m=={2:1,3:1} and not r and st["merges"]==2,
         "all-class certified quotient failed")
    print("MRE6F_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="mre5/native")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard,a.binary)
    else:audit()
