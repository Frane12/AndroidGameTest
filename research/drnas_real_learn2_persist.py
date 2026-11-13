#!/usr/bin/env python3
"""Append-only REAL2 verified benchmark evidence with immutable split and engine audit."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path

PROTOCOL="DRNAS-REAL-LEARN2-v1"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def put(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(body,sort_keys=True,indent=2)+"\n")

def trials(path,split,cap,arms,repeats,allowed):
    all_rows=[];by_source=collections.defaultdict(list);shards=[]
    for manifest in sorted(Path(path).rglob("manifest.json")):
        m=read(manifest);shards.append(m)
        if m["cap"]!=cap or m["stage"]!=split or m["repeats"]!=repeats or tuple(m["arms"])!=arms:
            raise RuntimeError("incorrect trial manifest cap/stage/arms")
        if m["logical_cpu_count"]!=1:
            raise RuntimeError("not pinned to one logical CPU")
        for line in (manifest.parent/"trials.jsonl").read_text().splitlines():
            if not line.strip():continue
            row=json.loads(line)
            if row["sha256"] not in allowed or row["split"] != allowed[row["sha256"]]:
                raise RuntimeError("sample outside locked source split")
            if row["accepted"] and not row["verified"]:
                raise RuntimeError("uncertified row received solved credit")
            if row["PAR2"]!=(row["e2e_s"] if row["accepted"] else 2*cap):
                raise RuntimeError("PAR2 mismatch")
            by_source[row["sha256"]].append(row);all_rows.append(row)
    if len(shards)!=8 or {m["shard"] for m in shards}!=set(range(8)):
        raise RuntimeError("missing shard manifests")
    expected={h for h,s in allowed.items() if (split=="holdout" and s=="holdout") or
              (split=="train" and s in ("train","validation"))}
    if set(by_source)!=expected:
        raise RuntimeError("source coverage incomplete")
    for source,items in by_source.items():
        if {(r["arm"],r["rep"]) for r in items}!={(arm,k) for arm in arms for k in range(repeats)}:
            raise RuntimeError("missing paired arm/repetition")
    return all_rows

def persist(args):
    delta=read(args.delta)["sources"]
    material=read(args.material);splits=read(args.splits)
    report=read(args.report);policy=read(args.policy)
    if report["status"]!="COMPLETE" or report["promoted"] or policy["promoted"]:
        raise RuntimeError("experiment must never deploy policy")
    if policy.get("extension")!=PROTOCOL:
        raise RuntimeError("model version changed")
    cap=report["cap_s"]
    if cap!=15.0 or policy["cap_s"]!=cap:
        raise RuntimeError("training caps mismatched")
    if len(delta)!=splits["source_count"] or len(delta)!=material["selected"]:
        raise RuntimeError("source manifest mismatch")
    if {x["sha256"] for x in delta}!={x["sha256"] for x in splits["sources"]}:
        raise RuntimeError("source SHA identity mismatch")
    seen={};sem=set();family_roles={}
    original=read(args.old_splits)
    for src in original["sources"]:
        family_roles[src["family"]]=src["split"]
    catalog_path=args.root/"catalog.json"
    catalog=read(catalog_path) if catalog_path.exists() else {"protocol":PROTOCOL,"sources":[]}
    if catalog.get("protocol")!=PROTOCOL:
        raise RuntimeError("wrong catalog version")
    for src in catalog["sources"]:
        seen[src["sha256"]]=src
        sem.add(src["semantic_sha"])
        fam=src["family"]
        if fam in family_roles and family_roles[fam]!=src["split"]:
            raise RuntimeError("historical family leakage")
        family_roles[fam]=src["split"]
    if report["holdout_sources"]!=splits["split_counts"]["holdout"]:
        raise RuntimeError("holdout count mismatched")
    for src in delta:
        if src["sha256"] in seen or src["semantic_sha"] in sem:
            raise RuntimeError("duplicate source from previous cycles")
        fam=src["family"];role=src["split"]
        if fam in family_roles and family_roles[fam]!=role:
            raise RuntimeError("cross-cycle train/validation/holdout family contamination")
        family_roles[fam]=role
        seen[src["sha256"]]=src
        sem.add(src["semantic_sha"])
    allowed={r["sha256"]:r["split"] for r in delta}
    train_rows=trials(args.train_dir,"train",cap,("CORE","X5_NO_MIN","X52_LBD"),1,allowed)
    holdout_rows=trials(args.holdout_dir,"holdout",cap,
                        ("CORE","X5_NO_MIN","X52_LBD","LEARN1_ROUTED","Kissat","CaDiCaL"),2,allowed)
    groups={"train":[],"validation":[],"holdout":[]}
    for r in train_rows+holdout_rows:
        groups[r["split"]].append(r)
    for split in groups:
        expected=sum(s["split"]==split for s in delta)
        # Holdout has six arms and two paired repeats; TRAIN has three arms once.
        expected*=12 if split=="holdout" else 3
        if len(groups[split])!=expected:
            raise RuntimeError("one split missing paired trial rows")
    if any(r["effective_arm"]!="CORE" for r in groups["holdout"] if
           r["arm"]=="LEARN1_ROUTED") and not policy["model_activated"]:
        raise RuntimeError("unpromoted model unexpectedly intervened")
    run=args.root/"runs"/args.run_id
    run.mkdir(parents=True,exist_ok=False)
    copies={"splits.json":splits,"catalog_delta.json":{"sources":delta},
            "material.json":material,"policy.json":policy,"final_report.json":report}
    for name,value in copies.items():put(run/name,value)
    engine_sha=sha(args.engine_source.read_bytes())
    eligible=collections.Counter()
    for split,rows in groups.items():
        data=("\n".join(json.dumps(r,sort_keys=True,separators=(",",":")) for r in rows)+"\n").encode()
        (run/(split+".jsonl.gz")).write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
        source_status=collections.defaultdict(bool)
        for row in rows:
            source_status[row["sha256"]]|=bool(row["accepted"])
        eligible[split]=sum(source_status.values())
    audit={"protocol":PROTOCOL,"cap_s":cap,"engine_sha":engine_sha,
           "sources":len(delta),"train_sources":splits["split_counts"]["train"],
           "validation_sources":splits["split_counts"]["validation"],
           "holdout_sources":splits["split_counts"]["holdout"],
           "verified_source_counts":dict(eligible),
           "trials":{k:len(v) for k,v in groups.items()},
           "holdout_never_train":True,"model_never_deployed":True,
           "SAT_requires_original_witness":True,"UNSAT_requires_independent_proof":True}
    put(run/"training_audit.json",audit)
    catalog["sources"]+=delta
    put(catalog_path,catalog)
    latest={
        "protocol":PROTOCOL,"last_run":args.run_id,
        "cumulative_unique_original_sources":len(catalog["sources"]),
        "cumulative_train_sources":sum(s["split"]=="train" for s in catalog["sources"]),
        "cumulative_validation_sources":sum(s["split"]=="validation" for s in catalog["sources"]),
        "cumulative_sealed_holdout_sources":sum(s["split"]=="holdout" for s in catalog["sources"]),
        "last_material":material,
        "last_training_verified_source_counts":dict(eligible),
        "cumulative_training_informative":policy["informative_train_sources"],
        "training_sources_used_this_cycle":policy["train_sources"],
        "model_activated":policy["model_activated"],"model_reasons":policy["reasons"],
        "holdout_reference_core_PAR2":report["arms"]["CORE"]["PAR2_s"],
        "holdout_learned_PAR2":report["arms"]["LEARN1_ROUTED"]["PAR2_s"],
        "candidate_for_replication":report["eligible_for_later_independent_replication"],
        "promoted":False,
        "run_path":str(run),
    }
    put(args.root/"latest.json",latest)
    print("REAL2_PERSISTED",json.dumps({"last_run":args.run_id,
        "total_sources":latest["cumulative_unique_original_sources"],
        "verified":dict(eligible),"informative_train":policy["informative_train_sources"],
        "candidate_for_replication":latest["candidate_for_replication"]},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    for key in ("root","delta","material","splits","policy","report","train_dir","holdout_dir","old_splits","engine_source"):
        p.add_argument("--"+key.replace("_","-"),type=Path,required=True)
    p.add_argument("--run-id",required=True)
    persist(p.parse_args())
