#!/usr/bin/env python3
"""DELTA3 retrospective original SAT2024 paired A/B with independently checked bridge lemmas.

For every solver: same original 36 CNFs, cap 5 seconds, 2 repeats, one
logical CPU. All SAT models checked on original CNF, UNSAT on original proof.
This is a retrospective development cohort, NEVER a blind holdout/promotion.
"""
import argparse
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0,str(Path("research").resolve()))
sys.path.insert(0,str(Path("tests").resolve()))
from drnas_deltacoop2 import paired as P
from test_drnas_deltacoop3 import validate_lemma,canon
import drnas_x55_cpu_real36 as B

P.ARMS=("OFF","JOIN","BRIDGE-SHADOW","BRIDGE","KISSAT","CADICAL")
P.BINS={
    "OFF":"build/drnas-deltacoop2",
    "JOIN":"build/drnas-deltacoop2",
    "BRIDGE-SHADOW":"build/drnas-deltacoop3",
    "BRIDGE":"build/drnas-deltacoop3",
    "KISSAT":"cross/x59/build/kissat",
    "CADICAL":"cross/x59/build/cadical",
}
P.CAP=5.0;P.REPS=2;P.SHARDS=6
base_sample=P.sample

def sample(src,arm,rep,cap,rawdir):
    row=base_sample(src,arm,rep,cap,rawdir)
    row["bridge_independent_resolvents"]=0
    if arm.startswith("BRIDGE"):
        original=B.parse_cnf(Path(src["path"]).read_bytes())[1]
        source={canon(c) for c in original}
        stderr=(rawdir/f"{src['id']}-{rep}-{arm}.stderr").read_text()
        emissions=[]
        for line in stderr.splitlines():
            if line.startswith("DELTA3_LEMMA "):
                certificate=json.loads(line.split(" ",1)[1])
                validate_lemma(certificate,source)
                emissions.append(certificate)
        st=row["stats"].get("DELTA2_JOIN",{})
        if "bridge_injected" not in st:
            raise RuntimeError("DELTA3_TELEMETRY_MISSING")
        if arm=="BRIDGE-SHADOW":
            assert st["bridge_injected"]==0 and not emissions
        else:
            assert len(emissions)<=st["bridge_injected"]
        row["bridge_independent_resolvents"]=len(emissions)
    return row
P.sample=sample

def shard(index):
    P.shard(index,False)
    folder=Path(f"delta2_shards/{index}")
    manifest=json.loads((folder/"manifest.json").read_text())
    manifest["policy"]="delta3-nonlinear-witness-gated-short-original-rup"
    manifest["frozen_delta2_run"]=43584992768
    manifest["experiment_branch"]="experiment/drnas-deltacoop3-nonlinear-clause-20261114"
    P.save(folder/"manifest.json",manifest)
    P.emit("DELTA3_SHARD_PASS",{"shard":index,"originals":6,"trials":72})

