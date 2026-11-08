#!/usr/bin/env python3
"""DRNAS MRE6i: proof-safe sampled XOR gate vs in-process GF2.

Eight frozen source SHAs: 4 new official SAT2026 chosen by external
CaDiCaL3 reference time ONLY, 2 reused known diagnostic originals,
and 2 fresh deterministic planted-SAT XOR/CNF mechanistic controls.
Not an exhaustively verified historical blind holdout. Every trial
charges parse+pretest+proof+rewrite+CMS solve+SAT witness verification
inside 35s full wall. Signed substitutions require independent original
CNF proof replay and full SAT witness reconstruction. No UNSAT LRAT.
"""
from __future__ import annotations
import argparse,collections,json,os,pathlib,random,subprocess,sys,tempfile,time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195
import mre1_cross_representation as mre1
import mre5_cpu_watch_cost as mre5
import mre6d_all_equalities as all_eq
import mre6g_proof_graph as graph
import mre6h_fast_gf2 as fast
import mre6i_source_freeze as frozen
import mre7_medium_pilot as previous

PROTO="DRNAS-MRE6I-8SHA-4FRESH2026-2KNOWN-2SYNTH-5ARM-2REP-35S-v1"
ROOT=pathlib.Path("mre6i")
INPUT=pathlib.Path("mre6i_sources")
CAP=35.0
REPS=2
SHARDS=4
MODES=("native_no_xor","source_xor","fast_gf2_no_xor","mre6i_gate_no_xor","mre6i_gate_with_xor")
MAX_PREP_CLAUSES=35000
CMS_SOURCE_SHA="3b709118fd08eb1d15f25e0e239dbc596f967b60"
GRAPH_BUDGET_S=.42
GF2_CHILD_HARD_WALL_S=1.45
GF2_MIN_ROWS=2
GF2_MIN_CLAUSES=200
GATE_SAMPLE_CLAUSES=6000

def need(cond,reason):
    if not cond:raise RuntimeError("MRE6I_FAIL_CLOSED "+str(reason))

def cheap_xor_structure_gate(original,limit=GATE_SAMPLE_CLAUSES):
    """Cheap, conservative *sampled* pretest for complete parity CNF blocks.

    A width-k XOR needs 2**(k-1) clauses sharing the same absolute
    variable set. Sample only the first k clauses to bound cost, and
    abstain (never rewrite) if no candidate is observed.
    This can miss later source XORs. Report that limitation honestly.
    No candidate is ever treated as proof; source extraction/replay
    still mandatory.
    """
    start=time.perf_counter()
    observed={}
    scanned=0
    for c in original[:limit]:
        scanned+=1
        w=len(c)
        if not (2<=w<=6):continue
        # Distinct absolute variables are required for XOR encoding.
        k=tuple(sorted(abs(v) for v in c))
        if len(set(k))!=w:continue
        n=observed.get(k,0)+1
        if n>=(1<<(w-1)):
            return True,dict(status="sampled_candidate_only_not_proof",
                scanned=scanned,sample_limit=limit,
                candidate_width=w,elapsed_s=round(time.perf_counter()-start,6),
                possible_false_negative_outside_sample=True)
        observed[k]=n
    return False,dict(status="no_sampled_complete_parity_candidate",
          scanned=scanned,sample_limit=limit,
          elapsed_s=round(time.perf_counter()-start,6),
          possible_false_negative_outside_sample=True)

