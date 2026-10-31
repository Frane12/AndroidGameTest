#!/usr/bin/env python3
"""Unofficial SAT Competition 2026 *mini-simulation*.

Not an official rank or certification. Uses 18 genuine 2026 Main-Track CNFs
already frozen in V9.6 (six previously selected diagnostics and twelve
previously attempted prospective formulas). All strategies use the same pinned
inputs, CPU affinity, memory and wall time. Output includes separate cohorts.
"""
import argparse, hashlib, json, os, random, resource, statistics, subprocess, time
from pathlib import Path
import official_shortlong_select as source

SOURCE_RUN=41239481557
PROTOCOL="DRNAS-2026-official-main-mini-sim-20261031-v1"
CORES=1
REPS=2
CAP=30.0  # 30 s, NOT official 5000 s
MEMORY_GIB=3  # NOT official 32 GiB
MODES=("DRNAS_LBD","DRNAS_Legacy","DRNAS_Soft","DRNAS_NoLate",
       "CaDiCaL301","Kissat404")
DRNAS_POLICY={"DRNAS_LBD":"v100_late_lbd_force",
              "DRNAS_Legacy":"v100_late_legacy_force",
              "DRNAS_Soft":"v100_late_soft_force",
              "DRNAS_NoLate":"v100_late_plain_force",
              "CaDiCaL301":"ca_plain"}
source.RAW_CAP=96*1024*1024
source.CNF_CAP=96*1024*1024
source.VARIABLE_CAP=1_000_000
source.CLAUSE_CAP=4_000_000

def save(dest,obj):
    Path(dest).parent.mkdir(parents=True,exist_ok=True)
    Path(dest).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def freeze(a):
    m=json.loads(Path(a.v96).read_text())
    six=m["known_diagnostic"]
    twelve=m["new_prospective"]
    assert len(six)==6 and len(twelve)==12
    ids=[x["id"] for x in six+twelve]
    assert len(ids)==len(set(ids))==18
    assert all(c["official_label"] in ("SAT","UNSAT") for c in six+twelve)
    assert all(len(c["sha256"])==64 and "features" in c for c in six+twelve)
    cases=[{**c,"cohort":"diagnostic_preselected" if i<6 else
                       "prior_prospective_2026"} for i,c in enumerate(six+twelve)]
    save(a.out,{
      "protocol":PROTOCOL,"source_run_id":SOURCE_RUN,"source_sha256":sha(a.v96),
      "official_2026_score_git_blob":m["score_git_blob"],
      "official_2026_git_commit":m["official_commit"],
      "cases":cases,"modes":MODES,"repetitions":REPS,"cap_seconds":CAP,
      "memory_limit_gib":MEMORY_GIB,
      "official_track_properties":{"wall_time_limit_s":5000,"memory_limit_gib":32,
                                    "scoring":"PAR2", "certificate_required":True},
      "limitations":[
       "NOT A SAT Competition entry, official 2026 rank, or official hardware",
       "30 s cap and 3 GiB, rather than official 5000 s and 32 GiB",
       "18 preselected official 2026 instances, rather than the complete main track",
       "All eighteen instances were previously used in DRNAS development",
       "Six diagnostic instances were deliberately chosen based on prior wins",
       "Twelve previously prospective instances were also measured in V9.6",
       "SAT model and UNSAT proof output not independently certified",
       "Kissat 4.0.4 is upstream Kissat, not a claim to use the 2026 winning submission",
       "At most one CPU per invocation; CPU characteristics differ from official hardware",
       "All winner declarations apply to this exact mini-simulation only"
      ]})
    print("MINI_FREEZE_PASS",len(cases),len(MODES),REPS,flush=True)

def parse_drnas(stdout,expected):
    finals=[line for line in stdout.splitlines()
            if line.startswith("DRNAS_CAUSAL\t")]
    if len(finals)!=1:raise RuntimeError("missing/duplicate DRNAS_CAUSAL line")
    kv=dict(x.split("=",1) for x in finals[0].split("\t")[1:])
    if kv["mode"]!=expected:raise RuntimeError("wrong DRNAS mode")
    return kv["answer"]

def parse_kissat(stdout):
    answers=[]
    for line in stdout.splitlines():
        if line.strip()=="s SATISFIABLE":answers.append("SAT")
        if line.strip()=="s UNSATISFIABLE":answers.append("UNSAT")
    if len(answers)!=1:raise RuntimeError("wrong or missing Kissat answer")
    return answers[0]

