#!/usr/bin/env python3
"""DELTAX-GRAPHLAB1: explain selective GUARD utility in graph 3-coloring.

Four modes of exactly the SAME frozen DELTAX-GUARD1 native executable:
JOIN, SHADOW, DELTAX, DELTAX-GUARD. Source-original SAT witness checked;
independent original-CNF DRAT needed for all credited UNSAT verdicts.
All graph class labels and color certificates are only seen by TEST harness,
never the native solver. Avoid claiming broad generalization from one seed.
"""
import argparse
import collections
import hashlib
import json
import os
import random
import sys
from pathlib import Path

R=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(R/"research/drnas_deltax_guard"),
             str(R/"research/drnas_deltax"),str(R/"research")]
from drnas_deltax_guard import paired as P
from graphlab_sources import write as generate

ARMS=P.ARMS
SHARDS=4
CAP=4.0

def sha(data):return hashlib.sha256(data).hexdigest()
def emit(tag,value):P.emit(tag,value)

def manifest():
    path=R/"deltax_graphlab1_inputs/manifest.json"
    original=json.loads(path.read_text())
    assert len(original)==20 and len({c["sha256"] for c in original})==20
    assert sum(c["motifs"]==0 for c in original)==2
    for c in original:
        assert sha((R/c["path"]).read_bytes())==c["sha256"],("SOURCE_DRIFT",c["name"])
        assert c["original_graph_certificate_checked"]
    return original,sha(path.read_bytes())

def expected(s):
    return "SAT_VERIFIED" if s["expected_by_graph"]=="SAT" else "UNSAT_CERTIFIED"

def check_result(s,trial):
    assert trial["guard_invalid_source"]==0,("INVALID_SOURCE_CLAUSE",s["name"])
    assert trial["guard_clones_inconsistent"]==0,("CLONE_DIVERGENCE",s["name"])
    if trial["verified"]:
        assert trial["status"]==expected(s),("GRAPH_THEOREM_DISAGREES_WITH_CNF",s["name"],trial)
    if s["motifs"]==0:
        assert trial["guard_accepted"]==0 and trial["deltax_lemmas"]==0,(
            "CONTROL_WITHOUT_GADGET_WAS_ALIASED",s["name"],trial)

def add_links(s,trial,folder):
    trial["source_kind"]="graphlab_original_nonlinear_motif"
    trial["graph_kind"]=s["graph_kind"]
    trial["graph_vertices"]=s["graph_vertices"]
    trial["graph_edges"]=s["graph_edges"]
    trial["motifs"]=s["motifs"]
    trial["permuted"]=s["permuted"]
    trial["accepted_graph_links"]=[]
    if trial["arm"]!="deltax-guard":return trial
    path=folder/"raw"/(s["name"]+"-deltax-guard.events.json")
    if not path.exists():return trial
    events=json.loads(path.read_text())
    assert len(events["aliases"])<=trial["deltax_lemmas"]
    for e in events["aliases"]:
        links=[link for link in s["gadget_to_graph_links"]
               if link["y"] in (e["a"],e["b"])]
        trial["accepted_graph_links"].append({
            "guard":e["guard"],"a":e["a"],"b":e["b"],
            "original_source_clause":e["forward"],
            "core_links":links,
        })
    if events["aliases"]:
        P.save(folder/"graph_link_audit"/(s["name"]+".json"),{
            "name":s["name"],"graph_type":s["graph_kind"],
            "graph_vertices":s["graph_vertices"],
            "edges":s["graph_edges_explicit"],
            "links_to_coloring_variables":s["gadget_to_graph_links"],
            "guarded_source_lemmas":events["aliases"],
            "paired_clone_probes":events["probe_samples"],
            "actual_cdcl_propagation_reasons":events["causal"]})
    return trial

def run_one(s,arm,cap,out):
    row=P.trial(s,arm,cap,out/"raw")
    check_result(s,row)
    add_links(s,row,out)
    return row

