#!/usr/bin/env python3
"""DRNAS BINARY-SCC2: one-core paired E2E original vs source SCC quotient.
17 previously seen original SHA (12 EQUIV9 + 5 EQUIV10M5), 6 arms, 2 reps.
Each trial contains SHA, original parse, C++ clean/quotient, an independent
Tarjan replay of ALL aliases, all original clause substitution checks, CDCL
solve, SAT witness lifted and verified on the ORIGINAL CNF, and cleanup.
No parallel child solvers. UNSAT is accepted for PAR2 only on a SHA where
original Kissat and original CaDiCaL agree. This is not independent LRAT
or a new blind competition result. No auto-promotion to main.
"""
from __future__ import annotations
import argparse, collections, itertools, json, os, pathlib, random
import resource, statistics, subprocess, tempfile, time
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_binary_scc1_source_audit as s1

ROOT=pathlib.Path("mre_binary_scc2")
BIN=ROOT/"bin/scc_quotient"
PROTO="DRNAS-BINARY-SCC2-17FROZEN-SHA-6ARM-2REP-15S-E2E-v1"
ARMS=("kissat_orig","kissat_clean","kissat_scc",
      "cadical_orig","cadical_clean","cadical_scc")
CAP=15.0
REPS=2
SHARDS=6
NCASE=17
EXPECTED=NCASE*REPS*len(ARMS)
EXPECTED_ALIASES={
 "16b427cd6ffac58fe865c5d8a88bde4517bb44de3d2a9ab9436ecac15f3923fb":864,
 "c84316b8a5eb43914f9c2c5a55b6437fdc4033a08e3ec34b790438d05ec7195e":400,
 "327bfcaa1933d1c2b293f90f5761bfb25448c577d4a6958b962d4a09a1c88b7a":4,
}

def need(cond,why):
    if not cond:raise RuntimeError("BINARY_SCC2_FAIL_CLOSED "+str(why))
def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def cases():
    cs=s1.cases()
    need(len(cs)==NCASE and
         len({c["sha256"] for c in cs})==NCASE,"source roster drift")
    return cs
def bins():
    return dict(native_reducer=e9.digest(BIN),
        kissat=e9.digest(e9.KISSAT),cadical=e9.digest(e9.CAD))
def freeze():
    cs=cases()
    need(BIN.is_file(),"native binary not compiled")
    manifest=dict(protocol=PROTO,source_count=NCASE,trial_count=EXPECTED,
       source_cohorts=dict(EQUIV9_holdout=12,EQUIV10M5=5),
       selected_on_prior_original_SCC_alias_diagnostics=True,
       not_blind=True,source_SHA_unchanged=True,one_logical_CPU_per_arm=True,
       no_concurrent_child_processes=True,
       no_independent_UNSAT_LRAT=True,
       UNSAT_accepted_only_on_original_Kissat_and_CaDiCaL_agreement=True,
       original_SAT_witness_required=True,
       full_E2E_includes_all_independent_proof_checks=True,
       precommitted_alias_source_count=3,
       precommitted_source_alias_counts=EXPECTED_ALIASES,
       clauses_are_independently_verified_after_substitution=True,
       clean_is_original_CNFSCC_placebo_without_aliases=True,
       caps_s=CAP,reps=REPS,shards=SHARDS,arms=list(ARMS),
       cases=cs,script_sha256=e9.digest(__file__),
       cpp_source_sha256=e9.digest("research/drnas_binary_scc2_quotient.cpp"),
       backend_SHA=bins(),
       predecessor_manifest_SHA=e9.digest(s1.ROOT/"manifest.json"),
       no_auto_promotion=True)
    save(ROOT/"manifest.json",manifest)
    verify()
    print("BINARY_SCC2_FROZEN "+json.dumps(dict(
       original_SHA=NCASE,aliases_from_original=sum(EXPECTED_ALIASES.values()),
       arms=len(ARMS),reps=REPS,expected_trials=EXPECTED,cap_s=CAP,
       one_cpu=True,not_blind=True),sort_keys=True),flush=True)
