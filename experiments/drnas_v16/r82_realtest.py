#!/usr/bin/env python3
"""R82 RealTest: certified algebraic method against original SAT Competition CNFs.

Source cohort is a pre-existing SHA-frozen R82 wide 2025/2026 sample.
No selection by runtime or XOR structure; 2026 may be historical replay.
R82 proposal: use the EXACT R81C certified method with a 0.35s analysis budget
instead of R81C's 3s. Fail closed to unchanged Kissat on every unsupported
or uncertain case. All time charged end-to-end, including budget/fallback.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, os, random, shutil, signal
import subprocess, time
from pathlib import Path
import r81c_exact_algebra as algebra
import r32p_real_satcomp26_benchmark as r32p

PROTO="DRNAS-R82-REALTEST-ORIGINAL2025-2026-20261104-v1"
PARENT="DRNAS-R82-WIDE-OFFICIAL-2025-2026-NOSCREEN-20261104-v1"
SALT="DRNAS-R82-REALTEST-UNSEEN-SELECTION-PRECOMMIT-20261104-v1"
N25,N26,SHARDS,REPS,CAP=16,8,8,2,30.0
MODES=("kissat_original","kissat_404","cadical_301","r81c_exact","r82_budgeted")

def check(ok,what):
    if not ok: raise RuntimeError("R82_REALTEST_FAIL_CLOSED: "+str(what))
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def stable(case):
    return hashlib.sha256((SALT+case["sha256"]).encode()).hexdigest()

def freeze(a):
    old=Path(a.old)
    p=old/"manifest.json"
    mf=json.loads(p.read_text())
    check(mf["protocol"]==PARENT and len(mf["cases"])==48,
          "wrong or incomplete pre-frozen R82 wide originals")
    c25=sorted((x for x in mf["cases"] if x["year"]==2025),key=stable)
    c26=sorted((x for x in mf["cases"] if x["year"]==2026),key=stable)
    check(len(c25)>=N25 and len(c26)>=N26,"insufficient official-source cohort")
    selected=c25[:N25]+c26[:N26]
    check(len({c["sha256"] for c in selected})==N25+N26,"duplicate source")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    for case in selected:
        inp=old/case["filename"]
        check(inp.is_file() and digest(inp)==case["sha256"],"source SHA mismatch")
        shutil.copyfile(inp,out/case["filename"])
        check(digest(out/case["filename"])==case["sha256"],"copy drift")
    original_sha=digest(p)
    outmf=dict(protocol=PROTO,prior_protocol=PARENT,source_manifest_sha=original_sha,
        selection_salt=SALT,source_count=len(selected),cases=selected,
        source_years={"2025":N25,"2026":N26},modes=MODES,shards=SHARDS,
        repeats=REPS,cap_s=CAP,selected_without_timing_or_xor_screening=True,
        r81c_budget_s=3.0,r82_budget_s=0.35,
        limitations=[
          "2025 cohort was SHA-frozen by previous R82 wide run; not independently unseen to all projects.",
          "2026 cohort is retrospective and may include previously benchmarked originals.",
          "R82 is the R81C certified exact solver under a shorter frozen analysis budget, not a new algebraic theorem.",
          "2025 UNSAT from external solvers has no independently imported proof; direct R81C UNSAT is checked.",
          "GitHub runners and 30s PAR2 are not official competition ranking conditions."])
    dump(out/"manifest.json",outmf)
    (out/"source.sha256").write_text("".join(c["sha256"]+"  "+c["filename"]+"\n" for c in selected))
    print("R82_REALTEST_FREEZE_PASS",json.dumps(dict(sources=len(selected),
          y2025=N25,y2026=N26,sha=digest(out/"manifest.json"))),flush=True)

def run_native(binary,original,seconds):
    if seconds<=0:return "UNKNOWN",0.0,"budget_exhausted"
    t=time.monotonic()
    with subprocess.Popen([str(binary),str(original)],stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,errors="replace",start_new_session=True) as p:
        try:
            out,err=p.communicate(timeout=seconds)
        except subprocess.TimeoutExpired:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.communicate()
            return "UNKNOWN",time.monotonic()-t,"timeout"
    elapsed=time.monotonic()-t
    check(p.returncode in (10,20),"bad native exit "+str(p.returncode)+": "+err[-500:])
    ans="SAT" if p.returncode==10 else "UNSAT"
    if ans=="SAT":r32p.verify_sat_witness(original,out)
    return ans,elapsed,"native_verified_sat" if ans=="SAT" else "native_unsat_unproven"

def measure(a):
    root=Path(a.sources)
    mf=json.loads((root/"manifest.json").read_text())
    check(mf["protocol"]==PROTO and len(mf["cases"])==N25+N26,"manifest")
    check(0<=a.shard<SHARDS,"shard")
    bins=Path(a.bins).resolve();native=Path(a.native).resolve()
    for folder,fn in [(bins,"binaries.sha256"),(native,"binary.sha256")]:
        p=subprocess.run(["sha256sum","-c",fn],cwd=folder,capture_output=True,text=True)
        check(p.returncode==0,"solver SHA: "+p.stderr[-500:])
    binaries={"kissat_original":native/"kissat",
              "kissat_404":bins/"kissat_4_0_4",
              "cadical_301":bins/"cadical_3_0_1"}
    for p in binaries.values():check(p.is_file(),"solver missing "+str(p))
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in mf["cases"][a.shard::SHARDS]:
        original=root/case["filename"]
        check(digest(original)==case["sha256"],"source tampering")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(order)
            for mode in order:
                start=time.monotonic()
                direct=None
                if mode in ("r81c_exact","r82_budgeted"):
                    budget=3.0 if mode=="r81c_exact" else 0.35
                    direct=algebra.solve(original,case,max_budget_s=budget)
                    if direct.get("solved"):
                        ans=direct["answer"];route=direct["route"]
                        if ans=="SAT":
                            check(algebra.verify_sat_model(original,direct["model"],case["variables"]),
                                  "invalid direct SAT witness")
                        elif ans=="UNSAT":
                            check(algebra.verify_unsat_certificate(original,direct["proof"]),
                                  "invalid direct UNSAT proof")
                        else:check(False,"invalid direct answer")
                    else:
                        ans,wall,route=run_native(binaries["kissat_original"],original,
                                    CAP-(time.monotonic()-start))
                        route="kissat_fallback_"+direct["route"]+"_"+route
                else:
                    ans,wall,route=run_native(binaries[mode],original,
                                            CAP-(time.monotonic()-start))
                elapsed=time.monotonic()-start
                solved=ans!="UNKNOWN" and elapsed<=CAP
                if not solved:ans="UNKNOWN"
                if solved and case.get("source_verified_status"):
                    check(ans==case["official_status"],
                          "disagrees with published official 2026 answer: "+case["gbd"])
                row=dict(source_id=case["gbd"],year=case["year"],
                    sha256=case["sha256"],group=case.get("group","unknown"),
                    rep=rep,mode=mode,answer=ans,solved=solved,
                    wall_s=round(elapsed,6),par2_s=round(elapsed if solved else 2*CAP,6),
                    route=route,
                    direct_model_hex=(hex(direct["model"]) if direct and direct.get("solved") and ans=="SAT" else None),
                    direct_proof=(direct["proof"] if direct and direct.get("solved") and ans=="UNSAT" else None),
                    runner=os.getenv("RUNNER_NAME",""),commit=os.getenv("GITHUB_SHA",""))
                rows.append(row)
                print("R82_REALTEST_TRIAL",json.dumps({k:row[k] for k in
                    ("source_id","year","rep","mode","answer","par2_s","route")}),flush=True)
            answers={r["answer"] for r in rows if r["sha256"]==case["sha256"]
                     and r["rep"]==rep and r["answer"]!="UNKNOWN"}
            check(len(answers)<=1,"solver verdict disagreement")
    check(len(rows)==len(mf["cases"][a.shard::SHARDS])*REPS*len(MODES),"incomplete rows")
    dump(out/"shard.json",dict(protocol=PROTO,shard=a.shard,manifest_sha=digest(root/"manifest.json"),
        binary_sha={k:digest(v) for k,v in binaries.items()},rows=rows,
        cpu=Path("/proc/cpuinfo").read_text(errors="replace")[:1000]))
    print("R82_REALTEST_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources)
    mf=json.loads((root/"manifest.json").read_text())
    check(mf["protocol"]==PROTO and len(mf["cases"])==N25+N26,"bad freeze")
    cases={x["sha256"]:x for x in mf["cases"]}
    for c in cases.values():check(digest(root/c["filename"])==c["sha256"],"SHA audit")
    rows=[];pins=[]
    for sh in range(SHARDS):
        p=Path(a.combined)/("r82-realtest-shard-"+str(sh))/"results"/"shard.json"
        check(p.is_file(),"missing shard "+str(sh))
        d=json.loads(p.read_text())
        check(d["protocol"]==PROTO and d["shard"]==sh and
              d["manifest_sha"]==digest(root/"manifest.json"),"shard provenance")
        check(len(d["rows"])==len(mf["cases"][sh::SHARDS])*REPS*len(MODES),"rows")
        pins.append(json.dumps(d["binary_sha"],sort_keys=True))
        rows+=d["rows"]
    check(len(set(pins))==1 and len(rows)==len(cases)*REPS*len(MODES),
          "incomplete paired test or solver drift")
    paired=collections.defaultdict(dict)
    for r in rows:
        check(r["sha256"] in cases and r["mode"] in MODES and r["rep"] in range(REPS),
              "unknown row")
        k=(r["sha256"],r["rep"])
        check(r["mode"] not in paired[k],"duplicate mode")
        paired[k][r["mode"]]=r
        if r["direct_model_hex"]:
            check(r["mode"] in ("r81c_exact","r82_budgeted") and
                  algebra.verify_sat_model(root/cases[r["sha256"]]["filename"],
                      int(r["direct_model_hex"],16),cases[r["sha256"]]["variables"]),
                  "invalid SAT model")
        if r["direct_proof"] is not None:
            check(r["mode"] in ("r81c_exact","r82_budgeted") and
                  algebra.verify_unsat_certificate(root/cases[r["sha256"]]["filename"],
                      r["direct_proof"]),"bad UNSAT proof")
        if r["solved"] and cases[r["sha256"]].get("source_verified_status"):
            check(r["answer"]==cases[r["sha256"]]["official_status"],"2026 verdict error")
    check(len(paired)==len(cases)*REPS,"missing pairs")
    for p in paired.values():
        check(set(p)==set(MODES),"missing solver")
        check(len({v["answer"] for v in p.values() if v["answer"]!="UNKNOWN"})<=1,
              "contradictory SAT/UNSAT")
    summary={}
    for year in (2025,2026,"all"):
        rr=[r for r in rows if year=="all" or r["year"]==year]
        summary[str(year)]={m:dict(par2_s=round(sum(r["par2_s"] for r in rr if r["mode"]==m),6),
             solved=sum(r["solved"] for r in rr if r["mode"]==m),
             timeouts=sum(not r["solved"] for r in rr if r["mode"]==m))
             for m in MODES}
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    dump(out/"results.json",dict(protocol=PROTO,status="PASS_UNOFFICIAL",trials=len(rows),
       sources=len(cases),summary=summary,limitations=mf["limitations"]))
    with (out/"paired.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["source_sha","year","rep"]+list(MODES))
        for (sha,rep),p in sorted(paired.items()):
            w.writerow([sha,cases[sha]["year"],rep]+[p[m]["par2_s"] for m in MODES])
    md=["# R82 RealTest — original SAT Competition 2025/2026",
        "24 source CNFs, 2 repeats, five solvers; 30s cap, PAR-2 60s on timeout.",
        "All source SHA-256 and solver binary hashes checked, SAT models and direct UNSAT certificates verified.",
        "",
        "| Cohort | Mode | PAR-2 seconds | Solved / runs |",
        "|---|---|---:|---:|"]
    for y in ("2025","2026","all"):
        for m in MODES:
            v=summary[y][m];md.append(f"| {y} | {m} | {v['par2_s']:.3f} | {v['solved']}/{(N25 if y=='2025' else N26 if y=='2026' else N25+N26)*REPS} |")
    md+=["","**Important:** 2026 includes historical source replays. 2025 was pre-frozen in an earlier R82 experiment. This is not an official world ranking."]
    (out/"report.md").write_text("\n".join(md)+"\n")
    print("R82_REALTEST_FINAL_PASS",json.dumps(summary),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("freeze");f.add_argument("--old",required=True);f.add_argument("--out",required=True)
    m=sub.add_parser("measure")
    for k in ("sources","bins","native","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):a.add_argument("--"+k,required=True)
    q=p.parse_args()
    {"freeze":freeze,"measure":measure,"audit":audit}[q.cmd](q)
if __name__=="__main__":main()
