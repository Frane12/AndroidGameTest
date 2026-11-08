#!/usr/bin/env python3
"""C8c — first accepted BVE pivots, true resolvents and SAT-preserving skip ablation.

Three frozen C8/C8b DEVELOPMENT SAT originals. Exact upstream CaDiCaL 1.7.3
commit 38e073... pristine binary controls against instrumented copy. No custom
clauses, no invalid transformation: intervention ONLY declines selected BVE
candidate IDs before trying them. Both variants independently replay SAT
witness on original SHA. Same seed behavior (CaDiCaL CLI not independent seeds).
Original C8 PAR2 is prior evidence and is not conflated with this new C8c PAR2.

BVE is interleaved with other simplifiers; the result of blocking one pivot
is a causal intervention on the pipeline but not proof one resolution clause
was individually harmful.  No blind holdout or generalization assertion.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, re, subprocess, time
import c8_bve_cdcl_trace as c8
import c7_standard_solver_bve_crosscheck as c7
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms
PROTO="DRNAS-C8C-3SHA-CAUSAL-BVE-PIVOT-SKIP-8ARMS-2REPS-25S-v1"
ROOT=pathlib.Path("c8c_out")
BIN={"plain":"c8c/bin/plain","patched":"c8c/bin/instrumented"}
MODES=("plain","instrumented_control","noelim",
       "skip_first_candidate","skip_first_8_candidates",
       "skip_first_success","skip_first_8_success",
       "skip_late_8_candidates")
REPS=2
CAP=25.0
EVENT_MAX=25000
def need(b,msg):
    if not b:raise RuntimeError("C8C_FAIL_CLOSED "+str(msg))
def sources():
    return c8.sources()
def source(i):
    ss=sources()
    need(0<=i<len(ss),"invalid frozen source")
    return ss[i]
def parse_c8c(stderr):
    events=[]
    for line in stderr.splitlines():
        if not line.startswith("C8C_"):continue
        p=line.strip().split()
        label=p[0]
        fields={}
        for item in p[1:]:
            k,sep,v=item.partition("=")
            if sep:
                try: fields[k]=int(v)
                except ValueError: fields[k]=v
        events.append(dict(kind=label,**fields))
    need(len(events)<=EVENT_MAX,"unexpected huge diagnostic: change event budget explicitly")
    return events
def run_bin(c,bin_type,opts=(),env_extra=None,verbose=False,cap=CAP):
    src=c["path"]
    need(c7.digest(src)==c["sha256"],"original SAT CNF SHA changed")
    env=os.environ.copy()
    for name in ("DRNAS_C8C_SKIP_VARS","DRNAS_C8C_TRACE"):
        env.pop(name,None)
    env.update(env_extra or {})
    cmd=[str(pathlib.Path(BIN[bin_type]).resolve()),*opts]
    if verbose:cmd+=["-v"]
    cmd.append(str(src.resolve()))
    t=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
            check=False,timeout=cap,env=env)
    except subprocess.TimeoutExpired:
        p=None
    wall=time.perf_counter()-t
    status="TIMEOUT";verified=False;stats=None;events=[]
    if p is not None:
        status,model=ref.external_parse(p)
        if status=="SAT":
            cms.verify_model(src,model);verified=True
        need(status!="UNSAT","original SAT contradiction")
        if verbose:
            stats,_=c8.parse_stats(p.stdout)
            c8.validate_stats(stats,"noelim" if "--no-elim" in opts else "default")
        events=parse_c8c(p.stderr)
    if wall>cap or status!="SAT":
        status="TIMEOUT";verified=False
    return dict(status=status,wall_s=round(wall,6),
        PAR2_s=round(wall if status=="SAT" else 2*cap,6),
        original_sat_model_verified=verified,stats=stats,
        events=events,process_finished=p is not None)
def first_phase_events(events):
    return [x for x in events
            if x["kind"]=="C8C_CANDIDATE" and x.get("round")==1]
def profiles(i):
    p=ROOT/("profile-%d.json"%i)
    need(p.is_file(),"missing trace profile")
    x=json.loads(p.read_text())
    need(x["protocol"]==PROTO and
         x["sha256"]==source(i)["sha256"],"frozen profile source mismatch")
    return x
def profile(i):
    c=source(i)
    ROOT.mkdir(exist_ok=True)
    p=run_bin(c,"plain",verbose=True)
    t=run_bin(c,"patched",env_extra={"DRNAS_C8C_TRACE":"1"},
              verbose=True)
    need(p["status"]=="SAT" and t["status"]=="SAT",
         "baseline pristine or patched trace failed original SAT")
    need(p["stats"]==t["stats"],
         "tracing changed actual CDCL counts, instrumentation not observational")
    candidates=first_phase_events(t["events"])
    need(len(candidates)>8,"initial elimination schedule unexpectedly short")
    ids=[x["idx"] for x in candidates]
    need(len(set(ids))>=16,"too few distinct candidates to compare controls")
    accepted=[]
    for x in candidates:
        if x["accepted"] and x["idx"] not in accepted:
            accepted.append(x["idx"])
    first8=list(dict.fromkeys(ids))[:8]
    last8=list(dict.fromkeys(ids))[-8:]
    need(not(set(first8)&set(last8)),
         "early and late candidate negative controls overlapped")
    choices={
       "plain":[],
       "instrumented_control":[],
       "noelim":[],
       "skip_first_candidate":first8[:1],
       "skip_first_8_candidates":first8,
       "skip_first_success":accepted[:1],
       "skip_first_8_success":accepted[:8],
       "skip_late_8_candidates":last8
    }
    match_original_stats={}
    # Old C8 reference is the APT binary.  Diagnostic may differ by build;
    # do not misattribute distro build flags to our instrumentation.
    data=dict(protocol=PROTO,source=i,gbd=c["gbd"],sha256=c["sha256"],
       upstream_tag="rel-1.7.3",upstream_commit=
           "38e073b389a877b0a0d3c91136d2443ab95fdeba",
       identical_pristine_vs_instrumented_CADICAL_stats=True,
       first_candidate_conflict=candidates[0]["conflicts"],
       first_candidate_ids=first8,
       first_accepted_ids=accepted[:16],
       total_initial_candidates=len(candidates),
       total_initial_success=sum(x["accepted"] for x in candidates),
       first_accepted_conflict=(next((x["conflicts"] for x in candidates
                                    if x["accepted"]),None)),
       first_16_candidates=candidates[:16],
       first_16_accepted=[x for x in candidates if x["accepted"]][:16],
       first_vivify_start=next((x for x in t["events"]
                                if x["kind"]=="C8C_VIVIFY_START"),None),
       first_vivify_end=next((x for x in t["events"]
                              if x["kind"]=="C8C_VIVIFY_END"),None),
       first_16_insertions=[x for x in t["events"]
           if x["kind"]=="C8C_INSERT"][:16],
       rejected_reason_counts=dict(collections.Counter(x.get("reason")
             for x in t["events"] if x["kind"]=="C8C_REJECT")),
       accepted_count=sum(x["accepted"] for x in t["events"]
             if x["kind"]=="C8C_CANDIDATE"),
       skipped_candidate_order_development_only=choices,
       full_event_count=len(t["events"]),
       original_plain_full_stats=p["stats"],
       source_benchmark_e2e_control_plain_s=p["wall_s"])
    (ROOT/("profile-%d.json"%i)).write_text(
       json.dumps(data,indent=2,sort_keys=True)+"\n")
    # All detailed raw events are separate JSON artifact (not printed as logs).
    (ROOT/("trace-%d.json"%i)).write_text(
       json.dumps(t["events"],indent=2,sort_keys=True)+"\n")
    print("C8C_PROFILE_PASS",json.dumps({k:v for k,v in data.items()
        if k in ("gbd","total_initial_candidates","total_initial_success",
                 "first_candidate_conflict","first_accepted_conflict",
                 "first_candidate_ids","first_accepted_ids",
                 "first_vivify_start","first_vivify_end",
                 "rejected_reason_counts","accepted_count","full_event_count")},
                 sort_keys=True),flush=True)
def smoke():
    ROOT.mkdir(exist_ok=True)
    small=ROOT/"smoke.cnf"
    small.write_text("p cnf 5 7\n1 2 0\n-1 2 0\n2 3 0\n-3 4 0\n4 0\n5 0\n5 2 0\n")
    for kind in ("plain","patched"):
        path=str(pathlib.Path(BIN[kind]).resolve())
        p=subprocess.run([path,"-v",str(small.resolve())],
            capture_output=True,text=True,check=False,timeout=10)
        status,model=ref.external_parse(p)
        need(status=="SAT","compiled upstream C8c SAT smoke failed")
        cms.verify_model(small,model)
        if kind=="patched":
            for env_key in ("DRNAS_C8C_TRACE","DRNAS_C8C_SKIP_VARS"):
                env=os.environ.copy()
                env[env_key]="1"
                run=subprocess.run([path,"-v",str(small.resolve())],
                    capture_output=True,text=True,env=env,timeout=10)
                status,model=ref.external_parse(run)
                need(status=="SAT","sound BVE block/trace broke SAT selftest")
                cms.verify_model(small,model)
    print("C8C_SOURCE_PATCH_COMPILED_SAT_AND_SAFE_SKIP_SMOKE_PASS",flush=True)
def bench(i):
    c=source(i)
    prof=profiles(i)
    ROOT.mkdir(exist_ok=True)
    chosen=prof["skipped_candidate_order_development_only"]
    rows=[]
    for rep in range(REPS):
        arms=list(MODES)
        seed=int(hashlib.sha256(
            (PROTO+"|"+c["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)
        import random
        random.Random(seed).shuffle(arms)
        for mode in arms:
            btype="plain" if mode in ("plain","noelim") else "patched"
            opts=["--no-elim"] if mode=="noelim" else []
            vars_=chosen[mode]
            env={"DRNAS_C8C_SKIP_VARS":",".join(map(str,vars_))}
            outcome=run_bin(c,btype,opts,env_extra=env,verbose=False)
            row=dict(protocol=PROTO,gbd=c["gbd"],sha256=c["sha256"],
                mode=mode,rep=rep,run_order_seed=seed,
                independent_seed_applied=False,
                source_original_sat=True,cap_s=CAP,
                selected_skipped_candidate_variables=vars_,
                status=outcome["status"],original_SAT_verified=
                outcome["original_sat_model_verified"],
                wall_s=outcome["wall_s"],PAR2_s=outcome["PAR2_s"],
                source_cohort="C8 selected development not blind",
                build_sha=os.getenv("GITHUB_SHA","LOCAL"))
            rows.append(row)
            (ROOT/("bench-%d.json"%i)).write_text(
                json.dumps(rows,indent=2,sort_keys=True)+"\n")
            print("C8C_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES),"partial end-to-end ablation")
    print("C8C_BENCH_SHARD_PASS",i,len(rows),flush=True)
def audit():
    result=[]
    for i,c in enumerate(sources()):
        pro=profiles(i)
        f=ROOT/("bench-%d.json"%i)
        need(f.is_file(),"incomplete C8c end-to-end benchmark")
        rows=json.loads(f.read_text())
        need(len(rows)==len(MODES)*REPS,"missing complete source matrix")
        paired=collections.defaultdict(set)
        for x in rows:
            need(x["sha256"]==c["sha256"] and x["gbd"]==c["gbd"] and
                 x["protocol"]==PROTO and x["mode"] in MODES and
                 x["rep"] in range(REPS),"source or run protocol changed")
            need(x["selected_skipped_candidate_variables"]==
                 pro["skipped_candidate_order_development_only"][x["mode"]],
                 "selected variable intervention changed")
            need(x["status"] in ("SAT","TIMEOUT"),"bad result")
            need(x["status"]!="SAT" or x["original_SAT_verified"],
                 "invalid original SHA SAT proof")
            need(x["status"]!="TIMEOUT" or x["PAR2_s"]==CAP*2,
                 "missing standard PAR2 cap penalty")
            need(x["mode"] not in paired[x["rep"]],"duplicate matched mode")
            paired[x["rep"]].add(x["mode"])
        need(len(paired)==REPS and all(x==set(MODES) for x in paired.values()),
             "pairing incomplete")
        bymode={}
        for mode in MODES:
            a=[x for x in rows if x["mode"]==mode]
            bymode[mode]=dict(solved=sum(x["status"]=="SAT" for x in a),
                 PAR2_s=round(sum(x["PAR2_s"] for x in a),6),
                 wall_s=round(sum(x["wall_s"] for x in a),6),
                 source_original_SAT_models_checked=True)
        baseline=bymode["plain"]["PAR2_s"]
        for mode in bymode:
            bymode[mode]["speedup_vs_plain_x"]=round(
                baseline/bymode[mode]["PAR2_s"],6)
        result.append(dict(gbd=c["gbd"],sha256=c["sha256"],
                           profile=pro,scores=bymode))
    output=dict(protocol=PROTO,cohort="3 posthoc C8 SAT development SHA, not blind",
        upstream_tag="rel-1.7.3",pinned_upstream_sha=
           "38e073b389a877b0a0d3c91136d2443ab95fdeba",
        source_count=3,real_E2E_trials=3*REPS*len(MODES),
        true_original_SAT_witnesses_replayed=True,
        independent_solver_seeds=False,independent_UNSAT_LRAT=False,
        cap_s=CAP,reps=REPS,modes=list(MODES),
        instrumentation_control_binary_telemetry_parity=True,
        source_pivot_ablation_is_sound_but_POSTHOC=True,
        no_auto_promotion=True,
        per_source=result)
    (ROOT/"report.json").write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    print("C8C_FINAL",json.dumps({k:v for k,v in output.items() if k!="per_source"},
                                 sort_keys=True),flush=True)
    for x in result:
        print("C8C_CASE",json.dumps(dict(gbd=x["gbd"],
           first_candidate_conflict=x["profile"]["first_candidate_conflict"],
           first_accepted_conflict=x["profile"]["first_accepted_conflict"],
           first_vivify_start=x["profile"]["first_vivify_start"],
           first_accepted_ids=x["profile"]["first_accepted_ids"],
           rejected_reason_counts=x["profile"]["rejected_reason_counts"],
           scores=x["scores"]),sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("verify","smoke","profile","bench","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="verify":
        print("C8C_SOURCE_SHA_PINNED",len(sources()),flush=True)
    elif a.action=="smoke":smoke()
    elif a.action=="profile":profile(a.shard)
    elif a.action=="bench":bench(a.shard)
    else:audit()
