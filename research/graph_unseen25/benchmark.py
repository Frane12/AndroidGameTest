#!/usr/bin/env python3
"""Prospective-to-DRNAS graph family 2025 holdout; exact original CNFs.

Ten prespecified GBD SAT2025 Main originals, two serial paired repeats,
six arms: 120 trials. Original source freeze runs before ANY solver/test.
Single logical CPU per solver. Strict proof verification inside 8s E2E.
No data leakage from catalog outcomes; no outcome-directed substitutions.
"""
import argparse,collections,hashlib,importlib.util,json,os,pathlib,random,statistics,sys

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"results/graph_unseen25"
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as frozen
sys.path.insert(0,str(ROOT/"research/graphclique"))
import real67 as graph
CAP=8.0;REPS=2;SHARDS=5
ARMS=("GRAPH_ONLY","GRAPH_PLUS_MATH5","X59_MATH5_VERIPB",
      "Kissat","CaDiCaL","CryptoMiniSat")
REFS=("Kissat","CaDiCaL","CryptoMiniSat")
STRICT={"MODEL","DRAT","FRAT","VERIPB_CAPACITY","VERIPB_MATH5","VERIPB_GRAPH"}

def sha(path):return frozen.sha(path)

def onecpu():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        assert len(os.sched_getaffinity(0))==1

def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def source_manifest():
    prespec=json.loads((HERE/"prespec.json").read_text())
    m=json.loads((HERE/"inputs/manifest.json").read_text())
    assert prespec["protocol"]==m["protocol"]
    assert len(m["sources"])==prespec["number_selected"]==10
    assert sha(HERE/"prespec.json")==m["prespec_sha256"]
    assert all(x["file_id"]==y["gbd_hash"] and
               x["isohash"]==y["isohash"] and
               x["id"]==y["id"] and
               x["family"]==y["family"]
               for x,y in zip(m["sources"],prespec["instances"]))
    for x in m["sources"]:
        assert sha(ROOT/x["path"])==x["sha256"],("ORIGINAL_2025_CNF_CHANGED",x["id"])
    assert m["no_outcome_based_replacements"] and m["source_count"]==10
    return m

def prepare():
    onecpu()
    m=source_manifest()
    originals=json.loads((ROOT/"unified_realblind100_inputs/manifest.json").read_text())
    assert sha(ROOT/"unified_realblind100_inputs/manifest.json")==m["frozen_2026_manifest_sha256"]
    prior_ids={s["file_id"] for s in originals["sources"]}
    prior_iso={s["isohash"] for s in originals["sources"]}
    assert not ({x["gbd_hash"] for x in m["sources"]}&prior_ids)
    assert not ({x["isohash"] for x in m["sources"]}&prior_iso)
    pins=frozen.pinned()
    policy={"name":"DRNAS-GRAPH-UNSEEN25-STRICT-PAR2-V1",
            "new_source_2025_frozen_manifest_sha256":sha(HERE/"inputs/manifest.json"),
            "prior_67_manifest_sha256":m["frozen_2026_manifest_sha256"],
            "prespec_sha256":m["prespec_sha256"],
            "binary_sha256":pins,
            "graph_emitter_sha256":sha(ROOT/"research/graphclique/emit_veripb.py"),
            "math5_emitter_sha256":sha(ROOT/"research/math5/emit_veripb_eo_multiplicity.py"),
            "benchmark_script_sha256":sha(HERE/"benchmark.py"),
            "git_commit":os.environ.get("GITHUB_SHA"),
            "source_count":10,"arms":list(ARMS),"reps":REPS,"shards":SHARDS,
            "expected_trials":10*REPS*len(ARMS),
            "one_logical_cpu":True,"cap_s":CAP,
            "strict_standard_proof_checker":sorted(STRICT),
            "source_isohash_disjoint_from_prior_67":True,
            "no_pretest_candidates_or_replacement":True,
            "no_main_promotion":True,
            "claim":"Prospective for DRNAS with metadata-only preselection; historical work in every branch not exhaustively excluded; small 10-source 2025 Main pilot."}
    save(OUT/"protocol.json",policy)
    print("GRAPH_UNSEEN25_READY "+json.dumps(
        {"sources":policy["source_count"],"arms":list(ARMS),
         "total_trials":policy["expected_trials"],
         "source_manifest":policy["new_source_2025_frozen_manifest_sha256"],
         "previous_gbd_overlap":0,"previous_isohash_overlap":0},
        sort_keys=True),flush=True)

