#!/usr/bin/env python3
"""DELTAX GRAPH-ABLATION1: matched *identical graph edges* causal analysis.

For each of 12 new graph cores, compare:
  core-only (separate dimensional reference)
  off, low1, high1, low3, high3 (identical total variables and clauses)
in JOIN, DELTAX-SHADOW, DELTAX and DELTAX-GUARD modes of the exact same
frozen solver. Two repeats per source/arm.

All credited SAT models independently checked on ORIGINAL CNF; all credited
UNSAT require original-CNF drat-trim certification. Clone returns NEVER
accepted as SAT or UNSAT proof. No performance or general-math promotion.
"""
import argparse,collections,hashlib,json,os,random,sys
from pathlib import Path

R=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(R/"research/drnas_deltax_guard"),
             str(R/"research/drnas_deltax"),
             str(R/"research")]
from drnas_deltax_guard import paired as P
from graph_ablation_sources import write as generate,VARIANTS,MATCHED

ARMS=P.ARMS
SHARDS=4
REPS=2
CAP=4.0
EXPECTED_N_GRAPHS=12
EXPECTED_N_SOURCES=EXPECTED_N_GRAPHS*len(VARIANTS)

def sha(data):return hashlib.sha256(data).hexdigest()
def emit(tag,x):P.emit(tag,x)
def save(path,x):P.save(path,x)

def manifest():
    p=R/"deltax_graph_ablation1_inputs/manifest.json"
    rows=json.loads(p.read_text())
    assert len(rows)==EXPECTED_N_SOURCES and len({s["sha256"] for s in rows})==len(rows)
    groups=collections.defaultdict(list)
    for s in rows:
        groups[s["graph_id"]].append(s)
        assert sha((R/s["path"]).read_bytes())==s["sha256"],("SOURCE_DRIFT",s["name"])
    assert len(groups)==EXPECTED_N_GRAPHS
    for name,variants in groups.items():
        assert {v["variant"] for v in variants}==set(VARIANTS)
        exact={v["variant"]:v for v in variants}
        for v in MATCHED:
            assert exact[v]["graph_sha256"]==exact["off"]["graph_sha256"]
            assert exact[v]["nvars"]==exact["off"]["nvars"]
            assert exact[v]["nclauses"]==exact["off"]["nclauses"]
        assert exact["core"]["graph_sha256"]==exact["off"]["graph_sha256"]
        assert len({v["sha256"] for v in variants})==len(VARIANTS),(
            "IDENTICAL_CONTROL_SOURCES",name)
    return rows,sha(p.read_bytes())

def expected(row):
    return "SAT_VERIFIED" if row["expected_by_graph"]=="SAT" else "UNSAT_CERTIFIED"

def one(row,arm,rep,cap,folder):
    native=P.trial(row,arm,cap,folder/"raw"/f"rep{rep}")
    if native["verified"]:
        assert native["status"]==expected(row),(
            "GRAPH_SAT_THEOREM_CONFLICT",row["name"],arm,native["status"])
    assert native["guard_invalid_source"]==0,("UNSOUND_SOURCE",row["name"],arm)
    assert native["guard_clones_inconsistent"]==0,("INCONSISTENT_CLONES",row["name"],arm)
    native["rep"]=rep
    native["graph_id"]=row["graph_id"]
    native["graph_kind"]=row["graph_kind"]
    native["graph_sha256"]=row["graph_sha256"]
    native["graph_vertices"]=row["graph_vertices"]
    native["graph_edges"]=row["graph_edges"]
    native["variant"]=row["variant"]
    native["active_graph_links"]=row["attached_links"]
    native["link_target_degrees"]=[x["degree"] for x in row["link_role"] if x["attached"]]
    native["position_control"]="matched_same_graph_same_nvars_nclauses" if row["variant"]!="core" else "core_only"
    # Preserve exact source-RUP event + active clause-to-color-bit linking.
    if arm=="deltax-guard":
        path=folder/"raw"/f"rep{rep}"/(row["name"]+"-deltax-guard.events.json")
        if path.exists():
            events=json.loads(path.read_text())
            alias=events["aliases"]
            # Events are independently source/parent/RUP checked by P.trial.
            native["accepted_alias_events"]=len(alias)
            native["accepted_alias_gadget_links"]=[]
            for a in alias:
                # A source-entailed conditional equality may involve a local
                # gadget variable. We do NOT assume that every accepted
                # alias acts directly on the coloring core.
                matched=[]
                for link in row["link_role"]:
                    if link["y_variable"] in (a["a"],a["b"]):
                        matched.append({
                            "slot":link["slot"],"attached":link["attached"],
                            "vertex":link["vertex"],"degree":link["degree"],
                            "color":link["color_index"]})
                native["accepted_alias_gadget_links"].append(matched)
            assert len(alias)<=native["deltax_lemmas"]
    return native

