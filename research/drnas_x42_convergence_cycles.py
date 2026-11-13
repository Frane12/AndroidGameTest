#!/usr/bin/env python3
"""DRNAS X4.2: three trajectory cycles, independently scored by exact SAT oracle.

Only for small n<=18. The observer never reads oracle truth, satisfying models
or planted witness. It records complete *current decision/BCP trail* only in
diagnostic mode. Ground truth is independently enumerated AFTER execution.

This is a controlled diagnostic, not a general computable SAT-distance function.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import tempfile
import time

FAMILIES=("planted3","planted_xor","planted_2sat","php_unsat")
WINDOWS=((1,8),(9,16),(17,128))

def emit(tag, obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def build_case(family,i):
    rng=random.Random(0x46020261113+100003*FAMILIES.index(family)+7919*i)
    clauses=[]
    n=12+(i%6)
    target=[None]+[bool(rng.randrange(2)) for _ in range(n)]
    def planted_clause(k):
        vs=rng.sample(range(1,n+1),k)
        signs=[v*rng.choice((-1,1)) for v in vs]
        if not any((v>0)==target[abs(v)] for v in signs):
            signs[rng.randrange(k)]*=-1
        return signs
    if family=="planted3":
        clauses=[planted_clause(3) for _ in range(5*n)]
    elif family=="planted_2sat":
        clauses=[planted_clause(2) for _ in range(6*n)]
    elif family=="planted_xor":
        for _ in range(n+4):
            vs=rng.sample(range(1,n+1),3)
            desired=sum(target[v] for v in vs)%2
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=desired:
                    clauses.append([(-v if b else v) for v,b in zip(vs,bits)])
        clauses.extend(planted_clause(3) for _ in range(n))
    elif family=="php_unsat":
        holes=3 if i%2 else 2
        pigeons=holes+1
        n=holes*pigeons
        v=lambda p,h:p*holes+h+1
        clauses.extend([[v(p,h) for h in range(holes)] for p in range(pigeons)])
        for h in range(holes):
            for p in range(pigeons):
                for q in range(p+1,pigeons):
                    clauses.append([-v(p,h),-v(q,h)])
        for _ in range(3+i%7):
            a,b=rng.sample(range(1,n+1),2)
            clauses.append([a*rng.choice((-1,1)),b*rng.choice((-1,1))])
        target=None
    else:raise ValueError(family)
    clean=sorted(set(tuple(sorted(set(c),key=lambda v:(abs(v),v<0))) for c in clauses))
    if target is not None:
        assert all(any((l>0)==target[abs(l)] for l in c) for c in clean)
    return {"n":n,"clauses":[list(x) for x in clean],
            "family":family,"base_id":i,"has_planted_witness":target is not None}

def literal_masks(clauses):
    result=[]
    for clause in clauses:
        positive,negative=0,0
        for l in clause:
            bit=1<<(abs(l)-1)
            if l>0:positive|=bit
            else:negative|=bit
        if positive&negative:continue
        result.append((positive,negative))
    return result

def exact_models(n,clauses):
    # This exhaustive small-n oracle is independent of the native solver's
    # watches, trail logic, CDCL heuristics, and internal SAT/UNSAT declaration.
    masks=literal_masks(clauses)
    output=[]
    for bits in range(1<<n):
        if all((bits&p)!=0 or (bits&neg)!=neg for p,neg in masks):
            output.append(bits)
    return output

def permute(n,clauses,rng,cycle):
    p=[0]+list(range(1,n+1))
    if cycle:
        rng.shuffle(p[1:])  # Do not rely on slice in-place; set explicitly.
        target=list(range(1,n+1))
        rng.shuffle(target)
        p=[0]+target
    newclauses=[[p[abs(l)]*(1 if l>0 else -1) for l in c] for c in clauses]
    return newclauses,p

def transform_model(mask,permutation):
    result=0
    for original in range(1,len(permutation)):
        if mask>>(original-1)&1:
            result|=1<<(permutation[original]-1)
    return result

def write_dimacs(path,n,clauses):
    content=f"p cnf {n} {len(clauses)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in clauses)
    path.write_text(content)
    return hashlib.sha256(content.encode()).hexdigest()

def measure(n,models,trail):
    positive=0;negative=0
    for l in trail:
        bit=1<<(abs(l)-1)
        if l==0 or abs(l)>n or ((positive|negative)&bit):
            raise AssertionError("bad or duplicated native trail literal")
        if l>0:positive|=bit
        else:negative|=bit
    known=positive|negative
    free=n-len(trail)
    good=0;min_flips=n+1
    for bits in models:
        if (bits&known)==positive:good+=1
        flipped=((bits^positive)&known).bit_count()
        if flipped<min_flips:min_flips=flipped
    if not models:
        return {"sat_completion_exists":False,"solution_count":0,
                "conditional_completion_probability":None,
                "min_hamming_flips_to_any_solution":None,
                "assigned":len(trail)}
    return {"sat_completion_exists":good>0,"solution_count":good,
            "conditional_completion_probability":good/(1<<free),
            "min_hamming_flips_to_any_solution":min_flips,
            "assigned":len(trail)}

def external_model_ok(n,clauses,stdout):
    status=[x.strip() for x in stdout.splitlines() if x.startswith("s ")]
    if status!=["s SATISFIABLE"]:return False
    assignment={}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for piece in line[1:].split():
                l=int(piece)
                if l==0:continue
                if abs(l)>n or abs(l) in assignment:return False
                assignment[abs(l)]=l>0
    if len(assignment)!=n:return False
    return all(any(assignment[abs(l)]==(l>0) for l in c) for c in clauses)

def analyze_run(source,cycle,binary,root,limit,base_models):
    n,clauses=source["n"],source["clauses"]
    permuted,p=permute(n,clauses,random.Random(9900+source["base_id"]*71+
                                             FAMILIES.index(source["family"])*13+cycle*147),cycle)
    models=[transform_model(m,p) for m in base_models]
    cnf=root/"input.cnf";trace=root/"trace.jsonl"
    sha=write_dimacs(cnf,n,permuted)
    core_cmd=[str(binary.resolve()),str(cnf),"--mode","trace","--time",str(limit),
              "--stats","--transitions",str(trace),"--trace-trail"]
    started=time.monotonic()
    p1=subprocess.run(core_cmd,capture_output=True,text=True,timeout=limit+1.0)
    wall=time.monotonic()-started
    if p1.returncode not in (0,10,20):
        raise RuntimeError("X4 diagnostic solver crash "+str(p1.returncode)+" "+p1.stderr[-1200:])
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p1.returncode]
    if status=="SAT":
        if not models or not external_model_ok(n,permuted,p1.stdout):
            raise AssertionError("unverified SAT original CNF")
    if status=="UNSAT" and models:raise AssertionError("native false UNSAT")
    if status=="UNKNOWN":
        raise AssertionError("diagnostic did not finish; increase cap or reduce case")
    if models and status!="SAT":raise AssertionError("missed SAT within cap")
    if not models and status!="UNSAT":raise AssertionError("missed UNSAT within cap")
    rows=[json.loads(x) for x in trace.read_text().splitlines()]
    assert rows[0]["type"]=="meta" and rows[0]["observational_only"]
    transitions=[x for x in rows[1:] if x["type"]=="transition"]
    if len(transitions)>128:raise AssertionError("overlong diagnostic trace")
    events=[]
    for rec in transitions:
        before=rec["before"];after=rec["after"]
        t0=rec.get("trail_before");t1=rec.get("trail_after")
        assert t0 is not None and t1 is not None
        assert len(t0)==before["assigned"] and len(t1)==after["assigned"]
        q0,q1=measure(n,models,t0),measure(n,models,t1)
        # IMPORTANT: zero SAT completion means inconsistent partial trail,
        # not a proof that the original SAT formula itself is unsatisfiable.
        delta=(q1["conditional_completion_probability"]-q0["conditional_completion_probability"]
               if models else None)
        classification="UNSAT_UNDEFINED"
        if delta is not None:
            classification=("toward" if delta>1e-12 else
                            "away" if delta < -1e-12 else "flat")
        events.append({"decision":after["decisions"],"delta_p":delta,
            "direction":classification,
            "exact_probability_before":q0["conditional_completion_probability"],
            "exact_probability_after":q1["conditional_completion_probability"],
            "satisfying_completion_exists_after":q1["sat_completion_exists"],
            "min_flips_before":q0["min_hamming_flips_to_any_solution"],
            "min_flips_after":q1["min_hamming_flips_to_any_solution"],
            "sampled_delta_satisfied":rec["structure"]["delta_satisfied"],
            "delta_conflicts":after["conflicts"]-before["conflicts"],
            "unit_propagations":rec["logic"]["unit_propagations_under_assumptions"]})
    if status=="SAT" and not models:raise AssertionError("oracle says no SAT solution")
    windows=[]
    for lo,hi in WINDOWS:
        subset=[x for x in events if lo<=x["decision"]<=hi]
        directions=Counter(x["direction"] for x in subset)
        diffs=[x["delta_p"] for x in subset if x["delta_p"] is not None]
        windows.append({"window":f"decisions_{lo}_{hi}","samples":len(subset),
            "toward":directions["toward"],"away":directions["away"],
            "flat":directions["flat"],"mean_exact_probability_change":(
                round(statistics.mean(diffs),8) if diffs else None),
            "branch_incompatible_count":sum(
                x["satisfying_completion_exists_after"] is False for x in subset)})
    return {"family":source["family"],"base_id":source["base_id"],
        "cycle":cycle,"sha256":sha,"nvars":n,"oracle_solution_count":len(models),
        "status":status,"oracle_independently_verified":True,
        "native_wall_s":round(wall,6),"transitions":len(events),
        "path":events,"windows":windows}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--binary",type=Path,default=Path("build/drnas-x42"))
    parser.add_argument("--out",type=Path,default=Path("x42_convergence"))
    parser.add_argument("--per-family",type=int,default=8)
    parser.add_argument("--cycles",type=int,default=3)
    parser.add_argument("--cap",type=float,default=1.5)
    args=parser.parse_args()
    if args.per_family<3 or args.cycles!=3 or args.cap<0.2:
        raise ValueError("expect at least 3 per family and exactly 3 search cycles")
    args.out.mkdir(parents=True,exist_ok=False)
    all_rows=[]
    with tempfile.TemporaryDirectory(prefix="x42-") as td:
        root=Path(td)
        for family in FAMILIES:
            for i in range(args.per_family):
                case=build_case(family,i)
                models=exact_models(case["n"],case["clauses"])
                if case["has_planted_witness"] and not models:raise AssertionError("planted SAT missing")
                if family=="php_unsat" and models:raise AssertionError("PHP construction not UNSAT")
                for cycle in range(args.cycles):
                    row=analyze_run(case,cycle,args.binary,root,args.cap,models)
                    all_rows.append(row)
                    emit("X42_CYCLE",{"family":family,"id":i,"cycle":cycle,
                        "status":row["status"],"transitions":row["transitions"],
                        "toward":sum(x["toward"] for x in row["windows"]),
                        "away":sum(x["away"] for x in row["windows"]),
                        "flat":sum(x["flat"] for x in row["windows"]),
                        "incompatible_branch_steps":sum(x["branch_incompatible_count"]
                                                         for x in row["windows"])})
    if len({x["sha256"] for x in all_rows})!=len(all_rows):
        raise AssertionError("duplicate permutation cycles")
    (args.out/"trajectories.jsonl").write_text(
        "".join(json.dumps(row,sort_keys=True)+"\n" for row in all_rows))
    by_cycle={}
    for cycle in range(args.cycles):
        rows=[r for r in all_rows if r["cycle"]==cycle]
        events=[ev for r in rows if r["status"]=="SAT" for ev in r["path"]]
        counter=Counter(e["direction"] for e in events)
        samples=sum(r["transitions"] for r in rows)
        by_cycle[str(cycle+1)]={"runs":len(rows),"sat_verified":sum(r["status"]=="SAT" for r in rows),
            "unsat_exhaustive_oracle":sum(r["status"]=="UNSAT" for r in rows),
            "sampled_steps":samples,
            "toward":counter["toward"],"away":counter["away"],"flat":counter["flat"],
            "branch_incompatible":sum(
                e["satisfying_completion_exists_after"] is False for e in events)}
    window_summary=[]
    for k,(lo,hi) in enumerate(WINDOWS):
        w=[r["windows"][k] for r in all_rows if r["status"]=="SAT"]
        window_summary.append({"decision_window":f"{lo}-{hi}",
            "observations":sum(x["samples"] for x in w),
            "toward":sum(x["toward"] for x in w),
            "away":sum(x["away"] for x in w),
            "flat":sum(x["flat"] for x in w)})
    sat_events=[e for r in all_rows if r["status"]=="SAT" for e in r["path"]]
    comparisons=[e for e in sat_events if e["delta_p"] is not None and e["delta_p"]!=0
                 and e["sampled_delta_satisfied"]!=0]
    agrees=sum((e["delta_p"]>0)==(e["sampled_delta_satisfied"]>0) for e in comparisons)
    report={"protocol":"X4.2 exact small-CNF retrospective search-direction diagnostic",
        "independent_CNF_sources":len(FAMILIES)*args.per_family,
        "3_isomorphic_replay_cycles":True,
        "replays_are_not_independent_formulas":True,
        "runs":len(all_rows),"verified_sat":sum(r["status"]=="SAT" for r in all_rows),
        "exhaustively_checked_unsat":sum(r["status"]=="UNSAT" for r in all_rows),
        "cycle_summary":by_cycle,"decision_windows":window_summary,
        "structural_proxy_direction_agreement":{
            "eligible_nonflat_events":len(comparisons),"same_sign":agrees,
            "agreement_fraction":round(agrees/len(comparisons),5) if comparisons else None},
        "important_limits":[
            "Minimum Hamming flips and random-completion probabilities use exponential offline oracle enumeration.",
            "These quantities are not generally computable cheaply for large SAT instances.",
            "An episode with zero compatible solutions may later recover by CDCL backtracking.",
            "CNF satisfiability is invariant across cycles; cycles change representation, not logical truth.",
            "Retrospective observations do not measure causal utility of alternative actions."
        ]}
    (args.out/"summary.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("X42_FINAL",report)

if __name__=="__main__":
    main()