def preflight():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    sources=generate("deltax_graphlab1_inputs")
    assert len(sources)==20
    select=[];seen=set()
    for s in sources:
        category=s["graph_kind"] if s["motifs"] else "no_motif"
        if category not in seen:select.append(s);seen.add(category)
    assert len(select)==5
    out=R/"deltax_graphlab1_preflight"
    rows=[]
    for s in select:
        for arm in ARMS:
            rows.append(run_one(s,arm,2.0,out))
    assert len(rows)==20
    verified=sum(r["verified"] for r in rows)
    assert verified>=12,("PREFLIGHT_TOO_MANY_TIMEOUTS",verified)
    P.save(out/"report.json",{
        "status":"PASS","source_manifest_sha256":manifest()[1],
        "graph_classes":sorted(seen),"cases":len(select),
        "trials":len(rows),"verified":verified,"single_logical_cpu":True,
        "source_proof_verification":True,"experimental_only":True})
    emit("DELTAX_GRAPHLAB_PREFLIGHT_PASS",{
        "cases":len(select),"trials":len(rows),"verified":verified})

def shard(index):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    data,checksum=manifest()
    select=[x for i,x in enumerate(data) if i%SHARDS==index]
    out=R/f"deltax_graphlab1_shards/{index}"
    out.mkdir(parents=True,exist_ok=False)
    P.save(out/"manifest.json",{
        "shard":index,"source_manifest_sha256":checksum,
        "arms":ARMS,"cap_s":CAP,"one_cpu":sorted(os.sched_getaffinity(0)),
        "binary_sha256":P.sha(P.BINARY),"drat_sha256":P.sha(P.DRAT),
        "blind_holdout":False,"retrospective_protocol":True,
        "no_promotion":True})
    with (out/"trials.jsonl").open("w") as f:
        for s in select:
            arms=list(ARMS)
            random.Random(int(s["sha256"][:16],16)).shuffle(arms)
            for arm in arms:
                row=run_one(s,arm,CAP,out)
                f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
                emit("DELTAX_GRAPHLAB_TRIAL",{
                    "name":s["name"],"type":s["graph_kind"],
                    "arm":arm,"verified":row["verified"],"status":row["status"],
                    "decisions":row["decisions"],"conflicts":row["conflicts"],
                    "approvals":row["guard_accepted"],"vetoes":row["guard_rejected"],
                    "injected":row["deltax_lemmas"],
                    "causal":row["causal_enqueues"]})
    emit("DELTAX_GRAPHLAB_SHARD_PASS",{"shard":index,"trials":len(select)*len(ARMS)})