def preflight():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=generate("deltax_graph_ablation1_inputs")
    assert len(rows)==EXPECTED_N_SOURCES
    manifest()
    graphs=set()
    chosen=[]
    for row in rows:
        if row["graph_kind"] not in graphs:
            graphs.add(row["graph_kind"])
            for var in ("core","off","high3"):
                chosen.append(next(x for x in rows if
                                   x["graph_id"]==row["graph_id"] and
                                   x["variant"]==var))
    assert len(chosen)==12 and len(graphs)==4
    folder=R/"deltax_graph_ablation1_preflight"
    trials=[]
    for s in chosen:
        for arm in ARMS:
            trials.append(one(s,arm,0,3.0,folder))
    assert len(trials)==48
    assert sum(t["verified"] for t in trials)>=40,(
        "PREFLIGHT_TOO_MANY_INCONCLUSIVES",sum(t["verified"] for t in trials))
    record={
        "status":"PASS","graph_families":sorted(graphs),
        "source_count":EXPECTED_N_SOURCES,"pilot_sources":len(chosen),
        "pilot_attempts":len(trials),
        "pilot_verified":sum(t["verified"] for t in trials),
        "manifest_sha":manifest()[1],
        "matched_same_nvars_and_clauses":True,
        "model_proof_verified":True,"single_cpu":True,
        "frozen_solver":True,"no_main_change":True
    }
    save(folder/"report.json",record)
    emit("DELTAX_ABLATION_PREFLIGHT_PASS",record)

