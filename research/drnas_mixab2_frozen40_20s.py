#!/usr/bin/env python3
"""DRNAS MIXAB2: source-frozen original CNF 12 SEARCH5 + 12 SEARCH6 + 16 EQUIV9; one CPU.
A/B exact GF2 1.5s scanner versus 120ms bounded scanner; 20s CMS17/Kissat4
untouched baselines and routed variants; original SAT witness and original CNF
algebraic GF2 proof independently verified. Backend UNSAT requires reference
agreement for PAR2; no LRAT and no globally-blind claims.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,shutil,subprocess,tempfile,time
import drnas_gf2_proof_first_s1 as gf
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_binary_scc2_e2e as s2

ROOT=pathlib.Path("mre_mixab2")
SOURCE=e9.SOURCE
SEARCH6=pathlib.Path("mre_search6")
SEARCH5=pathlib.Path("mre_search5")
CMS=pathlib.Path("mre_equiv12/bin/cryptominisat5")
PROTO="DRNAS-MIXAB2-40FROZEN-7ARM-BUDGETED-GF2-CMS17-KISSAT4-1CPU-20S-v1"
ARMS=("kissat_plain","cms_plain","gf2_full_kissat","gf2_budget_kissat",
      "combo_full","combo_budget","combo_budget_placebo")
N=40
REPS=2
SHARDS=10
CAP=20.0
EXPECTED=N*len(ARMS)*REPS
XOR_ROUTE_MIN=16
# Cheap source geometry gate; avoid expensive scanning on very large inputs.
GATE_MAX_CLAUSES=65000
GATE_MAX_BYTES=6*1024*1024

def need(x,s):
    if not x:raise RuntimeError("MIXAB2_FAIL_CLOSED "+str(s))
def sha(p):return e9.digest(p)
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")

def roster():
    a=read(SEARCH5/"manifest.json")["original_cases"]
    b=read(SEARCH6/"manifest.json")["original_SHA_sources"]
    c=read(e9.ROOT/"manifest.json")["cases"]
    need(len(a)==12 and len(b)==12 and len(c)==16,
         "frozen SEARCH5+SEARCH6+EQUIV9 roster drift")
    cases=([dict(x,source_cohort="search5") for x in a]
          +[dict(x,source_cohort="search6") for x in b]
          +[dict(x,source_cohort="equiv9") for x in c])
    need(len(cases)==N and len({x["sha256"] for x in cases})==N
         and len({x["gbd"] for x in cases})==N,
         "frozen MIX40 overlapping or duplicate original SHA/GBD")
    return sorted(cases,key=lambda x:x["sha256"])

def source(c):
    p=SOURCE/c["filename"]
    need(sha(p)==c["sha256"],"original SHA differs from frozen source cohort")
    return p

def signature():
    return dict(code_sha=sha(__file__),cpp_source_sha=sha("research/drnas_gf2_proof_first_s1.cpp"),
         scanner_binary_sha=sha(gf.BIN),native_bin_sha=sha(e9.NATIVE),
         kissat_bin_sha=sha(e9.KISSAT),cms_bin_sha=sha(CMS),
         search5_manifest_sha=sha(SEARCH5/"manifest.json"),
         search6_manifest_sha=sha(SEARCH6/"manifest.json"),
         equiv9_manifest_sha=sha(e9.ROOT/"manifest.json"),
         provenance="Pre-frozen SEARCH5 12 SEARCH6 12 EQUIV9 16 sources; dedupe fail-closed; not blind; no outcome-based reselection")

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    SOURCE.mkdir(parents=True,exist_ok=True)
    need(all(p.is_file() for p in (gf.BIN,e9.NATIVE,e9.KISSAT,CMS,SEARCH5/"manifest.json",SEARCH6/"manifest.json")),
         "frozen binaries or manifest missing")
    cs=roster()
    for c in cs:
        if c["source_cohort"] in ("search5","search6"):
            directory=SEARCH5 if c["source_cohort"]=="search5" else SEARCH6
            raw=directory/"cases"/c["filename"]
            need(raw.is_file() and sha(raw)==c["sha256"],
                 "missing frozen original "+c["source_cohort"])
            dst=SOURCE/c["filename"]
            if dst.exists():
                need(sha(dst)==c["sha256"],"frozen source filename collision")
            else:
                shutil.copyfile(raw,dst)
        source(c)
    m=dict(protocol=PROTO,original_cases=cs,source_count=N,arms=list(ARMS),
      reps=REPS,cap_s=CAP,shards=SHARDS,trials=EXPECTED,
      route_min_complete_XOR_equations=XOR_ROUTE_MIN,
      gate_max_clauses=GATE_MAX_CLAUSES,gate_max_bytes=GATE_MAX_BYTES,
      precommitted_fixed_roster_from_three_prior_frozen_sources=True,
      earlier_solver_outcomes_exist=True,not_new_SHA=True,
      original_SHA_unchanged=True,one_logical_CPU=True,no_parallel_children=True,
      SAT_original_model_required=True,
      independent_algebraic_UNSAT_certificate_required=True,
      independent_UNSAT_LRAT=False,
      proof_on_original_not_derived_CNF=True,
      backend_UNSAT_requires_Kissat_CMS_original_agreement_no_LRAT=True,
      no_auto_promotion=True,signatures=signature())
    save(ROOT/"manifest.json",m)
    verify()
    print("MIXAB2_FROZEN "+json.dumps(dict(sources=N,arms=len(ARMS),trials=EXPECTED,
      one_cpu=True,source_selection_not_blind=True),sort_keys=True),flush=True)

def verify():
    m=read(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["original_cases"]==roster() and
         m["source_count"]==N and m["arms"]==list(ARMS) and
         m["reps"]==REPS and m["shards"]==SHARDS and m["cap_s"]==CAP and
         m["trials"]==EXPECTED and m["signatures"]==signature() and
         m["route_min_complete_XOR_equations"]==XOR_ROUTE_MIN and
         m["gate_max_clauses"]==GATE_MAX_CLAUSES and
         m["gate_max_bytes"]==GATE_MAX_BYTES,
         "frozen protocol or binary/manifest drift")
    for c in m["original_cases"]:source(c)
    return m

def selftest():
    need(gf.BIN.is_file(),"exact native scanner absent")
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/"toy.cnf"
        for k in (2,3,4):
            clauses=[]
            for parity in (0,1):
                for mask in range(1<<k):
                    if mask.bit_count()%2==parity:
                        clauses.append([-(i+1) if mask&(1<<i) else i+1 for i in range(k)])
            for count,expected in ((len(clauses),True),(len(clauses)-1,False)):
                out=clauses[:count]
                p.write_text("p cnf %d %d\n"%(k,len(out))+
                    "".join(" ".join(map(str,line))+" 0\n" for line in out))
                r=gf.scan(p)
                need(r["proved"]==expected,"independent GF2 toy proof failure")
    print("MIXAB2_SELFTEST_PASS "+json.dumps(dict(
       complete_XOR_UNSAT=3,incomplete_SAT_negative=3,
       proof_checker="independent_original_CNF_replay",one_cpu=True)),flush=True)

def cms_trial(c,rep,cap):
    src=source(c)
    n,clauses=e9.x22.read_cnf(src)
    need(n>0 and len(clauses)>0,"CMS original CNF parse failed")
    cpu=min(os.sched_getaffinity(0))
    t=time.perf_counter()
    before=e9.x22.child_cpu()
    status="TIMEOUT";witness=False
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        child=e9.x22.launch("cms",[str(CMS),"--verb","0","-t","1",str(src)],cpu,temp)
        try:
            while child["p"].poll() is None and time.perf_counter()-t < cap-0.018:
                time.sleep(.004)
            if child["p"].poll() is not None:
                stdout,stderr=e9.x22.read_output(child)
                status,witness=e9.x22.solver_result("cms",
                       child["p"].returncode,stdout,clauses,{})
        finally:e9.x22.cleanup([child])
    elapsed=time.perf_counter()-t
    if elapsed>=cap or status not in ("SAT","UNSAT"):
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"CMS SAT original model NOT VERIFIED")
    return dict(status=status,SAT_original_witness_verified=bool(witness),
                wall_E2E_s=elapsed,child_CPU_s=e9.x22.child_cpu()-before)

def backend(c,rep,name,seconds):
    if seconds<=.08:return dict(status="TIMEOUT",SAT_original_witness_verified=False,
                              wall_E2E_s=0.0,child_CPU_s=0.0)
    if name=="native":
        return e9.trial(dict(c,cohort="holdout"),rep,"native1",cap=seconds)
    if name=="kissat":
        s2.ROOT.mkdir(parents=True,exist_ok=True)
        return s2.trial(dict(c,cohort="holdout"),rep,"kissat_orig",cap=seconds)
    need(name=="cms","unsupported backend")
    return cms_trial(c,rep,seconds)

def shape_gate(c):
    clauses=c.get("clauses",c.get("original_source_signals",{}).get("clauses",0))
    need(clauses>0 and c["bytes"]>0,"source-only shape metadata unavailable")
    return clauses<=GATE_MAX_CLAUSES and c["bytes"]<=GATE_MAX_BYTES

def budget_scan(src):
    """A/B: same immutable C++ complete-XOR detector, but 120 ms scan cap.
    Timeout -> abstain and run untouched solver; no unsound shortcut.
    Any candidate UNSAT is independently checked on original CNF.
    """
    begin=time.perf_counter()
    try:
        r=subprocess.run([str(gf.BIN.resolve()),str(src.resolve())],
                         capture_output=True,text=True,timeout=0.120)
    except subprocess.TimeoutExpired:
        return dict(proved=False,abstained=True,
                    probe_wall_s=round(time.perf_counter()-begin,6),
                    reason="budgeted_120ms_timeout",proof=None,equations=0)
    if r.returncode!=0:
        return dict(proved=False,abstained=True,
                    probe_wall_s=round(time.perf_counter()-begin,6),
                    reason="budgeted_native_abstention",proof=None,equations=0)
    lines=[line[len("GF2_S1_RESULT "):] for line in r.stdout.splitlines()
           if line.startswith("GF2_S1_RESULT ")]
    need(len(lines)==1,"budget scanner missing C++ result")
    record=json.loads(lines[0])
    proof=gf.verify_algebraic_certificate(src,record) if record["xor_unsat"] else None
    return dict(proved=proof is not None,abstained=record["abstained"],
                probe_wall_s=round(time.perf_counter()-begin,6),
                reason="independent_GF2_proof" if proof else "no_exact_contradiction",
                proof=proof,equations=record["xor_equations"],
                scan_native_ms=record["scan_ms"])

def one(c,rep,arm):
    need(arm in ARMS and rep in (0,1),"invalid arm/rep")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    started=time.perf_counter()
    cpu0=time.process_time();child0=e9.x22.child_cpu()
    src=source(c);state=None;called=False
    selected={"kissat_plain":"kissat","cms_plain":"cms",
              "gf2_full_kissat":"kissat","gf2_budget_kissat":"kissat"}.get(arm)
    do_scan=arm not in ("kissat_plain","cms_plain")
    gated=arm.startswith("combo_")
    if do_scan and (not gated or shape_gate(c)):
        state=gf.scan(src) if arm in ("gf2_full_kissat","combo_full") else budget_scan(src)
    eq=state["equations"] if state else 0
    if selected is None:
        selected="cms" if eq>=XOR_ROUTE_MIN else "kissat"
    certified=bool(state and state["proved"])
    # The placebo scans and routes exactly as budgeted COMBO, but cannot short-circuit.
    shortcut=certified and arm!="combo_budget_placebo"
    backend_status=None
    status="UNSAT" if shortcut else "TIMEOUT"
    witness=False
    if not shortcut:
        left=CAP-(time.perf_counter()-started)
        if left>.08:
            called=True
            r=backend(c,rep,selected,left)
            backend_status=r["status"]
            status=r["status"];witness=r["SAT_original_witness_verified"]
    wall=time.perf_counter()-started
    if wall>=CAP:
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"non-original SAT witness")
    need(sha(src)==c["sha256"],"original CNF modified during trial")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
         rep=rep,arm=arm,cap_s=CAP,original_SHA_verified=True,
         pinned_logical_cpu=cpu,one_solver_child_max=True,
         status=status,SAT_original_witness_verified=bool(witness if status=="SAT" else False),
         UNSAT_independent_GF2_certificate_verified=bool(shortcut),
         UNSAT_exact_GF2_found=certified,
         UNSAT_independent_LRAT=False,certificate_terms=state["proof"]["terms"] if certified else 0,
         scan_abstained=state["abstained"] if state else False,
         scan_reason=state["reason"] if state else "geometry_gate_skip" if do_scan else "no_scan_baseline",
         xor_equations=eq,scan_E2E_s=state["probe_wall_s"] if state else 0.0,
         source_only_shape_gate=shape_gate(c),
         selected_backend=selected,backend_called=called,backend_status=backend_status,
         wall_E2E_s=round(wall,6),
         actual_child_CPU_s=round(e9.x22.child_cpu()-child0,6),
         actual_parent_CPU_s=round(time.process_time()-cpu0,6))

def shard(index):
    m=verify()
    need(index in range(SHARDS),"invalid shard")
    cs=[c for i,c in enumerate(m["original_cases"]) if i%SHARDS==index]
    rows=[]
    for c in cs:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(c["sha256"]+str(rep)+"MIXAB2-2026").shuffle(order)
            for arm in order:
                row=one(c,rep,arm);row["shard"]=index
                need(row["wall_E2E_s"]<=CAP+0.2,"wall budget exceeded")
                rows.append(row)
                save(ROOT/f"shard-{index}.json",rows)
                print("MIXAB2_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cs)*REPS*len(ARMS),"missing paired observations")
    print(f"MIXAB2_SHARD_PASS {index} {len(rows)}",flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        rr=read(ROOT/f"shard-{i}.json")
        need(len(rr)==len([c for j,c in enumerate(m["original_cases"]) if j%SHARDS==i])
              *REPS*len(ARMS),"missing shard trial")
        rows+=rr
    keys={(c["sha256"],rep,arm) for c in m["original_cases"]
          for rep in range(REPS) for arm in ARMS}
    seen={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(seen)==EXPECTED and seen==keys,"duplicate or missing trials")
    bysha=collections.defaultdict(list)
    for x in rows:
        need(x["protocol"]==PROTO and x["original_SHA_verified"] and
             x["one_solver_child_max"] and x["cap_s"]==CAP and
             x["status"] in ("SAT","UNSAT","TIMEOUT") and
             x["wall_E2E_s"]<=CAP+.2 and
             (x["status"]!="SAT" or x["SAT_original_witness_verified"]),
             "trial correctness failure")
        bysha[x["sha256"]].append(x)
    math={sha for sha,rr in bysha.items()
          if any(x["UNSAT_independent_GF2_certificate_verified"] for x in rr)}
    consensus={sha for sha,rr in bysha.items()
               if any(x["arm"]=="kissat_plain" and x["status"]=="UNSAT" for x in rr)
               and any(x["arm"]=="cms_plain" and x["status"]=="UNSAT" for x in rr)}
    for sha,rr in bysha.items():
        need(len({x["status"] for x in rr if x["status"]!="TIMEOUT"})<=1,
             "different SAT and UNSAT on original source")
    def verified(x):
        return (x["status"]=="SAT" and x["SAT_original_witness_verified"]) or \
               (x["status"]=="UNSAT" and x["sha256"] in (math|consensus))
    def penalty(x):return x["wall_E2E_s"] if verified(x) else 2*CAP
    def score(rr):
        return dict(attempts=len(rr),solved=sum(verified(x) for x in rr),
          SAT_original_verified=sum(x["status"]=="SAT" and verified(x) for x in rr),
          UNSAT_proved_directly_this_arm=sum(x["status"]=="UNSAT" and x["UNSAT_independent_GF2_certificate_verified"] for x in rr),
          UNSAT_GF2_proof_exists_on_SHA=sum(x["status"]=="UNSAT" and x["sha256"] in math for x in rr),
          UNSAT_cross_solver_agreed_no_LRAT=sum(x["status"]=="UNSAT" and
                       x["sha256"] in consensus-math for x in rr),
          UNSAT_unverified=sum(x["status"]=="UNSAT" and not verified(x) for x in rr),
          timeouts=sum(x["status"]=="TIMEOUT" for x in rr),
          PAR2_s=round(sum(penalty(x) for x in rr),6),
          total_wall_s=round(sum(x["wall_E2E_s"] for x in rr),6),
          total_CPU_s=round(sum(x["actual_parent_CPU_s"]+x["actual_child_CPU_s"] for x in rr),6),
          scan_wall_s=round(sum(x["scan_E2E_s"] for x in rr),6),
          GF2_proof_repetitions=sum(x["UNSAT_exact_GF2_found"] for x in rr),
          scanner_abstentions=sum(x["scan_abstained"] for x in rr),
          route_to_CMS=sum(x["selected_backend"]=="cms" for x in rr))
    scores={arm:score([x for x in rows if x["arm"]==arm]) for arm in ARMS}
    for arm in ARMS:
        scores[arm]["speedup_vs_kissat_PAR2_x"]=round(
            scores["kissat_plain"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
    paired={}
    for arm in ARMS:
        if arm=="kissat_plain":continue
        diff=[]
        for sha,rr in bysha.items():
            for rep in range(REPS):
                a=next(x for x in rr if x["rep"]==rep and x["arm"]==arm)
                b=next(x for x in rr if x["rep"]==rep and x["arm"]=="kissat_plain")
                diff.append(penalty(a)-penalty(b))
        paired[arm]=dict(wins=sum(d<-.02 for d in diff),
             losses=sum(d>.02 for d in diff),ties=sum(abs(d)<=.02 for d in diff),
             net_PAR2_gain_s=round(-sum(diff),6),
             largest_gain_s=round(min(diff),6),largest_regression_s=round(max(diff),6))
    def comparisons(a,b):
        diff=[penalty(next(x for x in rr if x["rep"]==rep and x["arm"]==a))
             -penalty(next(x for x in rr if x["rep"]==rep and x["arm"]==b))
             for sha,rr in bysha.items() for rep in range(REPS)]
        return dict(wins=sum(x<-.02 for x in diff),losses=sum(x>.02 for x in diff),
                    ties=sum(abs(x)<=.02 for x in diff),
                    net_PAR2_gain_s=round(-sum(diff),6),
                    best_gain_s=round(min(diff),6),worst_regression_s=round(max(diff),6))
    report=dict(protocol=PROTO,sources=N,trials=EXPECTED,
      source_only_prior_frozen_SHA_not_new=True,globally_blind=False,
      strict_original_SAT_witness=True,independent_GF2_math_proof_NOT_LRAT=True,
      no_independent_LRAT_for_backend_UNSAT=True,no_auto_promotion=True,
      one_logical_cpu=True,no_parallel_portfolio=True,
      math_certified_originals=sorted(math),backend_UNSAT_agreement=sorted(consensus-math),
      scores=scores,paired=paired,
      paired_vs_CMS={a:comparisons(a,'cms_plain') for a in ARMS if a!='cms_plain'},
      causal_GF2_budget_vs_placebo=comparisons('combo_budget','combo_budget_placebo'),
      long_vs_budget=comparisons('combo_budget','combo_full'),
      per_shard={str(i):{a:score([x for x in rows if x["shard"]==i and x["arm"]==a])
         for a in ARMS} for i in range(SHARDS)},
      per_SHA={sha:{a:[dict(rep=x["rep"],status=x["status"],E2E_s=x["wall_E2E_s"],
                    XOR=x["xor_equations"],route=x["selected_backend"],
                    proof=x["UNSAT_independent_GF2_certificate_verified"])
                    for x in rr if x["arm"]==a] for a in ARMS} for sha,rr in bysha.items()})
    save(ROOT/"report.json",report)
    print("MIXAB2_FINAL "+json.dumps({k:v for k,v in report.items() if k not in ("per_SHA",)},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        globals()[a.action]()
        if a.action=="verify":print("MIXAB2_VERIFY_PASS",flush=True)
