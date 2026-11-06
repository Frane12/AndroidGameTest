#!/usr/bin/env python3
"""DRNAS R173 source-structural GF2 selector, precommitted before timing.

Two independently provided frozen source sets: 25 R155 original CNFs (seen),
20 R171 easy (12 public SATLIB, 8 explicit synthetic), 45 * 4 * 2 = 360
paired attempts. R172 native executable is reused byte-for-byte.
The gate NEVER reads case IDs, family labels, SAT status, solver telemetry,
previous timings, or frozen manifest metadata to make its selection.
Only exact source CNF clause shapes; when chosen, uses same source-certified
R157 extraction and R172 utility-budget. If abstaining, runs clean CDCL
with screen-only time charged. All original SAT witnesses checked.
Results are development-only; no blind benchmark, no UNSAT LRAT.
"""
import argparse,collections,hashlib,json,os,pathlib,random,statistics,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r165_component_benchmark as base

ROOT=pathlib.Path("r173")
PROTO="DRNAS-R173-STRUCTURAL-GF2-SELECTOR-PRECOMMIT-20261106-v1"
MODES=("clean","direct_two_way_newonly","direct_two_way_budget","select_budget")
REPS=2
SHARDS=5
CAP={"hard":8.0,"easy":3.0}
# Conservative structural minimum, frozen before any R173 timing.
MIN_CERTIFIABLE_LINKED_ROWS=32
MIN_OVERLAP_ROWS=16
EXPECTED_R172_BINARY_COMMIT="507540d283d5a4dce356d20b15d4aa31861c8bbf"

def need(ok,why):
    if not ok:raise RuntimeError("R173_FAIL_CLOSED "+str(why))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,dat):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(dat,sort_keys=True,indent=2)+"\n")
def frozen(tier):
    return ROOT/tier/"frozen"
def all_cases():
    hard=base.rd(frozen("hard")/"manifest.json")["cases"]
    easy=base.rd(frozen("easy")/"manifest.json")["cases"]
    need(len(hard)==25 and len(easy)==20,"expected 25 original, 20 easy")
    cases=[dict(c,tier=tier) for tier,arr in (("hard",hard),("easy",easy)) for c in arr]
    need(len({c["sha256"] for c in cases})==45,"duplicate SHA across source sets")
    for c in cases:
        need(sha(frozen(c["tier"])/(c["id"]+".cnf"))==c["sha256"],
             "original source checksum mismatch "+c["id"])
    return sorted(cases,key=lambda c:(c["tier"],c["sha256"]))
def screen(source):
    """Linear-ish source-only exact XOR group screening; no solver calls.

    Finds fully encoded parity groups, excludes explicit units, tests
    residual CNF connectivity, and whether multiple rows share variables.
    This step is deliberately independent of the R157 selected proof.
    """
    begin=time.perf_counter()
    n,clauses=base.dimacs(source)
    groups=collections.defaultdict(set)
    units=set()
    clause_info=[]
    for cl in clauses:
        if len(cl)==1:units.add(abs(cl[0]))
        if 2<=len(cl)<=6 and len({abs(x) for x in cl})==len(cl):
            ordered=sorted(cl,key=abs)
            vs=tuple(abs(v) for v in ordered)
            mask=sum(1<<i for i,lit in enumerate(ordered) if lit<0)
            groups[vs].add(mask)
            clause_info.append((cl,(vs,mask)))
        else:clause_info.append((cl,None))
    complete=[];covered=set()
    for vs,masks in groups.items():
        k=len(vs)
        for parity,rhs in ((0,1),(1,0)):
            required={mask for mask in range(1<<k) if mask.bit_count()%2==parity}
            if required.issubset(masks):
                rem=tuple(v for v in vs if v not in units)
                if len(rem)>=2:complete.append(rem)
                for mask in required:covered.add((vs,mask))
    residual=set()
    for cl,info in clause_info:
        if len(cl)>1 and (info is None or info not in covered):
            residual.update(abs(lit) for lit in cl)
    linked=[vs for vs in complete if any(v in residual for v in vs)]
    incidence=collections.Counter(v for vs in linked for v in vs)
    overlapping=sum(any(incidence[v]>1 for v in vs) for vs in linked)
    decision=(len(linked)>=MIN_CERTIFIABLE_LINKED_ROWS and
              overlapping>=MIN_OVERLAP_ROWS)
    duration=time.perf_counter()-begin
    return dict(selected=decision,certifiable_linked_rows=len(linked),
         overlapping_rows=overlapping,full_source_xor_rows=len(complete),
         screen_s=duration,variables=n,clauses=len(clauses))
