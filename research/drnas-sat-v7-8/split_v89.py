#!/usr/bin/env python3
"""Two fully disjoint V8.9 structural SAT splits (100 training + 100 holdout).

Usage: SHARD=0 STAGE=train python3 split_v89.py
       SHARD=0 STAGE=test MODEL_FILE=trained-model/model.json python3 split_v89.py

Separate SHA256 domains and distinct pigeonhole cardinalities. The selector is
fitted ONLY after training completes; test phase reads a frozen model file.
All methods use frozen v7.6 / CaDiCaL 3.0.1 via the v89_yield_probe binary.
"""
import csv
import hashlib
import itertools
import json
import math
import os
import random
import tempfile
import time
from pathlib import Path

import blind_v89 as core
from structural_pilot_v89 import structural_features

VERSION="drnas-v89-20-per-class-per-split-20261031-v1"
FAMILIES=("random3","random4","color3","xor3","pigeonhole")
CAP=3.0
REPEATS=3
BASE_MODES=("ca_plain","orig_v76","orig_v76_plain")
FEATURES=("density","mean_width","binary_fraction","degree_cv",
          "max_degree_over_mean","polarity_imbalance",
          "largest_component_fraction","isolated_variable_fraction")
SIZES={
    "random3":(180,205,230,255),
    "random4":(100,120,140,160),
    "color3":(230,280,330,380),
    "xor3":(180,240,300,360),
}
# 40 distinct (holes, pigeon surplus) parameter pairs. Test gets 20 pairs
# that are not isomorphic to any training pair by pigeon/hole cardinalities.
# Surplus >= 2 ensures we do not recycle earlier p=h+1 families.
PIGEON_PAIRS=tuple((h,extra) for h in range(3,13) for extra in (2,3,4,5))
assert len(PIGEON_PAIRS)==40