def verify():
    cs=cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["cases"]==cs and
         m["trial_count"]==EXPECTED and m["source_count"]==NCASE and
         m["reps"]==REPS and m["shards"]==SHARDS and
         m["arms"]==list(ARMS) and m["caps_s"]==CAP and
         m["backend_SHA"]==bins() and
         m["precommitted_source_alias_counts"]==EXPECTED_ALIASES and
         m["script_sha256"]==e9.digest(__file__) and
         m["cpp_source_sha256"]==e9.digest("research/drnas_binary_scc2_quotient.cpp") and
         m["predecessor_manifest_SHA"]==e9.digest(s1.ROOT/"manifest.json"),
         "source, code or solver binary drift")
    for c in cs:
        need(e9.digest(e9.SOURCE/c["filename"])==c["sha256"],
             "original SHA changed")
    return m

def parse_map(path,n):
    lines=pathlib.Path(path).read_text().splitlines()
    need(bool(lines) and len(lines[0].split())==4,"mapping header absent")
    head=lines[0].split()
    need(head[:2]==["p","map"] and int(head[2])==n and
         int(head[3])==len(lines)-1,"mapping count invalid")
    mapping={}
    for line in lines[1:]:
        a,b=map(int,line.split())
        need(0<a<=n and 0<abs(b)<a and a not in mapping,
             "illegal original literal equivalence")
        mapping[a]=b
    return mapping

def normalized_original_clause(c,mapping):
    out=set()
    for l in c:
        rep=mapping.get(abs(l),abs(l))
        v=rep if l>0 else -rep
        if -v in out:return None
        out.add(v)
    return tuple(sorted(out))

def verify_transformed(n,original,reduced,mapping):
    # Different implementation from C++: canonical sorted tuple sets.
    need(len(set(mapping))==len(mapping),"duplicate alias")
    e=set()
    for clause in original:
        r=normalized_original_clause(clause,mapping)
        if r is not None:e.add(r)
    actual=[tuple(sorted(c)) for c in reduced]
    need(len(actual)==len(e) and set(actual)==e,
         "rewritten CNF differs from exact original-clause substitution")
    need(all(len(c)==len(set(c)) and not any(-l in c for l in c)
             for c in reduced),"invalid reduced clause")
    return dict(input_clauses=len(original),output_clauses=len(reduced),
                clauses_removed=len(original)-len(reduced))

def independently_verify_aliases(n,original,mapping,expected):
    # Source-only Tarjan: independent of native C++ Kosaraju.
    g,edges,geometry=s1.independent_graph(n,original)
    comp,_=s1.independent_tarjan(g)
    all_alias,contrad,stats=s1.verified_alias_map(comp,n)
    need(not contrad,"binary SCC source contradiction -> keep source unchanged; "
         "this experiment does not claim an UNSAT proof")
    need(len(all_alias)==expected,"new alias count drift from BINARY-SCC1")
    need(mapping==dict(all_alias),"not all C++ aliases replayed from original")
    return stats

def reducer(src,n,original,mode,folder,expected):
    output=pathlib.Path(folder)/"modified.cnf"
    mapping_file=pathlib.Path(folder)/"aliases.map"
    result=subprocess.run([str(BIN.resolve()),mode,str(src.resolve()),
        str(output),str(mapping_file),"0"],
        text=True,capture_output=True,timeout=CAP)
    need(result.returncode==0,"native C++ reducer error "+result.stderr[-300:])
    lines=[x for x in result.stdout.splitlines()
           if x.startswith("BINARY_SCC2_REDUCER ")]
    need(len(lines)==1,"native C++ telemetry missing")
    tele=json.loads(lines[0][len("BINARY_SCC2_REDUCER "):])
    mapping=parse_map(mapping_file,n)
    if mode=="clean":
        need(not mapping and tele["aliases"]==0,"clean control unexpectedly mapped")
    else:
        need(tele["aliases"]==expected==len(mapping),"native alias count drift")
        independently_verify_aliases(n,original,mapping,expected)
    rn,reduced=e9.x22.read_cnf(output)
    need(rn==n,"solver variable numbering changed without source map")
    check=verify_transformed(n,original,reduced,mapping)
    need(check["input_clauses"]==tele["input_clauses"] and
         check["output_clauses"]==tele["output_clauses"],
         "C++/independent CNF clause count mismatch")
    need(tele["eligible_aliases"]==expected,
         "source original SCC evidence differs from preregistered proof")
    return output,mapping,tele,check

