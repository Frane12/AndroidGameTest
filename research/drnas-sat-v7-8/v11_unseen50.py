#!/usr/bin/env python3
"""DRNAS frozen holdout: 2026 official CNFs excluded from every earlier 2026 experiment.

Not an official world rank or certification. Select SHA-verified genuinely new-to-DRNAS
2026 official instances, before any V11 solve, with hard memory constraints.
No tuning based on holdout outcomes. All methods run on the same CPU affinity.
"""
import argparse, csv, hashlib, json, os, random, resource, statistics, subprocess, time
from pathlib import Path
import official_shortlong_select as source

SOURCE_RUN=41239481557
TARGET=50
MIN_ACCEPT=20
SHARDS=10
SOURCE_GIT_BLOB="9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef"
SALT="DRNAS-2026-CNF-NEW-20261031-SAT-UNSAT-fair-v1"
PROTOCOL="DRNAS-SAT-2026-UNSEEN50-FROZEN-20261031-v1"
CORES=1
REPS=2
CAP=30.0  # 30 s, NOT official 5000 s
MEMORY_GIB=3  # NOT official 32 GiB
MODES=("DRNAS_Legacy","DRNAS_NoLate","CaDiCaL301","Kissat404")
DRNAS_POLICY={"DRNAS_Legacy":"v100_late_legacy_force",
              "DRNAS_NoLate":"v100_late_plain_force",
              "CaDiCaL301":"ca_plain"}
source.RAW_CAP=160*1024*1024
source.CNF_CAP=160*1024*1024
source.VARIABLE_CAP=1_000_000
source.CLAUSE_CAP=4_000_000

