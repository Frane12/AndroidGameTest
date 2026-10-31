#!/usr/bin/env python3
"""DRNAS SAT V9.7: freeze 12 truly new official 2026 CNFs, paired late-phase test.
Known six diagnostic CNFs are analyzed separately; they never count as new evidence.
All four V9.7 modes have identical unphased first 64/128/256 conflict search.
"""
import argparse,csv,hashlib,json,os,random,statistics,subprocess,time,math
from collections import Counter,defaultdict
from pathlib import Path
import official_shortlong_select as source
from official_shortlong_select import REV,SCORES_GIT_BLOB
source.RAW_CAP=96*1024*1024
source.CNF_CAP=96*1024*1024
source.VARIABLE_CAP=1000000
source.CLAUSE_CAP=4000000
SALT="DRNAS-v97-late-learning-frozen-20261031-v1"
MODES=("ca_plain","orig_v76","v92_sparse",
       "v97_late_never","v97_late_always","v97_late_quality","v97_late_yield")
LATE=tuple(m for m in MODES if m.startswith("v97_"))
CHECKPOINT=("v96_status64","v96_status128","v96_c64","v96_c128",
 "v96_lbd2_64","v96_lbd2_128","v96_lbd4_64","v96_lbd4_128",
 "v96_props64","v96_props128","v96_jump64","v96_jump128",
 "v96_learn64","v96_learn128","v90_learned_256",
 "v90_lbd2_256","v90_lbd4_256","v90_lbd_sum_256",
 "v90_props_256","v90_conflicts_256","v90_jumpdepth_256",
 "v90_jumps_256","learned_delta","threshold","active_pre",
 "active_256","hints","v96_durable_predicted")
DECISIONS=("apply","quality","yield","durable")
FIELDS=("id","group","sha256","rep","mode","selected","status",
        "wall_s","error")+CHECKPOINT+DECISIONS
REPS=2
CAP=15.
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,doc):Path(p).write_text(json.dumps(doc,sort_keys=True,indent=2)+"\n")
def hashed(k):return hashlib.sha256((SALT+"/"+k).encode()).hexdigest()
def freeze(args):
    previous=json.loads(Path(args.previous).read_text())
    assert len(previous["prior_54_excluded"])==54
    assert len(previous["known_diagnostic"])==6
    assert len(previous["new_prospective"])==12
    exclude=set(previous["prior_54_excluded"])|{x["id"] for x in previous["new_prospective"]}
    assert len(exclude)==66, len(exclude)
    # Six previously studied cases are included for mechanistic analysis only.
    known=[{**x,"group":"known_diagnostic"} for x in previous["known_diagnostic"]]
    with Path(args.scores).open(newline="",encoding="utf8") as f: records=list(csv.DictReader(f))
    baseline=[r for r in records if r["solverid"]=="biere_cadical3[main]"]
    assert len(baseline)==400
    candidates=defaultdict(list)
    for row in baseline:
        id=row["instanceid"]
        if id in exclude or row["status"] not in ("sat-verified","unsat-verified"):continue
        t=float(row["runtime"])
        # Include hard official cases as well: old <=180s 2026 cohort was
        # exhausted after excluding prior 66. Frozen sampling, no DRNAS feedback.
        if not (.5<=t<=5000):continue
        label="SAT" if row["status"]=="sat-verified" else "UNSAT"
        grade="fast" if t<5 else ("mid" if t<30 else "slow")
        candidates[label+"_"+grade].append({"id":id,
            "official_label":label,"stratum":label+"_"+grade,
            "official_baseline_s":t})
    chosen=[];attempts=[];attempted=set()
    for label in ("SAT","UNSAT"):
        for grade in ("fast","mid","slow"):
            count=0
            for c in sorted(candidates[label+"_"+grade],key=lambda x:hashed(x["id"])):
                if count==2:break
                attempted.add(c["id"])
                try:info=source.download_and_features(c["id"])
                except Exception as exc:
                    attempts.append({"id":c["id"],"ok":False,"reason":str(exc)})
                    print("V97_REJECT",c["id"],str(exc),flush=True)
                    continue
                chosen.append({**c,**info,"group":"fresh_holdout"})
                attempts.append({"id":c["id"],"ok":True})
                print("V97_ACCEPT",c["id"],label,grade,flush=True);count+=1
            if count<2:print("V97_STRATUM_SHORT",label,grade,count,flush=True)
    for label in ("SAT","UNSAT"):
        while sum(x["official_label"]==label for x in chosen)<6:
            pool=sorted([c for k,v in candidates.items() if k.startswith(label+"_")
                          for c in v if c["id"] not in attempted],
                          key=lambda c:hashed("spill/"+c["id"]))
            if not pool:raise RuntimeError("Insufficient new CNFs "+label)
            accepted=False
            for c in pool:
                attempted.add(c["id"])
                try:info=source.download_and_features(c["id"])
                except Exception as exc:
                    attempts.append({"id":c["id"],"ok":False,"reason":str(exc)})
                    continue
                chosen.append({**c,**info,"group":"fresh_holdout"})
                attempts.append({"id":c["id"],"ok":True})
                print("V97_SPILL",c["id"],label,flush=True)
                accepted=True;break
            if not accepted:raise RuntimeError("No accessible CNFs "+label)
    assert len(chosen)==12 and not ({x["id"] for x in chosen}&exclude)
    chosen.sort(key=lambda x:hashed("schedule/"+x["id"]))
    save(args.out,{"protocol":SALT,"previous_manifest_sha256":digest(args.previous),
        "excluded_prior_66":sorted(exclude),
        "known_diagnostic":known,"fresh_holdout":chosen,"cases":known+chosen,
        "scores_git_blob":SCORES_GIT_BLOB,"official_commit":REV,
        "acceptance_log":attempts,
        "rule_frozen":{"quality":"L>=20; LBD<=2 >=6%; propagations/conflict>=32; active>0",
         "yield":"quality AND delta(128->256) learned>=8 AND >=6% delta LBD<=2 AND >=24 props/conflict"},
        "limitations":["Known six are outcome-selected and NOT prospective",
          "12 new official 2026 published CNFs exclude every prior project problem",
          "Baseline competition runtimes used only for size-screened stratification, NEVER routing",
          "Broader <=5000s official-time cohort may have many 15-second timeouts",
          "No official competition ranking or world record claimed"]})
    print("V97_MANIFEST_FROZEN",len(chosen),digest(args.out),flush=True)
