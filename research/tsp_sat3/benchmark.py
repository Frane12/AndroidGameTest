#!/usr/bin/env python3
"""TSP-SAT3 retrospective paired A/B optimizer research.

Same previously seen TSP-SAT2 seed instances; five arms:
  X59_BASE           original two-smallest-edges LB, no symmetry
  X59_ONE_TREE       certified integer 1-tree LB, no symmetry
  X59_ONE_TREE_SYM   certified 1-tree LB plus reversed-cycle symmetry break
  SG_ONE_TREE_SYM    same with DRNAS Structure Gate solver
  KISSAT_ONE_TREE_SYM external comparison with same strong bound and encoding

Autonomous search NEVER accesses exact Held-Karp dynamic programming.
SAT tours and UNSAT proofs must be independently checked and retained.
This is NOT a new blind holdout, nor a claim of general TSP superiority.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/tsp_sat2"))
import optimizer as base
sys.path.insert(0,str(ROOT/"research/tsp_sat3"))
from one_tree import improve_bound, verify_independent_kruskal

OUT=ROOT/"results/tsp_sat3"
REPS=2
ARMS={
    "X59_BASE":("DRNAS_X59","degree",False),
    "X59_ONE_TREE":("DRNAS_X59","one_tree",False),
    "X59_ONE_TREE_SYM":("DRNAS_X59","one_tree",True),
    "SG_ONE_TREE_SYM":("DRNAS_STRUCTURE_GATE","one_tree",True),
    "KISSAT_ONE_TREE_SYM":("Kissat","one_tree",True)
}
PIN=base.PIN

def sha(p):
    return base.sha(p)

def freeze():
    base.affinity()
    cases=[]
    for name,n,seed in base.CASES:
        coords=base.coords_for(n,seed)
        D=base.enc.euc_distance(coords)
        heuristic=base.two_opt(base.nearest_neighbor(D),D)
        U=base.enc.cost(heuristic,D)
        L,cert=improve_bound(D,U)
        assert verify_independent_kruskal(D,cert)==cert["one_tree_lower_bound"]
        src=OUT/"sources"/(name+".json")
        base.save(src,dict(name=name,n=n,seed=seed,coords=coords,
                          metric="INTEGER_EUC_2D"))
        cases.append(dict(name=name,n=n,seed=seed,coords=coords,
                          source=str(src.relative_to(ROOT)),
                          sha256=sha(src),two_opt_upper=U,
                          one_tree_lower=L,cert=cert))
    manifest=dict(protocol="DRNAS-TSP-SAT3-ONE-TREE-RETROSPECTIVE-V1",
                  source_disjoint_from_tsp_sat2=False,
                  blind_holdout=False,
                  cases=cases)
    base.save(OUT/"manifest.json",manifest)
    proto=dict(protocol=manifest["protocol"],
               git_sha=os.environ.get("GITHUB_SHA"),
               manifest_sha=sha(OUT/"manifest.json"),
               benchmark_sha=sha(Path(__file__)),
               baseline_optimizer_sha=sha(ROOT/"research/tsp_sat2/optimizer.py"),
               bound_sha=sha(ROOT/"research/tsp_sat3/one_tree.py"),
               encoder_sha=sha(ROOT/"research/tsp_sat1/encoding.py"),
               pinned={p:sha(ROOT/p) for p in PIN},
               arms=ARMS,reps=REPS,trials=len(cases)*REPS*len(ARMS),
               per_decision_cap_s=base.CAP_QUERY_S,
               per_case_cap_s=base.CAP_CASE_S,
               sequential_one_cpu=True,no_portfolio=True,
               independent_proof_audit_required=True,
               no_main_promotion=True)
    base.save(OUT/"protocol.json",proto)
    print("TSP_SAT3_READY "+json.dumps(dict(
        instances=len(cases),trials=proto["trials"],
        seeds=[s["seed"] for s in cases],
        first_upper={s["name"]:s["two_opt_upper"] for s in cases},
        one_tree_lower={s["name"]:s["one_tree_lower"] for s in cases},
        retrospective=True),sort_keys=True),flush=True)

def check():
    base.affinity()
    manifest=json.loads((OUT/"manifest.json").read_text())
    proto=json.loads((OUT/"protocol.json").read_text())
    assert proto["protocol"]==manifest["protocol"]
    assert proto["git_sha"]==os.environ.get("GITHUB_SHA")
    assert proto["manifest_sha"]==sha(OUT/"manifest.json")
    assert proto["benchmark_sha"]==sha(Path(__file__))
    assert proto["baseline_optimizer_sha"]==sha(ROOT/"research/tsp_sat2/optimizer.py")
    assert proto["bound_sha"]==sha(ROOT/"research/tsp_sat3/one_tree.py")
    assert proto["encoder_sha"]==sha(ROOT/"research/tsp_sat1/encoding.py")
    assert proto["pinned"]=={p:sha(ROOT/p) for p in PIN}
    assert [(c["name"],c["n"],c["seed"]) for c in manifest["cases"]]==list(base.CASES)
    for case in manifest["cases"]:
        assert case["coords"]==base.coords_for(case["n"],case["seed"])
        assert sha(ROOT/case["source"])==case["sha256"]
        D=base.enc.euc_distance(case["coords"])
        assert verify_independent_kruskal(D,case["cert"])==case["cert"]["one_tree_lower_bound"]
        assert case["one_tree_lower"]==case["cert"]["combined_lower_bound"]
    return manifest,proto

def shard(i):
    manifest,p=check()
    assert 0<=i<len(manifest["cases"])
    case=manifest["cases"][i]
    folder=OUT/f"case-{i}"
    folder.mkdir(parents=True,exist_ok=False)
    records=[]
    for rep in range(REPS):
        order=list(ARMS)
        random.Random(f"tsp3:{case['sha256']}:{rep}").shuffle(order)
        for label in order:
            solver,mode,sym=ARMS[label]
            target=folder/f"{label}-rep{rep}"
            target.mkdir(parents=True,exist_ok=False)
            result=base.optimize(case["coords"],solver,target,
                                 bound_mode=mode,break_reversal=sym)
            result.update(name=case["name"],n=case["n"],rep=rep,
                          label=label,source_sha256=case["sha256"])
            base.save(target/"record.json",result)
            records.append(result)
            with (folder/"trials.jsonl").open("a") as f:
                f.write(json.dumps(result,sort_keys=True)+"\n");f.flush()
            print("TSP_SAT3_TRIAL "+json.dumps(dict(
                name=case["name"],label=label,rep=rep,
                status=result["status"],best=result["best_cost"],
                lower_initial=result["initial_lower_bound"],
                query_count=result["queries"],wall_s=result["wall_s"],
                final_sat_unsat_proof=result["proof_at_bound"]),sort_keys=True),flush=True)
            if result["critical"]:
                raise RuntimeError("CRITICAL_SAT_OR_UNSAT_RESULT")
    assert len(records)==REPS*len(ARMS)
    print("TSP_SAT3_SHARD "+json.dumps(dict(
        index=i,name=case["name"],trials=len(records)),sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("prepare","shard"))
    parser.add_argument("--index",type=int)
    args=parser.parse_args()
    if args.action=="prepare":freeze()
    else:shard(args.index)
