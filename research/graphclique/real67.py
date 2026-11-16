#!/usr/bin/env python3
"""Paired 67-original retrospective graph-clique+MATH5 strict E2E PAR2 audit.

Six serial arms, two repetitions and ten independent shards. Frozen exact
2026 sources, source hashes, comparators and verifier binaries are restored
from successful GRAND UNIFIED run 43853390060. All wall-clock costs
(counted before native solver, and including VeriPB checker) share an 8s cap.
A graph-guard miss falls back to unchanged X59+MATH5, NEVER a parallel solver.
"""
import argparse,collections,hashlib,importlib.util,json,os,pathlib,random,statistics,sys,tempfile,time

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as frozen
spec=importlib.util.spec_from_file_location(
    "math5_standard_real67_base",
    ROOT/"research/math5_standard_real67/benchmark.py")
old=importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

OUT=ROOT/"results/graphclique_real67"
EXPORTER=HERE/"emit_veripb.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
CAP=8.0;SHARDS=10;REPS=2
ARMS=("GRAPH_ONLY","GRAPH_PLUS_MATH5","X59_MATH5_VERIPB",
      "Kissat","CaDiCaL","CryptoMiniSat")
REFS=("Kissat","CaDiCaL","CryptoMiniSat")
STRICT={"MODEL","DRAT","FRAT","VERIPB_CAPACITY","VERIPB_MATH5","VERIPB_GRAPH"}

def sha(path):return frozen.sha(path)
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def one_cpu():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        assert len(os.sched_getaffinity(0))==1

def signature(cnf):
    """Cheap CONTENT-ONLY gate: disjoint positive ALOs of uniform width.

    No family, CNF basename, expected status or catalog label is consulted.
    Source graph prover will independently verify every row and edge.
    """
    widths=[];seen=set()
    with cnf.open("r",encoding="ascii") as fd:
        for raw in fd:
            line=raw.split()
            if not line or line[0] in ("c","p"):continue
            # Only inspect the early source clauses, never read all huge CNFs.
            if len(line)>1 and line[-1]=="0":
                row=[int(v) for v in line[:-1]]
                if 2<=len(row)<=64 and all(v>0 for v in row):
                    if any(v in seen for v in row):return False
                    seen.update(row);widths.append(len(row))
                    if len(widths)>=8:break
                elif len(widths)>=2:
                    break
                if len(widths)>20:break
    return len(widths)>=8 and len(set(widths))==1

def unknown(source,rep,arm,started,status,reason=None,critical=False,guard_s=0):
    elapsed=time.perf_counter()-started
    return {"id":source["id"],"file_id":source["file_id"],
        "source_sha256":source["sha256"],"family":source["family"],
        "catalog_label":source["catalog_label"],"arm":arm,"rep":rep,
        "rc":None,"status":status,"reason":reason,"critical":critical,
        "accepted":False,"strict_accepted":False,
        "certificate_kind":None,"e2e_s":round(elapsed,6),
        "PAR2_s":2*CAP,"PAR2_strict_s":2*CAP,
        "guard_s":round(guard_s,6),"checker_s":0,
        "proof_sha256":None,"proof_bytes":0}