def aggregate():
    sources,manifest_sha=manifest()
    recs=[];manifests=[]
    for i in range(SHARDS):
        path=R/f"deltax_graphlab1_downloads/deltax-graphlab-shard-{i}/deltax_graphlab1_shards/{i}"
        manifests.append(json.loads((path/"manifest.json").read_text()))
        recs.extend(json.loads(s) for s in (path/"trials.jsonl").read_text().splitlines())
    keys={(s["sha256"],arm) for s in sources for arm in ARMS}
    actual=[(x["sha256"],x["arm"]) for x in recs]
    assert len(actual)==len(keys)==80 and len(set(actual))==80 and set(actual)==keys
    for m in manifests:
        assert m["source_manifest_sha256"]==manifest_sha
        assert tuple(m["arms"])==ARMS and m["cap_s"]==CAP and len(m["one_cpu"])==1
        assert m["binary_sha256"]==manifests[0]["binary_sha256"]
        assert m["drat_sha256"]==manifests[0]["drat_sha256"]
        assert not m["blind_holdout"] and m["retrospective_protocol"] and m["no_promotion"]
    verdict=collections.defaultdict(set)
    for row in recs:
        if row["verified"]:verdict[row["sha256"]].add(row["status"])
        assert row["guard_invalid_source"]==row["guard_clones_inconsistent"]==0
    assert all(len(v)<=1 for v in verdict.values()),"CONTRADICTORY_SOLVER_CERTIFICATES"
    bykey={(r["sha256"],r["arm"]):r for r in recs}
    arms={}
    for a in ARMS:
        r=[x for x in recs if x["arm"]==a]
        arms[a]={
            "sources":len(r),
            "verified":sum(x["verified"] for x in r),
            "sat_verified":sum(x["verified"] and x["status"]=="SAT_VERIFIED" for x in r),
            "unsat_certified":sum(x["verified"] and x["status"]=="UNSAT_CERTIFIED" for x in r),
            "unknown":sum(not x["verified"] for x in r),
            "guard_checked":sum(x["guard_checks"] for x in r),
            "guard_accepted":sum(x["guard_accepted"] for x in r),
            "guard_vetoed":sum(x["guard_rejected"] for x in r),
            "proof_lemmas":sum(x["deltax_lemmas"] for x in r),
            "causal_propagations":sum(x["causal_enqueues"] for x in r)
        }
    paired=[]
    for src in sources:
        rows={a:bykey[(src["sha256"],a)] for a in ARMS}
        same=all(rows[a]["verified"] for a in ARMS)
        pair={"name":src["name"],"graph_kind":src["graph_kind"],
              "vertices":src["graph_vertices"],"edges":src["graph_edges"],
              "motifs":src["motifs"],"permuted":src["permuted"],
              "expected":src["expected_by_graph"],"all_verified":same,
              "decisions":{a:rows[a]["decisions"] for a in ARMS},
              "conflicts":{a:rows[a]["conflicts"] for a in ARMS},
              "verified_status":{a:rows[a]["status"] for a in ARMS},
              "guard_checked":rows["deltax-guard"]["guard_checks"],
              "guard_accepted":rows["deltax-guard"]["guard_accepted"],
              "guard_vetoed":rows["deltax-guard"]["guard_rejected"],
              "guard_causal":rows["deltax-guard"]["causal_enqueues"],
              "accepted_links":rows["deltax-guard"]["accepted_graph_links"]}
        paired.append(pair)
    comp=[x for x in paired if x["all_verified"]]
    def gain(key):
        return (sum(p[key]["deltax-guard"]<p[key]["join"] for p in comp),
                sum(p[key]["deltax-guard"]>p[key]["join"] for p in comp))
    dgood,dbad=gain("decisions")
    cgood,cbad=gain("conflicts")
    kinds={}
    for category in sorted({x["graph_kind"] for x in paired}):
        rr=[x for x in paired if x["graph_kind"]==category]
        kinds[category]={
            "cases":len(rr),"verified":sum(x["all_verified"] for x in rr),
            "positive_guards":sum(x["guard_accepted"] for x in rr),
            "rejected_guards":sum(x["guard_vetoed"] for x in rr),
            "fewer_decisions":sum(x["all_verified"] and x["decisions"]["deltax-guard"]<
                                 x["decisions"]["join"] for x in rr),
            "more_decisions":sum(x["all_verified"] and x["decisions"]["deltax-guard"]>
                                x["decisions"]["join"] for x in rr)
        }
    report={
        "status":"COMPLETE","new_graph_cases":len(sources),"trials":len(recs),
        "graph_witness_or_obstruction_verified_by_generator":True,
        "all_credited_sat_models_checked_against_original_cnf":True,
        "all_credited_unsat_proofs_independently_verified":True,
        "single_logical_cpu":True,"binary_frozen_from_guard1":True,
        "no_speed_or_general_math_claim":True,"promotion":False,
        "blind_holdout":False,"source_manifest_sha256":manifest_sha,
        "arms":arms,"matched_verified":len(comp),
        "guard_decision_better_than_join":dgood,
        "guard_decision_worse_than_join":dbad,
        "guard_conflict_better_than_join":cgood,
        "guard_conflict_worse_than_join":cbad,
        "by_graph_structure":kinds,"paired":paired
    }
    P.save(R/"deltax_graphlab1_final/report.json",report)
    P.save(R/"deltax_graphlab1_final/trials.json",recs)
    emit("DELTAX_GRAPHLAB_FINAL",{k:v for k,v in report.items() if k!="paired"})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("preflight","shard","aggregate"))
    parser.add_argument("--shard",type=int,default=0)
    opts=parser.parse_args()
    if opts.stage=="preflight":preflight()
    elif opts.stage=="shard":shard(opts.shard)
    else:aggregate()

if __name__=="__main__":main()