def memory_limit():
    resource.setrlimit(resource.RLIMIT_AS,(MEMORY_GIB*1024**3,MEMORY_GIB*1024**3))

def trial(mode,path,seed,drnas,kissat,official):
    if mode=="Kissat404":
        cmd=[str(Path(kissat).resolve()),str(Path(path).resolve())]
    else:
        cmd=[str(Path(drnas).resolve()),DRNAS_POLICY[mode],
             str(Path(path).resolve()),str(seed)]
    start=time.monotonic()
    status="ERROR";msg="";answer=None;exit_code=None
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
             timeout=CAP,preexec_fn=memory_limit,check=False)
        elapsed=time.monotonic()-start
        exit_code=proc.returncode
        if mode=="Kissat404":
            if exit_code not in (10,20):raise RuntimeError(
                "Kissat unexpected exit: "+str(exit_code)+" "+proc.stderr[-250:])
            answer=parse_kissat(proc.stdout)
            if (exit_code==10)!=(answer=="SAT"):raise RuntimeError("exit/answer mismatch")
        else:
            if exit_code!=0:raise RuntimeError(
                "DRNAS unexpected exit: "+str(exit_code)+" "+proc.stderr[-250:])
            answer=parse_drnas(proc.stdout,DRNAS_POLICY[mode])
        if answer!=official:raise RuntimeError(
            "Disagreement with official label: "+answer+" versus "+official)
        status=answer
    except subprocess.TimeoutExpired:
        elapsed=CAP
        status="TIMEOUT"
    except Exception as exc:
        elapsed=min(time.monotonic()-start,CAP)
        msg=str(exc)[:320]
        status="ERROR"
    return dict(status=status,seconds=round(elapsed,6),answer=answer,
                error=msg,exit_code=exit_code)