def run(args):
    manifest=json.loads(Path(args.manifest).read_text())
    assert manifest["protocol"]==SALT and 0<=args.shard<6
    group="known_diagnostic" if args.shard<2 else "fresh_holdout"
    cases=(manifest["known_diagnostic"][args.shard*3:args.shard*3+3] if args.shard<2
           else manifest["fresh_holdout"][(args.shard-2)*3:(args.shard-1)*3])
    assert len(cases)==3
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    core=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{core})
    save(out/"meta.json",{"group":group,"shard":args.shard,"cases":[x["id"] for x in cases],
         "manifest_sha256":digest(args.manifest),"core":core,"cap":CAP,"reps":REPS})
    rows=[];issues=[]
    with (out/"raw.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for case in cases:
            ident=case["id"];cnf=out/(ident+".cnf")
            checked=source.download_and_features(ident,cnf)
            assert checked["sha256"]==case["sha256"],"Input SHA changed"
            assert checked["features"]==case["features"],"Input features changed"
            print("V97_VERIFIED_SHA",ident,case["sha256"],flush=True)
            for rep in range(REPS):
                modes=list(MODES)
                random.Random(97131+int(ident[:8],16)+rep*7001).shuffle(modes)
                seed=(830031+int(case["sha256"][:8],16)+rep*527)%(2**32)
                for mode in modes:
                    started=time.monotonic();data={};error=""
                    try:
                        proc=subprocess.run([str(Path(args.exe).resolve()),mode,
                            str(cnf),str(seed)],capture_output=True,text=True,
                            timeout=CAP,check=False)
                        sec=time.monotonic()-started
                        if proc.returncode:
                            raise RuntimeError("exit="+str(proc.returncode)+" "+proc.stderr[-250:])
                        lines=[x for x in proc.stdout.splitlines() if x.startswith("DRNAS_CAUSAL\t")]
                        if len(lines)!=1:raise RuntimeError("Missing terminal record")
                        data.update(dict(x.split("=",1) for x in lines[0].split("\t")[1:]))
                        assert data["mode"]==mode
                        if mode in LATE:
                            early=[x for x in proc.stdout.splitlines() if x.startswith("DRNAS_EARLY\t")]
                            decision=[x for x in proc.stdout.splitlines() if x.startswith("DRNAS_DECISION\t")]
                            if len(early)!=1:raise RuntimeError("Missing early telemetry")
                            data.update(dict(x.split("=",1) for x in early[0].split("\t")[1:]))
                            if data["stage1"]=="0":
                                if len(decision)!=1:raise RuntimeError("Missing decision trace")
                                data.update(dict(x.split("=",1) for x in decision[0].split("\t")[1:]))
                        status=data["answer"]
                        if status!=case["official_label"]:
                            raise RuntimeError("Incorrect SAT/UNSAT response")
                    except subprocess.TimeoutExpired as exc:
                        status="TIMEOUT";sec=CAP
                        raw=exc.stdout or b""
                        if isinstance(raw,bytes):raw=raw.decode("utf-8","replace")
                        early=[x for x in raw.splitlines() if x.startswith("DRNAS_EARLY\t")]
                        decision=[x for x in raw.splitlines() if x.startswith("DRNAS_DECISION\t")]
                        if early:
                            data.update(dict(x.split("=",1) for x in early[-1].split("\t")[1:]))
                        if decision:
                            data.update(dict(x.split("=",1) for x in decision[-1].split("\t")[1:]))
                    except Exception as exc:
                        status="ERROR";sec=time.monotonic()-started;error=str(exc)
                        issues.append(ident+" "+mode+" "+error)
                    row={"id":ident,"group":group,"sha256":case["sha256"],
                         "rep":rep,"mode":mode,"selected":data.get("apply",""),
                         "status":status,"wall_s":round(sec,6),"error":error}
                    for k in CHECKPOINT+DECISIONS:row[k]=data.get(k,"")
                    writer.writerow(row);f.flush();rows.append(row)
                    print("V97_TRIAL",ident[:10],group,"rep",rep,mode,status,
                          row["wall_s"],"gate",row["selected"],flush=True)
            cnf.unlink(missing_ok=True)
    assert len(rows)==3*REPS*len(MODES)
    # Every V9.7 intervention starts with exactly the same unphased history.
    # Flushed early traces survive even after timeouts and are checked here.
    checked_count=0
    for c in cases:
        for rep in range(REPS):
            group=[r for r in rows if r["id"]==c["id"] and r["rep"]==rep and r["mode"] in LATE]
            assert len(group)==len(LATE)
            # If an early trace was not emitted before timeout, retain as censored.
            full=[r for r in group if r["v96_c128"]!=""]
            for metric in CHECKPOINT:
                values=[x[metric] for x in full]
                if len(set(values))>1:
                    issues.append("PRE256_INVARIANT "+c["id"]+" rep="+str(rep)+" metric="+metric)
            if len(full)==len(LATE):checked_count+=1
    save(out/"summary.json",{"count":len(rows),"shard":args.shard,
         "checked_complete_matched_sets":checked_count,"issues":issues})
    if issues:raise RuntimeError("Invalid V97 trials "+str(issues[:5]))
    print("V97_SHARD_PASS",args.shard,len(rows),flush=True)
def audit(args):
    manifest=json.loads(Path(args.manifest).read_text())
    assert manifest["protocol"]==SALT and len(manifest["cases"])==18
    ids={x["id"]:x for x in manifest["cases"]}
    rows=[];seen=set()
    for i in range(6):
        with (Path(args.combined)/f"v97-shard-{i}"/"results"/"raw.csv").open(newline="") as f:
            rows+=list(csv.DictReader(f))
    assert len(rows)==252,len(rows)
    cost=defaultdict(lambda:defaultdict(list))
    traces=defaultdict(dict)
    for r in rows:
        key=(r["id"],r["mode"],int(r["rep"]))
        assert key not in seen;seen.add(key)
        assert r["id"] in ids and r["mode"] in MODES and int(r["rep"]) in (0,1)
        assert r["sha256"]==ids[r["id"]]["sha256"] and not r["error"]
        assert r["status"] in ("SAT","UNSAT","TIMEOUT")
        if r["status"]!="TIMEOUT":assert r["status"]==ids[r["id"]]["official_label"]
        cost[r["id"]][r["mode"]].append(30 if r["status"]=="TIMEOUT" else float(r["wall_s"]))
        traces[r["id"]][(r["mode"],int(r["rep"]))]={k:r[k] for k in CHECKPOINT+DECISIONS}
    assert all(len(cost[id][m])==REPS for id in ids for m in MODES)
    result={"protocol":SALT,"trials":len(rows),"independent_fresh":12,
            "prior_diagnostic":6,"groups":{},"per_case":[]}
    for grp in ("known_diagnostic","fresh_holdout"):
        cc=[c for c in ids.values() if c["group"]==grp]
        means={m:statistics.mean(t for c in cc for t in cost[c["id"]][m]) for m in MODES}
        solved={m:sum(t<30 for c in cc for t in cost[c["id"]][m]) for m in MODES}
        result["groups"][grp]={"cases":len(cc),"meanPAR2":means,
                               "solved_trials":solved}
        for c in cc:
            p={m:statistics.mean(cost[c["id"]][m]) for m in MODES}
            result["per_case"].append({"id":c["id"],"group":grp,"label":c["official_label"],
                                      "features":c["features"],"PAR2":p,
                                      "trace_rep0":{m:traces[c["id"]][(m,0)] for m in LATE}})
    fresh=[x for x in result["per_case"] if x["group"]=="fresh_holdout"]
    comparisons={}
    rnd=random.Random(970031)
    for other in ("v97_late_never","v97_late_always","orig_v76","ca_plain","v92_sparse"):
        diffs=[x["PAR2"][other]-x["PAR2"]["v97_late_quality"] for x in fresh]
        boots=sorted(statistics.mean(rnd.choices(diffs,k=len(diffs))) for _ in range(5000))
        npos=sum(x>1e-3 for x in diffs);nneg=sum(x< -1e-3 for x in diffs)
        comparisons[other]={"delta_other_minus_quality_mean_s":statistics.mean(diffs),
            "bootstrap_CI_95_s":[boots[125],boots[4874]],"wins":npos,"losses":nneg,
            "ties":12-npos-nneg}
    result["fresh_pairwise_quality"]=comparisons
    result["limitations"]=[
      "Known diagnostic cases outcome-selected; do not include in novel 12-case validation",
      "Pre-search rule thresholds adopted from previous V9.1 exploratory studies, not a proof",
      "Only 12 fresh instances, size-screened and baseline time-stratified",
      "2 repetitions share one CNF - statistical unit is the unique problem",
      "LBD is instrumented internal learned-clause metric, not mathematical proof of speedup",
      "No independent UNSAT certificate, compared with official verified label",
      "Feature extraction and rule decision overhead included in timed C++ modes; baseline instrumentation differs",
      "PAR2 timeouts charged 30 seconds; true time beyond cutoff unknown",
      "No official competition placing or universal speedup"]
    save(args.out,result)
    lines=["# DRNAS V9.7 — late 256-conflict learning gate prospective audit","",
       "18 official SAT 2026 instances, six known diagnostic and 12 new held-out.",
       "252 trials, 15s wall cap, PAR2 timeout penalty 30s.",
       "Precommitted V9.1 quality rule and new incremental 128->256 yield variant.",""]
    for grp in ("known_diagnostic","fresh_holdout"):
        g=result["groups"][grp]
        lines+=[f"## {grp}, {g['cases']} CNF cases","",
           "| Method | Solved trials | Mean PAR2 (seconds) |","|---|---:|---:|"]
        for m in MODES:
            lines.append(f"| {m} | {g['solved_trials'][m]}/{2*g['cases']} | {g['meanPAR2'][m]:.4f} |")
        lines.append("")
    lines+=["## Prespecified fresh-holdout paired contrasts","",
       "Positive differences mean V9.7 late quality is better.","",
       "| Comparator | Other minus late quality PAR2 (s) | 95% bootstrap interval | Wins / losses / ties |",
       "|---|---:|---|---|"]
    for m,rec in comparisons.items():
        b=rec["bootstrap_CI_95_s"]
        lines.append(f"| {m} | {rec['delta_other_minus_quality_mean_s']:.4f} | "+
            f"[{b[0]:.3f}, {b[1]:.3f}] | "+
            f"{rec['wins']} / {rec['losses']} / {rec['ties']} |")
    lines+=["","## Every fresh CNF","",
      "| ID | SAT/UNSAT | CaDiCaL | V7.6 | Sparse | Late Never | Late Always | Late Quality | Late Yield |",
      "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in fresh:
        p=x["PAR2"]
        lines.append(f"| {x['id'][:10]} | {x['label']} | "+
           " | ".join(f"{p[m]:.3f}" for m in MODES)+" |")
    lines+=["","No scientific law or world record follows from this small experiment."]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="action",required=True)
    f=sub.add_parser("freeze")
    for p in ("previous","scores","out"):f.add_argument("--"+p,required=True)
    r=sub.add_parser("run")
    for p in ("manifest","exe","out"):r.add_argument("--"+p,required=True)
    r.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for p in ("manifest","combined","out","md"):a.add_argument("--"+p,required=True)
    args=ap.parse_args()
    {"freeze":freeze,"run":run,"audit":audit}[args.action](args)
if __name__=="__main__":main()