def save(dest,obj):
    Path(dest).parent.mkdir(parents=True,exist_ok=True)
    Path(dest).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def freeze(a):
    history=json.loads(Path(a.v96).read_text())
    oldids=set(history["prior_54_excluded"])
    oldids.update(c["id"] for c in history["known_diagnostic"])
    oldids.update(c["id"] for c in history["new_prospective"])
    assert len(history["known_diagnostic"])==6 and len(history["new_prospective"])==12
    assert len(oldids)>=66,len(oldids)
    rows=list(csv.DictReader(Path(a.scores).open(newline="",encoding="utf8")))
    baselines=[r for r in rows if r["solverid"]=="biere_cadical3[main]"]
    assert len(baselines)==400
    eligible=[]
    for r in baselines:
        if r["instanceid"] in oldids:continue
        if r["status"] not in ("sat-verified","unsat-verified"):continue
        sec=float(r["runtime"])
        if not (0.01<=sec<=1200):continue
        label="SAT" if r["status"]=="sat-verified" else "UNSAT"
        band="fast" if sec<10 else ("mid" if sec<90 else "slow")
        eligible.append(dict(id=r["instanceid"],official_label=label,
                             official_baseline_s=sec,stratum=label+"_"+band))
    assert len(eligible)>=TARGET,len(eligible)
    # Shuffle with deterministic SHA256, never the label, CNF content, family
    # name or any observed DRNAS runtime. Only official base time for binning.
    groups={}
    for e in eligible:groups.setdefault(e["stratum"],[]).append(e)
    for k in groups:
        groups[k].sort(key=lambda c:hashlib.sha256(
            (SALT+"/"+c["id"]).encode()).hexdigest())
    strata=["SAT_fast","UNSAT_fast","SAT_mid","UNSAT_mid",
            "SAT_slow","UNSAT_slow"]
    cursor={x:0 for x in strata}
    accepted=[];attempts=[];already=set()
    # Round-robin all six bins to preserve balanced SAT/UNSAT and difficulty,
    # increasing breadth without selecting on any DRNAS trial outcome.
    exhausted=set()
    while len(accepted)<TARGET and len(exhausted)<len(strata):
        for stratum in strata:
            if len(accepted)>=TARGET:break
            if stratum in exhausted:continue
            bucket=groups.get(stratum,[])
            if cursor[stratum]>=len(bucket):
                exhausted.add(stratum);continue
            c=bucket[cursor[stratum]]
            cursor[stratum]+=1
            if c["id"] in already:continue
            already.add(c["id"])
            try:
                feat=source.download_and_features(c["id"])
                # A SHA256 digest of actual uncompressed CNF is pinned
                # before the solver builds, even on rejected candidates.
                accepted.append({**c,**feat,"cohort":"2026_new_to_DRNAS_v11"})
                attempts.append({"id":c["id"],"result":"accepted"})
                print("V11_ACCEPT",len(accepted),stratum,c["id"],feat["sha256"],flush=True)
            except Exception as exc:
                attempts.append({"id":c["id"],"result":"rejected","reason":str(exc)[:150]})
                print("V11_REJECT",stratum,c["id"],str(exc)[:90],flush=True)
    if len(accepted)<MIN_ACCEPT:
        raise RuntimeError("Fewer than 20 feasible genuinely new-to-DRNAS 2026 formulas: "
                           +str(len(accepted))+"; do not claim benchmark success")
    accepted.sort(key=lambda c:hashlib.sha256(
        (SALT+"/schedule/"+c["id"]).encode()).hexdigest())
    save(a.out,{
      "protocol":PROTOCOL,"selection_target":TARGET,"selection_minimum":MIN_ACCEPT,
      "accepted_count":len(accepted),"sha_pinned":True,
      "source_run_id":SOURCE_RUN,"source_sha256":sha(a.v96),
      "official_scores_git_blob":SOURCE_GIT_BLOB,
      "excluded_previous_2026_ids":sorted(oldids),
      "eligible_count":len(eligible),"attempts":attempts,
      "cases":accepted,"modes":MODES,"repetitions":REPS,"cap_seconds":CAP,
      "memory_limit_gib":MEMORY_GIB,
      "official_track_properties":{"wall_time_limit_s":5000,"memory_limit_gib":32,
                                   "scoring":"PAR2","certificate_required":True},
      "limitations":[
       "NOT an official SAT Competition 2026 entry, score, hardware or world rank",
       "Selected from original 2026 official scoreboard excluding 66 earlier DRNAS 2026 cases",
       "Not guaranteed unseen to other people; previously unmeasured by DRNAS in these manifests",
       "Selection bounded by input size, official CaDiCaL run-time and downloadable status",
       "Official CaDiCaL timings used ONLY to stratify difficulty; no DRNAS timing leakage",
       "All solver policies, input order and caps frozen BEFORE these runs",
       "30 second cap and 3 GiB memory rather than competition 5000s and 32 GiB",
       "The baseline Kissat 4.0.4 is NOT the 2026 championship solver",
       "SAT/UNSAT answer checked against official label, not independent proof certificates",
       "No solver code modifications or threshold tuning after trial results"
      ]})
    print("V11_FREEZE_PASS",len(accepted),len(eligible),len(oldids),flush=True)

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
    assert 0<=a.shard<SHARDS
    subset=m["cases"][a.shard::SHARDS]
    assert 2<=len(subset)<=5
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
        print("V11_INPUT_VERIFIED",c["id"],c["sha256"],flush=True)
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
                print("V11_TRIAL",c["id"][:12],rep,mode,obs["status"],
                      f'{obs["seconds"]:.3f}',flush=True)
                save(out/"rows.json",rows)
                if obs["status"]=="ERROR":
                    raise RuntimeError("Fail-closed: "+mode+" "+obs["error"])
        file.unlink(missing_ok=True)
    assert len(rows)==len(subset)*REPS*len(MODES)
    print("V11_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    m=json.loads(Path(a.manifest).read_text())
    assert m["protocol"]==PROTOCOL and m["modes"]==list(MODES)
    assert MIN_ACCEPT<=len(m["cases"])<=TARGET
    cases={c["id"]:c for c in m["cases"]}
    rows=[];models=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/("v11-shard-"+str(shard))/"results"
        meta=json.loads((folder/"meta.json").read_text())
        assert meta["shard"]==shard
        assert meta["source_sha256"]==m["source_sha256"]
        assert meta["cases"]==[c["id"] for c in m["cases"][shard::SHARDS]]
        models.add(meta["model"])
        sr=json.loads((folder/"rows.json").read_text())
        assert len(sr)==len(meta["cases"])*REPS*len(MODES)
        rows.extend(sr)
    assert len(rows)==len(m["cases"])*len(MODES)*REPS
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
        assert len(rr)==len(MODES)*REPS and {x["mode"] for x in rr}==set(MODES)
    cohorts={}
    for group in ("2026_new_to_DRNAS_v11","all"):
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
    lines=["# DRNAS V11 — Frozen 2026 previously-unseen holdout","",
       "**NOT a world ranking or 2026 official submission.**",
       "Actual: 30 s time and 3 GiB RAM; official main: 5000 s and 32 GiB.",
       str(len(m["cases"]))+" previously unmeasured-by-DRNAS official 2026 CNFs.",
       str(len(MODES))+" frozen methods, 10 equal CPU-affinity shards, two repetitions.",
       "Kissat 4.0.4 is NOT official 2026 winner; official labels are metadata.",
       "SAT models and UNSAT proofs are NOT independently certified; official labels cross-checked.",
       "All CNF SHA256 digests verified before testing.",""]
    for label in ("2026_new_to_DRNAS_v11","all"):
        lines += ["## "+label,"","| Solver | Solved | PAR2 s (lower better) |",
                  "|---|---:|---:|"]
        for name,data in sorted(cohorts[label].items(),
                         key=lambda v:(v[1]["PAR2_seconds"],-v[1]["solved"])):
            lines.append(f'| {name} | {data["solved"]}/{data["total"]} | {data["PAR2_seconds"]:.4f} |')
        lines.append("")
    lines += ["## Scope limits"]+["- "+q for q in m["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V11_AUDIT_PASS",len(rows),len(cases),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    cmd=p.add_subparsers(dest="command",required=True)
    for name,props in (("freeze",("v96","scores","out")),
                       ("run",("manifest","drnas","kissat","out")),
                       ("audit",("manifest","combined","out","md"))):
        c=cmd.add_parser(name)
        for prop in props:c.add_argument("--"+prop,required=True)
        if name=="run":c.add_argument("--shard",type=int,required=True)
    args=p.parse_args()
    {"freeze":freeze,"run":run,"audit":audit}[args.command](args)