def graph_trial(source,arm,rep):
    started=time.perf_counter()
    cnf=ROOT/source["path"]
    assert sha(cnf)==source["sha256"],"source identity changed"
    is_combo=arm=="GRAPH_PLUS_MATH5"
    probe_elapsed=0
    if signature(cnf):
        with tempfile.TemporaryDirectory(prefix="graphclique-real67-") as d:
            folder=pathlib.Path(d)
            proof=folder/"graph.pbp";meta=folder/"graph.json"
            budget=min(4.5,CAP-(time.perf_counter()-started))
            if budget>0.01:
                run=frozen.execute([sys.executable,str(EXPORTER),
                    "--cnf",str(cnf),"--pbp",str(proof),
                    "--meta",str(meta)],budget)
                probe_elapsed=run["wall_s"]
                if run["expired"]:
                    # Guard ran out of its limited scout budget. Safe fallback.
                    pass
                elif run["returncode"]==0:
                    if not proof.is_file() or not meta.is_file():
                        return unknown(source,rep,arm,started,
                            "INVALID_MISSING_GRAPH_PROOF",critical=True,guard_s=probe_elapsed)
                    info=json.loads(meta.read_text())
                    if info["source_sha256"]!=source["sha256"]:
                        return unknown(source,rep,arm,started,
                            "INVALID_GRAPH_SOURCE_SHA",critical=True,guard_s=probe_elapsed)
                    remaining=CAP-(time.perf_counter()-started)
                    if remaining<=0:
                        return unknown(source,rep,arm,started,
                            "NO_STANDARD_VERIPB_BUDGET",guard_s=probe_elapsed)
                    checked=frozen.execute([str(VERIPB),"--cnf",str(cnf),
                        str(proof)],remaining)
                    verified=(not checked["expired"] and checked["returncode"]==0
                        and "s VERIFIED UNSATISFIABLE" in checked["stdout"]+checked["stderr"])
                    if not verified:
                        return unknown(source,rep,arm,started,
                            "GRAPH_VERIPB_CHECK_TIMEOUT" if checked["expired"]
                            else "INVALID_EXTERNAL_GRAPH_VERIPB",
                            reason=(checked["stdout"]+checked["stderr"])[-350:],
                            critical=not checked["expired"],guard_s=probe_elapsed)
                    elapsed=time.perf_counter()-started
                    if elapsed<=CAP:
                        return {"id":source["id"],"file_id":source["file_id"],
                            "source_sha256":source["sha256"],"family":source["family"],
                            "catalog_label":source["catalog_label"],"arm":arm,"rep":rep,
                            "rc":20,"status":"UNSAT_VERIFIED","reason":None,"critical":False,
                            "accepted":True,"strict_accepted":True,
                            "certificate_kind":"VERIPB_GRAPH",
                            "e2e_s":round(elapsed,6),"PAR2_s":round(elapsed,6),
                            "PAR2_strict_s":round(elapsed,6),
                            "guard_s":round(probe_elapsed,6),
                            "checker_s":round(checked["wall_s"],6),
                            "proof_sha256":sha(proof),"proof_bytes":proof.stat().st_size,
                            "color_count":info["color_count"],
                            "clique_size":info["clique_size"]}
                    return unknown(source,rep,arm,started,"E2E_OVER_CAP",guard_s=probe_elapsed)
                elif run["returncode"]==2 and not proof.exists():
                    pass # Unsupported structure, NOT a negative proof.
                else:
                    return unknown(source,rep,arm,started,
                        "INVALID_GRAPH_EMITTER",
                        reason=(run["stdout"]+run["stderr"])[-350:],
                        critical=True,guard_s=probe_elapsed)
    if not is_combo:
        return unknown(source,rep,arm,started,
                       "GRAPH_UNKNOWN_SAFE_FALLBACK_NOT_REQUESTED",guard_s=probe_elapsed)
    remaining=CAP-(time.perf_counter()-started)
    if remaining<=0.015:
        return unknown(source,rep,arm,started,
                       "NO_NATIVE_FALLBACK_BUDGET",guard_s=probe_elapsed)
    # Charge the graph guard's elapsed time to the SAME 8-second trial.
    # This changes the time cap of the unchanged frozen sequential X59
    # wrapper only for this one local call; no second solver is parallel.
    saved_cap=old.CAP
    old.CAP=remaining
    try:
        native=old.standard_trial(source,rep)
    finally:
        old.CAP=saved_cap
    elapsed=time.perf_counter()-started
    accepted=bool(native["accepted"] and elapsed<=CAP and not native["critical"])
    strict=bool(accepted and native["strict_accepted"]
                and native["certificate_kind"] in STRICT)
    row=dict(native)
    row.update(arm=arm,e2e_s=round(elapsed,6),
               accepted=accepted,strict_accepted=strict,
               PAR2_s=round(elapsed if accepted else 2*CAP,6),
               PAR2_strict_s=round(elapsed if strict else 2*CAP,6),
               guard_s=round(elapsed-native["e2e_s"],6))
    if elapsed>CAP and not row["critical"]:row["status"]="E2E_OVER_CAP"
    return row

def one(source,arm,rep):
    if arm.startswith("GRAPH_"):return graph_trial(source,arm,rep)
    if arm=="X59_MATH5_VERIPB":return old.standard_trial(source,rep)
    return frozen.trial(source,arm,rep)