def one_solver(solver,source,seed,n,original,mapping,remaining,folder,cpu):
    # Python and every child are pinned to the same logical CPU.
    need(remaining>.07,"insufficient solver time")
    command=e9.command("kissat1" if solver=="kissat" else "cadical301_default",
                       source,seed)
    child=e9.x22.launch(solver,command,cpu,folder)
    result="TIMEOUT";model=False
    start=time.perf_counter()
    try:
        while child["p"].poll() is None and time.perf_counter()-start<remaining-.02:
            time.sleep(.004)
        if child["p"].poll() is not None:
            out,err=e9.x22.read_output(child)
            result,model=e9.x22.solver_result(solver,child["p"].returncode,
                                                out,original,mapping)
    finally:
        e9.x22.cleanup([child])
    if time.perf_counter()-start>=remaining:
        result="TIMEOUT";model=False
    return result,model

def trial(case,rep,arm,cap=CAP,toy=False):
    need(arm in ARMS and 0<=rep<REPS,"unsupported arm/rep")
    src=pathlib.Path(case["filename"]) if toy else e9.SOURCE/case["filename"]
    allowed=sorted(os.sched_getaffinity(0));need(allowed,"missing CPU affinity")
    cpu=allowed[0]
    os.sched_setaffinity(0,{cpu})
    begin=time.perf_counter()
    main_before=time.process_time()
    child_before=e9.x22.child_cpu()
    need(e9.digest(src)==case["sha256"],"original CNF SHA changed")
    n,original=e9.x22.read_cnf(src)
    need(n>0 and bool(original),"empty original DIMACS")
    expected=case.get("expected_aliases",EXPECTED_ALIASES.get(case["sha256"],0))
    solver,mode=arm.split("_",1)
    aliases={};tele={};proof_ms=0;prep_s=0;rewrite={}
    result="TIMEOUT";verified=False;started_solver=False
    seed=e9.seedpair(case["sha256"],rep)[0]
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        target=src
        if mode!="orig":
            t0=time.perf_counter()
            target,aliases,tele,rewrite=reducer(src,n,original,
                "clean" if mode=="clean" else "quotient",folder,expected)
            proof_ms=(time.perf_counter()-t0)*1000
        prep_s=time.perf_counter()-begin
        remaining=cap-prep_s
        if remaining>.07:
            started_solver=True
            result,verified=one_solver(solver,target,seed,n,original,aliases,
                                       remaining,folder,cpu)
    wall=time.perf_counter()-begin
    if wall>=cap:
        result="TIMEOUT";verified=False
    need(result!="SAT" or verified,"solver did not verify original SAT model")
    need(e9.digest(src)==case["sha256"],"original CNF mutated by surgery")
    return dict(protocol=PROTO,sha256=case["sha256"],gbd=case["gbd"],
      arm=arm,rep=rep,cap_s=cap,source_selection="seen alias mechanism cohort",
      expected_original_SCC_aliases=expected,
      validated_aliases=len(aliases),original_sha256_verified=True,
      SAT_original_witness_verified=verified if result=="SAT" else False,
      UNSAT_independent_LRAT=False,status=result,
      original_input_unchanged=True,one_logical_cpu=cpu,
      solver_children=1 if started_solver else 0,
      reducer_children=0 if mode=="orig" else 1,
      concurrent_solver_children=False,
      rewrite=rewrite,telemetry=tele,
      reducer_plus_proof_E2E_s=round(proof_ms/1000,6),
      prep_E2E_s=round(prep_s,6),
      wall_E2E_s=round(wall,6),
      parent_CPU_s=round(time.process_time()-main_before,6),
      child_CPU_s=round(e9.x22.child_cpu()-child_before,6))

