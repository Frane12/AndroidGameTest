#!/usr/bin/env python3
"""10 genuinely NEW source-/isohash-/catalog-family-disjoint graph-adjacent CNFs.

Source-only GBD SHA freeze runs IN THE PREPARE JOB before ANY of these
solver/guard arms is executed. This script requires an already completed,
immutable 10-source manifest. Seven arms; 10*2*7=140 paired attempts.
All comparisons have 8s E2E cap inclusive of source SHA, proof emitter,
independent VeriPB/DRAT/FRAT checker, native solver startup and fallback.
One logical CPU per trial, no parallel solver portfolio.
"""
import argparse,collections,hashlib,json,os,pathlib,random,statistics,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
INPUT=HERE/"inputs"
OUT=ROOT/"results/graph_family_disjoint25"
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as frozen
sys.path.insert(0,str(ROOT/"research/graphclique"))
import real67 as graph
EXT=ROOT/"research/clique_color_er/emit_veripb.py"
EXT_SRC=ROOT/"research/clique_color_er/source_check.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
CAP=8.0;REPS=2;SHARDS=5
ARMS=("CLIQUE_EXT_ONLY","CLIQUE_EXT_GRAPH_MATH5","GRAPH_MATH5",
      "X59_MATH5_VERIPB","Kissat","CaDiCaL","CryptoMiniSat")
REFS=("Kissat","CaDiCaL","CryptoMiniSat")
STRICT={"MODEL","DRAT","FRAT","VERIPB_CAPACITY","VERIPB_MATH5",
        "VERIPB_GRAPH","VERIPB_CLIQUE_EXT"}

def sha(p):return frozen.sha(p)

