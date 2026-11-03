#!/usr/bin/env python3
"""R55b: prospectively frozen SAT Competition 2026 holdout for R54's head24 rule.

This test is designed BEFORE reviewing R55 clause-interaction outcomes.
Original SATComp26 GBD IDs are SHA-disjoint from R32p/R32r/R52/R53/R54/R55
known cohorts, selected using only published CaDiCaL 2026 status/runtime
strata and a salted hash. No DRNAS timing or solver outcome used to select.
Compare unmodified Kissat, frozen gate+first16 / first24 / all40 policies
and CaDiCaL 3.0.1 on same GitHub core, 40s end-to-end, two repeats.
This is an external check of PRESELECTED head24, not an automatic R55
causal discovery or official SAT Competition rank.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,os,random,resource,statistics,subprocess,tempfile,time
from pathlib import Path
import r32p_real_satcomp26_benchmark as r32p
import r32r_more_real_satcomp26_benchmark as r32r
import r52_prospective_2026_toprefs as r52
import r49_pivot_coherence_gate as r49

PROTO="DRNAS-R55B-HEAD24-FROZEN-PROSPECTIVE2026-20261103-v1"
SALT="R55B-20261103-PRECOMMIT-HEAD24-PRIOR-TO-CAUSAL-RESULTS"
URI=r52.URI
SCORES=r52.SCORES
MODES=("clean","head16_gate","head24_gate","full40_gate","cadical_3_0_1")
STRATA=("sat_fast","unsat_fast","sat_mid","unsat_mid")
CAP=40.0
SHARDS=6
REPS=2
READY_PER=3
ATTEMPTS_PER=16
RAW_CAP=28*1024*1024
CNF_CAP=48*1024*1024
R52_RUN=41684183452

def check(ok,msg):
    if not ok:raise RuntimeError("R55B_FAIL_CLOSED "+str(msg))
def sha(path):
    return r52.digest(path)
def hashed(s):
    return hashlib.sha256((SALT+":"+s).encode()).hexdigest()
def freeze(a):
    folder=Path(a.out)
    folder.mkdir(parents=True,exist_ok=True)
    earlier=json.loads((Path(a.previous)/"manifest.json").read_text())
    check(earlier["protocol"]==r52.PROTO and len(earlier["cases"])==11,
          "wrong R52 previously exposed original set")
    ids=set(x["gbd"] for x in earlier["cases"])
    older=set(g for _,g in r32p.PINS)|set(g for _,g in r32r.PINS)
    check(len(older)==37 and not ids.intersection(older),
          "prior registry changed")
    excluded=ids|older
    official_raw=r52.fetch_bytes(URI,100000)
    urls=official_raw.decode("utf-8").strip().splitlines()
    gbd=[x.rsplit("/",1)[-1] for x in urls]
    check(len(gbd)==400 and len(set(gbd))==400,"official 2026 list mutated")
    official_set=set(gbd)
    score_raw=r52.fetch_bytes(SCORES,32*1024*1024)
    rows=list(csv.DictReader(io.StringIO(score_raw.decode())))
    official_scores=[x for x in rows if x["solverid"]=="biere_cadical3[main]"
        and x["instanceid"] in official_set]
    check(len(official_scores)==400,"published baseline score count changed")
    pools={s:[] for s in STRATA}
    for r in official_scores:
        uid=r["instanceid"]
        if uid in excluded or r["status"] not in ("sat-verified","unsat-verified"):
            continue
        t=float(r["runtime"])
        band="fast" if 0<=t<10 else "mid" if 10<=t<80 else None
        if band is None:continue
        key=("sat" if r["status"]=="sat-verified" else "unsat")+"_"+band
        pools[key].append(dict(gbd=uid,official_2026_index=gbd.index(uid),
            published_control_runtime_s=t,
            official_status="SAT" if r["status"]=="sat-verified" else "UNSAT"))
    r32p.CNF_LIMIT=CNF_CAP
    ready=[];log=[];used=set()
    for cohort in STRATA:
        sorted_candidates=sorted(pools[cohort],key=lambda z:hashed(cohort+"/"+z["gbd"]))
        accepted=0
        for c in sorted_candidates[:ATTEMPTS_PER]:
            g=c["gbd"]
            check(g not in used and g not in excluded,"source identity leaked")
            used.add(g)
            note=dict(stratum=cohort,gbd=g,index=c["official_2026_index"])
            filename=g+".cnf"
            source=folder/filename
            try:
                raw,redirect=r32p.request_url(
                    "https://benchmark-database.de/file/"+g,RAW_CAP,seconds=55)
                data,compression=r32p.decode(raw)
                check(len(data)<=CNF_CAP,"uncompressed DIMACS exceeds cap")
                n,m=r32p.parse_dimacs_metadata(data)
                source.write_bytes(data)
                # Freeze policy features and proof before viewing any new solver results
                plan=r49.compute_plan(source)
                check(len(plan["clauses"])==plan["derived"]<=40,
                      "proof count invalid")
                case=dict(**c,filename=filename,source_sha256=sha(source),
                     vars=n,clauses=m,raw_bytes=len(raw),cnf_bytes=len(data),
                     compression=compression,redirect=redirect,
                     r49_gate=plan["gate"],derived=plan["derived"],
                     dominance=plan["dominance"],
                     certificate_sha256=plan["certificate_sha256"],
                     policy="head24 iff R49 gate true (original policy already frozen R54)")
                check(case["source_sha256"] not in
                      {x["sha256"] for x in earlier["cases"]},"source duplicated by SHA")
                ready.append(case);accepted+=1
                note.update(state="READY",sha256=case["source_sha256"],
                            active=plan["gate"],derived=plan["derived"])
            except Exception as err:
                source.unlink(missing_ok=True)
                note.update(state="EXCLUDED_SIZE_DOWNLOAD_OR_PARSE",
                            reason=(type(err).__name__+": "+str(err))[:350])
            log.append(note)
            print("R55B_FREEZE_ATTEMPT",json.dumps(note,sort_keys=True),flush=True)
            if accepted>=READY_PER:break
    check(8<=len(ready)<=12 and len({x["source_sha256"] for x in ready})==len(ready),
          "too few or duplicate fresh original SHA identities")
    meta=dict(protocol=PROTO,salt=SALT,official_uri=URI,official_scores=SCORES,
         official_uri_sha256=hashlib.sha256(official_raw).hexdigest(),
         official_scores_sha256=hashlib.sha256(score_raw).hexdigest(),
         older_R32p_R32r_ids=sorted(older),older_R52_ids=sorted(ids),
         previous_R52_manifest_sha=sha(Path(a.previous)/"manifest.json"),
         source_selection="pre-committed SAT/UNSAT and fast/mid strata from public CaDiCaL results",
         selection_disjoint_from_known_id_sets=True,
         global_project_history_disjoint_not_verified=True,
         official_sources_already_published_not_truly_unseen_2026_competition=True,
         no_DRNAS_results_used_to_select=True,
         max_downloads_per_stratum=ATTEMPTS_PER,desired_per_stratum=READY_PER,
         modes=list(MODES),repeats=REPS,shards=SHARDS,cap_s=CAP,
         cases=ready,download_log=log,
         limitations=[
           "Official CaDiCaL 2026 classification and runtime used for stratified selection",
           "Disjoint from R32p R32r R52 R53 R54 R55 ID list; other old project history not fully excluded",
           "Frozen head24 rule is from R54, before R55 ablation outcomes",
           "No official contest solver winner, hardware or scoring claim",
           "Original SAT witness verified, UNSAT not separately LRAT certified",
           "40s cap includes all certified clause analysis, rewriting, witness checking"])
    (folder/"manifest.json").write_text(json.dumps(meta,indent=2)+"\n")
    (folder/"source.sha256").write_text("".join(
        c["source_sha256"]+"  "+c["filename"]+"\n" for c in ready))
    print("R55B_FREEZE_PASS",len(ready),"prospective matched 2026 originals",
          "active",sum(c["r49_gate"] for c in ready),
          "rejected",sum(x["state"]!="READY" for x in log),flush=True)

def child_memory():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
def one(original,case,mode,kissat,cadical):
    t0=time.monotonic();inp=original;added=0;status="TIMEOUT"
    with tempfile.TemporaryDirectory(prefix="drnas-r55b-") as d:
        if mode in ("head16_gate","head24_gate","full40_gate"):
            plan=r49.compute_plan(original)
            check(plan["certificate_sha256"]==case["certificate_sha256"] and
                  plan["derived"]==case["derived"] and plan["gate"]==case["r49_gate"],
                  "frozen certificate/selector drift")
            if plan["gate"]:
                count={"head16_gate":16,"head24_gate":24,"full40_gate":40}[mode]
                selected=plan["clauses"][:count]
                if selected:
                    inp=Path(d)/"augmented.cnf"
                    assert len(selected)<=40
                    audit=r49.r48.safe_rewrite(original,inp,selected)
                    check(audit["added"]==len(selected),"rewrite wrong")
                    added=len(selected)
        prep=time.monotonic()-t0
        if prep<CAP:
            solver=cadical if mode=="cadical_3_0_1" else kissat
            try:
                p=subprocess.run([str(solver),str(inp)],
                    capture_output=True,text=True,errors="replace",
                    timeout=CAP-prep,preexec_fn=child_memory)
                check(p.returncode in (10,20),"solver exited incorrectly "+str(p.returncode))
                status="SAT" if p.returncode==10 else "UNSAT"
                if status=="SAT":
                    r32p.verify_sat_witness(original,p.stdout)
            except subprocess.TimeoutExpired:
                status="TIMEOUT"
        total=time.monotonic()-t0
    if total>CAP:status="TIMEOUT"
    wall=round(min(total,CAP),6)
    return dict(status=status,wall_s=wall,prep_s=round(prep,6),
         par2_s=round(wall if status!="TIMEOUT" else 2*CAP,6),added=added)

def measure(args):
    m=json.loads((Path(args.sources)/"manifest.json").read_text())
    check(m["protocol"]==PROTO and args.shard in range(SHARDS),"wrong design/shard")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    kb=Path(args.kissat).resolve();cb=Path(args.cadical).resolve()
    check(kb.is_file() and cb.is_file(),"pinned binaries absent")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    meta=dict(protocol=PROTO,shard=args.shard,
        source_manifest_sha=sha(Path(args.sources)/"manifest.json"),
        kissat_sha=sha(kb),cadical_sha=sha(cb))
    (out/"meta.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for case in m["cases"][args.shard::SHARDS]:
        source=Path(args.sources)/case["filename"]
        check(sha(source)==case["source_sha256"],"original SHA drift")
        for rep in range(REPS):
            order=list(MODES)
            seed=int(hashed(case["source_sha256"]+"/"+str(rep)),16)
            random.Random(seed).shuffle(order)
            for mode in order:
                data=one(source,case,mode,kb,cb)
                check(data["status"]=="TIMEOUT" or data["status"]==case["official_status"],
                      "conflict with official SATComp26 answer")
                r=dict(gbd=case["gbd"],source_sha=case["source_sha256"],
                       rep=rep,mode=mode,gate=case["r49_gate"],**data)
                rows.append(r)
                print("R55B_TRIAL",case["gbd"],"rep",rep,mode,data["status"],
                      data["wall_s"],"PAR2",data["par2_s"],"added",data["added"],
                      flush=True)
                (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
    check(len(rows)==len(m["cases"][args.shard::SHARDS])*len(MODES)*REPS,
          "missing measured original")

def audit(args):
    m=json.loads((Path(args.sources)/"manifest.json").read_text())
    check(m["protocol"]==PROTO,"not frozen")
    rows=[];solvers=set()
    for shard in range(SHARDS):
        root=Path(args.combined)/f"r55b-shard-{shard}"/"results"
        info=json.loads((root/"meta.json").read_text())
        check(info["protocol"]==PROTO and info["shard"]==shard and
              info["source_manifest_sha"]==sha(Path(args.sources)/"manifest.json"),
              "mixed source manifests")
        solvers.add((info["kissat_sha"],info["cadical_sha"]))
        current=json.loads((root/"rows.json").read_text())
        check(len(current)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
              "incomplete run")
        rows.extend(current)
    check(len(solvers)==1 and len(rows)==len(m["cases"])*REPS*len(MODES),
          "binaries differ or attempts missing")
    summary={}
    for mode in MODES:
        x=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in x),
            attempts=len(x),par2_total_s=round(sum(r["par2_s"] for r in x),6),
            active_interventions=sum(r["added"]>0 for r in x),
            injected_clauses=sum(r["added"] for r in x))
    baseline=summary["clean"]["par2_total_s"]
    for z in summary.values():
        z["delta_vs_clean_pct"]=round(100*(z["par2_total_s"]/baseline-1),4)
    bycase={}
    for case in m["cases"]:
        rr=[r for r in rows if r["gbd"]==case["gbd"]]
        check(len(rr)==REPS*len(MODES) and all(r["source_sha"]==case["source_sha256"] for r in rr),
              "original case not fully matched")
        for rep in range(REPS):
            xs=[r for r in rr if r["rep"]==rep]
            check(set(r["mode"] for r in xs)==set(MODES),"mode missing")
            check(all(r["status"]=="TIMEOUT" or r["status"]==case["official_status"] for r in xs),
                  "wrong SAT result")
        bycase[case["gbd"]]=dict(gate=case["r49_gate"],
            derived=case["derived"],
            modes={mode:dict(times=[r["wall_s"] if r["status"]!="TIMEOUT" else "TO"
                for r in sorted(rr,key=lambda z:z["rep"]) if r["mode"]==mode],
                par2_s=round(sum(r["par2_s"] for r in rr if r["mode"]==mode),6))
                for mode in MODES})
    report=dict(protocol=PROTO,cases=len(m["cases"]),attempts=len(rows),
        pinned_binaries=next(iter(solvers)),aggregate=summary,
        bycase=bycase,rows=rows,manifest=m)
    Path(args.json).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# R55b — frozen first-24 R54 rule, source-disjoint 2026 validation",
           f"{len(m['cases'])} previously untested-by-R32p/R32r/R52 Main2026 originals; two repeats.",
           "Source selection based on PUBLIC CaDiCaL official scores (not DRNAS outcome).",
           "40s wall, 80s PAR2 timeout, same pinned Kissat and CaDiCaL runner.",
           "Not a truly official or universally unseen SAT Competition cohort.",
           "", "| Method | Solved | PAR2 total s | vs clean | Active attempts |",
           "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        s=summary[mode]
        lines.append(f'| {mode} | {s["solved"]}/{s["attempts"]} | {s["par2_total_s"]:.3f} | {s["delta_vs_clean_pct"]:+.2f}% | {s["active_interventions"]} |')
    lines+=["","## Per-source 2026 original (two repeats, PAR2 sum seconds)",
       "| GBD prefix | Gate | "+" | ".join(MODES)+" |",
       "|---|---|"+("|---:|"*len(MODES))]
    for case in m["cases"]:
        b=bycase[case["gbd"]]
        lines.append("| "+case["gbd"][:12]+" | "+str(b["gate"])+" | "+" | ".join(
            f'{b["modes"][mode]["par2_s"]:.3f}' for mode in MODES)+" |")
    lines+=["","Global project-history disjointness not exhaustively verified.",
       "No selection/retuning using R55 target formula while this holdout runs."]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R55B_FINAL_AUDIT_PASS",len(rows),json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();subs=p.add_subparsers(dest="action",required=True)
    x=subs.add_parser("freeze")
    for f in ("previous","out"):x.add_argument("--"+f,required=True)
    x=subs.add_parser("measure")
    for f in ("sources","shard","kissat","cadical","out"):
        x.add_argument("--"+f,required=True)
    x=subs.add_parser("audit")
    for f in ("sources","combined","json","md"):
        x.add_argument("--"+f,required=True)
    a=p.parse_args()
    if a.action=="freeze":freeze(a)
    elif a.action=="measure":
        a.shard=int(a.shard);measure(a)
    else:audit(a)
if __name__=="__main__":main()