def restore():
    onecpu()
    m=source_manifest()
    p=json.loads((OUT/"protocol.json").read_text())
    assert p["name"]=="DRNAS-GRAPH-UNSEEN25-STRICT-PAR2-V1"
    assert p["new_source_2025_frozen_manifest_sha256"]==sha(HERE/"inputs/manifest.json")
    assert p["prior_67_manifest_sha256"]==sha(ROOT/"unified_realblind100_inputs/manifest.json")
    assert p["binary_sha256"]==frozen.pinned()
    assert p["graph_emitter_sha256"]==sha(ROOT/"research/graphclique/emit_veripb.py")
    assert p["math5_emitter_sha256"]==sha(ROOT/"research/math5/emit_veripb_eo_multiplicity.py")
    assert p["benchmark_script_sha256"]==sha(HERE/"benchmark.py")
    assert p["git_commit"]==os.environ.get("GITHUB_SHA")
    assert p["arms"]==list(ARMS) and p["cap_s"]==CAP
    return m["sources"]

def run_one(src,arm,rep):
    if arm=="GRAPH_ONLY" or arm=="GRAPH_PLUS_MATH5":
        row=graph.graph_trial(src,arm,rep)
    elif arm=="X59_MATH5_VERIPB":
        row=graph.old.standard_trial(src,rep)
    else:
        row=frozen.trial(src,arm,rep)
    assert row["id"]==src["id"] and row["source_sha256"]==src["sha256"]
    assert row["arm"]==arm
    return row

def shard(idx):
    assert 0<=idx<SHARDS
    sources=restore()
    partition=[x for x in sources if x["id"]%SHARDS==idx]
    assert len(partition)==2,("INCORRECT_SHARD_PARTITION",idx,len(partition))
    out=OUT/f"shard-{idx}"
    out.mkdir(parents=True,exist_ok=False)
    records=[]
    with (out/"trials.jsonl").open("w") as fd:
        for src in partition:
            for rep in range(REPS):
                arms=list(ARMS)
                random.Random(f"DRNAS-UNSEEN25-{src['gbd_hash']}-{rep}").shuffle(arms)
                summary={}
                for arm in arms:
                    row=run_one(src,arm,rep)
                    fd.write(json.dumps(row,sort_keys=True)+"\n");fd.flush()
                    records.append(row)
                    summary[arm]={"strict":row["strict_accepted"],
                        "kind":row["certificate_kind"],
                        "PAR2":row["PAR2_strict_s"],
                        "status":row["status"]}
                print("GRAPH_UNSEEN25_PAIRED "+json.dumps(
                    {"id":src["id"],"family":src["family"],"rep":rep,
                     "arms":summary},sort_keys=True),flush=True)
    assert len(records)==len(partition)*REPS*len(ARMS)==24
    print("GRAPH_UNSEEN25_SHARD "+json.dumps(
        {"shard":idx,"original_CNFs":len(partition),
         "trials":len(records),
         "strict":{arm:{
            "accepted":sum(r["strict_accepted"] for r in records if r["arm"]==arm),
            "PAR2_s":round(sum(r["PAR2_strict_s"] for r in records if r["arm"]==arm),6)}
            for arm in ARMS}},sort_keys=True),flush=True)

