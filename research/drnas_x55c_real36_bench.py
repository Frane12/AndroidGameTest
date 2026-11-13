#!/usr/bin/env python3
"""X5.5c: 36 SHA-frozen original SAT2024 CNFs x 2 repeats x 8 arms, 15s.

Primary question: does watched-literal rotation improve verified PAR2 or
process CPU after compensating for profiling overhead and recompilation?
This reuses previously seen original REAL36 formulas: retrospective,
not a blind holdout. All SAT witnesses checked; all accepted UNSAT answers
require independent DRAT. Never infer solved from plain rc=20.
"""
import argparse,collections,hashlib,json,pathlib,random,tempfile
import drnas_x55b_batched_real12 as E

B=E.B
CAP=15.0
REPEATS=2
SHARDS=12
DRNAS_ARMS=("X54_CONTROL","X54_ROTATE","X55B_CONTROL_OFF",
            "X55B_CONTROL_ON","X55B_ROTATE_OFF","X55B_ROTATE_ON")
REF_ARMS=("KISSAT","CADICAL")
ARMS=DRNAS_ARMS+REF_ARMS

# Only source and cap selection differ from validated predecessors.
E.CAP=CAP
B.CAP=CAP
E.BIN["X55B_ROTATE_OFF"]="build/drnas-x55b"
E.ARMS=DRNAS_ARMS
E.PROFILED={"X55B_CONTROL_ON","X55B_ROTATE_ON"}