def trial(c,mode,rep,prep,binary):
    src=frozen(c["tier"])/(c["id"]+".cnf")
    proof=ROOT/("full-"+c["id"]+".tsv")
    need(sha(src)==c["sha256"] and sha(proof)==prep["full_tsv_sha"],
        "original SHA / proof SHA drift")
    gate=screen(src) if mode=="select_budget" else None
    charge=(gate["screen_s"]+(prep["preprocessing_s"] if gate["selected"] else 0.0)
        if gate else (0.0 if mode=="clean" else prep["preprocessing_s"]))
    execute=("direct_two_way_budget" if gate and gate["selected"] else
            "clean" if gate else mode)
    cap=CAP[c["tier"]]
    need(charge+0.5<cap,"selector/source preparation over cap")
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),execute,str(src.resolve()),
            str(proof.resolve()),str(cap-charge)],stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,timeout=cap+12)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("R173_NATIVE_SAFETY_TIMEOUT "+c["id"]) from exc
    wall=time.perf_counter()-start+charge
    need(p.returncode in (0,10,20),"R173 native failed "+
         str(p.returncode)+" "+p.stderr[-600:].decode(errors="replace"))
    out,native,stats,source_rows,derived=base.parse_native(p.stdout,execute)
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    need(p.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],
         "native exit mismatch")
    need(source_rows==(0 if execute=="clean" else prep["full_rows"]),
         "wrong source-certified row count")
    need(abs(float(native["solver_s"])-(wall-charge))<0.6,
         "native timer mismatch")
    if status=="SAT":
        need(native.get("source_sat_witness_checked")=="1","SAT witness unchecked")
        base.sat_check(src,out)
    if c["tier"]=="easy":
        need(status==c["expected"],"easy known SAT/UNSAT mismatch")
    used=int(native["two_way_used_reasons"])
    proposals=int(native["two_way_proposals"])
    sweeps=int(native["two_way_sweeps"])
    need(used<=proposals,"used reason unproved by GF2 proposal")
    if execute=="clean":
        need(used==proposals==sweeps==0,"inactive selector emitted GF2")
    if gate:
        need(gate["selected"]==(execute=="direct_two_way_budget"),
             "gate/solver routing mismatch")
    need(stats.get("conflicts") is not None and stats.get("decisions") is not None,
         "missing native CaDiCaL counters")
    return dict(protocol=PROTO,id=c["id"],source_sha256=c["sha256"],
       tier=c["tier"],cohort=c["cohort"],mode=mode,native_mode=execute,
       repeat=rep,cap_s=cap,status=status,elapsed_s=round(wall,6),
       solver_s=float(native["solver_s"]),charged_preprocess_s=round(charge,6),
       par2_s=round(2*cap if status=="TIMEOUT" else min(cap,wall),6),
       screen=gate,source_rows=source_rows,derived_rows=derived,
       used_reasons=used,proposals=proposals,sweeps=sweeps,
       GF2_processing_ns=int(native["two_way_ns"]),
       cdcl_conflicts=int(stats["conflicts"]),cdcl_decisions=int(stats["decisions"]),
       proof=("SOURCE_SAT_MODEL_CHECKED" if status=="SAT" else
         "UNSAT_NATIVE_NO_INDEPENDENT_LRAT" if status=="UNSAT" else "TIMEOUT"))