def prepare():
    one_cpu()
    originals=frozen.frozen_sources()
    assert originals["selected"]==67
    pins=frozen.pinned()
    proto={"protocol":"DRNAS-GRAPH-CLIQUE-REAL67-E2E-PAR2-V1",
           "snapshot":"GRAND UNIFIED 43853390060",
           "source_manifest_sha256":sha(frozen.DATA/"manifest.json"),
           "prior_protocol_sha256":sha(frozen.OUT/"protocol.json"),
           "frozen_binaries":pins,
           "graph_proof_emitter_sha256":sha(EXPORTER),
           "benchmark_script_sha256":sha(HERE/"real67.py"),
           "run_commit":os.environ.get("GITHUB_SHA"),
           "shards":SHARDS,"repetitions":REPS,"source_count":67,
           "arms":list(ARMS),"cap_s":CAP,
           "expected_trials":67*REPS*len(ARMS),
           "strict_standard_verification":sorted(STRICT),
           "retrospective_not_blind":True,
           "one_logical_cpu_per_solver":True,"no_parallel_portfolio":True,
           "no_auto_promotion":True}
    save(OUT/"protocol.json",proto)
    print("GRAPH_67_READY "+json.dumps(
        {"sources":67,"shards":SHARDS,"arms":ARMS,
         "trials":proto["expected_trials"]},sort_keys=True),flush=True)

def restore():
    one_cpu()
    sources,prior=frozen.restore()
    proto=json.loads((OUT/"protocol.json").read_text())
    assert proto["source_count"]==len(sources)==67
    assert proto["arms"]==list(ARMS) and proto["cap_s"]==CAP
    assert proto["source_manifest_sha256"]==sha(frozen.DATA/"manifest.json")
    assert proto["prior_protocol_sha256"]==sha(frozen.OUT/"protocol.json")
    assert proto["frozen_binaries"]==frozen.pinned()
    assert proto["graph_proof_emitter_sha256"]==sha(EXPORTER)
    assert proto["benchmark_script_sha256"]==sha(HERE/"real67.py")
    assert proto["run_commit"]==os.environ.get("GITHUB_SHA")
    return sources