def selftest():
    need(BIN.is_file(),"native reducer missing")
    ROOT.mkdir(exist_ok=True,parents=True)
    rng=random.Random(6222026)
    cases_checked=0
    with tempfile.TemporaryDirectory() as folder:
        p=pathlib.Path(folder);src=p/"source.cnf"
        for n in range(1,7):
            for i in range(12):
                clauses=[]
                for _ in range(rng.randrange(1,20)):
                    clauses.append(tuple(rng.choice((-1,1))*rng.randint(1,n)
                                         for _ in range(rng.randrange(0,5))))
                if i==0 and n>=2:
                    clauses=[(-1,2),(1,-2),(1,),(2,)]
                src.write_text("p cnf %d %d\n"%(n,len(clauses))+
                               "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
                nn,orig=e9.x22.read_cnf(src)
                g,_,_=s1.independent_graph(nn,orig)
                comp,_=s1.independent_tarjan(g)
                mapped,contrad,_=s1.verified_alias_map(comp,nn)
                if contrad:
                    # Skip quotient with contradictory source graph;
                    # result does not imply an LRAT proof.
                    continue
                allmaps={}
                for mode in ("clean","quotient"):
                    _,mapping,tele,meta=reducer(src,nn,orig,mode,p,len(mapped))
                    allmaps[mode]=mapping
                    _,reduced=e9.x22.read_cnf(p/"modified.cnf")
                    src_sat=any(e9.x22.holds(orig,{j+1:bool(mask&(1<<j))
                                       for j in range(nn)}) for mask in range(1<<nn))
                    transformed_sat=any(e9.x22.holds(reduced,{j+1:bool(mask&(1<<j))
                                       for j in range(nn)}) for mask in range(1<<nn))
                    need(src_sat==transformed_sat,"source/quotient SAT not equivalent")
                    for mask in range(1<<nn):
                        model={j+1:bool(mask&(1<<j)) for j in range(nn)}
                        if e9.x22.holds(reduced,model):
                            need(e9.x22.holds(orig,e9.x22.lift(model,mapping)),
                                 "lifted transformed SAT fails original")
                    cases_checked+=1
    print("BINARY_SCC2_SELFTEST_PASS "+json.dumps(dict(
        positive_and_negative_toy_comparisons=cases_checked,
        exhaustive_SAT_equivalence=True,all_lifted_models_verified=True,
        original_clauses_replay_verified=True),sort_keys=True),flush=True)

def shard(idx):
    need(0<=idx<SHARDS,"invalid shard")
    m=verify()
    cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx]
    rows=[]
    for c in cs:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+"|SCC2|"+str(rep)).shuffle(arms)
            for arm in arms:
                r=trial(c,rep,arm)
                r["shard"]=idx
                need(r["wall_E2E_s"]<=CAP+.1 and
                     (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
                     "E2E limit or SAT witness violation")
                rows.append(r)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("BINARY_SCC2_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(cs)*REPS*len(ARMS),"incomplete shard")
    print("BINARY_SCC2_SHARD_PASS "+json.dumps(dict(
        shard=idx,originals=len(cs),trials=len(rows)),sort_keys=True),flush=True)

def audit():
    m=verify();rows=[]
    for idx in range(SHARDS):
        rr=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
        cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx]
        need(len(rr)==len(cs)*REPS*len(ARMS),"shard incomplete "+str(idx))
        rows+=rr
    expect={(c["sha256"],rep,arm) for c in m["cases"]
            for rep in range(REPS) for arm in ARMS}
    seen={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(expect)==len(seen)==EXPECTED and seen==expect,
         "incomplete or duplicate paired benchmark")
    lookup={(r["sha256"],r["rep"],r["arm"]):r for r in rows}
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and
             r["original_sha256_verified"] and
             r["wall_E2E_s"]<=CAP+.1 and
             not r["concurrent_solver_children"] and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "row verification failed")
        bysha[r["sha256"]].append(r)
    agreed=set()
    for sha,rr in bysha.items():
        need(len({r["status"] for r in rr if r["status"]!="TIMEOUT"})<=1,
             "SAT/UNSAT disagreement on original "+sha)
        if (any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rr) and
            any(r["arm"]=="cadical_orig" and r["status"]=="UNSAT" for r in rr)):
            agreed.add(sha)
    def solved(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agreed)
    def par2(r):
        return r["wall_E2E_s"] if solved(r) else 2*CAP
    def scores(g):
        return dict(n=len(g),solved=sum(solved(r) for r in g),
           SAT_original_verified=sum(r["status"]=="SAT" for r in g),
           UNSAT_original_two_solver_agree_no_LRAT=sum(
               r["status"]=="UNSAT" and r["sha256"] in agreed for r in g),
           UNSAT_unverified=sum(r["status"]=="UNSAT" and
                                r["sha256"] not in agreed for r in g),
           TIMEOUT=sum(r["status"]=="TIMEOUT" for r in g),
           PAR2_s=round(sum(par2(r) for r in g),6),
           wall_total_s=round(sum(r["wall_E2E_s"] for r in g),6),
           child_CPU_s=round(sum(r["child_CPU_s"] for r in g),6),
           parent_CPU_s=round(sum(r["parent_CPU_s"] for r in g),6),
           reducer_with_proof_s=round(sum(r["reducer_plus_proof_E2E_s"] for r in g),6))
    totals={a:scores([r for r in rows if r["arm"]==a]) for a in ARMS}
    for solver in ("kissat","cadical"):
        baseline=totals[solver+"_orig"]["PAR2_s"]
        for mode in ("orig","clean","scc"):
            st=totals[solver+"_"+mode]
            st["speedup_vs_original_PAR2_x"]=round(baseline/st["PAR2_s"],6)
    classes={}
    for label,keys in (("alias_positive",set(EXPECTED_ALIASES)),
                       ("alias_zero",{c["sha256"] for c in m["cases"]}-set(EXPECTED_ALIASES))):
        classes[label]={
            "sources":len(keys),
            "arms":{a:scores([r for r in rows if r["arm"]==a and r["sha256"] in keys])
                    for a in ARMS}}
    per_sha={}
    for c in m["cases"]:
        sha=c["sha256"]
        per_sha[sha]=dict(gbd=c["gbd"],expected_aliases=EXPECTED_ALIASES.get(sha,0),
           baseline_and_quotient={
             a:[dict(rep=r["rep"],status=r["status"],time_s=r["wall_E2E_s"],
                     aliases=r["validated_aliases"])
                for r in bysha[sha] if r["arm"]==a]
             for a in ARMS})
    pairs={}
    for solver in ("kissat","cadical"):
        for mode in ("clean","scc"):
            differences=[]
            for c in m["cases"]:
                for rep in range(REPS):
                    t=lookup[(c["sha256"],rep,solver+"_"+mode)]
                    b=lookup[(c["sha256"],rep,solver+"_orig")]
                    differences.append(round(par2(t)-par2(b),6))
            pairs[solver+"_"+mode]=dict(
                 wins=sum(d<-.02 for d in differences),
                 losses=sum(d>.02 for d in differences),
                 ties=sum(abs(d)<=.02 for d in differences),
                 biggest_gain_s=min(differences),
                 biggest_regression_s=max(differences))
    report=dict(protocol=PROTO,source_count=NCASE,trial_count=EXPECTED,
        not_blind=True,selected_by_prior_proven_alias_signal=True,
        one_logical_CPU_per_solver=True,
        no_parallel_solver_children=True,
        original_CNF_SHA_unchanged=True,
        alias_count_expected=EXPECTED_ALIASES,
        independent_original_Tarjan_alias_verification=True,
        independent_full_rewritten_CNF_clause_replay=True,
        original_SAT_model_reconstruction_verified=True,
        UNSAT_agreement_source_SHA=sorted(agreed),
        independent_UNSAT_LRAT=False,
        no_auto_promotion=True,
        cap_s=CAP,scores=totals,
        source_classes=classes,
        per_SHA=per_sha,
        paired_differences_vs_original=pairs,
        per_shard={str(i):dict(
             original_count=len({r["sha256"] for r in rows if r["shard"]==i}),
             trial_count=sum(r["shard"]==i for r in rows),
             by_arm={a:scores([r for r in rows if r["arm"]==a and r["shard"]==i])
                     for a in ARMS}) for i in range(SHARDS)})
    save(ROOT/"report.json",report)
    print("BINARY_SCC2_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    a=parser.parse_args()
    if a.action=="shard":shard(a.shard)
    elif a.action=="selftest":selftest()
    else:
        globals()[a.action]()
        if a.action=="verify":print("BINARY_SCC2_VERIFY_PASS",flush=True)
