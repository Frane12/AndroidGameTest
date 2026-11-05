#!/usr/bin/env python3
"""R4 frozen early restarts gate -- independent official 2026 paired holdout.

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

CONFIG=Path("experiments/drnas_v16/r4_frozen_official_candidates.json")
ROOT=Path("drnas-r4-r512-official-results")
ORIGINAL="/tmp/kissat-r4-original/build/kissat"
PATCHED="/tmp/kissat-r4-patched/build/kissat"
STABLE="/tmp/drnas-v1531-r4"
CAP=45
REPEATS=2
MODES=("original","instrumented_monitor","forced_2048_restart25",
       "r4_early_restart_le20","r4_inverse_restart_gt20","stable_v1531")
COLS=("shard","index","gbd_hash","cnf_sha256","expected","repeat","mode",
      "status","wall_s","cpu_s","par2_s","sat_witness_verified",
      "early_conflicts","early_restarts","early_lbd_ratio",
      "early_propagations","early_decisions","r4_eligible",
      "r4_action","switch_at","restart_before","restart_after",
      "final_conflicts","final_restarts","early_trace_present","warning")

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def csvwrite(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLS,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def obtain_cases(shard,out,config):
    assert config["track_commit"]==common.PINNED_TRACK
    assert config["kissat_commit"]==common.PINNED_KISSAT
    assert config["threshold_at_conflict"]==512
    assert config["early_restarts_leq"]==20
    assert config["intervention_conflict"]==2048
    assert config["intervention_restartint"]==25
    assert tuple(config["policies"])==MODES
    assert config["caps_seconds"]==CAP and config["repeats"]==REPEATS
    candidates=config["groups"][shard]
    assert len(candidates)==6
    url=f"https://raw.githubusercontent.com/satcompetition/2026/{common.PINNED_TRACK}/downloads/track_main_2026.uri"
    uri_data=common.fetch(url,100000,timeout=35)
    urls=uri_data.decode("ascii").strip().splitlines()
    assert len(urls)==400
    (out/"track_uri_sha256.txt").write_text(sha(uri_data)+"\n")
    cases=[];failures=[]
    for item in candidates:
        if len(cases)>=config["max_downloaded_per_shard"]:break
        index=int(item["index"])
        assert item["shard"]==shard
        target=urls[index].replace("http://","https://",1)
        if target.rsplit("/",1)[-1]!=item["gbd_hash"]:
            raise ValueError(f"Official URL identity changed {index}")
        expected=item["official_kissat"]["result"].upper()
        assert expected in ("SAT","UNSAT")
        assert item["official_kissat"]["status"] in ("sat-verified","unsat-verified")
        try:
            compressed=common.fetch(target,
              config["max_compressed_bytes"],timeout=50)
            common.RAW_LIMIT=config["max_uncompressed_bytes"]
            raw=common.unpack_limited(compressed)
            n,m=common.dimensions(raw)
            path=out/f"official_{index}.cnf"
            path.write_bytes(raw)
            case=dict(shard=shard,index=index,
              gbd_hash=item["gbd_hash"],path=path,
              cnf_sha256=sha(raw),archive_sha256=sha(compressed),
              nvars=n,nclauses=m,
              cnf_bytes=len(raw),archive_bytes=len(compressed),
              source_url=target,expected=expected,
              external_kissat_seconds=item["official_kissat"]["seconds"])
            cases.append(case)
            print("R4_OFFICIAL_INPUT",json.dumps(
                {k:(str(v) if isinstance(v,Path) else v)
                 for k,v in case.items() if k!="path"}),flush=True)
        except (ValueError,TimeoutError,OSError,EOFError) as err:
            failures.append(dict(index=index,error=str(err)[:250]))
            print("R4_INPUT_SKIP",index,str(err)[:180],flush=True)
    meta=dict(shard=shard,policy_frozen="R512<=20 -> restartint25 at C2048",
         full_candidate_sha256=sha(CONFIG.read_bytes()),
         selection=config["selection"],
         chosen_indices=[x["index"] for x in cases],
         candidates=[x["index"] for x in candidates],
         skips=failures,
         official_2026_uri_sha256=sha(uri_data),
         source_kissat_commit=config["kissat_commit"],
         source_track_commit=config["track_commit"],
         sources={k:str(v) for k,v in
                   [("original",ORIGINAL),("patched",PATCHED),("v1531",STABLE)]},
         binary_sha256={k:sha(Path(v).read_bytes()) for k,v in
                   [("original",ORIGINAL),("patched",PATCHED),("v1531",STABLE)]},
         hardware=subprocess.run(["lscpu"],capture_output=True,
              text=True,check=True).stdout,
         platform=platform.platform(),
         cases=[{k:(str(v) if isinstance(v,Path) else v)
                  for k,v in case.items() if k!="path"} for case in cases],
         type="official competition instances; independent development-runner replay",
         blind_for_r4=True,randomized_execution_order=True,
         no_reselection_after_outcome=True,
         not_official_competition_scoring=True,
         independent_unsat_certificate_check=False,
         cap_seconds=CAP,repeats=REPEATS,modes=MODES)
    (out/"manifest.json").write_text(json.dumps(meta,indent=2))
    if not cases:raise RuntimeError("No eligible official CNF downloads; inspect manifest.json")
    return cases

def tags(output):
    def get(prefix):
        for line in output.splitlines():
            if line.startswith(prefix):
                return dict(part.split("=",1) for part in line.split()[2:] if "=" in part)
        return {}
    return get("c DRNAS_V177_EARLY "),get("c R4_EARLY "),get("c DRNAS_V177_SWITCH "),get("c DRNAS_V177_FINAL ")

def run_one(case,repeat,mode):
    env=os.environ.copy()
    env.pop("DRNAS_V177_MODE",None)
    env.pop("DRNAS_V177_RULE_FILE",None)
    if mode=="original":
        cmd=[ORIGINAL,"-s",str(case["path"].resolve())]
    elif mode=="stable_v1531":
        cmd=[STABLE,str(case["path"].resolve()),ORIGINAL,"1"]
    else:
        options={
          "instrumented_monitor":"r4_monitor",
          "forced_2048_restart25":"switch2048",
          "r4_early_restart_le20":"r4_gate",
          "r4_inverse_restart_gt20":"r4_inverse",
        }
        env["DRNAS_V177_MODE"]=options[mode]
        cmd=[PATCHED,"-s",str(case["path"].resolve())]
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    start=time.perf_counter()
    proc=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,text=True,errors="replace",
          start_new_session=True)
    try:
        stdout,stderr=proc.communicate(timeout=CAP)
        code=proc.returncode
        status={10:"SAT",20:"UNSAT"}.get(code,"ERROR")
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
    # Independent SAT witness validator (same checker used by R2/R3).
    witness=False
    if status=="SAT":
        witness=common.check_model(case["path"],output,payload)
        if not witness:
            raise RuntimeError(f"SAT witness invalid/missing {case['index']} {mode} {repeat}")
    if status in ("SAT","UNSAT") and status!=case["expected"]:
        raise RuntimeError(f"Official reference contradiction index={case['index']} mode={mode} got={status} expected={case['expected']}")
    if status=="ERROR":
        raise RuntimeError(f"Unexpected solver status for {case['index']} {mode}: {output[-450:]}")
    early,gate,switched,finish=tags(output)
    warn=[]
    patchmode=mode not in ("original","stable_v1531")
    if patchmode:
        final=int(finish.get("conflicts","0"))
        if status!="TIMEOUT" and not finish:
            warn.append("No search FINAL trace; likely solved during preprocessing")
        if final>=512 and not early:
            raise RuntimeError(f"R4 missing early trace despite {final} conflicts: {case['index']} {mode}")
        if mode in ("instrumented_monitor","r4_early_restart_le20","r4_inverse_restart_gt20"):
            if early and not gate:
                raise RuntimeError(f"R4 early decision tag missing: {case['index']} {mode}")
        if gate and early:
            assert int(gate["conflict"])==512 or int(gate["conflict"])>=512
            should_accept=int(gate["restarts"])<=20
            if bool(int(gate["eligible"]))!=should_accept:
                raise RuntimeError("R4 frozen restart-threshold violated")
            if mode=="r4_early_restart_le20" and int(gate["action"])!=(2048 if should_accept else 0):
                raise RuntimeError("R4 gate action inconsistent with frozen rule")
            if mode=="r4_inverse_restart_gt20" and int(gate["action"])!=(0 if should_accept else 2048):
                raise RuntimeError("R4 inverse action inconsistent")
            if mode=="instrumented_monitor" and int(gate["action"])!=0:
                raise RuntimeError("Monitor must not intervene")
        if switched:
            if mode=="instrumented_monitor":raise RuntimeError("Monitor illegally switched")
            if int(switched.get("restart_after","-1"))!=25:
                raise RuntimeError("R4 switch not to restartint25")
            if int(switched.get("at","0"))<2048:
                raise RuntimeError("R4 premature switch")
        if gate and int(gate.get("action","0"))==0 and switched:
            raise RuntimeError("R4 unauthorized switch")
    row=dict(shard=case["shard"],index=case["index"],gbd_hash=case["gbd_hash"],
        cnf_sha256=case["cnf_sha256"],expected=case["expected"],repeat=repeat,mode=mode,
        status=status,wall_s=round(wall,6),cpu_s=round(cpu,6),
        par2_s=round(wall,6) if status in ("SAT","UNSAT") else 2*CAP,
        sat_witness_verified=witness,
        early_conflicts=early.get("conflict",""),
        early_restarts=gate.get("restarts",early.get("restarts","")),
        early_lbd_ratio=early.get("g",""),
        early_propagations=early.get("p",""),
        early_decisions=early.get("d",""),
        r4_eligible=gate.get("eligible",""),
        r4_action=gate.get("action",""),
        switch_at=switched.get("at",""),
        restart_before=switched.get("restart_before",""),
        restart_after=switched.get("restart_after",""),
        final_conflicts=finish.get("conflicts",""),
        final_restarts=finish.get("restarts",""),
        early_trace_present=bool(early),
        warning=";".join(warn))
    print("R4_MEASURE",case["index"],repeat,mode,status,
          f"wall={wall:.5f}s",f"PAR2={row['par2_s']:.5f}",
          f"early_restarts={row['early_restarts']}",
          f"action={row['r4_action']}",f"switch={row['switch_at']}",flush=True)
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
            random.Random(41205+case["index"]*1009+shard*17+repeat).shuffle(order)
            for mode in order:
                rows.append(run_one(case,repeat,mode))
                csvwrite(out/"measurements.partial.csv",rows)
            answers={x["status"] for x in rows if
                     x["index"]==case["index"] and x["repeat"]==repeat and
                     x["status"] in ("SAT","UNSAT")}
            if len(answers)>1:
                raise RuntimeError(f"Contradiction among policies on {case['index']}")
            # Same pre-intervention state observations, never full-state proof.
            measurements=[x for x in rows if x["index"]==case["index"] and x["repeat"]==repeat]
            restarts={int(x["early_restarts"]) for x in measurements
                     if x["mode"] in ("instrumented_monitor","r4_early_restart_le20","r4_inverse_restart_gt20")
                     and str(x["early_restarts"]).strip()}
            if len(restarts)>1:
                raise RuntimeError(f"R4 pre-intervention discrepancy in restarts: {case['index']} {restarts}")
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
    print("R4_SHARD_FINAL",json.dumps(summary,separators=(",",":")),flush=True)

def aggregate():
    rows=[];manifest=[]
    for i in range(4):
        out=ROOT/f"shard_{i}"
        meta=json.loads((out/"manifest.json").read_text())
        manifest.append(meta)
        with (out/"measurements.csv").open(newline="") as f:
            rows.extend(csv.DictReader(f))
    keys={}
    for x in rows:keys.setdefault((x["index"],x["cnf_sha256"]),[]).append(x)
    assert keys, "No official formulas measured"
    for name,group in keys.items():
        expected={(r,m) for r in range(REPEATS) for m in MODES}
        assert {(int(x["repeat"]),x["mode"]) for x in group}==expected, f"Incomplete paired {name}"
        assert len(group)==REPEATS*len(MODES)
    seen_indices={m["index"] for x in manifest for m in x["cases"]}
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
        new=statistics.mean(float(x["par2_s"]) for x in group if x["mode"]=="r4_early_restart_le20")
        monitor=[x for x in group if x["mode"]=="instrumented_monitor"]
        vals=[int(x["early_restarts"]) for x in monitor if x["early_restarts"]]
        paired.append(dict(index=int(k[0]),expected=group[0]["expected"],
              original_par2_mean_s=round(original,6),
              r4_par2_mean_s=round(new,6),
              improvement_s=round(original-new,6),
              early_restarts=vals,passed_gate=[x<=20 for x in vals],
              r4_actual_switch_count=sum(bool(x["switch_at"]) for x in group if x["mode"]=="r4_early_restart_le20")))
    final=dict(experiment="DRNAS SAT R4.0 frozen R512<=20 blind candidate holdout",
        complete_shards=4,formula_count=len(keys),attempts=len(rows),
        official_input_source="SAT Competition 2026 Main Track; frozen URI list",
        official_scores_source_sha256_blob="9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef",
        kissat_original_sha="8af8e56f174b778aef3aa45af9f739b2a5f492c2",
        selector="<=20 restarts at conflict512 -> restartint25 at conflict2048",
        status="Independent unofficial replay; not official competition ranking; external reference labels checked",
        evidence_limit="Small stratified official subset, 2 reps, variable GitHub runner HW across shards",
        independent_unsat_proofs=0,
        policy_not_tuned_on_r4_holdout=True,
        candidates_frozen_before_results=True,
        formula_selection_skips=[{"shard":x["shard"],"skips":x["skips"]} for x in manifest],
        strategies=output,paired_formulas=paired)
    (ROOT/"aggregate.json").write_text(json.dumps(final,indent=2))
    print("R4_OFFICIAL_FINAL",json.dumps({k:v for k,v in final.items() if k!="paired_formulas"},separators=(",",":")),flush=True)
    for x in paired:print("R4_PAIRED",json.dumps(x,separators=(",",":")),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--shard",type=int)
    ap.add_argument("--aggregate",action="store_true")
    args=ap.parse_args()
    if args.aggregate:aggregate()
    elif args.shard in range(4):batch(args.shard)
    else:ap.error("Provide --shard 0..3 or --aggregate")