def report():
    sources=restore()
    rows=[]
    for idx in range(SHARDS):
        p=OUT/f"shard-{idx}/trials.jsonl"
        if not p.is_file():raise RuntimeError("MISSING_HOLDOUT_SHARD "+str(idx))
        rows.extend(json.loads(line) for line in p.read_text().splitlines())
    expected={(i,rep,arm) for i in range(10) for rep in range(REPS) for arm in ARMS}
    actual={(r["id"],r["rep"],r["arm"]) for r in rows}
    if not (len(rows)==len(actual)==len(expected)==120 and actual==expected):
        raise RuntimeError("INCOMPLETE_OR_DUPLICATE_HOLDOUT_MATRIX")
    originals={x["id"]:x for x in sources}
    errors=[]
    for r in rows:
        src=originals[r["id"]]
        if r["source_sha256"]!=src["sha256"] or r["family"]!=src["family"]:
            errors.append({"id":r["id"],"reason":"SOURCE_SHA_OR_FAMILY_CHANGED"})
        if r["critical"]:
            errors.append({"id":r["id"],"arm":r["arm"],
                           "reason":r["status"],"detail":r.get("reason")})
        if r["strict_accepted"] and (not r["accepted"] or
                                     r["certificate_kind"] not in STRICT):
            errors.append({"id":r["id"],"arm":r["arm"],
                           "reason":"CUSTOM_PROOF_WRONGLY_ACCEPTED_AS_STANDARD"})
    for i in range(10):
        passed=[r for r in rows if r["id"]==i and r["accepted"]]
        if any(r["status"]=="SAT_VERIFIED" for r in passed) and any(
                r["status"]=="UNSAT_VERIFIED" for r in passed):
            errors.append({"id":i,"reason":"CONTRADICTORY_SOURCE_VERIFIED_SAT_UNSAT"})
    totals={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        totals[arm]={"attempts":len(rr),
                     "verified":sum(r["accepted"] for r in rr),
                     "strict_verified":sum(r["strict_accepted"] for r in rr),
                     "unique_solved_sources":len({r["id"] for r in rr if r["strict_accepted"]}),
                     "verified_SAT":sum(r["status"]=="SAT_VERIFIED" and r["strict_accepted"] for r in rr),
                     "verified_UNSAT":sum(r["status"]=="UNSAT_VERIFIED" and r["strict_accepted"] for r in rr),
                     "graph_pbp":sum(r["strict_accepted"] and r["certificate_kind"]=="VERIPB_GRAPH" for r in rr),
                     "math5_pbp":sum(r["strict_accepted"] and r["certificate_kind"]=="VERIPB_MATH5" for r in rr),
                     "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in rr),6),
                     "structural_PAR2_s":round(sum(r["PAR2_s"] for r in rr),6),
                     "status_count":dict(collections.Counter(r["status"] for r in rr)),
                     "proof_kinds":dict(collections.Counter(
                         r["certificate_kind"] for r in rr if r["strict_accepted"]))}
    best=min(REFS,key=lambda a:totals[a]["strict_PAR2_s"])
    means={i:{arm:statistics.mean(r["PAR2_strict_s"] for r in rows
                                  if r["id"]==i and r["arm"]==arm)
              for arm in ARMS} for i in range(10)}
    families=collections.defaultdict(list)
    for src in sources:families[src["family"]].append(src["id"])
    rng=random.Random(20261116)
    paired={}
    for arm in ARMS:
        if arm in REFS:continue
        delta={i:means[i][best]-means[i][arm] for i in range(10)}
        clusters=[sum(delta[i] for i in ids) for ids in families.values()]
        samples=sorted(sum(clusters[rng.randrange(len(clusters))]
                    for _ in clusters) for _ in range(3000))
        paired[arm]={"best_reference":best,
            "source_mean_total_saving_s":round(sum(delta.values()),6),
            "wins":sum(x>1e-4 for x in delta.values()),
            "losses":sum(x<-1e-4 for x in delta.values()),
            "ties":sum(abs(x)<=1e-4 for x in delta.values()),
            "families":len(clusters),
            "family_cluster_bootstrap95_s":[round(samples[75],6),round(samples[2925],6)]}
    data={"status":"COMPLETE" if not errors else "CRITICAL",
          "new_source_count":len(sources),"attempts":len(rows),
          "track":"SAT Competition 2025 Main",
          "no_overlap_old_67_ids_or_isohashes":True,
          "repetitions":REPS,"cap_s":CAP,
          "best_reference":best,"totals":totals,"paired":paired,
          "source_ids":[{"id":x["id"],"gbd_hash":x["gbd_hash"],
                         "isohash":x["isohash"],"sha256":x["sha256"],
                         "family":x["family"]} for x in sources],
          "critical_count":len(errors),"critical":errors,
          "scope":"New fixed instance-level source/GBD-iso excluded pilot. Not proof unseen across every earlier branch; family cluster only 3 groups, small sample; no auto-main promotion."}
    save(OUT/"final.json",data)
    print("GRAPH_UNSEEN25_FINAL "+json.dumps(data,sort_keys=True),flush=True)
    if errors:raise SystemExit(1)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("prepare","shard","report"))
    a.add_argument("--index",type=int)
    v=a.parse_args()
    if v.action=="prepare":prepare()
    elif v.action=="shard":shard(v.index)
    else:report()