def shard(index):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows,checksum=manifest()
    groups=sorted({r["graph_id"] for r in rows})
    selected_graphs={g for i,g in enumerate(groups) if i%SHARDS==index}
    selected=[r for r in rows if r["graph_id"] in selected_graphs]
    assert len(selected)==(len(groups)//SHARDS)*len(VARIANTS)
    folder=R/f"deltax_graph_ablation1_shards/{index}"
    folder.mkdir(parents=True,exist_ok=False)
    save(folder/"manifest.json",{
        "shard":index,"graph_ids":sorted(selected_graphs),
        "manifest_sha256":checksum,
        "binary_sha256":P.sha(P.BINARY),"proof_checker_sha256":P.sha(P.DRAT),
        "arms":ARMS,"cap_s":CAP,"reps":REPS,
        "one_cpu":sorted(os.sched_getaffinity(0)),
        "matched_geometry":True,"matched_source_dimensions":True,
        "blind_holdout":False,"promotion":False
    })
    count=0
    with (folder/"trials.jsonl").open("w") as stream:
        for source in selected:
            for rep in range(REPS):
                order=list(ARMS)
                random.Random(int(source["sha256"][:16],16)+rep*919).shuffle(order)
                for arm in order:
                    result=one(source,arm,rep,CAP,folder)
                    stream.write(json.dumps(result,sort_keys=True)+"\n");stream.flush()
                    count+=1
                    emit("DELTAX_ABLATION_TRIAL",{
                        "graph":result["graph_id"],"kind":result["graph_kind"],
                        "variant":result["variant"],"arm":arm,"rep":rep,
                        "status":result["status"],"verified":result["verified"],
                        "decisions":result["decisions"],"conflicts":result["conflicts"],
                        "accepted":result["guard_accepted"],"rejected":result["guard_rejected"],
                        "causal":result["causal_enqueues"]})
    emit("DELTAX_ABLATION_SHARD_PASS",{
        "shard":index,"graphs":len(selected_graphs),"sources":len(selected),"attempts":count})

def aggregate():
    sources,checksum=manifest()
    rows=[];ms=[]
    for i in range(SHARDS):
        folder=R/f"deltax_graph_ablation1_downloads/deltax-ablation-shard-{i}/deltax_graph_ablation1_shards/{i}"
        m=json.loads((folder/"manifest.json").read_text());ms.append(m)
        rows += [json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
    expect={(r["sha256"],rep,arm) for r in sources for rep in range(REPS) for arm in ARMS}
    actual=[(r["sha256"],r["rep"],r["arm"]) for r in rows]
    assert len(rows)==576 and set(actual)==expect and len(set(actual))==len(actual)
    for m in ms:
        assert m["manifest_sha256"]==checksum
        assert m["binary_sha256"]==ms[0]["binary_sha256"]
        assert m["proof_checker_sha256"]==ms[0]["proof_checker_sha256"]
        assert tuple(m["arms"])==ARMS and m["cap_s"]==CAP and m["reps"]==REPS
        assert len(m["one_cpu"])==1 and m["matched_geometry"] and m["matched_source_dimensions"]
        assert not m["blind_holdout"] and not m["promotion"]
    outcomes=collections.defaultdict(set)
    for r in rows:
        if r["verified"]:outcomes[r["sha256"]].add(r["status"])
        assert r["guard_invalid_source"]==r["guard_clones_inconsistent"]==0
    assert all(len(v)<=1 for v in outcomes.values()),"CONTRADICTORY_SOURCE_CERTIFICATES"
    bykey={(r["sha256"],r["rep"],r["arm"]):r for r in rows}
    bysource={(r["graph_id"],r["variant"]):r for r in sources}
    arm_total={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        arm_total[arm]={
            "attempts":len(rr),"verified":sum(x["verified"] for x in rr),
            "SAT_verified":sum(x["verified"] and x["status"]=="SAT_VERIFIED" for x in rr),
            "UNSAT_certified":sum(x["verified"] and x["status"]=="UNSAT_CERTIFIED" for x in rr),
            "uncertified_or_unknown":sum(not x["verified"] for x in rr),
            "guard_checked":sum(x["guard_checks"] for x in rr),
            "guard_accepted":sum(x["guard_accepted"] for x in rr),
            "guard_rejected":sum(x["guard_rejected"] for x in rr),
            "source_RUP_lemmas":sum(x["deltax_lemmas"] for x in rr),
            "actual_CDCL_reason_propagations":sum(x["causal_enqueues"] for x in rr)
        }
    paired=[]
    for source in sources:
        for rep in range(REPS):
            pairs={arm:bykey[(source["sha256"],rep,arm)] for arm in ARMS}
            ok=all(pairs[a]["verified"] for a in ("join","deltax","deltax-guard"))
            if ok:
                assert len({pairs[a]["status"] for a in ARMS if pairs[a]["verified"]})<=1
            pair={
                "graph_id":source["graph_id"],"graph_kind":source["graph_kind"],
                "graph_vertices":source["graph_vertices"],
                "graph_edges":source["graph_edges"],
                "graph_sha256":source["graph_sha256"],
                "variant":source["variant"],"active_graph_links":source["attached_links"],
                "position_degrees":pairs["deltax-guard"]["link_target_degrees"],
                "rep":rep,"verified_paired":ok,
                "decisions":{arm:pairs[arm]["decisions"] for arm in ARMS},
                "conflicts":{arm:pairs[arm]["conflicts"] for arm in ARMS},
                "status":{arm:pairs[arm]["status"] for arm in ARMS},
                "guard_accepted":pairs["deltax-guard"]["guard_accepted"],
                "guard_rejected":pairs["deltax-guard"]["guard_rejected"],
                "causal":pairs["deltax-guard"]["causal_enqueues"],
                "accepted_source_gadget_links":
                    pairs["deltax-guard"].get("accepted_alias_gadget_links",[])
            }
            if ok:
                pair["decision_gain_JOIN_minus_GUARD"]=(
                    pairs["join"]["decisions"]-pairs["deltax-guard"]["decisions"])
                pair["conflict_gain_JOIN_minus_GUARD"]=(
                    pairs["join"]["conflicts"]-pairs["deltax-guard"]["conflicts"])
            paired.append(pair)
    matched=[r for r in paired if r["verified_paired"]]
    variant_summary={}
    for variant in VARIANTS:
        rr=[r for r in paired if r["variant"]==variant]
        ok=[r for r in rr if r["verified_paired"]]
        variant_summary[variant]={
            "pairs":len(rr),"verified_pairs":len(ok),
            "guard_accepted":sum(x["guard_accepted"] for x in rr),
            "guard_rejected":sum(x["guard_rejected"] for x in rr),
            "actual_CDCL_reasons":sum(x["causal"] for x in rr),
            "fewer_decisions":sum(x["decision_gain_JOIN_minus_GUARD"]>0 for x in ok),
            "more_decisions":sum(x["decision_gain_JOIN_minus_GUARD"]<0 for x in ok),
            "fewer_conflicts":sum(x["conflict_gain_JOIN_minus_GUARD"]>0 for x in ok),
            "more_conflicts":sum(x["conflict_gain_JOIN_minus_GUARD"]<0 for x in ok),
            "mean_decision_gain":sum(x["decision_gain_JOIN_minus_GUARD"] for x in ok)/len(ok) if ok else None,
            "mean_conflict_gain":sum(x["conflict_gain_JOIN_minus_GUARD"] for x in ok)/len(ok) if ok else None
        }
    # Difference-in-differences controls for solver baseline on the exact
    # SAME CNF. A graph-family paired comparison is not a randomized causal
    # estimate but is far less confounded than comparing unrelated graphs.
    did=[]
    for graph in sorted({s["graph_id"] for s in sources}):
        for rep in range(REPS):
            g={r["variant"]:r for r in paired if r["graph_id"]==graph and r["rep"]==rep}
            assert set(g)==set(VARIANTS)
            for variant in MATCHED[1:]:
                linked=g[variant];off=g["off"]
                comparable=linked["verified_paired"] and off["verified_paired"]
                r={"graph_id":graph,"kind":linked["graph_kind"],"rep":rep,
                   "variant":variant,"compared_to":"off",
                   "same_graph_sha256":linked["graph_sha256"]==off["graph_sha256"],
                   "comparable":comparable}
                if comparable:
                    r["incremental_guard_decision_gain_over_off"]=(
                        linked["decision_gain_JOIN_minus_GUARD"]-
                        off["decision_gain_JOIN_minus_GUARD"])
                    r["incremental_guard_conflict_gain_over_off"]=(
                        linked["conflict_gain_JOIN_minus_GUARD"]-
                        off["conflict_gain_JOIN_minus_GUARD"])
                did.append(r)
    assert all(x["same_graph_sha256"] for x in did)
    report={
        "status":"COMPLETE","base_graphs":12,"variants_per_graph":6,
        "matched_variant_count":5,"sources":len(sources),"attempts":len(rows),
        "reps":REPS,"retrospective_synthetic":True,"blind_holdout":False,
        "no_promotion":True,"one_logical_cpu_per_solver":True,
        "exact_frozen_solver_build":True,
        "graph_witness_obstructions_checked_before_benchmark":True,
        "original_CNF_SAT_models_and_UNSAT_DRAT_checked":True,
        "common_graph_edges_in_each_group":True,
        "same_variable_and_clause_count_in_five_matched_variants":True,
        "source_manifest_sha256":checksum,
        "arms":arm_total,"variants":variant_summary,
        "all_arm_paired_verified":len(matched),
        "did_comparable":sum(x["comparable"] for x in did),
        "did_linked_positive_conflict_gain":sum(x["comparable"] and x["incremental_guard_conflict_gain_over_off"]>0 for x in did),
        "did_linked_negative_conflict_gain":sum(x["comparable"] and x["incremental_guard_conflict_gain_over_off"]<0 for x in did),
        "matched_pairs":paired,
        "within_graph_off_control_differences":did,
        "not_new_math_or_speed_guarantee":True
    }
    save(R/"deltax_graph_ablation1_final/report.json",report)
    save(R/"deltax_graph_ablation1_final/trials.json",rows)
    emit("DELTAX_ABLATION_FINAL",{k:v for k,v in report.items()
          if k not in ("matched_pairs","within_graph_off_control_differences")})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("preflight","shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.stage=="preflight":preflight()
    elif a.stage=="shard":shard(a.shard)
    else:aggregate()

if __name__=="__main__":main()
