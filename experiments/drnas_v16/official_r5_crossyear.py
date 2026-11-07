#!/usr/bin/env python3
"""R5 multi-signal causal guard -- frozen official 2025+2026 cross-year holdouts.

This script never tunes the selector, changes its threshold, or selects
instances based on DRNAS runtime. All six policies run serialized on the
SAME runner per formula with paired randomized orders. Each shard has a
different physical GitHub-hosted runner.

The SAT Competition 2026 instance set is official; this replay is NOT
official competition scoring. Independent UNSAT proof checking is absent.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,platform,random,re,resource,signal
import statistics,subprocess,time
from pathlib import Path
import official_parallel_v180 as common

CONFIG=Path("experiments/drnas_v16/r5_frozen_crossyear_candidates.json")
ROOT=Path("drnas-r5-crossyear-holdout-results")
ORIGINAL="/tmp/kissat-r5-original/build/kissat"
PATCHED="/tmp/kissat-r5-patched/build/kissat"
STABLE="/tmp/drnas-v1531-r5"
CAP=60
REPEATS=2
MODES=("original","stable_v1531","monitor","r4_restart20",
       "r5_multisignal","forced_restart25")
COLS=("shard","year","index","gbd_hash","cnf_sha256","expected","repeat","mode",
      "status","wall_s","cpu_s","par2_s","sat_witness_verified",
      "early_conflicts","early_restarts","early_lbd_ratio",
      "early_propagations","early_decisions","r4_eligible",
      "r4_action","r5_eligible","r5_action","r5_glue","r5_propagations","r5_decisions",
      "switch_at","restart_before","restart_after",
      "final_conflicts","final_restarts","early_trace_present","warning")

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def csvwrite(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLS,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def obtain_cases(shard,out,config):
    assert config["references"]["kissat_source_commit"]==common.PINNED_KISSAT
    assert config["frozen_rule"]=={
        "sample_at_conflict":512,"early_restarts_max":20,
        "lbd_ratio_lt":0.965,"propagations_per_conflict_min":60.0,
        "propagations_per_conflict_max":200.0,"decisions_per_conflict_max":2.15,
        "intervention_at_conflict":2048,"action_restartint":25,
        "policy":"Require ALL conditions; otherwise continue original Kissat in-process; missing early sample => no-op"}
    assert tuple(config["policies"])==MODES
    assert config["cap_seconds"]==CAP and config["repeats"]==REPEATS
    candidates=config["groups"][shard]
    assert len([x for x in candidates if x["year"]==2026])==6
    assert len([x for x in candidates if x["year"]==2025])==10
    uri_lists={}
    hashes={}
    for year in (2026,2025):
        ref=config["references"][f"sat{year}"]
        url=f"https://raw.githubusercontent.com/satcompetition/{year}/{ref['git_commit']}/{ref['uri_path']}"
        raw=common.fetch(url,100000,timeout=30)
        urls=raw.decode("ascii").strip().splitlines()
        assert len(urls)==400, f"Unexpected {year} official URI count"
        uri_lists[year]=urls
        hashes[year]=sha(raw)
    cases=[];failures=[]
    for year in (2026,2025):
        accepted=0
        for item in [x for x in candidates if x["year"]==year]:
            if accepted>=config["selection"]["max_formulas_per_shard_per_year"]:break
            index=int(item["index"])
            target=uri_lists[year][index].replace("http://","https://",1)
            if target.rsplit("/",1)[-1]!=item["gbd_hash"]:
                raise ValueError(f"Official {year} URL identity changed {index}")
            if year==2026:
                assert item["official_kissat"]["status"] in ("sat-verified","unsat-verified")
                expected=item["official_kissat"]["result"].upper()
                assert expected in ("SAT","UNSAT")
            else:
                expected="UNKNOWN"
            try:
                compressed=common.fetch(target,config["selection"]["max_archive_bytes"],timeout=55)
                common.RAW_LIMIT=config["selection"]["max_dimacs_bytes"]
                raw=common.unpack_limited(compressed)
                n,m=common.dimensions(raw)
                path=out/f"official_{year}_{index}.cnf"
                path.write_bytes(raw)
                case=dict(shard=shard,year=year,index=index,
                    gbd_hash=item["gbd_hash"],path=path,
                    cnf_sha256=sha(raw),archive_sha256=sha(compressed),
                    nvars=n,nclauses=m,cnf_bytes=len(raw),
                    archive_bytes=len(compressed),source_url=target,
                    expected=expected,
                    official_reference_type=("2026 verified published status" if year==2026
                        else "2025 official collection: NO frozen per-formula result labels"),
                    official_kissat_seconds=(item["official_kissat"]["seconds"] if year==2026 else None))
                cases.append(case)
                accepted+=1
                print("R5_OFFICIAL_INPUT",json.dumps({
                    k:(str(v) if isinstance(v,Path) else v)
                    for k,v in case.items() if k!="path"}),flush=True)
            except (ValueError,TimeoutError,OSError,EOFError) as err:
                failures.append(dict(year=year,index=index,error=str(err)[:240]))
                print("R5_INPUT_SKIP",year,index,str(err)[:180],flush=True)
    meta=dict(shard=shard,
        policy_frozen=config["frozen_rule"],
        selection=config["selection"],
        full_config_sha256=sha(CONFIG.read_bytes()),
        chosen=[{"year":x["year"],"index":x["index"]} for x in cases],
        candidates=[{"year":x["year"],"index":x["index"]} for x in candidates],
        skips=failures,official_uri_sha256=hashes,
        source_kissat_commit=config["references"]["kissat_source_commit"],
        source_track_commits={year:config["references"][f"sat{year}"]["git_commit"] for year in (2025,2026)},
        binary_sha256={k:sha(Path(v).read_bytes()) for k,v in
              [("original",ORIGINAL),("patched",PATCHED),("v1531",STABLE)]},
        hardware=subprocess.run(["lscpu"],capture_output=True,
                  text=True,check=True).stdout,platform=platform.platform(),
        cases=[{k:(str(v) if isinstance(v,Path) else v)
                 for k,v in case.items() if k!="path"} for case in cases],
        benchmark_type="Unofficial paired replay, 2025 and 2026 official CNF inputs",
        independent_unsat_certificate_check=False,
        eligibility="R5 frozen development-fit prior to any R5 holdout measurements",
        cap_seconds=CAP,repeats=REPEATS,modes=MODES)
    (out/"manifest.json").write_text(json.dumps(meta,indent=2))
    if not cases:raise RuntimeError("No official instances downloaded")
    return cases

def tags(output):
    def get(prefix):
        for line in output.splitlines():
            if line.startswith(prefix):
                return dict(part.split("=",1) for part in line.split()[2:] if "=" in part)
        return {}
    return (get("c DRNAS_V177_EARLY "),get("c R4_EARLY "),
            get("c R5_EARLY "),get("c DRNAS_V177_SWITCH "),
            get("c DRNAS_V177_FINAL "))

def run_one(case,repeat,mode):
    env=os.environ.copy()
    env.pop("DRNAS_V177_MODE",None)
    env.pop("DRNAS_V177_RULE_FILE",None)
    if mode=="original":
        cmd=[ORIGINAL,"-s",str(case["path"].resolve())]
    elif mode=="stable_v1531":
        cmd=[STABLE,str(case["path"].resolve()),ORIGINAL,"1"]
    else:
        options={"monitor":"r5_monitor",
            "r4_restart20":"r4_gate",
            "r5_multisignal":"r5_gate",
            "forced_restart25":"switch2048"}
        env["DRNAS_V177_MODE"]=options[mode]
        cmd=[PATCHED,"-s",str(case["path"].resolve())]
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    start=time.perf_counter()
    proc=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,errors="replace",start_new_session=True)
    try:
        stdout,stderr=proc.communicate(timeout=CAP)
        status={10:"SAT",20:"UNSAT"}.get(proc.returncode,"ERROR")
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL)
        stdout,stderr=proc.communicate()
        status="TIMEOUT"
    wall=time.perf_counter()-start
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
    output=stdout+"\n"+stderr
    payload=None
    for line in stdout.splitlines():
        if line.startswith("DRNAS_HYBRID_RESULT\t"):
            payload=json.loads(line.split("\t",1)[1])
    if payload:
        status=str(payload.get("status","ERROR")).upper()
    witness=False
    if status=="SAT":
        witness=common.check_model(case["path"],output,payload)
        if not witness:
            raise RuntimeError(f"Invalid SAT witness or missing model year={case['year']} index={case['index']} mode={mode}")
    if case["expected"] in ("SAT","UNSAT") and status in ("SAT","UNSAT") and status!=case["expected"]:
        raise RuntimeError(f"Official 2026 contradiction index={case['index']} expected={case['expected']} got={status}")
    if status=="ERROR":
        raise RuntimeError(f"Solver error {case['year']} {case['index']} {mode}: {output[-600:]}")
    early,r4,r5,switched,finish=tags(output)
    patched=mode not in ("original","stable_v1531")
    if patched:
        if early and not r4 and mode!="forced_restart25":
            raise RuntimeError("R4 monitoring tag missing")
        if early and mode in ("monitor","r5_multisignal") and not r5:
            raise RuntimeError("R5 decision tag missing")
        if early and mode=="r4_restart20":
            r4accept=int(r4["restarts"])<=20
            if bool(int(r4["eligible"]))!=r4accept or int(r4["action"])!=(2048 if r4accept else 0):
                raise RuntimeError("R4 comparator does not follow original frozen rule")
        if early and mode in ("monitor","r5_multisignal"):
            rr=int(r5["restarts"])
            g,p,d=map(float,(r5["g"],r5["p"],r5["d"]))
            accept=(rr<=20 and g<0.965 and 60.0<=p<=200.0 and d<=2.15)
            action=2048 if accept and mode=="r5_multisignal" else 0
            if bool(int(r5["eligible"]))!=accept or int(r5["action"])!=action:
                raise RuntimeError(f"R5 frozen gate violation: {r5}")
            if r4 and int(r4["restarts"])!=rr:
                raise RuntimeError("R4 vs R5 restart sample inconsistent")
        if switched:
            if mode=="monitor":
                raise RuntimeError("Monitor switched restart policy")
            if int(switched.get("restart_after","-1"))!=25 or int(switched.get("at","0"))<2048:
                raise RuntimeError(f"Illegal restart intervention {switched}")
            if mode=="r5_multisignal" and not r5.get("action")=="2048":
                raise RuntimeError("R5 switched without permission")
            if mode=="r4_restart20" and r4.get("action")!="2048":
                raise RuntimeError("R4 comparator switched without permission")
        if mode=="r5_multisignal" and r5 and int(r5["action"])==0 and switched:
            raise RuntimeError("R5 made forbidden switch")
    row=dict(shard=case["shard"],year=case["year"],index=case["index"],
        gbd_hash=case["gbd_hash"],cnf_sha256=case["cnf_sha256"],
        expected=case["expected"],repeat=repeat,mode=mode,status=status,
        wall_s=round(wall,6),cpu_s=round(cpu,6),
        par2_s=round(wall,6) if status in ("SAT","UNSAT") else 2*CAP,
        sat_witness_verified=witness,
        early_conflicts=early.get("conflict",""),
        early_restarts=r5.get("restarts",r4.get("restarts",early.get("restarts",""))),
        early_lbd_ratio=early.get("g",""),
        early_propagations=early.get("p",""),
        early_decisions=early.get("d",""),
        r4_eligible=r4.get("eligible",""),r4_action=r4.get("action",""),
        r5_eligible=r5.get("eligible",""),r5_action=r5.get("action",""),
        r5_glue=r5.get("g",""),r5_propagations=r5.get("p",""),
        r5_decisions=r5.get("d",""),
        switch_at=switched.get("at",""),
        restart_before=switched.get("restart_before",""),
        restart_after=switched.get("restart_after",""),
        final_conflicts=finish.get("conflicts",""),final_restarts=finish.get("restarts",""),
        early_trace_present=bool(early),warning="")
    print("R5_MEASURE",case["year"],case["index"],repeat,mode,status,
        f"wall={wall:.6f}s",f"PAR2={row['par2_s']:.6f}s",
        f"R512={row['early_restarts']}","r5_action="+str(row["r5_action"]),
        "switch="+str(row["switch_at"]),flush=True)
    return row

def batch(shard):
    config=json.loads(CONFIG.read_text())
    out=ROOT/f"shard_{shard}"
    out.mkdir(parents=True,exist_ok=True)
    cases=obtain_cases(shard,out,config)
    rows=[]
    for case in cases:
        assert sha(case["path"].read_bytes())==case["cnf_sha256"]
        for repeat in range(REPEATS):
            order=list(MODES)
            random.Random(51505+case["year"]*10009+case["index"]*1009+shard*17+repeat).shuffle(order)
            for mode in order:
                rows.append(run_one(case,repeat,mode))
                csvwrite(out/"measurements.partial.csv",rows)
            answers={x["status"] for x in rows if
                     x["year"]==case["year"] and x["index"]==case["index"] and x["repeat"]==repeat and
                     x["status"] in ("SAT","UNSAT")}
            if len(answers)>1:
                raise RuntimeError(f"Contradiction among policies on {case['year']} {case['index']}")
            # Same pre-intervention state observations, never full-state proof.
            measurements=[x for x in rows if x["year"]==case["year"] and x["index"]==case["index"] and x["repeat"]==repeat]
            restarts={int(x["early_restarts"]) for x in measurements
                     if x["mode"] in ("monitor","r4_restart20","r5_multisignal")
                     and str(x["early_restarts"]).strip()}
            if len(restarts)>1:
                raise RuntimeError(f"R5 pre-intervention discrepancy in restarts: {case['year']} {case['index']} {restarts}")
    csvwrite(out/"measurements.csv",rows)
    rankings=[]
    for mode in MODES:
        part=[x for x in rows if x["mode"]==mode]
        rankings.append(dict(mode=mode,attempts=len(part),
             solved=sum(x["status"] in ("SAT","UNSAT") for x in part),
             par2_sum_s=round(sum(x["par2_s"] for x in part),6),
             par2_mean_s=round(statistics.mean(x["par2_s"] for x in part),6),
             checked_sat_models=sum(x["sat_witness_verified"] for x in part),
             early_snapshots=sum(x["early_trace_present"] for x in part),
             interventions=sum(bool(x["switch_at"]) for x in part)))
    summary=dict(shard=shard,n_cases=len(cases),n_measurements=len(rows),
          ranking=sorted(rankings,key=lambda x:x["par2_mean_s"]),
          cap_s=CAP,repeats=REPEATS,not_official_competition=True,
          not_generalized_due_to_small_holdout=True,
          independently_verified_unsat=0)
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    print("R5_SHARD_FINAL",json.dumps(summary,separators=(",",":")),flush=True)

def aggregate():
    rows=[];manifest=[]
    for i in range(4):
        out=ROOT/f"shard_{i}"
        meta=json.loads((out/"manifest.json").read_text())
        manifest.append(meta)
        with (out/"measurements.csv").open(newline="") as f:
            rows.extend(csv.DictReader(f))
    keys={}
    for x in rows:keys.setdefault((x["year"],x["index"],x["cnf_sha256"]),[]).append(x)
    assert keys, "No official formulas measured"
    for name,group in keys.items():
        expected={(r,m) for r in range(REPEATS) for m in MODES}
        assert {(int(x["repeat"]),x["mode"]) for x in group}==expected, f"Incomplete paired {name}"
        assert len(group)==REPEATS*len(MODES)
    seen_indices={(m["year"],m["index"]) for x in manifest for m in x["cases"]}
    assert len(seen_indices)==len(keys)
    base={k:statistics.mean(float(x["par2_s"]) for x in xs if x["mode"]=="original") for k,xs in keys.items()}
    output=[]
    for mode in MODES:
        xs=[x for x in rows if x["mode"]==mode]
        formula={k:statistics.mean(float(x["par2_s"]) for x in vs if x["mode"]==mode) for k,vs in keys.items()}
        deltas=[base[k]-formula[k] for k in sorted(keys)]
        rg=random.Random(412450)
        samples=sorted(statistics.mean(deltas[rg.randrange(len(deltas))] for _ in deltas) for _ in range(2000))
        output.append(dict(mode=mode,formula_count=len(keys),attempts=len(xs),
            solved=sum(x["status"] in ("SAT","UNSAT") for x in xs),
            mean_par2_s=round(statistics.mean(float(x["par2_s"]) for x in xs),6),
            total_par2_s=round(sum(float(x["par2_s"]) for x in xs),6),
            improvement_pct=round(100*(1-sum(formula.values())/sum(base.values())),4),
            bootstrap_formula_delta_ci95_s=[round(samples[49],6),round(samples[1949],6)],
            validated_sat_models=sum(x["sat_witness_verified"]=="True" for x in xs),
            independent_unsat_proofs=0,
            early_snapshots=sum(x["early_trace_present"]=="True" for x in xs),
            triggered_switches=sum(bool(x["switch_at"]) for x in xs)))
    output.sort(key=lambda x:x["mean_par2_s"])
    paired=[]
    for k,group in sorted(keys.items()):
        original=statistics.mean(float(x["par2_s"]) for x in group if x["mode"]=="original")
        new=statistics.mean(float(x["par2_s"]) for x in group if x["mode"]=="r5_multisignal")
        monitor=[x for x in group if x["mode"]=="monitor"]
        vals=[int(x["early_restarts"]) for x in monitor if x["early_restarts"]]
        paired.append(dict(year=int(k[0]),index=int(k[1]),expected=group[0]["expected"],
              original_par2_mean_s=round(original,6),
              r5_par2_mean_s=round(new,6),
              improvement_s=round(original-new,6),
              early_restarts=vals,
              passed_gate=[bool(int(x["r5_eligible"])) for x in monitor if x["r5_eligible"]],
              r5_actual_switch_count=sum(bool(x["switch_at"]) for x in group if x["mode"]=="r5_multisignal")))
    cohort_summaries=[]
    for year in (2025,2026):
        cohort_keys={k:group for k,group in keys.items() if int(k[0])==year}
        if not cohort_keys:
            cohort_summaries.append(dict(year=year,formula_count=0,
                note="No downloaded official formulas for this cohort"))
            continue
        baseline=sum(float(x["par2_s"]) for group in cohort_keys.values()
                     for x in group if x["mode"]=="original")
        by_mode=[]
        for mode in MODES:
            xs=[x for group in cohort_keys.values() for x in group if x["mode"]==mode]
            total=sum(float(x["par2_s"]) for x in xs)
            by_mode.append(dict(mode=mode,attempts=len(xs),
                solved=sum(x["status"] in ("SAT","UNSAT") for x in xs),
                total_par2_s=round(total,6),
                improvement_pct=round(100*(1-total/baseline),4),
                switches=sum(bool(x["switch_at"]) for x in xs),
                validated_sat_models=sum(x["sat_witness_verified"]=="True" for x in xs)))
        cohort_summaries.append(dict(year=year,formula_count=len(cohort_keys),
            reference_labels=("Published 2026 verified SAT/UNSAT statuses" if year==2026
               else "No frozen 2025 per-formula verified status; SAT models checked"),
            strategies=by_mode))
    final=dict(experiment="DRNAS SAT R5.0 multi-signal frozen 2025+2026 holdout",
        complete_shards=4,formula_count=len(keys),attempts=len(rows),
        official_input_source="SAT Competition 2025 and 2026 Main Track, pinned URI lists",
        official_scores_source_sha256_blob="9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef",
        kissat_original_sha="8af8e56f174b778aef3aa45af9f739b2a5f492c2",
        selector="R512<=20 AND g<0.965 AND 60<=p<=200 AND d<=2.15 => restartint25 at conflict2048",
        status="Independent unofficial replay; 2026 official labels checked, 2025 labels unavailable; independent UNSAT proof absent",
        evidence_limit="Small stratified official subset, 2 reps, variable GitHub runner HW across shards",
        independent_unsat_proofs=0,
        policy_not_tuned_on_r5_holdout=True,
        candidates_frozen_before_results=True,
        formula_selection_skips=[{"shard":x["shard"],"skips":x["skips"]} for x in manifest],
        strategies=output,cohorts=cohort_summaries,paired_formulas=paired)
    (ROOT/"aggregate.json").write_text(json.dumps(final,indent=2))
    print("R5_OFFICIAL_FINAL",json.dumps({k:v for k,v in final.items() if k!="paired_formulas"},separators=(",",":")),flush=True)
    for x in paired:print("R5_PAIRED",json.dumps(x,separators=(",",":")),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--shard",type=int)
    ap.add_argument("--aggregate",action="store_true")
    args=ap.parse_args()
    if args.aggregate:aggregate()
    elif args.shard in range(4):batch(args.shard)
    else:ap.error("Provide --shard 0..3 or --aggregate")
