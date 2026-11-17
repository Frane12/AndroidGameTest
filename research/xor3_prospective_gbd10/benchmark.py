#!/usr/bin/env python3
"""Prospective original SAT23/24/25 XOR3/Tseitin holdout: 10 x 2 x 6 arms.

All source identities were committed before ANY newly selected source was
downloaded or any candidate/reference solver evaluated on the ten originals.
The XOR3 extended-VeriPB producer is frozen from independently certified
original ID6 run 44041467828, not tuned against this new holdout.
One logical CPU per solver process; serial arms within source/repetition.
8s E2E includes CNF SHA checking, solver, producer, external proof checker.
All source/model/proof checker failures are fatal; UNKNOWN scores PAR2=16.
"""
import argparse,collections,importlib.util,json,os,pathlib,random,statistics,sys,time

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
DATA=HERE/"inputs"
OUT=ROOT/"results/xor3_prospective_gbd10"
sys.path.insert(0,str(ROOT/"research"/"unified_evidence"))
import benchmark as frozen
sys.path.insert(0,str(ROOT/"research"/"graphclique"))
import real67 as graph

# Import unchanged certified XOR3 proof pipeline from its existing script.
prior_spec=importlib.util.spec_from_file_location(
    "original_xor3_standard_bridge",
    ROOT/"research"/"math5"/"xor3_tseitin_id6.py")
xor3=importlib.util.module_from_spec(prior_spec)
prior_spec.loader.exec_module(xor3)

CAP=8.0
REPS=2
SHARDS=5
ARMS=("XOR3_NATIVE_VERIPB","XOR3_SCOUT_THEN_MATH5",
      "X59_MATH5_VERIPB","Kissat","CaDiCaL","CryptoMiniSat")
REFS=("Kissat","CaDiCaL","CryptoMiniSat")
STRICT={"MODEL","DRAT","FRAT","VERIPB_MATH5","VERIPB_XOR3_CARRY_RED_RUP_CP",
        "VERIPB_GRAPH","VERIPB_CAPACITY"}

SOURCE_MANIFESTS=(
    ROOT/"unified_realblind100_inputs/manifest.json",
    ROOT/"research/graph_unseen25/inputs/manifest.json",
    ROOT/"research/graph_family_disjoint25/inputs/manifest.json"
)
CHECKED_SCRIPTS=(
    ROOT/"research/math5/emit_veripb_xor3_carry.py",
    ROOT/"research/math5/check_math5.py",
    ROOT/"research/math5/xor3_tseitin_id6.py",
    ROOT/"research/math5/emit_veripb_eo_multiplicity.py",
    HERE/"benchmark.py"
)

def sha(p):return frozen.sha(p)

