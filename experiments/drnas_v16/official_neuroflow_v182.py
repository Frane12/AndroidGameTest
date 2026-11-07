#!/usr/bin/env python3
"""V18.2: sealed official 2026 paired benchmark of NeuroFlow regression guard.

Eight policies, two repeats, up to four frozen fresh official CNFs per shard;
one pinned runner per formula. Compares truly unmodified Kissat against
instrumented-no-change, fixed intervals, frozen LBD gate, and two reversible
guard policies. No use of V18.2 outcomes for instance selection.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,os,random,re,statistics
import subprocess,time
from pathlib import Path
import official_parallel_v180 as common

ROOT=Path("drnas-v182-neuroflow-results")
FROZEN=Path("experiments/drnas_v16/v182_frozen_official_cases.json")
POLICIES=("baseline","monitor","fixed10","fixed25","fixed50",
          "gate_no_guard","adaptive_gate","adaptive_force")
FIELDS=("shard","official_index","gbd_hash","sha256","nvars","nclauses",
        "reference_status","repeat","mode","status","seconds","par2",
        "sat_model_verified","independent_unsat_proof_verified",
        "monitor_internal_pct","monitor_ns","cpu_ns",
        "monitor_budget_abort","monitor_budget_at","samples",
        "switch_at","fallback_at","fallbacks","bad_streak",
        "early_glue","final_conflicts","final_restarts","reason")
TRACE_FIELDS=("shard","official_index","repeat","mode","conflict","cpu_ns",
              "restarts","focused_restarts","learned","propagations",
              "decisions","glue","cost_ns","prop_per_conf",
              "bad","stable","interval")
CAP=60.0
MAX_SIZE_COMPRESSED=24*1024*1024
MAX_SIZE_RAW=96*1024*1024
CAP_CASES=4
REPEATS=2
KISSAT_SHA="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
TRACK_SHA="3e2dee7cf5aa643c77bf946280a3c1c520756ef9"

def digest(content):return hashlib.sha256(content).hexdigest()

def write_csv(path,rows,fields):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def download(batch,out):
    frozen=json.loads(FROZEN.read_text())
    assert frozen["kissat_sha"]==KISSAT_SHA
    assert frozen["official_track_sha"]==TRACK_SHA
    assert tuple(frozen["policies"])==POLICIES
    possible=frozen["shards"][batch]
    assert len(possible)==5
    uri_data=common.fetch(
        f"https://raw.githubusercontent.com/satcompetition/2026/{TRACK_SHA}/downloads/track_main_2026.uri",
        100000,timeout=25)
    urls=uri_data.decode("utf-8").strip().splitlines()
    assert len(urls)==400
    (out/"official_track_sha256.txt").write_text(digest(uri_data)+"\n")
    cases=[];skipped=[]
    for entry in possible:
        if len(cases)>=CAP_CASES:break
        i=entry["official_index"]
        url=urls[i].replace("http://","https://",1)
        if url.rsplit("/",1)[-1]!=entry["gbd_hash"]:
            raise RuntimeError(f"Official GBD input changed for {i}")
        try:
            packed=common.fetch(url,MAX_SIZE_COMPRESSED,timeout=30)
            common.RAW_LIMIT=MAX_SIZE_RAW
            raw=common.unpack_limited(packed)
            n,m=common.dimensions(raw)
            folder=out/"cnf"
            folder.mkdir(exist_ok=True)
            path=folder/f"{i:03d}_{entry['gbd_hash']}.cnf"
            path.write_bytes(raw)
            case=dict(entry,path=str(path),nvars=n,nclauses=m,
                      sha256=digest(raw),archive_sha256=digest(packed),
                      archive_bytes=len(packed),decompressed_bytes=len(raw))
            cases.append(case)
            print("V182_CNF",batch,i,n,m,case["sha256"],flush=True)
        except Exception as e:
            skipped.append({"official_index":i,"reason":str(e)[:180]})
            print("V182_SKIP",batch,i,str(e)[:150],flush=True)
    manifest=dict(shard=batch,pinned_kissat=KISSAT_SHA,
          pinned_track=TRACK_SHA,
          frozen_sha256=digest(FROZEN.read_bytes()),
          original_selection=frozen["selection"],selected=len(possible),
          downloaded=len(cases),failed_downloads=skipped,
          cases=[{k:v for k,v in c.items() if k!="path"} for c in cases],
          policies=POLICIES,cap=CAP,repeats=REPEATS,
          monitor_every_conflicts=256,
          internal_overhead_target_pct=0.5,
          regression_bad_windows=3,
          independent_unsat_proofs=False,
          real_competition_score=False)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
    if not cases:raise RuntimeError("No frozen instances could be downloaded")
    return cases

def parse_telemetry(output,mode,batch,case,repeat):
    result=None;records=[]
    for line in output.splitlines():
        if line.startswith("c V182_RESULT ") or line.startswith("c V182_SAMPLE "):
            typ="RESULT" if line.startswith("c V182_RESULT ") else "SAMPLE"
            fields={}
            for token in line.split()[2:]:
                if "=" in token:
                    k,v=token.split("=",1)
                    fields[k]=v
            if fields.get("policy")!=mode:
                raise RuntimeError("Wrong policy telemetry")
            if typ=="RESULT":
                if result is not None:raise RuntimeError("Double final")
                result=fields
            else:
                records.append(dict(shard=batch,official_index=case["official_index"],
                                    repeat=repeat,mode=mode,**fields))
    seen=[int(x["conflict"]) for x in records]
    if seen!=sorted(set(seen)):raise RuntimeError("Duplicate or unsorted samples")
    if mode=="baseline" and (result or records):
        raise RuntimeError("Original Kissat emitted DRNAS telemetry")
    if result is not None:
        assert int(result["samples"])>=len(records)
        assert int(result["fallbacks"])<=1
        if mode in ("monitor","gate_no_guard","fixed10","fixed25","fixed50"):
            assert int(result["fallbacks"])==0
        if mode=="monitor":
            assert int(result["switch_at"])==0
        if mode in ("adaptive_gate","adaptive_force") and int(result["fallbacks"])==1:
            assert int(result["fallback_at"])>0
        # There must be no actions when budget abort is set before intervention.
    return result,records

def attempt(batch,case,repeat,mode,unpatched,instrumented):
    env=os.environ.copy()
    env.pop("DRNAS_V182_MODE",None)
    env.pop("DRNAS_V182_FORCE_BAD_SMOKE",None)
    is_baseline=(mode=="baseline")
    solver=unpatched if is_baseline else instrumented
    if not is_baseline:env["DRNAS_V182_MODE"]=mode
    cmd=[str(solver),"-s",str(Path(case["path"]).resolve())]
    started=time.perf_counter()
    try:
        p=subprocess.run(cmd,env=env,text=True,capture_output=True,
                         errors="replace",check=False,timeout=CAP)
        elapsed=time.perf_counter()-started
        output=p.stdout+"\n"+p.stderr
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
    except subprocess.TimeoutExpired as e:
        elapsed=time.perf_counter()-started
        def decode(x):
            if isinstance(x,bytes):return x.decode("utf-8","replace")
            return x or ""
        output=decode(e.stdout)+"\n"+decode(e.stderr)
        status="TIMEOUT"
    expected="SAT" if case["official_kissat"]["result"]=="sat" else "UNSAT"
    if status in ("SAT","UNSAT") and status!=expected:
        raise RuntimeError(f"Contradiction with verified official result {case['official_index']}")
    sat_verified=False
    if status=="SAT":
        sat_verified=common.check_model(Path(case["path"]),output,None)
        if not sat_verified:raise RuntimeError("SAT model doesn't satisfy CNF")
    if status=="ERROR":raise RuntimeError("Unexpected solver exit: "+output[-600:])
    result,snapshots=parse_telemetry(output,mode,batch,case,repeat)
    def field(key,default=""):
        return result.get(key,default) if result else default
    row=dict(shard=batch,official_index=case["official_index"],
       gbd_hash=case["gbd_hash"],sha256=case["sha256"],
       nvars=case["nvars"],nclauses=case["nclauses"],reference_status=expected,
       repeat=repeat,mode=mode,status=status,seconds=round(elapsed,6),
       par2=round(elapsed,6) if status in ("SAT","UNSAT") else 2*CAP,
       sat_model_verified=sat_verified,independent_unsat_proof_verified=False,
       monitor_internal_pct=field("monitor_pct"),monitor_ns=field("monitor_ns"),
       cpu_ns=field("cpu_ns"),
       monitor_budget_abort=field("budget_abort"),
       monitor_budget_at=field("budget_at"),
       samples=field("samples"),switch_at=field("switch_at"),
       fallback_at=field("fallback_at"),fallbacks=field("fallbacks"),
       bad_streak=field("bad_streak"),early_glue=field("early_glue"),
       final_conflicts=field("conflicts"),final_restarts=field("restarts"),
       reason=("timeout" if status=="TIMEOUT" else
               "early preprocess no search telemetry" if not result and not is_baseline else ""))
    return row,snapshots

def run_batch(batch):
    out=ROOT/f"shard_{batch}"
    out.mkdir(parents=True,exist_ok=True)
    cases=download(batch,out)
    unpatched=Path("/tmp/kissat-v182-original/build/kissat").resolve()
    instrumented=Path("/tmp/kissat-v182-instrumented/build/kissat").resolve()
    assert unpatched.is_file() and instrumented.is_file()
    rows=[];snapshots=[]
    for case in cases:
        for repeat in range(REPEATS):
            modes=list(POLICIES)
            random.Random(182000 + case["official_index"]*101+repeat).shuffle(modes)
            for mode in modes:
                row,snaps=attempt(batch,case,repeat,mode,unpatched,instrumented)
                rows.append(row)
                snapshots.extend(snaps)
                print("V182_MEASURE",batch,case["official_index"],repeat,mode,
                      row["status"],row["seconds"],"PAR2",row["par2"],
                      "guard",row["fallbacks"],"budget",row["monitor_budget_abort"],
                      "monitor_pct",row["monitor_internal_pct"],flush=True)
            write_csv(out/"measurements.partial.csv",rows,FIELDS)
            print("V182_PAIR_COMPLETE",batch,case["official_index"],repeat,flush=True)
    assert len(rows)==len(cases)*REPEATS*len(POLICIES)
    by=collections.defaultdict(dict)
    for row in rows:
        key=(row["official_index"],row["repeat"])
        if row["mode"] in by[key]:raise RuntimeError("Duplicate policy")
        by[key][row["mode"]]=row
    assert all(set(d)==set(POLICIES) for d in by.values())
    ranking=[]
    for mode in POLICIES:
        sub=[x for x in rows if x["mode"]==mode]
        nums=[float(x["par2"]) for x in sub]
        cost=[float(x["monitor_internal_pct"]) for x in sub
              if x["monitor_internal_pct"]!=""]
        ranking.append(dict(mode=mode,attempts=len(sub),
             solved=sum(x["status"] in ("SAT","UNSAT") for x in sub),
             mean_par2=round(statistics.mean(nums),6),
             timeouts=sum(x["status"]=="TIMEOUT" for x in sub),
             monitor_cost_max_pct=round(max(cost),6) if cost else None,
             monitoring_budget_aborts=sum(x["monitor_budget_abort"]=="1" for x in sub),
             fallback_count=sum(int(x["fallbacks"] or 0) for x in sub)))
    ranking.sort(key=lambda x:x["mean_par2"])
    overhead_pairs=[]
    for casekey,pair in by.items():
        base=pair["baseline"];mon=pair["monitor"]
        if base["status"] in ("SAT","UNSAT") and base["status"]==mon["status"]:
            overhead_pairs.append(dict(official_index=casekey[0],repeat=casekey[1],
                 baseline_s=base["seconds"],monitor_s=mon["seconds"],
                 paired_wall_pct=100*(mon["seconds"]/base["seconds"]-1),
                 monitor_internal_pct=mon["monitor_internal_pct"]))
    write_csv(out/"measurements.csv",rows,FIELDS)
    write_csv(out/"snapshots.csv",snapshots,TRACE_FIELDS)
    write_csv(out/"overhead.csv",overhead_pairs,
              ("official_index","repeat","baseline_s","monitor_s",
               "paired_wall_pct","monitor_internal_pct"))
    summary=dict(shard=batch,formula_count=len(cases),attempts=len(rows),
          paired_repeats=REPEATS, cap_seconds=CAP,
          ranking=ranking,
          precommitted_rules=True,
          SAT_witness_checks=sum(x["sat_model_verified"] for x in rows),
          independent_UNSAT_certificates=0,
          matched_plain_monitor_cases=len(overhead_pairs),
          median_monitor_wall_delta_pct=round(statistics.median(
              [x["paired_wall_pct"] for x in overhead_pairs]),6) if overhead_pairs else None,
          disclosure="0.5% is a CPU-monitor instrumented budget target; full wall overhead must be evaluated against real original Kissat, and noisy tiny runtimes can exceed this target. No guarantee.")
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    print("V182_SHARD_FINAL",json.dumps(summary,separators=(",",":")),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,choices=range(4),required=True)
    args=p.parse_args()
    run_batch(args.shard)

if __name__=="__main__":main()