def specs(split):
    assert split in ("train","test")
    result=[]
    for family in FAMILIES:
        if family=="pigeonhole":
            for i,(holes,extra) in enumerate(PIGEON_PAIRS):
                # Checkerboard split: every hole count and surplus level
                # occurs in BOTH splits, but no exact (holes,surplus) pair does.
                if ((i//4)+(i%4))%2==(0 if split=="train" else 1):
                    result.append((family,holes,extra))
        else:
            for size in SIZES[family]:
                for idx in range(5):
                    result.append((family,size,idx if split=="train" else idx+5))
    assert len(result)==100
    assert all(sum(r[0]==fam for r in result)==20 for fam in FAMILIES)
    return result

def pigeonhole(holes,extra,rng):
    pigeons=holes+extra
    var=lambda p,h:p*holes+h+1
    clauses=[]
    for p in range(pigeons):
        clauses.append([var(p,h) for h in range(holes)])
        for a,b in itertools.combinations(range(holes),2):
            clauses.append([-var(p,a),-var(p,b)])
    for h in range(holes):
        for p,q in itertools.combinations(range(pigeons),2):
            clauses.append([-var(p,h),-var(q,h)])
    return pigeons*holes,clauses,"UNSAT-by-pigeonhole-principle"

def make_case(split,spec,out):
    family,n,inst=spec
    salt=f"{VERSION}:NEW:{split}:{family}:{n}:{inst}"
    seed=int(hashlib.sha256(salt.encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    if family=="pigeonhole":
        nv,clauses,truth=pigeonhole(n,inst,rng)
    else:
        nv,clauses,truth=getattr(core,family)(n,rng)
    perm=list(range(1,nv+1));rng.shuffle(perm)
    flip=[rng.choice((-1,1)) for _ in range(nv)]
    shuffled=[[(1 if l>0 else -1)*perm[abs(l)-1]*flip[abs(l)-1]
               for l in clause] for clause in clauses]
    rng.shuffle(shuffled)
    out.mkdir(parents=True,exist_ok=True)
    path=out/f"{family}-{n}-{inst}-{split}.cnf"
    path.write_text("p cnf %d %d\n"%(nv,len(shuffled))+
                    "".join(" ".join(map(str,c))+" 0\n" for c in shuffled))
    return dict(family=family,size=n,instance=inst,split=split,
                cnf=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                generator_seed=seed,known_truth=truth,vars=nv,
                clauses=len(shuffled),features=structural_features(path))

def historical_hashes(root):
    """Audit against earlier V8.8 / V8.8b / V8.9 / 40-case pilot seeds."""
    import blind_v88
    import blind_v88b
    import blind_v89
    import structural_pilot_v89
    hashes=set()
    records=[
        (blind_v88,blind_v88.EXPERIMENT,blind_v88.SPECS),
        (blind_v88b,blind_v88b.EXPERIMENT,blind_v88b.SPECS),
        (blind_v89,blind_v89.EXPERIMENT,blind_v89.SPECS),
        (blind_v89,structural_pilot_v89.EXPERIMENT,structural_pilot_v89.SPECS),
    ]
    for number,(module,experiment,items) in enumerate(records):
        old_exp,old_out=module.EXPERIMENT,module.OUT
        try:
            module.EXPERIMENT=experiment
            module.OUT=root/("historical-%d"%number)
            module.OUT.mkdir(parents=True,exist_ok=True)
            for spec in items:
                old=module.make_case(*spec)
                if old["sha256"] in hashes:
                    # Earlier experiments may intentionally reuse exact CNFs;
                    # uniqueness here is only required of the new dataset.
                    continue
                hashes.add(old["sha256"])
        finally:
            module.EXPERIMENT, module.OUT=old_exp,old_out
    return hashes

def preflight_only():
    # Exact SHA256 checks across the ENTIRE 200-CNF set before any model fitting.
    # This does not look at test features or performance.
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)
        old=historical_hashes(root)
        train=[make_case("train",spec,root/"train") for spec in specs("train")]
        test=[make_case("test",spec,root/"test") for spec in specs("test")]
        train_hashes={c["sha256"] for c in train}
        test_hashes={c["sha256"] for c in test}
        assert len(train_hashes)==len(test_hashes)==100
        assert not(train_hashes&test_hashes), "TRAIN/TEST CNF COLLISION"
        assert not((train_hashes|test_hashes)&old), "PRIOR EXPERIMENT CNF COLLISION"
        assert set((c["size"],c["instance"]) for c in train if c["family"]=="pigeonhole").isdisjoint(
            (c["size"],c["instance"]) for c in test if c["family"]=="pigeonhole")
    print("200_UNSEEN_CNF_PREFLIGHT_OK train=100 test=100 prior_hashes=%d"%len(old),flush=True)

def decision(model,features):
    if model["policy"]=="always_plain":
        return "orig_v76_plain"
    if model["policy"]=="always_guided":
        return "orig_v76"
    if model["policy"]!="threshold":
        raise ValueError("unrecognized/future model policy")
    feature=model["feature"];value=float(features[feature])
    threshold=float(model["threshold"])
    guided=(value<=threshold if model["direction"]=="le" else value>threshold)
    return "orig_v76" if guided else "orig_v76_plain"

def main():
    stage=os.environ.get("STAGE","train")
    shard=int(os.environ.get("SHARD","0"))
    assert stage in ("train","test") and 0<=shard<5
    model=None
    if stage=="test":
        model=json.loads(Path(os.environ.get("MODEL_FILE","trained-model/model.json")).read_text())
        assert model["version"]==VERSION and model["source_split"]=="train"
    out=Path("structural-v89-200")/stage/("shard-%d"%shard)
    out.mkdir(parents=True,exist_ok=True)
    my_specs=[s for i,s in enumerate(specs(stage)) if i%5==shard]
    assert len(my_specs)==20
    cases=[make_case(stage,s,out) for s in my_specs]
    assert len({c["sha256"] for c in cases})==20
    modes=BASE_MODES+(("trained_selector",) if stage=="test" else ())
    manifest=dict(version=VERSION,stage=stage,shard=shard,
                  cap_s=CAP,repeats=REPEATS,modes=modes,cases=cases)
    if model is not None:
        manifest["model_sha256"]=hashlib.sha256(
            json.dumps(model,sort_keys=True).encode()).hexdigest()
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
    fields=("family","size","instance","split","case","sha256","mode","underlying_mode",
            "repeat","status","wall_s","seed","error","gate_reason",
            "feature_time_s","learned_delta","threshold","hints","active_256",
            "cpu_256_ns","cpu_total_ns")
    affinity=os.sched_getaffinity(0)
    os.sched_setaffinity(0,{min(affinity)})
    rows=[]
    with (out/"raw.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        for case in cases:
            for rep in range(REPEATS):
                order=list(modes)
                random.Random(case["generator_seed"]+rep*941).shuffle(order)
                for mode in order:
                    feature_time=0.0
                    selected=mode
                    if mode=="trained_selector":
                        ts=time.perf_counter()
                        fresh=structural_features(Path(case["cnf"]))
                        selected=decision(model,fresh)
                        feature_time=time.perf_counter()-ts
                    result=core.execute(case,selected,rep)
                    raw_time=result["wall_s"]
                    row=dict(
                        family=case["family"],size=case["size"],
                        instance=case["instance"],split=stage,
                        case=Path(case["cnf"]).stem,sha256=case["sha256"],
                        mode=mode,underlying_mode=selected,repeat=rep,
                        status=result["status"],
                        wall_s=raw_time+feature_time if result["status"]!="TIMEOUT"
                               else CAP,
                        seed=result["seed"],error=result.get("error",""),
                        gate_reason=result.get("gate_reason",""),
                        feature_time_s=feature_time,
                        learned_delta=result.get("learned_delta",""),
                        threshold=result.get("threshold",""),
                        hints=result.get("hints",""),
                        active_256=result.get("active_256",""),
                        cpu_256_ns=result.get("cpu_256_ns",""),
                        cpu_total_ns=result.get("cpu_total_ns",""))
                    rows.append(row)
                    w.writerow(row);f.flush()
                    print("V89_SPLIT",stage,row["case"],rep,mode,selected,
                          row["status"],round(row["wall_s"],4),flush=True)
    assert len(rows)==20*REPEATS*len(modes)
    for case in cases:
        block=[r for r in rows if r["sha256"]==case["sha256"]]
        answers={r["status"] for r in block if r["status"] in ("SAT","UNSAT")}
        if len(answers)>1 or any(r["status"]=="ERROR" for r in block):
            raise RuntimeError("contradiction or solver error: "+case["cnf"])
        if case["known_truth"].startswith("UNSAT") and "SAT" in answers:
            raise RuntimeError("known UNSAT contradicted: "+case["cnf"])
    print("V89_STAGE_SUCCESS",stage,shard,len(rows),flush=True)

if __name__=="__main__":
    if os.environ.get("PREFLIGHT_ONLY")=="1":
        preflight_only()
    else:
        main()
