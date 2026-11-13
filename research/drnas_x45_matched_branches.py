#!/usr/bin/env python3
"""DRNAS X4.5: exact matched-state counterfactual branch-polarity benchmark.

For each formula and target decision index K, run original CDCL once with
its default polarity and once with the opposite polarity at decision K.
The native solver calculates a pre-action hash of the complete trail,
decision levels, phases, variable activities and clause database. Credit a
pair only if BOTH hashes, the selected variable, and the full prefix counters
match; otherwise fail. Post-branch work is independently measured.

SAT is credited only with an external original-CNF witness check.
UNSAT is credited only when n<=18 and an independent exhaustive oracle
establishes no satisfying model. UNKNOWN earns no solved credit.
NO model reads oracle truth or affects the branch selector in this experiment.

Synthetic diagnostic, not globally blind SAT Competition evidence.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import tempfile
import time

FAMILIES=("planted3","planted4","xor_mixed","three_color_planted",
          "community_planted","unsat_php","unsat_k4")
CHECKPOINTS=(1,2,4,8)
REPEATS=3

def emit(name,obj):
    print(name+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def rng_for(family,index):
    digest=hashlib.sha256(f"X45:{family}:{index}:20261113".encode()).digest()
    return random.Random(int.from_bytes(digest[:8],"big"))

def clause_planted(rng,n,witness,k):
    variables=rng.sample(range(1,n+1),k)
    clause=[v*rng.choice((-1,1)) for v in variables]
    if not any(witness[abs(l)]==(l>0) for l in clause):
        clause[rng.randrange(k)]*=-1
    return clause

def add_parity(clauses,variables,target):
    for bits in itertools.product((0,1),repeat=len(variables)):
        if sum(bits)%2!=target:
            clauses.append([-v if bit else v for bit,v in zip(bits,variables)])

def make_case(family,i):
    rng=rng_for(family,i)
    clauses=[]
    oracle="SAT"
    if family in ("planted3","planted4","xor_mixed","community_planted"):
        n=32+(i%22) if family!="planted4" else 34+(i%20)
        witness=[False]+[bool(rng.randrange(2)) for _ in range(n)]
        if family=="planted3":
            for _ in range(round(n*rng.uniform(3.9,5.1))):
                clauses.append(clause_planted(rng,n,witness,3))
        elif family=="planted4":
            for _ in range(round(n*rng.uniform(7.4,10.2))):
                clauses.append(clause_planted(rng,n,witness,4))
        elif family=="xor_mixed":
            for _ in range(n+8):
                vs=rng.sample(range(1,n+1),3)
                desired=sum(int(witness[x]) for x in vs)%2
                add_parity(clauses,vs,desired)
            for _ in range(2*n):
                clauses.append(clause_planted(rng,n,witness,3))
        elif family=="community_planted":
            groups=[list(range(x+1,min(n+1,x+9))) for x in range(0,n,8)]
            for group in groups:
                if len(group)>=3:
                    for _ in range(5*len(group)):
                        variables=rng.sample(group,3)
                        c=[v*rng.choice((-1,1)) for v in variables]
                        if not any(witness[abs(l)]==(l>0) for l in c):c[0]*=-1
                        clauses.append(c)
            for _ in range(n):
                clauses.append(clause_planted(rng,n,witness,3))
    elif family=="three_color_planted":
        nodes=12+i%9
        n=nodes*3
        planted=[rng.randrange(3) for _ in range(nodes)]
        var=lambda v,c:3*v+c+1
        for v in range(nodes):
            clause=[var(v,c) for c in range(3)]
            clauses.append(clause)
            for a,b in itertools.combinations(clause,2):
                clauses.append([-a,-b])
        for a,b in itertools.combinations(range(nodes),2):
            if planted[a]!=planted[b] and rng.random()<rng.uniform(.5,.85):
                for c in range(3):
                    clauses.append([-var(a,c),-var(b,c)])
    elif family=="unsat_php":
        pigeons,holes=4,3;n=12
        oracle="UNSAT_BY_EXHAUSTIVE_ENUMERATION"
        var=lambda p,h:3*p+h+1
        for p in range(pigeons):
            clauses.append([var(p,h) for h in range(holes)])
        for h in range(holes):
            for a,b in itertools.combinations(range(pigeons),2):
                clauses.append([-var(a,h),-var(b,h)])
        for _ in range(3+i%10):
            a,b=rng.sample(range(1,n+1),2)
            clauses.append([a*rng.choice((-1,1)),b*rng.choice((-1,1))])
    elif family=="unsat_k4":
        n=12;oracle="UNSAT_BY_EXHAUSTIVE_ENUMERATION"
        var=lambda v,c:3*v+c+1
        for v in range(4):
            cols=[var(v,c) for c in range(3)]
            clauses.append(cols)
            for a,b in itertools.combinations(cols,2):
                clauses.append([-a,-b])
        for u,v in itertools.combinations(range(4),2):
            for c in range(3):
                clauses.append([-var(u,c),-var(v,c)])
        for _ in range(5+i%13):
            a,b=rng.sample(range(1,n+1),2)
            clauses.append([a*rng.choice((-1,1)),b*rng.choice((-1,1))])
    else:raise ValueError(family)
    # Remove duplicate and tautological clauses. Independently check witness.
    cleaned=[]
    for c in clauses:
        ss=set(c)
        if any(-x in ss for x in ss):continue
        cleaned.append(tuple(sorted(ss,key=lambda x:(abs(x),x<0))))
    normalized=sorted(set(cleaned))
    if family in ("planted3","planted4","xor_mixed","community_planted"):
        assert all(any(witness[abs(l)]==(l>0) for l in c) for c in normalized)
    if family=="three_color_planted":
        assert all(any((planted[(abs(l)-1)//3]==(abs(l)-1)%3)==(l>0)
                       for l in c) for c in normalized)
    content=f"p cnf {n} {len(normalized)}\n"+"".join(
        " ".join(str(x) for x in c)+" 0\n" for c in normalized)
    return {"family":family,"id":i,"n":n,"clauses":normalized,"oracle":oracle,
            "source":content,"sha256":hashlib.sha256(content.encode()).hexdigest()}

def exhaustive_sat(n,clauses):
    if n>18:raise ValueError("exhaustive UNSAT oracle restricted to <=18")
    masks=[]
    for clause in clauses:
        pos=neg=0
        for x in clause:
            if x>0:pos|=1<<(x-1)
            else:neg|=1<<(-x-1)
        masks.append((pos,neg))
    for mask in range(1<<n):
        if all((mask & p)!=0 or (mask&neg)!=neg for p,neg in masks):
            return True
    return False

def check_witness(n,clauses,stdout):
    statuses=[x.strip() for x in stdout.splitlines() if x.startswith("s ")]
    if statuses!=["s SATISFIABLE"]:return False
    assignment={}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for token in line[2:].split():
                lit=int(token)
                if not lit:continue
                if not(1<=abs(lit)<=n) or abs(lit) in assignment:
                    return False
                assignment[abs(lit)]=(lit>0)
    if len(assignment)!=n:return False
    return all(any(assignment[abs(l)]==(l>0) for l in c) for c in clauses)

def trial(binary,case,cnf,index,flip,cap):
    cmd=[str(binary),str(cnf),"--mode","core","--time",str(cap),
         "--branch-at",str(index),"--stats"]
    if flip:cmd+=["--flip-branch"]
    started=time.monotonic()
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+.75)
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","verified":False,"PAR2":2*cap,
                "wall_s":cap,"reached":False,"stats":{},"pre":{}}
    wall=time.monotonic()-started
    if p.returncode not in (0,10,20):
        raise RuntimeError(f"X45 native code {p.returncode}: {p.stderr[-1200:]}")
    stats=[];probe=[]
    for line in p.stderr.splitlines():
        if line.startswith("X41_STATS "):stats.append(json.loads(line[len("X41_STATS "):]))
        if line.startswith("X45_COMPARE "):probe.append(json.loads(line[len("X45_COMPARE "):]))
    if len(probe)!=1 or len(stats)!=1:
        raise AssertionError("missing native X45 comparison or stats telemetry")
    stats=stats[0];pre=probe[0]
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
    truth=(case["oracle"].startswith("UNSAT"))
    verified=(status=="SAT" and not truth and check_witness(case["n"],case["clauses"],p.stdout)
              or status=="UNSAT" and truth)
    if truth and status=="SAT":raise AssertionError("solver SAT on externally exhaustively UNSAT formula")
    if not truth and status=="UNSAT":raise AssertionError("solver UNSAT on constructed SAT formula")
    if status=="SAT" and not verified:raise AssertionError("invalid SAT model against original CNF")
    if status=="UNSAT" and not truth:
        raise AssertionError("UNSAT is not independently checked")
    within=verified and wall<=cap
    return {"status":status,"verified":verified,"within_cap":within,
            "PAR2":round(wall if within else 2*cap,7),
            "wall_s":round(wall,7),"reached":bool(pre["reached"]),
            "pre":pre,"stats":stats,
            "total_decisions":stats["decisions"],"total_conflicts":stats["conflicts"],
            "continuation_decisions":stats["decisions"]-index+1 if pre["reached"] else None,
            "continuation_conflicts":stats["conflicts"]-pre["prefix_conflicts"] if pre["reached"] else None,
            "continuation_s":max(0,stats["elapsed_s"]-pre["prefix_elapsed_s"]) if pre["reached"] else None}

def aggregate(pairs,tag):
    subset=[p for p in pairs if p["family"]==tag] if tag!="ALL" else pairs
    if not subset:return {"pairs":0}
    b=sum(p["base_PAR2"] for p in subset)
    a=sum(p["flip_PAR2"] for p in subset)
    decided=[p for p in subset if p["base_verified"] and p["flip_verified"]]
    d=sum(p["flip_decisions"]<p["base_decisions"] for p in decided)
    t=sum(p["flip_decisions"]>p["base_decisions"] for p in decided)
    u=sum(p["flip_decisions"]==p["base_decisions"] for p in decided)
    conf_delta=sum(p["flip_conflicts"]-p["base_conflicts"] for p in decided)
    return {"pairs":len(subset),"both_verified":len(decided),
        "PAR2_baseline_s":round(b,6),"PAR2_flip_s":round(a,6),
        "PAR2_improvement_flip_pct":round(100*(b-a)/b,4) if b else None,
        "flip_fewer_decisions":d,"baseline_fewer_decisions":t,"same_decisions":u,
        "total_conflict_delta_flip":conf_delta}

def uncertainty(pairs,draws=3000):
    # Cluster all checkpoints/repeats by original SHA (not by measured trial).
    groups=defaultdict(list)
    for row in pairs:groups[row["sha256"]].append(row)
    sources=sorted(groups)
    if not sources:return {}
    rng=random.Random(20261113)
    boot=[]
    for _ in range(draws):
        sampled=[groups[sources[rng.randrange(len(sources))]] for _ in sources]
        flat=[q for grp in sampled for q in grp]
        b=sum(x["base_PAR2"] for x in flat);f=sum(x["flip_PAR2"] for x in flat)
        if b>0:boot.append((b-f)/b)
    boot.sort()
    return {"distinct_original_formulas":len(sources),
       "formula_cluster_95pct_relative_PAR2_improvement":[round(boot[int(.025*(len(boot)-1))],6),
           round(boot[int(.975*(len(boot)-1))],6)],
       "same_formula_multiple_checkpoints_and_repeats_are_not_independent":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,default=Path("build/drnas-x45"))
    p.add_argument("--out",type=Path,default=Path("x45_matched"))
    p.add_argument("--per-family",type=int,default=24)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--cap",type=float,default=.8)
    p.add_argument("--index-offset",type=int,default=200000)
    args=p.parse_args()
    if args.repeats<2 or args.per_family<4 or args.cap<.3 or args.index_offset<100000:
        raise ValueError("bad fixed benchmark size, cap or fresh generator offset")
    args.out.mkdir(parents=True,exist_ok=False)
    binary=args.binary.resolve()
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=[make_case(family,args.index_offset+j) for family in FAMILIES
            for j in range(args.per_family)]
    if len({case["sha256"] for case in cases})!=len(cases):
        raise RuntimeError("duplicate original CNF SHA")
    for case in cases:
        if case["oracle"].startswith("UNSAT") and exhaustive_sat(case["n"],case["clauses"]):
            raise AssertionError("UNSAT construction not verified by independent enumeration")
    (args.out/"manifest.json").write_text(json.dumps({
        "cohort":"X45 fresh generator, original CNF, original SHA-distinct",
        "independent_original_sources":len(cases),"source_family_count":len(FAMILIES),
        "generator_offset":args.index_offset,"checkpoints":CHECKPOINTS,
        "repeats":args.repeats,"cap_s":args.cap,
        "subprocess_runner":"one logical CPU / rotated arms and checkpoints",
        "outcome_certification":"SAT original-CNF witness, UNSAT exhaustive <=18 variables",
        "same_state_identity":"identical pre-state hash, first selected literal, prefix counters",
        "replay_pairs_not_independent":True,
        "sources":[{k:case[k] for k in ("family","id","sha256","n","oracle")}
                   for case in cases]},indent=2,sort_keys=True)+"\n")
    pairs=[];not_reached=Counter();skips=Counter()
    with tempfile.TemporaryDirectory(prefix="x45-matched-") as td:
        cnf=Path(td)/"original.cnf"
        for i,case in enumerate(cases):
            cnf.write_text(case["source"])
            for index in CHECKPOINTS:
                for repeat in range(args.repeats):
                    arms=[False,True] if (i+index+repeat)%2 else [True,False]
                    trials={}
                    for flip in arms:
                        trials[flip]=trial(binary,case,cnf,index,flip,args.cap)
                    b=trials[False];f=trials[True]
                    if b["reached"]!=f["reached"]:
                        raise AssertionError("reached mismatch: intervention changed earlier decisions")
                    if not b["reached"]:
                        skips[(case["family"],index)]+=1
                        continue
                    bp,fp=b["pre"],f["pre"]
                    for key in ("decision_index","pre_state_digest","baseline_literal",
                                "prefix_conflicts","prefix_learnt","prefix_propagations"):
                        if bp[key]!=fp[key]:
                            raise AssertionError("PRE-STATE NOT MATCHED "+key+": "+
                                json.dumps({"source":case["sha256"],"K":index,
                                            "base":bp,"flipped":fp}))
                    if bp["actual_literal"]!=-fp["actual_literal"]:
                        raise AssertionError("two branches are not opposite polarity")
                    if not b["verified"] and not f["verified"]:
                        not_reached["neither_verified"]+=1
                    row={"sha256":case["sha256"],"family":case["family"],"nvars":case["n"],
                        "source_id":case["id"],"checkpoint":index,"repeat":repeat,
                        "pre_state_digest":bp["pre_state_digest"],
                        "selected_variable":abs(bp["baseline_literal"]),
                        "baseline_literal":bp["baseline_literal"],
                        "flipped_literal":fp["actual_literal"],
                        "base_status":b["status"],"flip_status":f["status"],
                        "base_verified":b["verified"],"flip_verified":f["verified"],
                        "base_PAR2":b["PAR2"],"flip_PAR2":f["PAR2"],
                        "base_wall_s":b["wall_s"],"flip_wall_s":f["wall_s"],
                        "base_decisions":b["continuation_decisions"],
                        "flip_decisions":f["continuation_decisions"],
                        "base_conflicts":b["continuation_conflicts"],
                        "flip_conflicts":f["continuation_conflicts"],
                        "base_continue_s":round(b["continuation_s"],7),
                        "flip_continue_s":round(f["continuation_s"],7)}
                    pairs.append(row)
            if (i+1)%20==0:
                with (args.out/"paired.jsonl").open("w") as out:
                    for row in pairs:out.write(json.dumps(row,sort_keys=True)+"\n")
                emit("X45_PROGRESS",{"completed_sources":i+1,"total_sources":len(cases),
                    "matched_pairs":len(pairs),"skipped_not_reached":sum(skips.values())})
    with (args.out/"paired.jsonl").open("w") as out:
        for row in pairs:out.write(json.dumps(row,sort_keys=True)+"\n")
    result={"status":"MATCHED_STATE_ABLATION_FINISHED",
        "distinct_source_formulas":len(cases),"source_families":list(FAMILIES),
        "checkpoint_indices":CHECKPOINTS,"repetitions":args.repeats,
        "matched_pairs":len(pairs),"not_reached_trial_pairs":sum(skips.values()),
        "unverified_pairs":sum(not(p["base_verified"] and p["flip_verified"]) for p in pairs),
        "groups":{family:aggregate(pairs,family) for family in FAMILIES},
        "by_checkpoint":{str(k):{
          "matched_pairs":sum(p["checkpoint"]==k for p in pairs),
          "flip_fewer_decisions":sum(p["checkpoint"]==k and p["flip_verified"] and p["base_verified"]
                                     and p["flip_decisions"]<p["base_decisions"] for p in pairs),
          "baseline_fewer_decisions":sum(p["checkpoint"]==k and p["flip_verified"] and p["base_verified"]
                                     and p["flip_decisions"]>p["base_decisions"] for p in pairs)}
          for k in CHECKPOINTS},
        "total":aggregate(pairs,"ALL"),
        "formula_cluster_uncertainty":uncertainty(pairs),
        "runtime_measurement_note":"Submillisecond process startup/timing noise; conflict/decision differences are stronger deterministic search-work evidence.",
        "counterfactual_scope":"same deterministic prefix in separate full runs; only polarity at designated decision differs; not alternative variable or proof generation strategy",
        "no_training_and_no_policy_selection":True,
        "SAT_original_CNF_model_verified":True,
        "UNSAT_only_small_exhaustive":True,
        "e2e_speedups_not_general_SAT_claim":True}
    (args.out/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    emit("X45_FINAL",result)

if __name__=="__main__":main()