def aggregate():
    originals,meta=B.official_manifest()
    rows=[];manifests=[]
    for i in range(P.SHARDS):
        folder=Path(f"delta3_downloads/delta3-shard-{i}/delta2_shards/{i}")
        manifests.append(json.loads((folder/"manifest.json").read_text()))
        rows += [json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
    actual=[(r["sha256"],r["rep"],r["arm"]) for r in rows]
    expected={(s["sha256"],rep,arm) for s in originals for rep in range(P.REPS) for arm in P.ARMS}
    assert len(rows)==36*2*6==432 and len(actual)==len(set(actual)) and set(actual)==expected
    hashes=manifests[0]["binary_sha256"]
    assert hashes["OFF"]==hashes["JOIN"]
    assert hashes["BRIDGE-SHADOW"]==hashes["BRIDGE"]
    assert hashes["BRIDGE"]!=hashes["JOIN"]
    for m in manifests:
        assert tuple(m["arms"])==P.ARMS and m["cap_s"]==P.CAP and m["reps"]==P.REPS
        assert m["source_manifest_sha256"]==meta["manifest_sha256"]
        assert m["binary_sha256"]==hashes and len(m["one_cpu"])==1
        assert m["retrospective"] and not m["blind_holdout"] and not m["promotion"]
        assert m["policy"]=="delta3-nonlinear-witness-gated-short-original-rup"
    verdict=collections.defaultdict(set)
    for r in rows:
        if r["verified"]:verdict[r["sha256"]].add(r["status"])
    assert all(len(v)<=1 for v in verdict.values()),"CONTRADICTORY_VERIFIED_RESULTS"
    fields={}
    math_keys=("bridge_witnesses","bridge_cross_proposals","bridge_unique_candidates",
               "bridge_active_candidates","bridge_shadow_candidates","bridge_injected",
               "bridge_satisfied_skips","bridge_known_skips","analysis_ms",
               "pair_evaluations","tuples_removed","nonlinear_tuple_events",
               "join_certified","join_nonlinear_certified")
    for arm in P.ARMS:
        v=[r for r in rows if r["arm"]==arm]
        fields[arm]={
            "trials":len(v),
            "verified":sum(r["verified"] for r in v),
            "sat_verified":sum(r["status"]=="SAT_VERIFIED" for r in v),
            "unsat_certified":sum(r["status"]=="UNSAT_CERTIFIED" for r in v),
            "par2_verified_s":round(sum(r["PAR2_verified_s"] for r in v),6),
            "bridge_original_rup_logged":sum(r["bridge_independent_resolvents"] for r in v),
            "math":{k:sum(r["stats"].get("DELTA2_JOIN",{}).get(k,0) for r in v)
                    for k in math_keys},
        }
    families=sorted({x["family"] for x in originals})
    f_par2={arm:{family:sum(r["PAR2_verified_s"] for r in rows
                              if r["arm"]==arm and r["family"]==family)
                 for family in families} for arm in P.ARMS}
    rng=random.Random(301114)
    draws=[[rng.choice(families) for _ in families] for _ in range(1200)]
    compares={}
    for baseline in ("OFF","JOIN","BRIDGE-SHADOW","KISSAT","CADICAL"):
        before=fields[baseline]["par2_verified_s"]
        after=fields["BRIDGE"]["par2_verified_s"]
        changes=[]
        for draw in draws:
            b=sum(f_par2[baseline][f] for f in draw)
            a=sum(f_par2["BRIDGE"][f] for f in draw)
            changes.append(100*(b-a)/b if b else 0)
        changes.sort()
        compares[f"BRIDGE_vs_{baseline}"]={
            "verified_par2_gain_pct":round(100*(before-after)/before,5),
            "family_cluster_ci95_pct":[round(changes[29],5),round(changes[1169],5)],
            "verified_solved_delta":fields["BRIDGE"]["verified"]-fields[baseline]["verified"],
        }
    bridge_sources=sorted({r["sha256"] for r in rows
                           if r["arm"]=="BRIDGE" and
                           r["stats"].get("DELTA2_JOIN",{}).get("bridge_injected",0)>0})
    report={"status":"COMPLETE","originals":36,"attempts":432,"reps":2,
            "cap_s":5,"retrospective":True,"blind_holdout":False,"promotion":False,
            "novel_math_claim":False,"one_cpu_per_solver":True,
            "original_sha_manifest":meta["manifest_sha256"],
            "bridge_sources_distinct":len(bridge_sources),
            "bridge_source_shas":bridge_sources,
            "fields":fields,"comparisons":compares,"binary_sha256":hashes}
    out=Path("delta3_final");out.mkdir(exist_ok=True)
    P.save(out/"report.json",report)
    P.save(out/"trials.json",rows)
    P.emit("DELTA3_FINAL",report)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.stage=="shard":shard(a.shard)
    else:aggregate()
if __name__=="__main__":main()