def save(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def onecpu():
    if hasattr(os,"sched_setaffinity"):
        allowed=os.sched_getaffinity(0)
        assert allowed, "NO_LOGICAL_CPU"
        os.sched_setaffinity(0,{min(allowed)})
        assert len(os.sched_getaffinity(0))==1

def load_originals():
    prespec=json.loads((HERE/"prespec.json").read_text())
    manifest=json.loads((DATA/"manifest.json").read_text())
    assert prespec["protocol"]=="DRNAS-XOR3-PROSPECTIVE-GBD10-20261117-V1"
    assert manifest["status"]=="FROZEN_SOURCE_ONLY_NO_SOLVER_RUN"
    assert manifest["protocol"]==prespec["protocol"]
    assert prespec["no_solver_until_all_original_SHA256_frozen"]
    assert prespec["no_post_outcome_instance_substitution"]
    assert len(prespec["instances"])==len(manifest["sources"])==10
    assert manifest["selected_count"]==10
    assert sha(HERE/"prespec.json")==manifest["prespec_sha256"]
    provenance=manifest["provenance"]
    assert provenance["previous_source_count"]==87
    assert provenance["source_GBD_disjoint"]
    assert provenance["source_isohashes_disjoint"]
    assert provenance["previous_gbd_overlap"]==provenance["previous_iso_overlap"]==0
    for p in SOURCE_MANIFESTS:
        assert sha(p)==provenance["old_manifests_sha256"][str(p.relative_to(ROOT))]
    for selected,source in zip(prespec["instances"],manifest["sources"]):
        for key in ("id","track","gbd_hash","isohash","isohash2","family"):
            assert selected[key]==source[key],("SOURCE_IDENTITY_CHANGED",key,source["id"])
        assert source["file_id"]==source["gbd_hash"]
        assert sha(ROOT/source["path"])==source["sha256"],("SOURCE_SHA_CHANGED",source["id"])
    return prespec,manifest

def prepare():
    onecpu()
    prespec,m=load_originals()
    pins=frozen.pinned()
    policy={"name":"DRNAS-XOR3-PROSPECTIVE-GBD10-STRICT-E2E-V1",
        "source_count":10,"family_count":len({s["family"] for s in m["sources"]}),
        "source_tracks":sorted({s["track"] for s in m["sources"]}),
        "expected_trials":10*REPS*len(ARMS),"shards":SHARDS,
        "repetitions":REPS,"arms":list(ARMS),"references":list(REFS),
        "cap_s":CAP,"PAR2_timeout_s":2*CAP,
        "source_manifest_sha256":sha(DATA/"manifest.json"),
        "prespec_sha256":sha(HERE/"prespec.json"),
        "prior_87_manifest_sha256":m["provenance"]["old_manifests_sha256"],
        "pinned_reference_binaries_sha256":pins,
        "pinned_code_sha256":{str(path.relative_to(ROOT)):sha(path)
                              for path in CHECKED_SCRIPTS},
        "executed_commit_sha256":os.environ.get("GITHUB_SHA"),
        "single_logical_cpu_per_trial":True,
        "no_parallel_solver_portfolio":True,
        "source_labels_not_exposed_to_solver":True,
        "standard_proof_kinds":sorted(STRICT),
        "frozen_before_any_holdout_outcomes":True,
        "not_family_disjoint_from_prior_graph_datasets":True,
        "no_main_promotion":True,
        "scope":"instance-level prospective; 10 originals/3 catalog families, mixed coding, no claim of family-disjoint general superiority"}
    save(OUT/"protocol.json",policy)
    xor3.OUT=OUT/"verified_proof_artifacts"
    print("XOR3_HOLDOUT_PREPARED "+json.dumps({
        "sources":10,"arms":len(ARMS),"expected_trials":policy["expected_trials"],
        "family_count":policy["family_count"],
        "manifest_sha256":policy["source_manifest_sha256"]},sort_keys=True),flush=True)

def restore():
    onecpu()
    pre,m=load_originals()
    p=json.loads((OUT/"protocol.json").read_text())
    assert p["name"]=="DRNAS-XOR3-PROSPECTIVE-GBD10-STRICT-E2E-V1"
    assert p["source_count"]==10 and p["arms"]==list(ARMS)
    assert p["source_manifest_sha256"]==sha(DATA/"manifest.json")
    assert p["prespec_sha256"]==sha(HERE/"prespec.json")
    assert p["pinned_reference_binaries_sha256"]==frozen.pinned()
    assert p["executed_commit_sha256"]==os.environ.get("GITHUB_SHA")
    for filepath,expected in p["pinned_code_sha256"].items():
        assert sha(ROOT/filepath)==expected,("BENCHMARK_CODE_SHA_CHANGED",filepath)
    xor3.OUT=OUT/"verified_proof_artifacts"
    return m["sources"],p

def unknown(s,rep,arm,started,reason,status="UNKNOWN",critical=False):
    elapsed=time.perf_counter()-started
    return {"id":s["id"],"file_id":s["file_id"],
         "source_sha256":s["sha256"],"family":s["family"],
         "arm":arm,"rep":rep,"status":status,"reason":reason,
         "critical":critical,"accepted":False,"strict_accepted":False,
         "certificate_kind":None,"e2e_s":round(elapsed,6),
         "PAR2_s":2*CAP,"PAR2_strict_s":2*CAP,"proof_sha256":None,
         "proof_bytes":0}

def wrap_xor(s,rep,arm,inner,started=None):
    row=dict(inner)
    row.update({"id":s["id"],"file_id":s["file_id"],"rep":rep,
                "source_sha256":s["sha256"],"family":s["family"],
                "arm":arm})
    if started is not None:
        elapsed=time.perf_counter()-started
        accepted=bool(row["accepted"] and not row["critical"] and elapsed<=CAP)
        strict=bool(accepted and row["strict_accepted"] and
                    row["certificate_kind"] in STRICT)
        row.update(accepted=accepted,strict_accepted=strict,
                   e2e_s=round(elapsed,6),
                   PAR2_s=round(elapsed if accepted else 2*CAP,6),
                   PAR2_strict_s=round(elapsed if strict else 2*CAP,6))
        if elapsed>CAP and not row["critical"]:
            row["status"]="E2E_OVER_CAP"
    return row

def new_only(s,rep):
    xor3.OUT=OUT/"verified_proofs"/f"source_{s['id']:02d}"
    inner=xor3.strict_xor3(s,rep)
    return wrap_xor(s,rep,"XOR3_NATIVE_VERIPB",inner)

def new_then_fallback(s,rep):
    xor3.OUT=OUT/"verified_proofs"/f"source_{s['id']:02d}"
    started=time.perf_counter()
    old_cap=xor3.CAP
    xor3.CAP=min(1.0,CAP)
    try:
        first=xor3.strict_xor3(s,rep)
    finally:
        xor3.CAP=old_cap
    elapsed=time.perf_counter()-started
    if first["critical"] or first["strict_accepted"]:
        return wrap_xor(s,rep,"XOR3_SCOUT_THEN_MATH5",first,started)
    rem=CAP-elapsed
    if rem<=0.025:
        return unknown(s,rep,"XOR3_SCOUT_THEN_MATH5",started,
                       "No time after bounded XOR3 scout","NO_FALLBACK_BUDGET")
    old_cap=graph.old.CAP
    graph.old.CAP=rem
    try:
        second=graph.old.standard_trial(s,rep)
    finally:
        graph.old.CAP=old_cap
    row=wrap_xor(s,rep,"XOR3_SCOUT_THEN_MATH5",second,started)
    row["xor3_scout_s"]=round(elapsed,6)
    row["xor3_scout_status"]=first["status"]
    return row

def trial(s,arm,rep):
    if arm=="XOR3_NATIVE_VERIPB":
        row=new_only(s,rep)
    elif arm=="XOR3_SCOUT_THEN_MATH5":
        row=new_then_fallback(s,rep)
    elif arm=="X59_MATH5_VERIPB":
        row=graph.old.standard_trial(s,rep)
    else:
        row=frozen.trial(s,arm,rep)
    assert row["id"]==s["id"] and row["arm"]==arm
    assert row["source_sha256"]==s["sha256"]
    assert row["rep"]==rep
    assert row["PAR2_strict_s"]<=2*CAP
    if row["strict_accepted"] and not (row["accepted"] and
                                      row["certificate_kind"] in STRICT):
        raise RuntimeError("NONSTANDARD_OR_INCORRECT_ACCEPTANCE")
    return row

def shard(index):
    assert 0<=index<SHARDS
    sources,_=restore()
    chosen=[s for s in sources if s["id"]%SHARDS==index]
    assert len(chosen)==2
    folder=OUT/f"shard-{index}"
    folder.mkdir(parents=True,exist_ok=False)
    data=[]
    with (folder/"trials.jsonl").open("w") as stream:
        for source in chosen:
            for rep in range(REPS):
                order=list(ARMS)
                random.Random(f"XOR3-PRESPEC-20261117-{source['gbd_hash']}:{rep}").shuffle(order)
                results={}
                for arm in order:
                    row=trial(source,arm,rep)
                    stream.write(json.dumps(row,sort_keys=True)+"\n")
                    stream.flush()
                    data.append(row)
                    results[arm]={"status":row["status"],
                                  "strict":row["strict_accepted"],
                                  "PAR2_strict_s":row["PAR2_strict_s"],
                                  "certificate_kind":row.get("certificate_kind")}
                print("XOR3_HOLDOUT_PAIR "+json.dumps(
                  {"id":source["id"],"family":source["family"],
                   "rep":rep,"arms":results},sort_keys=True),flush=True)
    assert len(data)==2*REPS*len(ARMS)==24
    print("XOR3_HOLDOUT_SHARD "+json.dumps(
      {"index":index,"sources":len(chosen),"trials":len(data),
       "totals":{arm:{"strict_verified":sum(r["strict_accepted"] for r in data if r["arm"]==arm),
                      "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in data if r["arm"]==arm),6)}
                  for arm in ARMS}},sort_keys=True),flush=True)

def report():
    sources,p=restore()
    all_rows=[]
    for index in range(SHARDS):
        f=OUT/f"shard-{index}/trials.jsonl"
        assert f.is_file(),("MISSING_SHARD",index)
        all_rows.extend(json.loads(line) for line in f.read_text().splitlines())
    expected={(i,rep,arm) for i in range(10) for rep in range(REPS) for arm in ARMS}
    observed={(r["id"],r["rep"],r["arm"]) for r in all_rows}
    assert len(all_rows)==len(expected)==len(observed)==120 and observed==expected,(
        "INCOMPLETE_OR_DUPLICATE_MATRIX",len(all_rows),len(observed))
    source_by_id={s["id"]:s for s in sources}
    critical=[]
    for r in all_rows:
        source=source_by_id[r["id"]]
        if r["critical"]:
            critical.append({"id":r["id"],"rep":r["rep"],
                             "arm":r["arm"],"reason":r["status"]})
        if r["source_sha256"]!=source["sha256"] or r["family"]!=source["family"]:
            critical.append({"id":r["id"],"reason":"IDENTITY_MISMATCH"})
        if r["strict_accepted"] and (not r["accepted"] or
                                    r["certificate_kind"] not in STRICT):
            critical.append({"id":r["id"],"reason":"UNVERIFIED_STRICT"})
        if r["PAR2_strict_s"]!=2*CAP and not r["strict_accepted"]:
            critical.append({"id":r["id"],"reason":"INVALID_PAR2_SCORING"})
    for i in range(10):
        good=[r for r in all_rows if r["id"]==i and r["strict_accepted"]]
        if (any(r["status"]=="SAT_VERIFIED" for r in good)
            and any(r["status"]=="UNSAT_VERIFIED" for r in good)):
            critical.append({"id":i,"reason":"CONTRADICTORY_CERTIFIED_SAT_UNSAT"})
    total={}
    for arm in ARMS:
        group=[r for r in all_rows if r["arm"]==arm]
        total[arm]={"attempts":len(group),
           "strict_verified":sum(r["strict_accepted"] for r in group),
           "source_verified":sum(r["accepted"] for r in group),
           "verified_sources":len({r["id"] for r in group if r["strict_accepted"]}),
           "strict_SAT":sum(r["status"]=="SAT_VERIFIED" and r["strict_accepted"] for r in group),
           "strict_UNSAT":sum(r["status"]=="UNSAT_VERIFIED" and r["strict_accepted"] for r in group),
           "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in group),6),
           "source_PAR2_s":round(sum(r["PAR2_s"] for r in group),6),
           "proof_kinds":dict(collections.Counter(r.get("certificate_kind")
                          for r in group if r["strict_accepted"])),
           "statuses":dict(collections.Counter(r["status"] for r in group))}
    best=min(REFS,key=lambda arm:total[arm]["strict_PAR2_s"])
    by_id={i:{arm:statistics.mean(r["PAR2_strict_s"] for r in all_rows
                                  if r["id"]==i and r["arm"]==arm)
               for arm in ARMS} for i in range(10)}
    by_family=collections.defaultdict(list)
    for s in sources:by_family[s["family"]].append(s["id"])
    rand=random.Random(20261117)
    compare={}
    for arm in ARMS:
        if arm in REFS:continue
        delta={i:by_id[i][best]-by_id[i][arm] for i in range(10)}
        clusters=[sum(delta[i] for i in ids) for ids in by_family.values()]
        samples=sorted(sum(clusters[rand.randrange(len(clusters))]
                       for _ in clusters) for _ in range(4000))
        compare[arm]={"best_reference":best,
          "source_mean_total_savings_s":round(sum(delta.values()),6),
          "source_wins":sum(x>0.0001 for x in delta.values()),
          "source_losses":sum(x<-0.0001 for x in delta.values()),
          "source_ties":sum(abs(x)<=0.0001 for x in delta.values()),
          "family_count":len(clusters),
          "family_bootstrap95_s":[round(samples[100],6),round(samples[3900],6)],
          "caution":"Only 3 catalog families, CI is descriptive and underpowered"}
    final={"status":"COMPLETE" if not critical else "CRITICAL",
       "track_set":sorted({s["track"] for s in sources}),
       "source_count":10,"families":sorted(by_family),
       "attempts":len(all_rows),"cap_s":CAP,
       "critical_count":len(critical),"critical":critical,
       "best_reference":best,"totals":total,"paired":compare,
       "source_manifest_sha256":p["source_manifest_sha256"],
       "prior_87_disjoint_source_identifiers":True,
       "per_source":[{"id":s["id"],"family":s["family"],"track":s["track"],
                      "gbd_hash":s["gbd_hash"],"isohash":s["isohash"],
                      "isohash2":s["isohash2"],"sha256":s["sha256"]}
                      for s in sources],
       "one_CPU_per_solver":True,"strict_independent_proofs_only":True,
       "not_blind_against_world":True,"instance_level_prospective":True,
       "no_main_promotion":True}
    save(OUT/"final.json",final)
    print("XOR3_HOLDOUT_FINAL "+json.dumps(final,sort_keys=True),flush=True)
    if critical:raise SystemExit(1)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("prepare","shard","report"))
    a.add_argument("--index",type=int)
    args=a.parse_args()
    if args.action=="prepare":prepare()
    elif args.action=="shard":shard(args.index)
    else:report()