def emit(key,obj):
    print(key+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def sources():
    arr,original=B.official_manifest()
    assert len(arr)==36 and len({x["sha256"] for x in arr})==36
    assert {x["id"] for x in arr}==set(range(36))
    return arr,original

def executable(arm):
    return E.BIN[arm] if arm in DRNAS_ARMS else B.BIN[arm]

def freeze():
    arr,original=sources()
    frozen={
      "dataset":"SAT Competition 2024 original REAL36 STRICT (previously evaluated)",
      "source_run":43387395060,
      "real36_manifest_sha256":original["manifest_sha256"],
      "source_hashes":[x["sha256"] for x in arr],
      "source_families":dict(collections.Counter(x["family"] for x in arr)),
      "selection":"all 36 pre-frozen source IDs 0..35; not filtered by solved status",
      "arms":list(ARMS),
      "binary_sha256":{arm:B.sha(pathlib.Path(executable(arm)).read_bytes()) for arm in ARMS},
      "cap_s":CAP,"repeats":REPEATS,"shards":SHARDS,
      "total_runs":36*REPEATS*len(ARMS),
      "proof_output_cap_bytes":512*1024*1024,
      "proof_check":"independent drat-trim for all UNSAT, original model for SAT",
      "cpu":"single logical CPU per solver; user+system externally observed",
      "promotion":"none: retrospective diagnosis, future family-held-out benchmark required"
    }
    save("x55c_freeze/protocol.json",frozen)
    emit("X55C_FREEZE",frozen)

def run(src,arm,rep,temp):
    if arm in DRNAS_ARMS:
        v=E.trial(src,arm,rep,temp)
    else:
        v=B.record(src,arm,rep,temp)
    if v["status"] in ("WRONG_SAT","PROCESS_ERROR"):
        raise RuntimeError("Incorrect answer or unexplained process error: "+json.dumps(v))
    return v

def shard(idx):
    if not 0<=idx<SHARDS:raise RuntimeError("Bad shard")
    arr,_=sources()
    protocol=json.loads(pathlib.Path("x55c_freeze/protocol.json").read_text())
    assert protocol["source_hashes"]==[x["sha256"] for x in arr]
    for arm in ARMS:
        assert B.sha(pathlib.Path(executable(arm)).read_bytes())==protocol["binary_sha256"][arm]
    chosen=[x for x in arr if x["id"]%SHARDS==idx]
    assert len(chosen)==3
    out=pathlib.Path("x55c_shards")/str(idx);out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as d,(out/"trials.jsonl").open("w") as log:
        temp=pathlib.Path(d)
        for src in chosen:
            for rep in range(REPEATS):
                order=list(ARMS)
                random.Random(551513+src["id"]*37+rep).shuffle(order)
                for arm in order:
                    row=run(src,arm,rep,temp)
                    log.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
                    log.flush()
                    emit("X55C_TRIAL",{k:row[k] for k in ("source_id","family","arm","rep",
                         "status","accepted","PAR2_s","solve_e2e_s","cpu_s","maxrss_kib")})
                emit("X55C_PROGRESS",{"shard":idx,"last_source_id":src["id"],"repetition":rep})
    save(out/"manifest.json",{"shard":idx,"trials":3*REPEATS*len(ARMS),
         "sources":[x["sha256"] for x in chosen],
         "original_manifest_sha256":protocol["real36_manifest_sha256"],
         "binary_sha256":protocol["binary_sha256"]})
    emit("X55C_SHARD_FINAL",{"shard":idx,"runs":3*REPEATS*len(ARMS)})

def overall(rows):
    a={}
    for arm in ARMS:
        x=[v for v in rows if v["arm"]==arm]
        prof=[v.get("profile") or v.get("partial") or {} for v in x]
        total_cpu=sum(v.get("cpu_s") or 0 for v in x)
        sample_ns=sum(p.get("propagate_sample_cpu_ns",0) for p in prof)
        sample_n=sum(p.get("propagate_samples",0) for p in prof)
        estimated=64*sample_ns/1e9 if sample_n else None
        a[arm]={
          "attempts":len(x),
          "solved":sum(bool(v["accepted"]) for v in x),
          "SAT_verified":sum(bool(v["accepted"]) and v["status"]=="SAT_VERIFIED" for v in x),
          "UNSAT_certified":sum(bool(v["accepted"]) and v["status"]=="UNSAT_CERTIFIED" for v in x),
          "PAR2_s":round(sum(v["PAR2_s"] for v in x),5),
          "solve_wall_s":round(sum(v["solve_e2e_s"] for v in x),5),
          "process_cpu_s":round(total_cpu,5),
          "proof_check_s":round(sum(v["proof_audit_s"] for v in x),5),
          "maxrss_kib":max((v.get("maxrss_kib") or 0) for v in x),
          "proof_resource_limited":sum(v["status"]=="PROOF_SIZE_LIMIT" for v in x),
          "unknown":sum(v["status"] in ("UNKNOWN","timeout") for v in x),
          "sampled_propagate_calls":sample_n,
          "sampled_propagate_cpu_ns":sample_ns,
          "propagate_cpu_estimate_s":round(estimated,5) if estimated is not None else None,
          "sample_plausibility":(estimated is not None and estimated<=1.25*total_cpu)
        }
    return a

def comparison(rows,left,right,metric):
    by=collections.defaultdict(list)
    for row in rows:by[row["sha256"]].append(row)
    diffs=[]
    for sha,group in sorted(by.items()):
        a=[x for x in group if x["arm"]==left]
        b=[x for x in group if x["arm"]==right]
        assert len(a)==len(b)==REPEATS
        if any(x.get(metric) is None for x in a+b):
            return {"left":left,"right":right,"metric":metric,"available":False,
                    "reason":"A trial lacks an external CPU measurement; never impute zero"}
        diffs.append(sum(x[metric] for x in b)-sum(x[metric] for x in a))
    rng=random.Random(551513)
    bootstrap=sorted(sum(rng.choices(diffs,k=len(diffs))) for _ in range(4000))
    return {"left":left,"right":right,"metric":metric,
      "delta_right_minus_left":round(sum(diffs),5),
      "bootstrap95":[round(bootstrap[100],5),round(bootstrap[3899],5)],
      "clusters":len(diffs),"repeats_per_cluster":REPEATS}

def finish():
    arr,orig=sources()
    frozen=json.loads(pathlib.Path("x55c_freeze/protocol.json").read_text())
    assert orig["manifest_sha256"]==frozen["real36_manifest_sha256"]
    rows=[]
    for idx in range(SHARDS):
        folder=pathlib.Path("x55c_downloads")/f"x55c-shard-{idx}"
        m=json.loads((folder/"manifest.json").read_text())
        assert m["shard"]==idx and m["trials"]==3*REPEATS*len(ARMS)
        assert m["original_manifest_sha256"]==frozen["real36_manifest_sha256"]
        assert m["binary_sha256"]==frozen["binary_sha256"]
        batch=[json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
        assert len(batch)==m["trials"]
        assert {v["sha256"] for v in batch}==set(m["sources"])
        rows.extend(batch)
    expected={(x["sha256"],rep,arm) for x in arr for rep in range(REPEATS) for arm in ARMS}
    actual={(x["sha256"],x["rep"],x["arm"]) for x in rows}
    assert len(rows)==len(expected)==576 and expected==actual
    wrong=[x for x in rows if x["status"] in ("WRONG_SAT","PROCESS_ERROR")]
    assert not wrong,wrong[:2]
    results=overall(rows)
    comparisons={}
    pairs=[
      ("rotate_frozen","X54_CONTROL","X54_ROTATE"),
      ("rotate_unprofiled","X55B_CONTROL_OFF","X55B_ROTATE_OFF"),
      ("profile_overhead_fixed","X55B_CONTROL_OFF","X55B_CONTROL_ON"),
      ("profile_overhead_rotating","X55B_ROTATE_OFF","X55B_ROTATE_ON"),
      ("control_recompile_effect","X54_CONTROL","X55B_CONTROL_OFF"),
      ("rotating_recompile_effect","X54_ROTATE","X55B_ROTATE_OFF"),
      ("profiled_rotation","X55B_CONTROL_ON","X55B_ROTATE_ON"),
      ("kissat_reference","X54_CONTROL","KISSAT"),
      ("cadical_reference","X54_CONTROL","CADICAL")
    ]
    for key,left,right in pairs:
        comparisons[key]={
          "PAR2":comparison(rows,left,right,"PAR2_s"),
          "CPU":comparison(rows,left,right,"cpu_s")
        }
    byfam={f:overall([x for x in rows if x["family"]==f]) for f in sorted({x["family"] for x in rows})}
    report={"status":"COMPLETE","protocol":frozen,"overall":results,
      "by_family":byfam,"comparisons":comparisons,
      "note":"Retrospective original SAT2024, no new blind holdout; no solver promotion.",
      "sampling_limitations":"Every 64th nonempty propagation is sampled. CPU estimates may be biased by cost heterogeneity; accept only plausible estimates, distinguish external CPU and profiler overhead."}
    folder=pathlib.Path("x55c_final");folder.mkdir(exist_ok=True)
    save(folder/"report.json",report)
    (folder/"trials.jsonl").write_text("".join(json.dumps(v,sort_keys=True)+"\n" for v in rows))
    emit("X55C_FINAL",{
       "status":"COMPLETE","overall":results,
       "comparisons":{k:v["PAR2"] for k,v in comparisons.items()}
    })

def main():
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("freeze","shard","finish"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.stage=="freeze":freeze()
    elif a.stage=="shard":shard(a.shard)
    else:finish()

if __name__=="__main__":main()