def shard(index,binary):
    need(0<=index<SHARDS and binary.is_file(),"bad shard/binary")
    pin=base.rd(ROOT/"bin/build-pin.json")
    need(sha(binary)==pin["binary_sha256"],"reuse exact R172 binary SHA")
    need(pin["source_commit"]==EXPECTED_R172_BINARY_COMMIT,
         "wrong source SHA for pinned R172 binary")
    if hasattr(os,"sched_getaffinity"):
        cpus=os.sched_getaffinity(0)
        if cpus:os.sched_setaffinity(0,{min(cpus)})
    arr=[]
    for j,c in enumerate(all_cases()):
        if j%SHARDS!=index:continue
        base.FROZEN=frozen(c["tier"])
        base.ROOT=ROOT
        prep=base.prepare(c)
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                z=trial(c,mode,rep,prep,binary)
                arr.append(z)
                save(ROOT/("shard-%d.json"%index),arr)
                print("R173_TRIAL",json.dumps({k:z[k] for k in (
                     "tier","id","mode","native_mode","repeat","status",
                     "elapsed_s","used_reasons","sweeps")},sort_keys=True),flush=True)
    need(len(arr)==len(all_cases()[index::SHARDS])*len(MODES)*REPS,
         "incomplete R173 shard")
    print("R173_SHARD_PASS",index,len(arr),flush=True)
