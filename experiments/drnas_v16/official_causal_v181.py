#!/usr/bin/env python3
"""DRNAS SAT V18.1 controlled in-process restart sensitivity on official 2026 CNFs.

Two disjoint stages: (a) retrospective diagnostics on V18.0 instances,
(b) new precommitted holdout official instances (no previous DRNAS timing).
Ten frozen policies: plain, instrumented control, 6 forced interventions,
2 prefrozen gates. Same runner for each formula/strategy pair; randomized
sequential order. One codebase, one pinned Kissat. No cold restart / hints.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, math, os, random
import re, statistics, subprocess, sys, time
from pathlib import Path
import official_parallel_v180 as legacy

ROOT = Path("drnas-v181-causal-results")
FROZEN = Path("experiments/drnas_v16/v181_frozen_official_cases.json")
POLICIES = ("plain","trace","switch512_i25","switch1024_i25",
            "switch2048_i10","switch2048_i25","switch2048_i50",
            "switch4096_i25","gate_r30_2048_i25","gate_g0869_1024_i25")
CHECKPOINTS = (256,512,1024,2048,4096,8192,16384,32768,
               65536,131072,262144,524288,1048576)
COUNT = {"diagnostic":2,"holdout":1}
CAP = 60.0
COMPRESSED_LIMIT = 24*1024*1024
RAW_LIMIT = 96*1024*1024
MAX_HOLDOUT_CASES = 4
PINNED_KISSAT = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
PINNED_TRACK = "3e2dee7cf5aa643c77bf946280a3c1c520756ef9"
HEADER = ("stage","shard","official_index","gbd_hash","sha256",
          "nvars","nclauses","official_status","official_kissat_seconds",
          "repeat","mode","status","seconds","par2","model_verified",
          "local_unsat_proof_verified","switch_count","first_switch_at",
          "first_switch_from","first_switch_to","r512","g512",
          "final_conflicts","final_restarts","final_learned","reason")

def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def get_cases(stage,shard,out):
    frozen = json.loads(FROZEN.read_text())
    assert frozen["pinned_2026_uri_commit"]==PINNED_TRACK
    assert frozen["pinned_kissat"]==PINNED_KISSAT
    assert tuple(frozen["policies"])==POLICIES
    ref_key = "diagnostic" if stage=="diagnostic" else "holdout_candidates"
    possible = frozen["stages"][ref_key][shard]
    assert all(int(x["shard"])==shard for x in possible)
    assert len(possible)==(3 if stage=="diagnostic" else 6)
    goal=len(possible) if stage=="diagnostic" else MAX_HOLDOUT_CASES
    uri_data = legacy.fetch(
      f"https://raw.githubusercontent.com/satcompetition/2026/{PINNED_TRACK}/downloads/track_main_2026.uri",
      100000, timeout=20)
    uris = uri_data.decode().strip().splitlines()
    assert len(uris)==400
    out.mkdir(parents=True, exist_ok=True)
    (out/"track_uris_sha256.txt").write_text(digest(uri_data)+"\n")
    failures=[]
    downloaded=[]
    for selection in possible:
        if len(downloaded)>=goal:break
        index=selection["official_index"]
        url=uris[index].replace("http://","https://",1)
        gb_hash=url.rsplit("/",1)[-1]
        assert gb_hash==selection["gbd_hash"], "Official track reference changed"
        reference=selection["official_kissat"]
        assert 5 <= reference["seconds"] <= 60
        assert reference["status"] in ("sat-verified","unsat-verified")
        try:
            packed=legacy.fetch(url,COMPRESSED_LIMIT,timeout=30)
            legacy.RAW_LIMIT=RAW_LIMIT
            content=legacy.unpack_limited(packed)
            n,m=legacy.dimensions(content)
            folder=out/"cnf"
            folder.mkdir(parents=True,exist_ok=True)
            path=folder/f"{index:03d}_{gb_hash}.cnf"
            path.write_bytes(content)
            item=dict(selection, nvars=n,nclauses=m,
                      url=url,compressed_sha256=digest(packed),
                      sha256=digest(content),cnf_bytes=len(content),path=str(path))
            downloaded.append(item)
            print("V181_OFFICIAL_FETCH",stage,shard,index,
                  item["sha256"],n,m,flush=True)
        except Exception as err:
            reason=str(err)[:250]
            failures.append(dict(official_index=index,reason=reason))
            print("V181_OFFICIAL_SKIP",stage,shard,index,reason,flush=True)
    manifest={
      "stage":stage,"shard":shard,"selected":len(possible),
      "available":len(downloaded),"skipped":failures,
      "frozen_manifest_sha256":digest(FROZEN.read_bytes()),
      "pinned_upstream_kissat":PINNED_KISSAT,
      "pinned_2026_track":PINNED_TRACK,
      "official_scores_blob_sha":frozen["pinned_official_scores_blob_sha"],
      "cap_seconds":CAP,"repeats":COUNT[stage],"policies":POLICIES,
      "blind_stage":stage=="holdout",
      "selected_without_drnas_holdout_outcomes":True,
      "formula_files_not_included_in_zip":True,
      "cases":[{k:v for k,v in x.items() if k!="path"} for x in downloaded],
      "formal_unsat_certificates_checked":False,
      "official_instances_not_official_competition_scoring":True
    }
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
    if not downloaded:raise RuntimeError("All frozen candidate downloads failed")
    return downloaded

def parse_events(output,case,mode,rep):
    ticks=[];events=[];switches=[];final={}
    for line in output.splitlines():
        if not line.startswith("c V181_"):continue
        words=line[2:].split()
        kind=words[0].removeprefix("V181_")
        data={}
        for token in words[1:]:
            if "=" in token:
                k,v=token.split("=",1)
                data[k]=v
        data.update(kind=kind,official_index=case["official_index"],
                    sha256=case["sha256"],mode=mode,repeat=rep)
        if kind=="TICK":ticks.append(data)
        elif kind=="SWITCH":switches.append(data)
        elif kind=="FINAL":final=data
        events.append(data)
    if len(switches)>1:raise RuntimeError("Multiple intervention events")
    for s in switches:
        if s["learned_before"]!=s["learned_after"]:
            raise RuntimeError("Learned clauses changed at intervention")
        if int(s["restart_before"])!=1 or int(s["restart_after"]) not in (10,25,50):
            raise RuntimeError("Restart parameter was not changed as designed")
    if mode in ("trace","plain") and switches:
        raise RuntimeError("Unmodified control switched")
    if mode=="plain" and events:
        raise RuntimeError("Uninstrumented control emitted telemetry")
    ordered=[int(t["at"]) for t in ticks]
    if ordered!=sorted(set(ordered)):
        raise RuntimeError("Out-of-order or repeated checkpoint")
    return ticks,events,switches,final

def attempt(case,mode,rep,solver):
    env=os.environ.copy()
    env.pop("DRNAS_V181_MODE",None)
    if mode!="plain":env["DRNAS_V181_MODE"]=mode
    cmd=[str(solver),"-s",str(Path(case["path"]).resolve())]
    started=time.perf_counter()
    try:
        p=subprocess.run(cmd,env=env,capture_output=True,text=True,
                         errors="replace",timeout=CAP,check=False)
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
    reason=""
    verified=False
    if status in ("SAT","UNSAT") and status!=expected:
        raise RuntimeError("Solver contradicts published verified official 2026 status")
    if status=="SAT":
        verified=legacy.check_model(Path(case["path"]),output,None)
        if not verified:
            raise RuntimeError("SAT model fails full original DIMACS witness validation")
    if status=="ERROR":
        reason="solver-error "+output[-300:].replace("\n"," ")
        raise RuntimeError(reason)
    ticks,events,switches,final=parse_events(output,case,mode,rep)
    early=next((x for x in ticks if x["at"]=="512"),{})
    row=dict(stage=case["stage"],shard=case["shard"],
             official_index=case["official_index"],
             gbd_hash=case["gbd_hash"],sha256=case["sha256"],
             nvars=case["nvars"],nclauses=case["nclauses"],
             official_status=expected,official_kissat_seconds=case["official_kissat"]["seconds"],
             repeat=rep,mode=mode,status=status,seconds=round(elapsed,6),
             par2=round(elapsed,6) if status in ("SAT","UNSAT") else 2*CAP,
             model_verified=verified,local_unsat_proof_verified=False,
             switch_count=len(switches),
             first_switch_at=switches[0]["at"] if switches else "",
             first_switch_from=switches[0]["restart_before"] if switches else "",
             first_switch_to=switches[0]["restart_after"] if switches else "",
             r512=early.get("restarts",""),
             g512=early.get("ratio",""),
             final_conflicts=final.get("conflicts",""),
             final_restarts=final.get("restarts",""),
             final_learned=final.get("learned",""),
             reason=reason)
    return row,events,ticks

def write_rows(out,rows,fieldnames):
    with out.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fieldnames,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def audit_premodified_trace(rows, ticks_by):
    # Preintervention counter paths must agree with the instrumented trace.
    by_pair=collections.defaultdict(dict)
    for row in rows:
        by_pair[(row["official_index"],row["repeat"])][row["mode"]]=row
    checked=0
    for key,modes in by_pair.items():
        reference=ticks_by.get((*key,"trace"),{})
        for mode,r in modes.items():
            if mode in ("trace","plain"):continue
            target={"switch512_i25":512,"switch1024_i25":1024,
                    "switch2048_i10":2048,"switch2048_i25":2048,
                    "switch2048_i50":2048,"switch4096_i25":4096,
                    "gate_r30_2048_i25":2048,
                    "gate_g0869_1024_i25":1024}[mode]
            candidate=ticks_by.get((*key,mode),{})
            for at,t in candidate.items():
                if at>target or at not in reference:continue
                a=reference[at]
                for field in ("restarts","decisions","propagations","learned",
                              "cut_n","cut_size","cut_glue","cut_span",
                              "cut_low","cut_short"):
                    if t[field]!=a[field]:
                        raise RuntimeError(f"PRE-SWITCH STATE DIVERGENCE {key} {mode} at={at} {field}: {t[field]} vs {a[field]}")
                checked+=1
    return checked

def run_stage(stage,shard):
    out=ROOT/f"{stage}_{shard}"
    cases=get_cases(stage,shard,out)
    for c in cases:c["stage"]=stage
    solver=Path("/tmp/kissat-v181/build/kissat").resolve()
    assert solver.is_file()
    rows=[];events=[];snapshots=[];ticks_by={}
    for case in cases:
        assert digest(Path(case["path"]).read_bytes())==case["sha256"]
        for rep in range(COUNT[stage]):
            modes=list(POLICIES)
            random.Random(181000 + case["official_index"]*17 + rep).shuffle(modes)
            for mode in modes:
                row,trace,ticks=attempt(case,mode,rep,solver)
                rows.append(row)
                for x in trace:
                    events.append({**x,"stage":stage,"shard":shard})
                for x in ticks:
                    snapshots.append({**x,"stage":stage,"shard":shard})
                ticks_by[(case["official_index"],rep,mode)]={
                    int(t["at"]):t for t in ticks}
                print("V181_MEASURE",stage,shard,case["official_index"],
                      "repeat",rep,mode,row["status"],
                      "seconds",row["seconds"],"PAR2",row["par2"],
                      "r512",row["r512"],"g512",row["g512"],
                      "switches",row["switch_count"],flush=True)
            write_rows(out/"measurements.partial.csv",rows,HEADER)
            print("V181_CASE_COMPLETE",stage,shard,case["official_index"],
                  "repeat",rep,"runs",len(POLICIES),flush=True)
    assert len(rows)==len(cases)*COUNT[stage]*len(POLICIES)
    checked=audit_premodified_trace(rows,ticks_by)
    write_rows(out/"measurements.csv",rows,HEADER)
    tick_cols=("stage","shard","official_index","sha256","repeat","mode",
               "kind","policy","at","conflicts","restarts","focused_restarts",
               "stable_restarts","decisions","propagations","learned",
               "glue_fast","glue_slow","ratio","stable","focused_modes",
               "stable_modes","reductions","rephased","elapsed_cpu_ms","interval",
               "focused_conflicts","stable_conflicts",
               "cut_n","cut_size","cut_glue","cut_span","cut_low","cut_short")
    write_rows(out/"checkpoints.csv",snapshots,tick_cols)
    keys=sorted(set(k for e in events for k in e))
    write_rows(out/"events.csv",events,keys)
    ranking=[]
    for mode in POLICIES:
        subset=[r for r in rows if r["mode"]==mode]
        ranking.append(dict(mode=mode,attempts=len(subset),
                            solved=sum(r["status"] in ("SAT","UNSAT") for r in subset),
                            par2=round(statistics.mean(r["par2"] for r in subset),6),
                            switched=sum(r["switch_count"] for r in subset)))
    ranking.sort(key=lambda r:r["par2"])
    summary=dict(stage=stage,shard=shard,official_formula_count=len(cases),
                 total_attempts=len(rows),repeat_count=COUNT[stage],cap=CAP,
                 pre_intervention_tick_comparisons=checked,
                 SAT_witnesses_validated=sum(r["model_verified"] for r in rows),
                 UNSAT_independent_certificates=0,
                 status_contradictions=0,ranking=ranking,
                 source_commit=os.getenv("GITHUB_SHA","local"),
                 runner=os.getenv("RUNNER_NAME","local"),
                 official_sample_only=True,
                 note="Only full paired complete cases; sample exploratory, no contest record")
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    print("V181_STAGE_AUDIT_PASS",json.dumps(summary,separators=(",",":")),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage",choices=COUNT)
    p.add_argument("--shard",type=int,choices=range(4))
    opts=p.parse_args()
    if opts.stage is None or opts.shard is None:p.error("stage+shard required")
    run_stage(opts.stage,opts.shard)

if __name__=="__main__":main()
