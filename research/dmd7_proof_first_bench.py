#!/usr/bin/env python3
"""DMD7 proof-first original-CNF resolution screening and one-core E2E.

SCREEN on 24 historically reused EQUIV7 original sources, no solver labels.
Bounded 2-parent resolution yields binary/ternary consequences with explicit
original clause indices and a pivot. Independent Python recomputes every
resolvent AND exhaustively verifies all assignments to its two parents.
Preselect up to 12 sources using original-only candidate counts.
Matched 8-second 7-arm 2-rep E2E on selected sources. No global blind holdout.
SAT original witness verified. UNSAT backend only, never independent LRAT.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,resource,tempfile,time
import dmd5_ablation_transfer as d5

PROTO="DRNAS-DMD7-PROOF-FIRST-SOURCE-RESOLUTION-24SCREEN-12SELECT-7ARM-2REP-8S-v1"
ROOT=pathlib.Path("mre_dmd7")
EXPAND=ROOT/"bin/dmd7_expand"
SCREEN_MS=700
CAP=8.0
REPS=2
SHARDS=4
LIMIT_CASES=12
ARMS=("cadical_clean","kissat_original","dmd1_all","dmd7_placebo",
      "dmd7_top1","dmd7_top4","dmd7_top12")
def need(ok,msg):
    if not ok:raise RuntimeError("DMD7_FAIL_CLOSED "+str(msg))
def setup():
    d5.ROOT=ROOT
    d5.DMD1=ROOT/"bin/dmd1_anf"
    d5.GATE=ROOT/"bin/dmd2_gate"
    d5.LIVE=ROOT/"bin/dmd5_live"
    d5.d1.ROOT=ROOT
def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def sources():
    setup()
    train,holdout=d5.read_cases()
    need(len(holdout)==24 and len({x["sha256"] for x in holdout})==24,
         "source-only 24 roster drift")
    return holdout
def cpu():
    return min(os.sched_getaffinity(0))
def cpu_children():
    q=resource.getrusage(resource.RUSAGE_CHILDREN)
    return q.ru_utime+q.ru_stime
def normalized(clause):
    return tuple(sorted(set(clause),key=lambda lit:(abs(lit),lit)))
def clause_sat(clause,assigned):
    return any(assigned[abs(lit)]==(lit>0) for lit in clause)
def replay(original,meta):
    """Independent truth-table and source-index resolution proof replayer."""
    n,cs=d5.d1.read_cnf(original)
    need(meta["protocol"]=="DMD7-RESOLUTION-SOURCE-PAIR-v1",
         "unexpected expander protocol")
    if meta["abstained"]:
        need(meta["selected"]==0 and meta["certificates"]==[],
             "abstained preprocessing emitted candidates")
        return n,cs,[]
    need(meta["source_vars"]==n and meta["source_clauses"]==len(cs),
         "source geometry mismatch")
    items=meta["certificates"]
    need(len(items)==meta["selected"] and len(items)<=48,
         "unexpected output bound")
    existing={normalized(c) for c in cs}
    seen=set()
    clauses=[]
    for entry in items:
        a,b,p=entry["parent_a"],entry["parent_b"],entry["pivot"]
        need(type(a)==type(b)==type(p)==int and
             0<=a<len(cs) and 0<=b<len(cs) and 0<abs(p)<=n and a!=b,
             "invalid original source pair")
        ca,cb=cs[a],cs[b]
        need(p in ca and -p in cb and
             len(ca)<=3 and len(cb)<=3 and len(ca)>0 and len(cb)>0,
             "not a valid parent pivot")
        expected=normalized([lit for lit in ca if lit!=p]+
                            [lit for lit in cb if lit!=-p])
        item=tuple(entry["clause"])
        need(item==expected and 1<=len(item)<=3 and
             all(-x not in item for x in item) and
             item not in existing and item not in seen,
             "invalid, duplicate or tautological resolvent")
        vars_=sorted({abs(x) for x in [*ca,*cb]})
        need(len(vars_)<=5,"local proof exceeds five variables")
        for mask in range(1<<len(vars_)):
            values={v:bool(mask&(1<<i)) for i,v in enumerate(vars_)}
            need(not (clause_sat(ca,values) and clause_sat(cb,values)) or
                 clause_sat(item,values),
                 "INDEPENDENT ORIGINAL CNF PROOF FAILURE")
        seen.add(item)
        clauses.append(item)
    return n,cs,clauses

def derive(case,work):
    original=pathlib.Path(case["path"])
    assert d5.d1.sha(original)==case["sha256"]
    certificate=work/"dmd7_resolution.json"
    rc,out,err,wall,child,timed=d5.d1.run_process(
        [EXPAND,original,certificate,SCREEN_MS],2.0,cpu())
    need(not timed and rc==0 and certificate.is_file(),
         "native resolution screening failed "+err[-250:])
    raw=json.loads(certificate.read_text())
    lines=[x[len("DMD7_EXPAND "):] for x in out.splitlines()
           if x.startswith("DMD7_EXPAND ")]
    need(len(lines)==1 and json.loads(lines[0])==raw,
         "native telemetry/certificate mismatch")
    n,source,verified=replay(original,raw)
    # Revalidate before/after because the original source prefix is sacred.
    need(d5.d1.sha(original)==case["sha256"],"original source modified")
    return n,source,verified,raw

def manifest():
    cases=sources()
    ROOT.mkdir(exist_ok=True)
    results=[]
    for c in cases:
        with tempfile.TemporaryDirectory(prefix="dmd7-screen-") as td:
            n,original,clauses,raw=derive(c,pathlib.Path(td))
        nbin=sum(len(x)<=2 for x in clauses)
        ntri=sum(len(x)==3 for x in clauses)
        item=dict(filename=c["filename"],sha256=c["sha256"],
                  source_vars=n,source_clauses=len(original),
                  proof_verified=len(clauses),
                  candidate_binary=nbin,candidate_ternary=ntri,
                  screen_abstained=raw["abstained"],
                  parent_pairs_checked=raw["parent_pairs_checked"],
                  pivot_variables_scanned=raw["pivot_variables_scanned"],
                  candidate_signature=digest(raw["certificates"]),
                  candidate_items=raw["certificates"])
        results.append(item)
        print("DMD7_SCREEN",json.dumps({k:v for k,v in item.items()
                 if k!="candidate_items"},sort_keys=True),flush=True)
    positive=[c for c in results if c["proof_verified"]>0 and not c["screen_abstained"]]
    positive.sort(key=lambda c:(-c["candidate_binary"],-c["proof_verified"],c["sha256"]))
    selected=positive[:LIMIT_CASES]
    bins={s:hashlib.sha256((ROOT/"bin"/s).read_bytes()).hexdigest()
          for s in ("dmd7_expand","dmd1_anf","dmd5_live")}
    obj=dict(protocol=PROTO,source_only_screen=True,
        original_count=24,all_sources=results,
        eligible_source_count=len(positive),
        selected=[x["sha256"] for x in selected],
        selected_cases=selected,
        selection_policy="rank binary count then candidate count then source SHA; no runtime labels",
        cap_s=CAP,reps=REPS,shards=SHARDS,
        arms=ARMS,expected_trials=len(selected)*REPS*len(ARMS),
        screen_ms=SCREEN_MS,binary_hashes=bins,
        not_blind=True,
        reuses_DMD5_DMD6_transfer_cohort=True,
        immutable_source_SHA=True,independent_two_parent_truth_table_proofs=True,
        SAT_original_witness_verified=True,UNSAT_independent_LRAT=False,
        one_pinned_logical_cpu=True,no_auto_promotion=True)
    (ROOT/"manifest.json").write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    need(obj["expected_trials"]>0,"screen found no candidates for E2E")
    print("DMD7_SCREEN_PASS",json.dumps({
       "original_count":24,"eligible":len(positive),
       "selected":len(selected),"expected_trials":obj["expected_trials"],
       "total_binary_candidates":sum(x["candidate_binary"] for x in results),
       "total_ternary_candidates":sum(x["candidate_ternary"] for x in results),
       "abstained_sources":sum(x["screen_abstained"] for x in results)
    },sort_keys=True),flush=True)
def check_manifest():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["source_only_screen"] and
         m["arms"]==list(ARMS) and m["cap_s"]==CAP and m["reps"]==REPS
         and m["shards"]==SHARDS and
         m["expected_trials"]==len(m["selected"])*REPS*len(ARMS),
         "frozen screen manifest mismatch")
    cases=sources()
    orig={c["sha256"]:c for c in cases}
    need(len(m["all_sources"])==24 and
         {c["sha256"] for c in m["all_sources"]}==set(orig),
         "original-screen SHA registry modified")
    need(len(m["selected"])==len(set(m["selected"])) and
         len(m["selected"])<=LIMIT_CASES and
         len(m["selected"])>0 and
         {c["sha256"] for c in m["selected_cases"]}==set(m["selected"]),
         "screen case selection drift")
    for s,h in m["binary_hashes"].items():
        need(hashlib.sha256((ROOT/"bin"/s).read_bytes()).hexdigest()==h,
             "native binary SHA drift")
    return m,orig

def trial(case,source_entry,arm,rep):
    need(arm in ARMS and rep in (0,1),"unregistered arm/rep")
    original=pathlib.Path(case["path"])
    need(d5.d1.sha(original)==case["sha256"],"source SHA drift")
    start=time.monotonic();cpu_start=cpu_children()
    n,source=d5.d1.read_cnf(original)
    chosen=[];candidates=0;prepared=False
    proof_hash=None
    with tempfile.TemporaryDirectory(prefix="dmd7-e2e-") as td:
        work=pathlib.Path(td)
        if arm.startswith("dmd7_"):
            nn,cc,proved,raw=derive(case,work)
            need(nn==n and cc==source and
                 digest(raw["certificates"])==source_entry["candidate_signature"] and
                 len(proved)==source_entry["proof_verified"],
                 "source proof candidates changed after freezing")
            candidates=len(proved);prepared=True
            if arm!="dmd7_placebo":
                chosen=proved[:int(arm.split("top")[1])]
        elif arm=="dmd1_all":
            nn,cc,local,all_lemmas,gate_l,gate_info,_=d5.discover(
                case,work,cpu(),gate=False)
            need(nn==n and cc==source,"DMD1 changed original CNF")
            chosen=all_lemmas
            prepared=True
        status,verified,stats,_=d5.solve(
            original,n,source,chosen,
            "kissat" if arm=="kissat_original" else "cadical",
            CAP,start,work,cpu())
    elapsed=time.monotonic()-start
    need(status!="SAT" or verified,"SAT witness failed original replay")
    return dict(protocol=PROTO,original_sha256=case["sha256"],filename=case["filename"],
        arm=arm,rep=rep,cohort="DMD5_reused_source_only_screen_selected",
        status=status,SAT_original_witness_verified=verified,
        UNSAT_independent_LRAT=False,one_logical_cpu=True,
        source_SHA_verified=True,
        independent_proof_replayed=prepared,proof_signature=proof_hash,
        candidates_proved=candidates,appended_lemmas=len(chosen),
        appended_shapes=dict(collections.Counter(d5.shape(v) for v in chosen)),
        cap_s=CAP,e2e_s=round(elapsed,6),
        PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
        full_CPU_s=round(cpu_children()-cpu_start,6),
        cdcl_stats=stats)

def selftest():
    need(EXPAND.is_file() and d5.DMD1.is_file() and
         d5.LIVE.is_file() and d5.KISSAT.is_file(),"native binaries missing")
    with tempfile.TemporaryDirectory(prefix="dmd7-toy-") as td:
        w=pathlib.Path(td)
        p=w/"toy.cnf"
        p.write_text("p cnf 5 5\n-1 2 0\n-2 3 0\n1 4 5 0\n-1 -4 0\n-3 5 0\n")
        c={"path":str(p),"sha256":d5.d1.sha(p)}
        n,original,proved,raw=derive(c,w)
        need(any(c==(-1,3) for c in proved) and
             any(len(c)==3 for c in proved) and
             len(proved)>=2,"binary path or ternary resolution missing")
    print("DMD7_PROOF_REPLAY_PASS",json.dumps({
       "independently_replayed_candidates":len(proved),
       "binary":sum(len(c)<=2 for c in proved),
       "ternary":sum(len(c)==3 for c in proved),
       "original_parent_truth_table":True},sort_keys=True),flush=True)

def shard(i):
    need(0<=i<SHARDS,"bad shard")
    m,orig=check_manifest()
    rows=[]
    selected=m["selected_cases"][i::SHARDS]
    for entry in selected:
        c=orig[entry["sha256"]]
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+str(rep)+"DMD7").shuffle(arms)
            for arm in arms:
                x=trial(c,entry,arm,rep)
                rows.append(x)
                (ROOT/f"shard-{i}.json").write_text(json.dumps(rows,sort_keys=True))
                print("DMD7_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    if not rows:
        (ROOT/f"shard-{i}.json").write_text("[]")
    expected=len(selected)*REPS*len(ARMS)
    need(len(rows)==expected,"missing or duplicate shard trials")
    print("DMD7_SHARD_PASS",i,len(rows),flush=True)
def audit():
    m,orig=check_manifest()
    rows=[]
    for i in range(SHARDS):
        path=ROOT/f"shard-{i}.json"
        need(path.is_file(),"missing shard "+str(i))
        items=json.loads(path.read_text())
        expected=len(m["selected_cases"][i::SHARDS])*REPS*len(ARMS)
        need(len(items)==expected,"incomplete shard "+str(i))
        rows+=items
    expected={(sha,rep,arm) for sha in m["selected"] for rep in range(REPS) for arm in ARMS}
    actual={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(actual)==len(expected)==m["expected_trials"] and
         actual==expected,"384? no: exact source-screen E2E coverage failed")
    for r in rows:
        need(r["protocol"]==PROTO and r["one_logical_cpu"] and r["source_SHA_verified"]
             and r["cap_s"]==CAP,"original E2E protocol drift")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT") and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "invalid original SAT result")
    byarm={}
    for arm in ARMS:
        q=[x for x in rows if x["arm"]==arm]
        byarm[arm]=dict(trials=len(q),
          solved=sum(x["status"]!="TIMEOUT" for x in q),
          SAT_verified=sum(x["status"]=="SAT" for x in q),
          UNSAT_backend_only=sum(x["status"]=="UNSAT" for x in q),
          PAR2_s=round(sum(x["PAR2_s"] for x in q),6),
          CPU_s=round(sum(x["full_CPU_s"] for x in q),6),
          lemma_sum=sum(x["appended_lemmas"] for x in q),
          cases_activated=sum(x["appended_lemmas"]>0 for x in q),
          conflicts=sum(x["cdcl_stats"].get("conflicts",0) for x in q),
          decisions=sum(x["cdcl_stats"].get("decisions",0) for x in q))
    ref=byarm["cadical_clean"]["PAR2_s"]
    for a in byarm.values():
        a["speedup_x_vs_clean"]=round(ref/a["PAR2_s"],6)
    matched={}
    indexed={(x["original_sha256"],x["rep"],x["arm"]):x for x in rows}
    for arm in ARMS:
        if arm in ("cadical_clean","kissat_original"):continue
        matches=[(indexed[(sha,r,arm)],indexed[(sha,r,"cadical_clean")],
                  indexed[(sha,r,"dmd7_placebo")])
                 for sha in m["selected"] for r in range(REPS)]
        matched[arm]=dict(
          paired=len(matches),
          wins_vs_clean=sum(a["PAR2_s"]<b["PAR2_s"]-.02 for a,b,p in matches),
          losses_vs_clean=sum(a["PAR2_s"]>b["PAR2_s"]+.02 for a,b,p in matches),
          PAR2_net_benefit_s=round(sum(b["PAR2_s"]-a["PAR2_s"] for a,b,p in matches),6),
          PAR2_net_vs_placebo_s=round(sum(p["PAR2_s"]-a["PAR2_s"] for a,b,p in matches),6),
          activated_pairs=sum(a["appended_lemmas"]>0 for a,b,p in matches),
          added_on_solved_cases=sum(a["appended_lemmas"]>0 and
               a["status"]!="TIMEOUT" for a,b,p in matches))
    result=dict(protocol=PROTO,original_sources_screened=24,
        source_selected=len(m["selected"]),
        trials=len(rows),one_logical_CPU_per_solver=True,
        fresh_holdout=False,source_only_selection=True,
        source_parent_truth_table_proof_replayed=True,
        original_SAT_witness_verified=True,UNSAT_independent_LRAT=False,
        no_auto_promotion=True,
        scores=byarm,paired=matched,screen={
          "eligible":m["eligible_source_count"],
          "selected":m["selected"],"screened":m["original_count"],
          "total_binary":sum(c["candidate_binary"] for c in m["all_sources"]),
          "total_ternary":sum(c["candidate_ternary"] for c in m["all_sources"]),
          "abstained":sum(c["screen_abstained"] for c in m["all_sources"])},
        rows=rows)
    (ROOT/"report.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("DMD7_FINAL",json.dumps({k:v for k,v in result.items() if k!="rows"},sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","screen","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    setup()
    {"selftest":selftest,"screen":manifest,"shard":lambda:shard(args.shard),
     "audit":audit}[args.action]()