def audit():
    cases=all_cases()
    rows=[]
    for i in range(SHARDS):
        p=ROOT/("shard-%d.json"%i)
        need(p.is_file(),"missing shard artifact")
        arr=base.rd(p)
        need(len(arr)==len(cases[i::SHARDS])*len(MODES)*REPS,
             "wrong shard cardinality")
        rows.extend(arr)
    need(len(rows)==45*len(MODES)*REPS==360,"expected 360 attempts")
    need(len({(r["source_sha256"],r["repeat"],r["mode"]) for r in rows})==360,
         "duplicate paired attempts")
    for c in cases:
        base.ROOT=ROOT;base.FROZEN=frozen(c["tier"])
        prep=base.rd(ROOT/("prep-"+c["id"]+".json"))
        cert=base.rd(ROOT/("cert-"+c["id"]+".json"))
        base.independent_cert(c,cert)
        need(prep["source_sha256"]==c["sha256"],"source proof provenance")
        need(sha(ROOT/("full-"+c["id"]+".tsv"))==prep["full_tsv_sha"],
             "source-proof TSV drift")
    summary={}
    for tier in ("all","hard","easy"):
        subset=[r for r in rows if tier=="all" or r["tier"]==tier]
        summary[tier]={}
        for mode in MODES:
            a=[r for r in subset if r["mode"]==mode]
            summary[tier][mode]=dict(trials=len(a),solved=sum(r["status"]!="TIMEOUT" for r in a),
                SAT=sum(r["status"]=="SAT" for r in a),UNSAT=sum(r["status"]=="UNSAT" for r in a),
                PAR2_s=round(sum(r["par2_s"] for r in a),6),
                end_to_end_wall_s=round(sum(r["elapsed_s"] for r in a),6),
                median_process_ms=round(1000*statistics.median(r["elapsed_s"] for r in a),4),
                total_GF2_ms=round(sum(r["GF2_processing_ns"] for r in a)/1e6,5),
                sweeps=sum(r["sweeps"] for r in a),
                used_reasons=sum(r["used_reasons"] for r in a),
                selected=sum(bool(r["screen"] and r["screen"]["selected"]) for r in a),
                screen_ms=round(1000*sum(r["screen"]["screen_s"] for r in a if r["screen"]),4),
                cdcl_conflicts=sum(r["cdcl_conflicts"] for r in a))
    missed=[];paired=[]
    for c in cases:
        for rep in range(REPS):
            z={r["mode"]:r for r in rows if r["source_sha256"]==c["sha256"]
               and r["repeat"]==rep}
            need(set(z)==set(MODES),"paired missing solver arm")
            solved={r["status"] for r in z.values() if r["status"]!="TIMEOUT"}
            need(len(solved)<=1,"contradictory SAT vs UNSAT answer")
            g=z["select_budget"];b=z["direct_two_way_budget"]
            need(g["screen"] is not None,"selector decision missing")
            need((g["native_mode"]=="direct_two_way_budget")==g["screen"]["selected"],
                 "incorrect source-only routing")
            if b["used_reasons"]>g["used_reasons"]:
                missed.append(dict(id=c["id"],repeat=rep,
                    budget_used=b["used_reasons"],selected_used=g["used_reasons"]))
            paired.append(dict(id=c["id"],tier=c["tier"],repeat=rep,
                selected=g["screen"]["selected"],
                linked_rows=g["screen"]["certifiable_linked_rows"],
                overlap_rows=g["screen"]["overlapping_rows"],
                clean_status=z["clean"]["status"],budget_status=b["status"],
                selected_status=g["status"],budget_GF2_ns=b["GF2_processing_ns"],
                selected_GF2_ns=g["GF2_processing_ns"],
                budget_reason=b["used_reasons"],selected_reason=g["used_reasons"],
                solved_speed_ratio=(round(z["clean"]["elapsed_s"]/g["elapsed_s"],5)
                    if z["clean"]["status"]!="TIMEOUT" and g["status"]!="TIMEOUT" else None)))
    report=dict(protocol=PROTO,status="R173_STRUCTURAL_SELECTOR_RESEARCH_AUDIT_PASS",
        original_hard_sources=25,original_public_satlib=12,synthetic_controls=8,
        attempts=360,repeats=REPS,cap_by_tier=CAP,
        selector_rules=dict(min_certifiable_linked_rows=MIN_CERTIFIABLE_LINKED_ROWS,
                            min_overlap_rows=MIN_OVERLAP_ROWS,
                            uses_case_identity=False,uses_prior_results=False,
                            source_only_precondition=True,
                            active_native_mode="direct_two_way_budget",
                            inactive_native_mode="clean"),
        R172_binary_source_pin=base.rd(ROOT/"bin/build-pin.json"),
        source_sha_verified=True,certified_Gf2_source_independent_replay=True,
        SAT_models_independent_clause_check=True,independent_UNSAT_LRAT=False,
        aggregate=summary,missed_Gf2_reason_cases=missed,
        all_budget_GF2_reasons_preserved=(len(missed)==0),
        paired=paired,raw=rows,
        caveats=["25 hard CNFs previously seen; 12 SATLIB public examples and 8 synthetic; NOT blind.",
                "A structural selector cannot promise not to miss useful GF2 on future unseen CNFs.",
                "Preprocessing measured and charged per arm; clean baseline incurs none.",
                "Hard timeouts cannot be used to infer real solve-time speedups.",
                "Budget and selector reuse exact R172 native binary without code changes.",
                "Small SATLIB instances may be dominated by process startup and screening overhead.",
                "Native UNSAT without independent LRAT/FRAT proof."])
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R173 structural GF2 selector — 360 paired original/synthetic attempts\n\n")
        f.write("**Research only, not blind.** 25 reused R155 CNFs, 12 public SATLIB, 8 synthetic.\n\n")
        for tier,group in summary.items():
            f.write("## "+tier+"\n\n")
            f.write("| Mode | Solved | PAR2 s | Wall s | GF2 ms | Sweeps | Used reasons | Activated |\n")
            f.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
            for mode,d in group.items():
                f.write(f'| {mode} | {d["solved"]}/{d["trials"]} | {d["PAR2_s"]:.3f} | {d["end_to_end_wall_s"]:.3f} | {d["total_GF2_ms"]:.3f} | {d["sweeps"]} | {d["used_reasons"]} | {d["selected"]} |\n')
            f.write("\n")
        f.write("GF2 reason preservation against always-on budget: "+
                ("PASS" if not missed else "FAIL — see report")+".\n")
    print("R173_FINAL",json.dumps(dict(status=report["status"],attempts=360,
       summary=summary,missed_GF2_reason_cases=missed),sort_keys=True),flush=True)
    # Fail-closed on known useful GF2 reasons sacrificed by source selector.
    need(not missed,"selector suppressed a proven consumed GF2 reason")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r173/bin/r172-native")
    args=p.parse_args()
    shard(args.shard,pathlib.Path(args.binary)) if args.action=="shard" else audit()
