#!/usr/bin/env python3
"""R32p: precommitted first-probe audit plus SAT Competition 2026 external test.

The R32o code/binary is pinned; no SAT control changes. Two separate data uses:
  EXPLORE R32o's 65 already studied synthetic CNFs for probe-level correlations;
  TEST eight SHA-disjoint competition CNFs not in R45 (not globally blind).
A lucky trace is a read-only observation, not proof of first-probe causality.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,re,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_shortlong_select import download_and_features
import r32o_lucky_probe_benchmark as o
import r32n_omission_timing_benchmark as n

PROTO="DRNAS-R32P-FIRST-PROBE-EXTERNAL-20261103-v1"
SALT="R32P-OFFICIAL-EXCLUDED-R45-20261103-PRECOMMITTED"
MODES=("clean","native_off","full")
CAP=12.0
REPS=2
SHARDS=4
MAX_QUOTA=4

def check(ok,what):
    if not ok:raise RuntimeError("R32P_AUDIT_FAILURE "+str(what))
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def textify(x):
    return x.decode("utf-8","replace") if isinstance(x,bytes) else (x or "")

def extract_first(trace):
    directions=trace.get("directions",[])
    earliest_probe=next((d["first_probe"] for d in directions if d["probes"]>0),None)
    earliest_conflict=next((d["first_conflict"] for d in directions if d["failures"]>0),None)
    total_probes=sum(d["probes"] for d in directions)
    total_failures=sum(d["failures"] for d in directions)
    return dict(first_probe=earliest_probe,first_conflict=earliest_conflict,
       total_probes=total_probes,total_failures=total_failures,
       winning_direction=trace.get("terminal_winner"))

def prior(args):
    report=json.loads(Path(args.source).read_text())
    check(report["protocol"].startswith("DRNAS-R32O-") and report["source_count"]==65,
          "Require R32o completed audit artifact")
    rows=report["rows"]
    check(len(rows)==1170,"Expected all 1170 R32o rows")
    pairs=collections.defaultdict(dict)
    for row in rows:
        if row["mode"] not in ("native_off","full"):continue
        key=(row["case"],row["repeat"])
        check(row["mode"] not in pairs[key],"Duplicate paired mode")
        pairs[key][row["mode"]]=row
    check(len(pairs)==65*3 and all(len(x)==2 for x in pairs.values()),
          "Unpaired R32o readings")
    differences=[]
    for (case,rep),d in sorted(pairs.items()):
        off=d["native_off"];full=d["full"]
        a=extract_first(off["lucky"]);b=extract_first(full["lucky"])
        differences.append(dict(case=case,repeat=rep,cohort=off["cohort"],
          off_terminal=off["terminal"],full_terminal=full["terminal"],
          off_first_conflict=a["first_conflict"],full_first_conflict=b["first_conflict"],
          off_first_probe=a["first_probe"],full_first_probe=b["first_probe"],
          off_total_failures=a["total_failures"],full_total_failures=b["total_failures"],
          off_winner=a["winning_direction"],full_winner=b["winning_direction"],
          off_wall_s=off["wall_s"],full_wall_s=full["wall_s"]))
    fresh=[x for x in differences if x["cohort"]!="prior_development"]
    shift=[x for x in fresh if x["off_terminal"]!=x["full_terminal"] or x["off_winner"]!=x["full_winner"]]
    summaries=dict(protocol=PROTO,prior_data="R32o prior, exploratory ONLY",
        examined_paired_measurements=len(differences),replayed_60_pair_measurements=len(fresh),
        changed_path_pair_measurements=len(shift),
        changed_first_conflict_on_changed_path=sum(x["off_first_conflict"]!=x["full_first_conflict"] for x in shift),
        changed_first_probe_on_changed_path=sum(x["off_first_probe"]!=x["full_first_probe"] for x in shift),
        off_late_to_full_early=sum(x["off_terminal"]=="lucky_late" and x["full_terminal"]=="lucky_early" for x in shift),
        first_probe_note="Internal signed index after initial native root unit insertion; not original DIMACS variable IDs",
        inference_warning="Correlated probe changes do not show necessity or sufficiency; no policy interventions, no truly independent sources")
    Path(args.output).write_text(json.dumps(dict(summary=summaries,changed_pairs=shift,all_pairs=differences),indent=2)+"\n")
    print("R32P_PRIOR_AUDIT_PASS",json.dumps(summaries,sort_keys=True),flush=True)

def freeze(args):
    pool18=json.loads(Path(args.prior18).read_text())["cases"]
    pool12=json.loads(Path(args.prior12).read_text())["cases"]
    selected45=json.loads(Path(args.r45).read_text())["cases"]
    check(len(pool18)==18 and len(pool12)==12 and len(selected45)==12,"Prior frozen source sizes")
    pool=pool18+pool12
    check(len({x["sha256"] for x in pool})==30,"Duplicate official candidate sources")
    r45_shas={x["sha256"] for x in selected45}
    check(r45_shas.issubset({x["sha256"] for x in pool}),"R45 provenance mismatch")
    excluded=[x for x in pool if x["sha256"] not in r45_shas]
    check(len(excluded)==18,"Expected 18 external sources not selected by R45")
    candidates_by_label={}
    for label in ("SAT","UNSAT"):
        candidates=[x for x in excluded if x["official_label"]==label and x["cnf_bytes"]<=20000000
                    and float(x["official_baseline_s"])<=300.0]
        # Frozen size/runtime feasibility; no reference to our solver timings.
        candidates.sort(key=lambda x:hashlib.sha256((SALT+"/"+label+"/"+x["id"]).encode()).hexdigest())
        candidates_by_label[label]=candidates
        print("R32P_ELIGIBLE",label,len(candidates),"of",
              sum(x["official_label"]==label for x in excluded),flush=True)
    quota=min(MAX_QUOTA,*(len(x) for x in candidates_by_label.values()))
    check(quota>=2,"Need at least two feasible external CNFs per status")
    selected=[x for label in ("SAT","UNSAT") for x in candidates_by_label[label][:quota]]
    selected.sort(key=lambda x:hashlib.sha256((SALT+"/schedule/"+x["id"]).encode()).hexdigest())
    check(len(selected)==2*quota and len({x["sha256"] for x in selected})==len(selected) and
          all(x["sha256"] not in r45_shas for x in selected),"R45 overlap or duplicate")
    m=dict(protocol=PROTO,cases=selected,selection=dict(
       prior18_manifest_sha=sha(args.prior18),prior12_manifest_sha=sha(args.prior12),
       r45_excluded_manifest_sha=sha(args.r45),r45_excluded_count=12,
       remaining_population=18,selection_salt=SALT,quota_per_status=quota,
       size_cap_bytes=20000000,published_CaDiCaL_max_seconds=300),
       modes=MODES,repeat_count=REPS,cap_seconds=CAP,expected_trials=len(selected)*REPS*len(MODES),
       caveats=["Original 2026 SAT Competition sources downloaded by verified SHA and features",
                "SHA-disjoint from R45, NOT globally blind: source IDs were seen in prior metadata",
                "Selected for file size and published CaDiCaL runtime, not representative of official competition",
                "R32o native read-only instrumentation same GF2 strategy, not production DRNAS solver",
                "SAT checks full original CNF; UNSAT checked against published label, not LRAT",
                "Native trace has overhead, and first conflict correlations do not prove first conflict causality",
                "TIMEOUT uses PAR2 and may censor probe traces",
                "GPU, parallel solvers, process watchdogs and restarts changes are NOT used"])
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(m,sort_keys=True,indent=2)+"\n")
    for x in selected:
        print("R32P_OFFICIAL_FREEZE",x["id"],x["official_label"],x["cnf_bytes"],
              "ref_CaDiCaL_s",x["official_baseline_s"],flush=True)
    print("R32P_FREEZE_PASS",len(selected),"original competition sha-distinct",sha(output),flush=True)

def sat_witness(path,output):
    model={}
    for line in output.splitlines():
        if line.startswith("v "):
            for t in line.split()[1:]:
                lit=int(t)
                if lit:
                    var=abs(lit);value=lit>0
                    check(var not in model or model[var]==value,"Contradictory SAT literals")
                    model[var]=value
    check(bool(model),"SAT witness absent")
    nvars=None;nclauses=None;seen=0;open_clause=False;satisfied=False
    with Path(path).open("rb") as f:
        for raw in f:
            line=raw.strip()
            if not line or line.startswith((b"c",b"%")):continue
            if line.startswith(b"p "):
                parts=line.split()
                check(len(parts)==4 and parts[1]==b"cnf" and nvars is None,"Invalid DIMACS header")
                nvars=int(parts[2]);nclauses=int(parts[3]);continue
            check(nvars is not None,"No DIMACS header")
            for part in line.split():
                lit=int(part)
                if lit:
                    check(abs(lit)<=nvars,"SAT witness variable not declared")
                    open_clause=True
                    if model.get(abs(lit))==(lit>0):satisfied=True
                else:
                    check(open_clause and satisfied,"SAT witness violates source clause")
                    seen+=1;open_clause=False;satisfied=False
    check(nvars is not None and seen==nclauses and not open_clause,"DIMACS source structure mismatch")
    return "complete_original_DIMACS_witness_pass"

def one(case,source,mode,binary):
    env=os.environ.copy()
    env["R32B_MODE"]="off" if mode in ("clean","native_off") else "r32k"
    env.pop("R32K_VARIANT",None)
    if mode=="full":env["R32K_VARIANT"]="full"
    if mode!="clean":env.update(R32L_TRACE="1",R32M_PHASES="1",R32O_TRACE="1")
    start=time.monotonic()
    try:
        r=subprocess.run([str(binary),str(source)],env=env,
          capture_output=True,text=True,errors="replace",timeout=CAP)
        elapsed=time.monotonic()-start
        check(r.returncode in (10,20),"Kissat error "+str(r.returncode)+" "+r.stderr[-300:])
        status="SAT" if r.returncode==10 else "UNSAT"
        check(status==case["official_label"],"Wrong published SAT/UNSAT verdict")
        validation=sat_witness(source,r.stdout) if status=="SAT" else "published_official_UNSAT_label_only"
        output=r.stdout
    except subprocess.TimeoutExpired as ex:
        elapsed=CAP;status="TIMEOUT";validation="censored"
        output=textify(ex.stdout)
    probes,final=n.b.parse_native(output)
    available=None;injected=None;root_proof=None
    if mode=="clean":
        check(not probes and final is None,"Unmodified Kissat has unexpected traces")
    elif mode=="native_off":
        check(not probes,"Native OFF emitted GF2 root work")
    else:
        roots=[x for x in probes if x.get("mark")==9999]
        check(len(roots)<=1,"Duplicate GF2 root discovery")
        if roots:
            root=roots[0]
            proof=n.b.compare_root(root,source)
            root_proof=proof["status"]
            check(root_proof in ("independent_proof_match","old_python_guard"),
                  "Original-CNF GF2 proof failed: "+str(root_proof))
        match=re.search(r"^c R32K_ABLATION variant=full available=(\d+) injected=(\d+) equations=(\d+) resolved=(\d+)$",
           output,re.MULTILINE)
        if match:
            available=int(match.group(1));injected=int(match.group(2))
            check(0<=injected<=12 and injected<=available,"Bad root unit injection count")
            if injected:check(root_proof=="independent_proof_match",
                    "Injected unit lacks independent full-source proof")
        elif status!="TIMEOUT":
            check("c R32C_ACTIVE signal=INPUT_GUARD injected=0 certified=0" in output,
                  "Unexplained missing root intervention")
            injected=0;available=0
    if status!="TIMEOUT" and mode!="clean":
        check(final and final["status"]==(10 if status=="SAT" else 20),
              "Missing or inaccurate native final telemetry")
    phase=None;lt=None
    if status!="TIMEOUT" and mode!="clean":
        phase=n.phase_log(output,mode,status,final)
        lt=o.trace(output,mode,phase)
    elif status!="TIMEOUT":
        lt=o.trace(output,mode,{"terminal":"not_instrumented"})
    first=extract_first(lt) if lt is not None else None
    return dict(status=status,wall_s=round(elapsed,6),
        par2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
        verification=validation,terminal=phase["terminal"] if phase else None,
        lucky=lt,first_probe_summary=first,
        root_units_available=available,root_units_injected=injected,
        original_root_proof=root_proof)

def measure(args):
    path=Path(args.manifest);manifest=json.loads(path.read_text())
    check(manifest["protocol"]==PROTO and 4<=len(manifest["cases"])<=8,"Bad frozen manifest")
    check(0<=args.shard<SHARDS,"Bad shard")
    clean=Path(args.clean).resolve();native=Path(args.native).resolve()
    check(clean.is_file() and native.is_file(),"Pinned binary missing")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(shard=args.shard,
        manifest_sha=sha(path),binary_sha={"clean":sha(clean),"native":sha(native)},
        cap=CAP,reps=REPS,modes=MODES),indent=2)+"\n")
    rows=[]
    for c in manifest["cases"][args.shard::SHARDS]:
        source=out/(c["id"]+".cnf")
        try:
            got=download_and_features(c["id"],source)
            check(got["sha256"]==c["sha256"] and got["features"]==c["features"],
                  "External official SHA/feature mismatch")
            for rep in range(REPS):
                order=list(MODES)
                random.Random(int(hashlib.sha256((SALT+c["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(order)
                for mode in order:
                    result=one(c,source,mode,clean if mode=="clean" else native)
                    rows.append(dict(id=c["id"],sha256=c["sha256"],label=c["official_label"],
                         rep=rep,mode=mode,**result))
                    (out/"rows.json").write_text(json.dumps(rows)+"\n")
                    print("R32P_TRIAL",args.shard,c["id"][:8],rep,mode,result["status"],
                          result["par2_s"],"injected",result["root_units_injected"],
                          "phase",result["terminal"],flush=True)
        finally:source.unlink(missing_ok=True)
    check(len(rows)==len(manifest["cases"][args.shard::SHARDS])*REPS*len(MODES),"Shard incomplete")
    print("R32P_SHARD_PASS",args.shard,len(rows),flush=True)

def aggregate(args):
    manifest=json.loads(Path(args.manifest).read_text())
    check(manifest["protocol"]==PROTO,"Unknown protocol")
    rows=[];binary_keys=set()
    for shard in range(SHARDS):
        base=Path(args.combined)/("r32p-shard-"+str(shard))/"results"
        meta=json.loads((base/"meta.json").read_text())
        check(meta["shard"]==shard and meta["manifest_sha"]==sha(args.manifest) and
              meta["cap"]==CAP and meta["reps"]==REPS,"Shard protocol drift")
        binary_keys.add(json.dumps(meta["binary_sha"],sort_keys=True))
        shard_rows=json.loads((base/"rows.json").read_text())
        check(len(shard_rows)==len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),"Shard row count")
        rows+=shard_rows
    check(len(rows)==len(manifest["cases"])*REPS*len(MODES) and len(binary_keys)==1,"Missing exact pinned attempts")
    byid={c["id"]:c for c in manifest["cases"]}
    lookup={}
    for r in rows:
        check(r["id"] in byid and r["sha256"]==byid[r["id"]]["sha256"],"Source identity failure")
        check(r["status"] in ("TIMEOUT",byid[r["id"]]["official_label"]),"Official source answer mismatch")
        key=(r["id"],r["rep"],r["mode"])
        check(key not in lookup,"Duplicate trial")
        lookup[key]=r
    check(len(lookup)==len(rows),"Incomplete exact paired trial grid")
    cases=[];summary={}
    for c in manifest["cases"]:
        modes={}
        for mode in MODES:
            sample=[lookup[(c["id"],rep,mode)] for rep in range(REPS)]
            modes[mode]=dict(mean_par2_s=round(statistics.mean(r["par2_s"] for r in sample),6),
                status=[r["status"] for r in sample],
                terminal=[r["terminal"] for r in sample],
                winner=[(r["first_probe_summary"] or {}).get("winning_direction") for r in sample],
                first_conflict=[(r["first_probe_summary"] or {}).get("first_conflict") for r in sample],
                injected=[r["root_units_injected"] for r in sample])
        cases.append(dict(id=c["id"],label=c["official_label"],
           reference_CaDiCaL_s=c["official_baseline_s"],modes=modes))
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(PAR2_s=round(sum(r["par2_s"] for r in subset),6),
           completed=sum(r["status"]!="TIMEOUT" for r in subset),
           timeouts=sum(r["status"]=="TIMEOUT" for r in subset),
           confirmed_injection_attempts=sum((r["root_units_injected"] or 0)>0 for r in subset),
           zero_injections=sum(r["root_units_injected"]==0 for r in subset))
    baseline=summary["native_off"]["PAR2_s"]
    summary["full"]["wall_delta_pct_vs_off"]=round(
      100*(summary["full"]["PAR2_s"]/baseline-1),4)
    prior_report=json.loads(Path(args.prior).read_text())
    check(prior_report["summary"]["examined_paired_measurements"]==195,
          "Missing prior exploratory R32o audit")
    result=dict(protocol=PROTO,manifest_sha=sha(args.manifest),source_count=len(cases),trials=len(rows),
        official_competition=True,known_prior_metadata=True,
        summary=summary,cases=cases,prior_exploratory_summary=prior_report["summary"],
        full_trials=rows,caveats=manifest["caveats"])
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print("R32P_EXTERNAL_AUDIT_PASS",len(rows),"original official paired trials",len(cases),"unique sources",flush=True)
    print("R32P_EXTERNAL_SUMMARY",json.dumps(summary,sort_keys=True),flush=True)
    for c in cases:
        print("R32P_EXTERNAL_CASE",c["id"][:8],c["label"],
              json.dumps({k:{"seconds":v["mean_par2_s"],"injected":v["injected"],
                  "terminal":v["terminal"]} for k,v in c["modes"].items()},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("prior");a.add_argument("--source",required=True);a.add_argument("--output",required=True)
    a=sub.add_parser("freeze")
    for k in ("prior18","prior12","r45","output"):a.add_argument("--"+k,required=True)
    a=sub.add_parser("measure")
    for k in ("manifest","clean","native","outdir"):a.add_argument("--"+k,required=True)
    a.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("aggregate")
    for k in ("manifest","combined","prior","output"):a.add_argument("--"+k,required=True)
    x=p.parse_args()
    if x.command=="prior":prior(x)
    elif x.command=="freeze":freeze(x)
    elif x.command=="measure":measure(x)
    else:aggregate(x)
if __name__=="__main__":main()