def save(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def affinity():
    if hasattr(os,"sched_setaffinity"):
        cpus=os.sched_getaffinity(0)
        assert cpus
        os.sched_setaffinity(0,{min(cpus)})
        assert len(os.sched_getaffinity(0))==1

def immutable():
    meta=json.loads((HERE/"prespec.json").read_text())
    m=json.loads((INPUT/"manifest.json").read_text())
    assert meta["protocol"]=="DRNAS-GRAPH-FAMILY-DISJOINT25-SMALL-PRESPEC-V2"
    assert m["status"]=="FROZEN_SOURCE_ONLY_NO_SOLVER_RUN"
    assert len(meta["records"])==len(m["sources"])==10
    assert meta["selected_sources"]==m["selected_count"]==10
    assert sha(HERE/"prespec.json")==m["prespec_sha256"]
    assert m["provenance"]["family_disjoint"]
    assert m["provenance"]["source_isohash_disjoint"]
    assert m["provenance"]["source_GBD_disjoint"]
    for selected,record in zip(meta["records"],m["sources"]):
        for field in ("id","family","gbd_hash","isohash","filename"):
            assert selected[field]==record[field],("PRESPEC_MISMATCH",field,record["id"])
        assert record["file_id"]==record["gbd_hash"]
        assert sha(ROOT/record["path"])==record["sha256"],("CNF_CHANGED",record["id"])
    return meta,m

def prepare():
    affinity()
    pre,m=immutable()
    old67=ROOT/"unified_realblind100_inputs/manifest.json"
    old10=ROOT/"research/graph_unseen25/inputs/manifest.json"
    assert sha(old67)==m["provenance"]["old67_manifest_sha256"]
    assert sha(old10)==m["provenance"]["old10_manifest_sha256"]
    prior=json.loads(old67.read_text())["sources"]+json.loads(old10.read_text())["sources"]
    assert not ({r["family"] for r in m["sources"]}&{s["family"] for s in prior})
    assert not ({r["gbd_hash"] for r in m["sources"]}&
                {s.get("file_id",s.get("gbd_hash")) for s in prior})
    assert not ({r["isohash"] for r in m["sources"]}&
                {s.get("isohash") for s in prior})
    pins=frozen.pinned()
    protocol={
        "experiment":"DRNAS-GRAPH-FAMILY-DISJOINT25-SMALL-STRICT-E2E-V2",
        "sources":10,"repetitions":REPS,"shards":SHARDS,
        "arms":list(ARMS),"expected_trials":10*REPS*len(ARMS),
        "cap_s":CAP,"PAR2_timeout_s":2*CAP,
        "one_logical_cpu_per_solver":True,
        "no_parallel_solver_portfolio":True,
        "new_source_manifest_sha256":sha(INPUT/"manifest.json"),
        "prespec_sha256":sha(HERE/"prespec.json"),
        "old67_manifest_sha256":sha(old67),
        "old10_manifest_sha256":sha(old10),
        "pinned_binary_sha256":pins,
        "clique_ext_emitter_sha256":sha(EXT),
        "clique_ext_source_checker_sha256":sha(EXT_SRC),
        "graph_emitter_sha256":sha(ROOT/"research/graphclique/emit_veripb.py"),
        "math5_emitter_sha256":sha(ROOT/"research/math5/emit_veripb_eo_multiplicity.py"),
        "benchmark_script_sha256":sha(HERE/"benchmark.py"),
        "workflow_commit_sha256":os.environ.get("GITHUB_SHA"),
        "source_and_family_disjoint":True,
        "selection_fixed_before_solver_outcomes":True,
        "strict_proof_whitelist":sorted(STRICT),
        "no_auto_main_promotion":True,
        "limitations":"10 original CNFs across seven catalog families. Disjoint only from 67+10 tracked development references, not all historic experiments."}
    save(OUT/"protocol.json",protocol)
    print("GRAPH_DISJOINT25_PREPARED "+json.dumps({
        "sources":10,"families":len({x["family"] for x in m["sources"]}),
        "arms":len(ARMS),"expected_trials":protocol["expected_trials"],
        "input_sha256":protocol["new_source_manifest_sha256"]},sort_keys=True),flush=True)

def restore():
    affinity()
    pre,m=immutable()
    p=json.loads((OUT/"protocol.json").read_text())
    assert p["experiment"]=="DRNAS-GRAPH-FAMILY-DISJOINT25-SMALL-STRICT-E2E-V2"
    assert p["sources"]==10 and p["arms"]==list(ARMS)
    assert p["new_source_manifest_sha256"]==sha(INPUT/"manifest.json")
    assert p["prespec_sha256"]==sha(HERE/"prespec.json")
    assert p["old67_manifest_sha256"]==sha(ROOT/"unified_realblind100_inputs/manifest.json")
    assert p["old10_manifest_sha256"]==sha(ROOT/"research/graph_unseen25/inputs/manifest.json")
    assert p["pinned_binary_sha256"]==frozen.pinned()
    assert p["clique_ext_emitter_sha256"]==sha(EXT)
    assert p["clique_ext_source_checker_sha256"]==sha(EXT_SRC)
    assert p["graph_emitter_sha256"]==sha(ROOT/"research/graphclique/emit_veripb.py")
    assert p["math5_emitter_sha256"]==sha(ROOT/"research/math5/emit_veripb_eo_multiplicity.py")
    assert p["benchmark_script_sha256"]==sha(HERE/"benchmark.py")
    assert p["workflow_commit_sha256"]==os.environ.get("GITHUB_SHA")
    return m["sources"],p

def unknown(s,rep,arm,started,status,reason=None,critical=False,guard_s=0):
    elapsed=time.perf_counter()-started
    return {"id":s["id"],"file_id":s["file_id"],"family":s["family"],
        "catalog_label":s["catalog_label"],"source_sha256":s["sha256"],
        "rep":rep,"arm":arm,"status":status,"rc":None,
        "accepted":False,"strict_accepted":False,"critical":critical,
        "reason":reason,"certificate_kind":None,"proof_sha256":None,
        "proof_bytes":0,"guard_s":round(guard_s,6),
        "checker_s":0,"e2e_s":round(elapsed,6),
        "PAR2_s":2*CAP,"PAR2_strict_s":2*CAP}

def ext_probe(s,cnf,started,rep,arm):
    """Return (accepted_proof_row, error_row, elapsed_guard).

    An unsupported or exhausted *bounded* scout is UNKNOWN, never UNSAT.
    Every non-timeout emitted proof must pass independent external VeriPB.
    """
    t=time.perf_counter()
    if cnf.stat().st_size>30_000_000:
        return None,None,time.perf_counter()-t
    # No filenames, catalog categories, expected statuses or source ID
    # are supplied to this external proof emitter.
    budget=min(0.85,CAP-(time.perf_counter()-started))
    if budget<0.04:return None,None,time.perf_counter()-t
    with tempfile.TemporaryDirectory(prefix="clique-disjoint-ext-") as d:
        work=pathlib.Path(d);pb=work/"source.pbp";meta=work/"metadata.json"
        emit=frozen.execute([sys.executable,str(EXT),
            "--cnf",str(cnf),"--pbp",str(pb),"--meta",str(meta)],budget)
        guard_time=time.perf_counter()-t
        if emit["expired"]:
            return None,None,guard_time
        if emit["returncode"]==2 and not pb.exists():
            return None,None,guard_time
        if emit["returncode"]!=0 or not pb.is_file() or not meta.is_file():
            return None,unknown(s,rep,arm,started,"INVALID_EXT_EMITTER",
                (emit["stdout"]+emit["stderr"])[-300:],True,guard_time),guard_time
        try:metadata=json.loads(meta.read_text())
        except (ValueError,UnicodeError) as e:
            return None,unknown(s,rep,arm,started,
                "INVALID_EXT_META",str(e),True,guard_time),guard_time
        if metadata.get("source_sha256")!=s["sha256"]:
            return None,unknown(s,rep,arm,started,
                "INVALID_EXT_SOURCE_BINDING",critical=True,guard_s=guard_time),guard_time
        rem=CAP-(time.perf_counter()-started)
        if rem<=0:
            return None,unknown(s,rep,arm,started,
                "NO_EXT_EXTERNAL_CHECK_BUDGET",guard_s=guard_time),guard_time
        checker=frozen.execute([str(VERIPB),"--cnf",str(cnf),str(pb)],rem)
        guard_time=time.perf_counter()-t
        if checker["expired"]:
            return None,unknown(s,rep,arm,started,
                "EXT_VERIPB_TIMEOUT",guard_s=guard_time),guard_time
        if (checker["returncode"]!=0 or
           "s VERIFIED UNSATISFIABLE" not in checker["stdout"]+checker["stderr"]):
            return None,unknown(s,rep,arm,started,"INVALID_EXT_VERIPB",
                (checker["stdout"]+checker["stderr"])[-300:],
                True,guard_time),guard_time
        elapsed=time.perf_counter()-started
        if elapsed>CAP:
            return None,unknown(s,rep,arm,started,
                "EXT_OVER_E2E_CAP",guard_s=guard_time),guard_time
        result={"id":s["id"],"file_id":s["file_id"],
          "source_sha256":s["sha256"],"family":s["family"],
          "catalog_label":s["catalog_label"],"rep":rep,"arm":arm,
          "status":"UNSAT_VERIFIED","rc":20,
          "accepted":True,"strict_accepted":True,"critical":False,
          "reason":None,"certificate_kind":"VERIPB_CLIQUE_EXT",
          "proof_sha256":sha(pb),"proof_bytes":pb.stat().st_size,
          "guard_s":round(emit["wall_s"],6),
          "checker_s":round(checker["wall_s"],6),
          "e2e_s":round(elapsed,6),"PAR2_s":round(elapsed,6),
          "PAR2_strict_s":round(elapsed,6)}
        return result,None,guard_time

def combined(s,rep,arm):
    started=time.perf_counter()
    cnf=ROOT/s["path"]
    assert sha(cnf)==s["sha256"],("SOURCE_CHANGED",s["id"])
    made,bad,guard_s=ext_probe(s,cnf,started,rep,arm)
    if bad is not None:return bad
    if made is not None:return made
    if arm=="CLIQUE_EXT_ONLY":
        return unknown(s,rep,arm,started,"EXT_UNSUPPORTED_SAFE_UNKNOWN",guard_s=guard_s)
    rem=CAP-(time.perf_counter()-started)
    if rem<=0.04:
        return unknown(s,rep,arm,started,"NO_FALLBACK_BUDGET",guard_s=guard_s)
    prior_graph_cap,prior_native_cap=graph.CAP,graph.old.CAP
    graph.CAP=rem
    graph.old.CAP=rem
    try:
        native=graph.graph_trial(s,"GRAPH_PLUS_MATH5",rep)
    finally:
        graph.CAP=prior_graph_cap
        graph.old.CAP=prior_native_cap
    elapsed=time.perf_counter()-started
    accepted=bool(native["accepted"] and not native["critical"] and elapsed<=CAP)
    strict=bool(accepted and native["strict_accepted"] and
                native["certificate_kind"] in STRICT)
    row=dict(native)
    row.update(arm=arm,accepted=accepted,strict_accepted=strict,
        e2e_s=round(elapsed,6),
        PAR2_s=round(elapsed if accepted else 2*CAP,6),
        PAR2_strict_s=round(elapsed if strict else 2*CAP,6),
        preceding_extension_guard_s=round(guard_s,6))
    if elapsed>CAP and not native["critical"]:row["status"]="E2E_OVER_CAP"
    return row

def one(s,arm,rep):
    if arm in ("CLIQUE_EXT_ONLY","CLIQUE_EXT_GRAPH_MATH5"):
        row=combined(s,rep,arm)
    elif arm=="GRAPH_MATH5":
        row=graph.graph_trial(s,"GRAPH_PLUS_MATH5",rep)
        row["arm"]=arm
    elif arm=="X59_MATH5_VERIPB":
        row=graph.old.standard_trial(s,rep)
    else:
        row=frozen.trial(s,arm,rep)
    assert row["arm"]==arm and row["id"]==s["id"]
    assert row["source_sha256"]==s["sha256"]
    return row

def shard(idx):
    assert 0<=idx<SHARDS
    sources,_=restore()
    subset=[s for s in sources if s["id"]%SHARDS==idx]
    assert len(subset)==2
    target=OUT/f"shard-{idx}"
    target.mkdir(parents=True,exist_ok=False)
    records=[]
    with (target/"trials.jsonl").open("w") as fd:
        for s in subset:
            for rep in range(REPS):
                arms=list(ARMS)
                random.Random(f"DRNAS-DISJOINT25-{s['gbd_hash']}:{rep}").shuffle(arms)
                results={}
                for arm in arms:
                    row=one(s,arm,rep)
                    fd.write(json.dumps(row,sort_keys=True)+"\n");fd.flush()
                    records.append(row)
                    results[arm]={"status":row["status"],
                                  "strict":row["strict_accepted"],
                                  "strict_PAR2_s":row["PAR2_strict_s"],
                                  "kind":row["certificate_kind"]}
                print("GRAPH_DISJOINT25_PAIR "+json.dumps({
                    "id":s["id"],"rep":rep,"arms":results},
                    sort_keys=True),flush=True)
    assert len(records)==len(subset)*REPS*len(ARMS)==28
    summary={arm:{"strict_verified":sum(x["strict_accepted"] for x in records if x["arm"]==arm),
                  "strict_PAR2_s":round(sum(x["PAR2_strict_s"] for x in records if x["arm"]==arm),6)}
             for arm in ARMS}
    print("GRAPH_DISJOINT25_SHARD "+json.dumps({
        "shard":idx,"sources":len(subset),"trials":len(records),
        "summary":summary},sort_keys=True),flush=True)

def report():
    sources,p=restore()
    rows=[]
    for idx in range(SHARDS):
        path=OUT/f"shard-{idx}"/"trials.jsonl"
        assert path.is_file(),("MISSING_SHARD",idx)
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    expectation={(i,rep,a) for i in range(10) for rep in range(REPS) for a in ARMS}
    observed={(row["id"],row["rep"],row["arm"]) for row in rows}
    assert len(rows)==len(expectation)==len(observed)==140 and observed==expectation
    by_id={x["id"]:x for x in sources}
    errors=[]
    for row in rows:
        src=by_id[row["id"]]
        if row["source_sha256"]!=src["sha256"] or row["family"]!=src["family"]:
            errors.append({"id":row["id"],"arm":row["arm"],"reason":"SOURCE_SHA_OR_FAMILY_MISMATCH"})
        if row["critical"]:
            errors.append({"id":row["id"],"arm":row["arm"],
                           "reason":row["status"],"detail":row.get("reason")})
        if row["strict_accepted"] and (not row["accepted"] or
            row["certificate_kind"] not in STRICT):
            errors.append({"id":row["id"],"arm":row["arm"],
                           "reason":"UNVERIFIED_PROOF_SCORED_STRICT"})
    for id in range(10):
        accepted=[r for r in rows if r["id"]==id and r["accepted"]]
        if any(r["status"]=="SAT_VERIFIED" for r in accepted) and any(
               r["status"]=="UNSAT_VERIFIED" for r in accepted):
            errors.append({"id":id,"reason":"CONTRADICTORY_VERIFIED_RESULTS"})
    total={}
    for arm in ARMS:
        rr=[row for row in rows if row["arm"]==arm]
        total[arm]={
            "attempts":len(rr),
            "verified":sum(r["accepted"] for r in rr),
            "strict_verified":sum(r["strict_accepted"] for r in rr),
            "solved_sources":len({r["id"] for r in rr if r["strict_accepted"]}),
            "SAT_verified":sum(r["status"]=="SAT_VERIFIED" and r["strict_accepted"] for r in rr),
            "UNSAT_verified":sum(r["status"]=="UNSAT_VERIFIED" and r["strict_accepted"] for r in rr),
            "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in rr),6),
            "source_PAR2_s":round(sum(r["PAR2_s"] for r in rr),6),
            "proof_kinds":dict(collections.Counter(
               r["certificate_kind"] for r in rr if r["strict_accepted"])),
            "statuses":dict(collections.Counter(r["status"] for r in rr))}
    best=min(REFS,key=lambda arm:total[arm]["strict_PAR2_s"])
    per_id={id:{arm:statistics.mean(r["PAR2_strict_s"] for r in rows
             if r["id"]==id and r["arm"]==arm) for arm in ARMS}
             for id in range(10)}
    families=collections.defaultdict(list)
    for s in sources:families[s["family"]].append(s["id"])
    rnd=random.Random(20261116)
    comparisons={}
    for arm in ARMS:
        if arm in REFS:continue
        delta={id:per_id[id][best]-per_id[id][arm] for id in range(10)}
        clusters=[sum(delta[id] for id in group) for group in families.values()]
        bootstrap=sorted(sum(clusters[rnd.randrange(len(clusters))]
                    for _ in clusters) for _ in range(4000))
        comparisons[arm]={
            "best_reference":best,"families":len(clusters),
            "source_mean_aggregate_saving_s":round(sum(delta.values()),6),
            "family_bootstrap95_s":[round(bootstrap[100],6),round(bootstrap[3900],6)],
            "wins":sum(x>1e-4 for x in delta.values()),
            "losses":sum(x< -1e-4 for x in delta.values()),
            "ties":sum(abs(x)<=1e-4 for x in delta.values())}
    summary={"status":"COMPLETE" if not errors else "CRITICAL",
        "sources":len(sources),"catalog_families":len(families),
        "all_source_families_disjoint_from_prior_77":True,
        "trials":len(rows),"shards":SHARDS,"repetitions":REPS,
        "cap_seconds":CAP,"best_reference":best,
        "totals":total,"paired_family_bootstrap":comparisons,
        "critical_count":len(errors),"critical":errors,
        "source_manifest_sha256":p["new_source_manifest_sha256"],
        "source_family_list":sorted(families),
        "provenance":[{"id":s["id"],"gbd_hash":s["gbd_hash"],
                       "isohash":s["isohash"],"family":s["family"],
                       "source_sha256":s["sha256"]} for s in sources],
        "no_main_promotion":True,
        "scope":"Family + GBD hash/isohash disjoint from two tracked development datasets. 10 sources, seven families; cannot prove untested across all historic branches."}
    save(OUT/"final.json",summary)
    print("GRAPH_DISJOINT25_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
    if errors:raise SystemExit(1)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("prepare","shard","report"))
    ap.add_argument("--index",type=int)
    a=ap.parse_args()
    if a.action=="prepare":prepare()
    elif a.action=="shard":shard(a.index)
    else:report()