def prepare(source,mode,tmp):
    """CPU-budgeted proof-only pre-solve, fail-closed if too expensive."""
    start=time.perf_counter()
    cpu0=time.process_time()
    need(mode in MODES,"unknown arm")
    n,original=exact.parse_dimacs(source)
    count=len(original)
    rows=[];mapping={};cnf=pathlib.Path(source)
    gating="native"
    evidence=dict(pairs=0,merges=0,classes=0,replaced_occurrences=0)
    graph_stats={}
    probe=dict(eligible=False,attempted=False,status="not_needed",
               hard_wall_budget_s=GF2_CHILD_HARD_WALL_S)
    if mode!="native_no_xor":
        if count>MAX_PREP_CLAUSES:
            gating="early_size_abstain"
        elif mode=="source_xor":
            rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
            mre1.replay_source_xors(original,rows)
            gating="verified_source_xor" if rows else "no_verified_source_xor"
        elif mode in ("fast_gf2_no_xor","mre6i_gate_no_xor","mre6i_gate_with_xor"):
            uses_gate=mode.startswith("mre6i_gate_")
            gate_ok=True
            if uses_gate:
                gate_ok,screen=cheap_xor_structure_gate(original)
                probe["screen"]=screen
                probe["screened_candidate"]=gate_ok
            rows=[]
            if gate_ok:
                rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
                mre1.replay_source_xors(original,rows)
            eligible=(len(rows)>=GF2_MIN_ROWS and count>=GF2_MIN_CLAUSES)
            probe["eligible"]=eligible
            probe["method"]="MRE6I_original_fast_GF2" if not uses_gate \
                 else "MRE6I_cheap_sample_gate_then_independent_GF2_proof"
            if eligible:
                probe["attempted"]=True
                mapping,eqproofs,info=fast.find_certified_mapping(
                    original,rows,budget_s=.30)
                probe.update(info)
                probe["derived_binary"]=len(eqproofs)
                probe["status"]=info.get("status","unavailable")
                graph_stats=info.get("graph",{})
            else:
                probe["status"]="no_source_row_or_structural_gate_abstain"
            if mapping:
                # Mathematical substitution is certified by original CNF
                # even when optional source XOR imports are omitted.
                imported=rows if mode=="mre6i_gate_with_xor" else []
                rewritten,translated,evidence=graph.quotient(
                    original,imported,mapping)
                cnf=tmp/"mre6i-certified-signed-quotient.cnf"
                mre1.write_cnf(cnf,n,rewritten,[])
                rows=translated
                gating="certified_GF2_signed_SCC_quotient"
            else:
                if mode!="mre6i_gate_with_xor":rows=[]
                gating="sampled_XOR_gate_abstain" if uses_gate and not gate_ok else \
                       "no_certified_GF2_equivalence"
        else:
            # Stage 1: implication SCC from ORIGINAL CNF only. All edges are
            # supported by actual original binary clauses.
            try:
                mapping,graph_stats=graph.discover(original,budget_s=GRAPH_BUDGET_S)
            except graph.Abstain as exc:
                mapping={}
                graph_stats=dict(status="abstain",why=str(exc))
            is_gf2=mode=="graph_scc_gf2"
            if is_gf2:
                # Optional imported XOR rows are mathematically replayed
                # against ORIGINAL CNF; they are part of the mode's full cost.
                rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
                mre1.replay_source_xors(original,rows)
                eligible=(len(rows)>=GF2_MIN_ROWS and
                          count>=GF2_MIN_CLAUSES and not mapping)
                probe["eligible"]=eligible
                if eligible:
                    probe["attempted"]=True
                    childfile=tmp/"certified-mf2-probe.json"
                    childcmd=[sys.executable,"research/mre6g_gf2_probe.py",
                              str(pathlib.Path(source).resolve()),
                              str(childfile.resolve()),"--inner-budget",".4"]
                    t=time.perf_counter()
                    try:
                        child=subprocess.run(childcmd,text=True,capture_output=True,
                           timeout=GF2_CHILD_HARD_WALL_S,check=False)
                    except subprocess.TimeoutExpired:child=None
                    probe["wall_s"]=round(time.perf_counter()-t,6)
                    if child is None:
                        probe["status"]="hard_wall_timeout_abstain"
                    elif child.returncode!=0:
                        probe["status"]="nonzero_exit_abstain"
                        probe["error"]=child.stderr[-240:]
                    elif not childfile.exists():
                        probe["status"]="missing_certificate_abstain"
                    else:
                        obj=json.loads(childfile.read_text())
                        need(obj["original_clause_count"]==count and
                             obj["original_vars"]==n,
                             "MRE1 child proof original source mismatch")
                        need(obj["source_rows"]==json.loads(
                            json.dumps(rows)),
                             "MRE1 child/source XOR rows changed")
                        # JSON roundtrip creates lists; MRE1 proof replay
                        # expects tuples in GF2 sources/rows. Canonicalize
                        # for the independent PARENT proof replay.
                        proof_rows=[(tuple(v),int(rhs))
                                    for v,rhs in obj["source_rows"]]
                        proofs=obj["proofs"]
                        for p in proofs:
                            p["clause"]=tuple(p["clause"])
                            if p["kind"]=="resolution":
                                p["left"]=tuple(p["left"])
                                p["right"]=tuple(p["right"])
                            else:
                                p["origins"]=[
                                    ("source",tuple(e[1]),e[2]) if e[0]=="source"
                                     else ("unit",e[1])
                                    for e in p["origins"]]
                        need(mre1.verify_proofs(original,proof_rows,proofs),
                             "parent independent GF2/resolution replay failed")
                        probe["proofs_replayed"]=len(proofs)
                        probe["derived_binary"]=sum(len(p["clause"])==2
                                                     for p in proofs)
                        probe["status"]="verified_proof_rows"
                        try:
                            extended,extra=graph.discover(
                                original,proof_rows,proofs,
                                budget_s=max(.55,GRAPH_BUDGET_S))
                        except graph.Abstain as exc:
                            extended={}
                            extra=dict(status="abstain",why=str(exc))
                        if extended:
                            mapping,graph_stats=extended,extra
            if mapping:
                rewritten,translated,evidence=graph.quotient(
                    original,rows,mapping)
                cnf=tmp/"certified-signed-SCC-quotient.cnf"
                mre1.write_cnf(cnf,n,rewritten,[])
                rows=translated
                gating="certified_signed_SCC_quotient"
            else:
                gating="no_proven_SCC_equivalence"
                if graph_stats.get("status")=="abstain":
                    gating="SCC_budget_abstain"
    xor=tmp/"source.tsv"
    mre1.write_xors(xor,rows)
    metadata=dict(gate=gating,
        source_clauses=count,
        input_clauses=(len(rewritten) if mapping else count),
        imported_xors=len(rows),
        applied=bool(mapping),
        eliminated_variables=len(mapping),
        evidence=evidence,
        graph=graph_stats,
        gf2_probe=probe,
        original_proof_edges_replayed=bool(mapping),
        preprocessing_wall_s=round(time.perf_counter()-start,6),
        preprocessing_cpu_s=round(time.process_time()-cpu0,6))
    return cnf,xor,metadata,mapping

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
    with tempfile.TemporaryDirectory(prefix="drnas-mre6i-") as td:
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
                         "unexpected tagged clause in MRE6i")
                except RuntimeError:
                    status,model,native=r195.parsed_native(p.stdout)
                    need(status=="UNSAT" and case["expected"]=="UNSAT",
                         "early root-level UNSAT missing native telemetry")
                need(status in ("SAT","UNSAT"),"unexpected native final status")
                need(status==case["expected"],"official original verdict mismatch")
                if status=="SAT":
                    if proof_map:
                        model=graph.reconstruct(model,proof_map)
                    r195.verify_model(original,model)
                    model_ok=True
        elapsed=time.perf_counter()-start
        if elapsed>=CAP:
            # A verdict completed after an overrun is not scored as solved.
            status="TIMEOUT"
            model_ok=False
    out=dict(protocol=PROTO,original_sha256=case["sha256"],source=case["name"],
        source_cohort=case["cohort"],expected=case["expected"],
        official_reference_s=case.get("official_reference_s"),mode=mode,
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
    frozen.verify()
    manifest=json.loads((INPUT/"manifest.json").read_text())
    need(len(manifest["cases"])==8,"source cohort not frozen MRE6i eight")
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
                print("MRE6I_TRIAL",json.dumps(z,sort_keys=True),flush=True)
    need(len(done)==20,"incomplete shard")
    print("MRE6I_SHARD_PASS",i,len(done),flush=True)

def audit():
    frozen.verify()
    manifest=json.loads((INPUT/"manifest.json").read_text())
    records=[]
    for i in range(SHARDS):
        file=ROOT/("shard-%d.json"%i)
        need(file.exists(),"missing shard")
        records+=json.loads(file.read_text())
    need(len(records)==8*REPS*len(MODES)==80,"expected 80 paired results")
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
    need(len(pairing)==16,"missing source-rep pair")
    for z in pairing.values():
        need(set(z)==set(MODES),"five-arm pair incomplete")
        need(len({a["seed"] for a in z.values()})==1,
             "different native solver seeds")
    bycohort={}
    for cohort in ("REUSED_known_solved_diagnostic","NEW_official_reference_medium","NEW_synthetic_XOR_controls"):
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
            status=c["expected"],external_reference_s=c.get("official_reference_s"),
            per_mode={m:dict(
                solved=sum(r["status"]!="TIMEOUT" for r in found if r["mode"]==m),
                par2_s=round(sum(r["par2_s"] for r in found if r["mode"]==m),6),
                gates=[r["gate"]["gate"] for r in found if r["mode"]==m],
                eliminated_variables=[r["gate"]["eliminated_variables"]
                                    for r in found if r["mode"]==m])
                for m in MODES}))
    report=dict(protocol=PROTO,sources=6,
       repeats=2,attempts=80,cap_s=CAP,
       anchors_reused=2,externally_selected_new_sources=4,new_synthetic_controls=2,
       comparison_design="same MRE6i pre-frozen 8 original SHA (4 new official, 2 old, 2 new synthetic) paired across five arms",
       official_source_disjoint_new_not_exhaustively_verified=True,
       cohort_is_not_new_blind_test=True,
       entire_35s_wall_charged=True,
       all_SAT_models_checked_on_original=True,
       UNSAT_independent_LRAT=False,
       no_unsolved_CDCL_counter_claims=True,
       by_cohort=bycohort,modes=allmodes,per_source=per_source,
       no_policy_promoted_without_new_source_validation=True)
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE6I_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    frozen.selftest()
    all_eq.selftest()
    graph.selftest()
    fast.selftest()
    gate_pos,meta=cheap_xor_structure_gate([(-1,2,3),(-1,2,-3),(1,-2,3),(1,-2,-3)])
    need(gate_pos and meta["candidate_width"]==3,"positive structural sample gate failed")
    no,meta=cheap_xor_structure_gate([(-1,2,3),(-4,5,6),(7,8,9)])
    need(not no,"false positive on distinct random triples")
    need(len(MODES)==5 and CAP==35.0 and REPS==2 and SHARDS==4,
         "frozen MRE6i cohort/modes/cap changed")
    a=[(-1,2),(1,-2),(-2,3),(2,-3)]
    r,_,m,st=all_eq.quotient(a)
    need(m=={2:1,3:1} and not r and st["merges"]==2,
         "all-class certified quotient failed")
    print("MRE6I_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="mre5/native")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard,a.binary)
    else:audit()