def run(a):
    m=json.loads(Path(a.manifest).read_text())
    assert m["protocol"]==PROTOCOL and m["modes"]==list(MODES)
    assert 0<=a.shard<6
    subset=m["cases"][3*a.shard:3*a.shard+3]
    assert len(subset)==3
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    allowed=os.sched_getaffinity(0)
    core=min(allowed)
    os.sched_setaffinity(0,{core})
    cpuinfo=Path("/proc/cpuinfo").read_text()
    cpu_model=next((l.split(":",1)[1].strip() for l in cpuinfo.splitlines()
                    if l.startswith("model name")),"unknown")
    rows=[]
    save(out/"meta.json",{"shard":a.shard,"cases":[c["id"] for c in subset],
                          "core":core,"model":cpu_model,
                          "official_cap_seconds":5000,
                          "actual_cap_seconds":CAP,
                          "source_sha256":m["source_sha256"]})
    for c in subset:
        file=out/(c["id"]+".cnf")
        chk=source.download_and_features(c["id"],file)
        if chk["sha256"]!=c["sha256"] or chk["features"]!=c["features"]:
            raise RuntimeError("SHA/features mismatch "+c["id"])
        print("MINI_INPUT_VERIFIED",c["id"],c["sha256"],flush=True)
        for rep in range(REPS):
            seed=(88181+1009*rep+int(c["sha256"][:8],16))%(2**32)
            modes=list(MODES)
            random.Random(seed^763109).shuffle(modes)
            for mode in modes:
                obs=trial(mode,file,seed,a.drnas,a.kissat,c["official_label"])
                row=dict(cnf_id=c["id"],cohort=c["cohort"],
                         official_label=c["official_label"],cnf_sha256=c["sha256"],
                         repetition=rep,seed=seed,mode=mode,**obs)
                rows.append(row)
                print("MINI_TRIAL",c["id"][:12],rep,mode,obs["status"],
                      f'{obs["seconds"]:.3f}',flush=True)
                save(out/"rows.json",rows)
                if obs["status"]=="ERROR":
                    raise RuntimeError("Fail-closed: "+mode+" "+obs["error"])
        file.unlink(missing_ok=True)
    assert len(rows)==3*REPS*len(MODES)==36
    print("MINI_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    m=json.loads(Path(a.manifest).read_text())
    assert m["protocol"]==PROTOCOL and m["modes"]==list(MODES)
    assert len(m["cases"])==18
    cases={c["id"]:c for c in m["cases"]}
    rows=[];models=set()
    for shard in range(6):
        folder=Path(a.combined)/("mini-shard-"+str(shard))/"results"
        meta=json.loads((folder/"meta.json").read_text())
        assert meta["shard"]==shard
        assert meta["source_sha256"]==m["source_sha256"]
        assert meta["cases"]==[c["id"] for c in m["cases"][3*shard:3*shard+3]]
        models.add(meta["model"])
        sr=json.loads((folder/"rows.json").read_text())
        assert len(sr)==36
        rows.extend(sr)
    assert len(rows)==18*6*2==216
    keys=set();by_case={}
    for r in rows:
        assert r["cnf_id"] in cases
        c=cases[r["cnf_id"]]
        assert (r["cnf_sha256"]==c["sha256"]
                and r["official_label"]==c["official_label"]
                and r["cohort"]==c["cohort"])
        assert r["mode"] in MODES and r["repetition"] in (0,1)
        assert r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"]
        assert r["status"]=="TIMEOUT" or r["status"]==c["official_label"]
        assert 0<=r["seconds"]<=CAP+0.2
        key=(r["cnf_id"],r["mode"],r["repetition"])
        assert key not in keys,key
        keys.add(key)
        by_case.setdefault(r["cnf_id"],[]).append(r)
    for c in m["cases"]:
        rr=by_case[c["id"]]
        assert len(rr)==12 and {x["mode"] for x in rr}==set(MODES)
    cohorts={}
    for group in ("prior_prospective_2026","diagnostic_preselected","all"):
        rr=[x for x in rows if group=="all" or x["cohort"]==group]
        tally={}
        for mode in MODES:
            subset=[x for x in rr if x["mode"]==mode]
            costs=[CAP*2 if x["status"]=="TIMEOUT" else x["seconds"] for x in subset]
            tally[mode]={"solved":sum(x["status"]!="TIMEOUT" for x in subset),
                         "total":len(subset),
                         "PAR2_seconds":round(statistics.mean(costs),4),
                         "mean_solved_runtime_s":round(statistics.mean([
                           x["seconds"] for x in subset if x["status"]!="TIMEOUT"]),4)
                           if any(x["status"]!="TIMEOUT" for x in subset) else None}
        cohorts[group]=tally
    report={"protocol":PROTOCOL,"total_attempts":len(rows),
            "verified_sha_inputs":len(cases),"CPU_models":sorted(models),
            "source":m,"cohorts":cohorts,"all_rows":rows,
            "ranking_basis":"PAR2 on this restricted runner only",
            "official_world_rank":None}
    save(a.out,report)
    lines=["# DRNAS SAT Competition 2026 — UNOFFICIAL Mini-Simulation","",
       "**NOT a world ranking or 2026 official submission.**",
       "Actual: 30 s time and 3 GiB RAM; official main: 5000 s and 32 GiB.",
       "18 previously observed genuine 2026 CNFs, six diagnostic and twelve prior prospective.",
       "Six methods on equal pinned runner core, two repetitions, 216 attempts.",
       "One Kissat 4.0.4 upstream comparator (not official winner build).",
       "SAT models and UNSAT proofs are NOT independently certified; official labels cross-checked.",
       "All CNF SHA256 digests verified before testing.",""]
    for label in ("prior_prospective_2026","diagnostic_preselected","all"):
        lines += ["## "+label,"","| Solver | Solved | PAR2 s (lower better) |",
                  "|---|---:|---:|"]
        for name,data in sorted(cohorts[label].items(),
                         key=lambda v:(v[1]["PAR2_seconds"],-v[1]["solved"])):
            lines.append(f'| {name} | {data["solved"]}/{data["total"]} | {data["PAR2_seconds"]:.4f} |')
        lines.append("")
    lines += ["## Scope limits"]+["- "+q for q in m["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("MINI_AUDIT_PASS",len(rows),len(cases),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    cmd=p.add_subparsers(dest="command",required=True)
    for name,props in (("freeze",("v96","out")),
                       ("run",("manifest","drnas","kissat","out")),
                       ("audit",("manifest","combined","out","md"))):
        c=cmd.add_parser(name)
        for prop in props:c.add_argument("--"+prop,required=True)
        if name=="run":c.add_argument("--shard",type=int,required=True)
    args=p.parse_args()
    {"freeze":freeze,"run":run,"audit":audit}[args.command](args)