def shard(i):
    assert 0<=i<SHARDS
    sources=restore()
    selection=[s for s in sources if s["id"]%SHARDS==i]
    assert selection
    out=OUT/f"shard-{i}"
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    with (out/"trials.jsonl").open("w") as output:
        for src in selection:
            for rep in range(REPS):
                arms=list(ARMS)
                random.Random(f"graph-clique-real67-20261116:{src['id']}:{rep}").shuffle(arms)
                per={}
                for arm in arms:
                    result=one(src,arm,rep)
                    rows.append(result)
                    output.write(json.dumps(result,sort_keys=True)+"\n");output.flush()
                    per[arm]={"status":result["status"],
                              "strict":result["strict_accepted"],
                              "PAR2_strict_s":result["PAR2_strict_s"]}
                print("GRAPH_67_PAIR "+json.dumps(
                    {"source_id":src["id"],"rep":rep,"arms":per},
                    sort_keys=True),flush=True)
    assert len(rows)==len(selection)*REPS*len(ARMS)
    summary={arm:{"strict":sum(r["strict_accepted"] for r in rows if r["arm"]==arm),
                  "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in rows if r["arm"]==arm),6)}
             for arm in ARMS}
    print("GRAPH_67_SHARD "+json.dumps(
        {"shard":i,"sources":len(selection),"trials":len(rows),
         "summary":summary},sort_keys=True),flush=True)

def aggregate():
    sources=restore()
    rows=[]
    for i in range(SHARDS):
        path=OUT/f"shard-{i}"/"trials.jsonl"
        assert path.is_file(),("MISSING_SHARD",i)
        rows.extend(json.loads(x) for x in path.read_text().splitlines())
    expected={(i,rep,arm) for i in range(67) for rep in range(REPS) for arm in ARMS}
    observed={(r["id"],r["rep"],r["arm"]) for r in rows}
    assert len(rows)==len(observed)==len(expected)==804 and observed==expected
    originals={src["id"]:src for src in sources}
    errors=[]
    for row in rows:
        src=originals[row["id"]]
        if row["source_sha256"]!=src["sha256"] or row["family"]!=src["family"]:
            errors.append({"id":row["id"],"error":"SOURCE_SHA_OR_FAMILY_MISMATCH"})
        if row["critical"]:errors.append({"id":row["id"],"arm":row["arm"],"status":row["status"]})
        if row["strict_accepted"] and (
                not row["accepted"] or row["certificate_kind"] not in STRICT):
            errors.append({"id":row["id"],"arm":row["arm"],"error":"NONSTANDARD_PROOF_SCORED"})
    for i in range(67):
        rr=[r for r in rows if r["id"]==i and r["accepted"]]
        if any(r["status"]=="SAT_VERIFIED" for r in rr) and any(
                r["status"]=="UNSAT_VERIFIED" for r in rr):
            errors.append({"id":i,"error":"CONTRADICTORY_VERIFIED_SAT_AND_UNSAT"})
    totals={}
    for arm in ARMS:
        r=[x for x in rows if x["arm"]==arm]
        totals[arm]={
           "attempts":len(r),"verified":sum(x["accepted"] for x in r),
           "strict_verified":sum(x["strict_accepted"] for x in r),
           "unique_strict_sources":len({x["id"] for x in r if x["strict_accepted"]}),
           "graph_veripb":sum(x["strict_accepted"] and x["certificate_kind"]=="VERIPB_GRAPH" for x in r),
           "math5_veripb":sum(x["strict_accepted"] and x["certificate_kind"]=="VERIPB_MATH5" for x in r),
           "SAT_verified":sum(x["accepted"] and x["status"]=="SAT_VERIFIED" for x in r),
           "UNSAT_verified":sum(x["accepted"] and x["status"]=="UNSAT_VERIFIED" for x in r),
           "structural_PAR2_s":round(sum(x["PAR2_s"] for x in r),6),
           "strict_PAR2_s":round(sum(x["PAR2_strict_s"] for x in r),6),
           "statuses":dict(collections.Counter(x["status"] for x in r)),
           "certificate_kinds":dict(collections.Counter(
               x["certificate_kind"] for x in r if x["accepted"]))}
    best=min(REFS,key=lambda a:totals[a]["strict_PAR2_s"])
    families=collections.defaultdict(list)
    for src in sources:families[src["family"]].append(src["id"])
    byid={i:{arm:statistics.mean(
        x["PAR2_strict_s"] for x in rows if x["id"]==i and x["arm"]==arm)
        for arm in ARMS} for i in range(67)}
    rng=random.Random(20261116)
    paired={}
    for arm in ARMS:
        if arm in REFS:continue
        differences={i:byid[i][best]-byid[i][arm] for i in range(67)}
        clusters=[sum(differences[i] for i in ids) for ids in families.values()]
        samples=sorted(sum(clusters[rng.randrange(len(clusters))]
            for _ in clusters) for _ in range(3000))
        paired[arm]={"reference":best,"families":len(clusters),
            "source_mean_total_saving_s":round(sum(differences.values()),6),
            "family_bootstrap95_s":[round(samples[75],6),round(samples[2925],6)],
            "wins":sum(x>1e-4 for x in differences.values()),
            "losses":sum(x< -1e-4 for x in differences.values()),
            "ties":sum(abs(x)<=1e-4 for x in differences.values())}
    all_graph=sorted({x["id"] for x in rows if
        x["arm"]=="GRAPH_PLUS_MATH5" and x["strict_accepted"]
        and x["certificate_kind"]=="VERIPB_GRAPH"})
    result={"status":"COMPLETE" if not errors else "FAILED",
        "N":67,"reps":REPS,"trials":len(rows),
        "retrospective_not_blind":True,"strict_reference":best,
        "totals":totals,"paired_family_bootstrap_strict":paired,
        "graph_verified_original_ids":all_graph,
        "critical":errors,"critical_count":len(errors),
        "no_main_promotion":True}
    save(OUT/"final.json",result)
    print("GRAPH_67_FINAL "+json.dumps(result,sort_keys=True),flush=True)
    if errors:raise SystemExit(1)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("prepare","shard","report"))
    p.add_argument("--index",type=int)
    a=p.parse_args()
    if a.action=="prepare":prepare()
    elif a.action=="shard":shard(a.index)
    else:aggregate()
