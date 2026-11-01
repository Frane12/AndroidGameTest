#!/usr/bin/env python3
"""V13.2 prospective LBD4 signal validation on SHA-disjoint SAT Competition 2026 CNFs.

Rule locked BEFORE new solve timings: predict Kissat-only (two Kissat solves,
zero DRNAS Legacy solves) if an exact CaDiCaL 256th-conflict snapshot has
>=20 learned clauses and fraction LBD<=4 < 0.20. Everything else is negative.
The rule is DIAGNOSTIC. Prefix probe creates a separate solver instance;
it cannot continue DRNAS's learned state. No official ranking or new solver.
"""
import argparse,csv,hashlib,json,os,random,resource,statistics,subprocess,time
from pathlib import Path
from collections import Counter,defaultdict
import official_shortlong_select as source
import official_2026_mini_sim as mini
P="DRNAS-V132-prospective-LBD4-locked-20261101"
SALT="DRNAS-V132-FROZEN-new-2026-CNF-001"
CAP=12.0; PREFIX_CAP=14.0; REPS=2; SHARDS=4; N=24
MODES=("DRNAS_Legacy","Kissat404")
LABELS=("SAT","UNSAT")
mini.CAP=CAP; mini.MEMORY_GIB=3
source.RAW_CAP=96*1024*1024;source.CNF_CAP=96*1024*1024
source.VARIABLE_CAP=1000000;source.CLAUSE_CAP=4000000
def check(condition,msg):
    if not condition: raise RuntimeError(msg)
def load(p):return json.loads(Path(p).read_text())
def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def eligible_sources(old131,mini_source,old100):
    old=load(old131)["cases"]
    prior=load(mini_source)["cases"]
    century=load(old100)["cases"]
    check(len(old)==132 and len(prior)==18,"Wrong frozen prior sources")
    ids={c["id"] for c in old+prior+century}|source.EXCLUDED
    shas={c["sha256"] for c in old+prior+century}
    return ids,shas
def predict(t):
    # Incomplete, solved-early or missing prefix -> conservative negative.
    if t is None or t["v90_conflicts_256"]!=256: return False
    learned=t["v90_learned_256"]
    return learned>=20 and t["v90_lbd4_256"]/learned<0.20
def selftest():
    t={"v90_conflicts_256":256,"v90_learned_256":100,"v90_lbd4_256":19}
    check(predict(t) and not predict({**t,"v90_lbd4_256":20}),"Threshold error")
    check(not predict({**t,"v90_conflicts_256":255}) and not predict(None),"Abstain error")
    print("V132_SELFTEST_PASS",flush=True)
def freeze(a):
    ids,shas=eligible_sources(a.prior131,a.prior_mini,a.prior100)
    with open(a.scores,newline="",encoding="utf8") as f: scores=list(csv.DictReader(f))
    buckets=defaultdict(list)
    for r in scores:
        if r["solverid"]!="biere_cadical3[main]" or r["status"] not in (
             "sat-verified","unsat-verified"):continue
        if r["instanceid"] in ids:continue
        sec=float(r["runtime"])
        label="SAT" if r["status"]=="sat-verified" else "UNSAT"
        grade="fast" if sec<10 else "mid" if sec<180 else "hard"
        buckets[label+"_"+grade].append(r)
    for group in buckets:
        buckets[group].sort(key=lambda r:hashlib.sha256(
            (SALT+"/"+r["instanceid"]).encode()).hexdigest())
    chosen=[];reject=[];keyed=sorted(buckets)
    check(len(keyed)>=2,"Insufficient nonempty source strata")
    print("V132_SOURCE_STRATA",[(k,len(buckets[k])) for k in keyed],flush=True)
    while len(chosen)<N and any(buckets.values()):
        for group in keyed:
            if len(chosen)>=N:break
            if not buckets[group]:continue
            row=buckets[group].pop(0)
            cid=row["instanceid"]
            try:
                c=source.download_and_features(cid)
                check(c["sha256"] not in shas,"Prior SHA duplicate")
                shas.add(c["sha256"]);ids.add(cid)
                c.update(cohort=group,
                         official_label="SAT" if row["status"]=="sat-verified" else "UNSAT")
                chosen.append(c)
                print("V132_FREEZE",len(chosen),cid,group,flush=True)
            except Exception as e:
                reject.append({"id":cid,"cohort":group,"reason":str(e)[:150]})
                print("V132_SKIP",cid,str(e)[:110],flush=True)
    check(len(chosen)==N and len({c["sha256"] for c in chosen})==N,"Insufficient new formulas")
    save(a.out,{"protocol":P,"cases":chosen,"cap_s":CAP,"prefix_cap_s":PREFIX_CAP,
       "reps":REPS,"shards":SHARDS,"source_score_sha256":digest(a.scores),
       "source_prior_sha256":[digest(a.prior131),digest(a.prior_mini),digest(a.prior100)],
       "rule":{"feature":"exact256_lbd4_fraction","threshold_strictly_below":0.20,
               "minimum_learned_clauses":20,"target":"Kissat_only_2vs0",
               "early_solved_prediction":False},
       "rejected":reject,"limits":[
        "All formulas from SAT Competition 2026; official labels and stratification buckets known",
        "SHA-disjoint only from three pinned sources, not guaranteed globally novel",
        "Rule frozen before new DRNAS/Kissat measurements; 12s cap, 3 GiB",
        "Prefix is a separate CaDiCaL run, NOT an integrated continuation",
        "Prediction seeks Kissat-only class, NOT faster runtime or a DRNAS-world-record",
        "Cross-runner CPU models may differ; pair within one runner",
        "SAT/UNSAT statuses checked against official labels, no independent proof certificates"]})
    print("V132_FREEZE_PASS",len(chosen),flush=True)
def mem():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
def prefix(binary,cnf,seed):
    start=time.monotonic()
    try:
        p=subprocess.run([str(Path(binary).resolve()),"v100_late_plain_force",
                          str(cnf.resolve()),str(seed)],
                         capture_output=True,text=True,errors="replace",
                         timeout=PREFIX_CAP,preexec_fn=mem)
        check(p.returncode==0,"Prefix probe exit "+str(p.returncode)+" "+p.stderr[-200:])
        lines=[l for l in p.stdout.splitlines() if l.startswith("DRNAS_EARLY\t")]
        check(len(lines)==1,"Prefix must emit one telemetry row")
        q=dict(v.split("=",1) for v in lines[0].split("\t")[1:])
        t={k:int(q[k]) for k in ("v90_conflicts_256","v90_lbd4_256",
               "v90_lbd2_256","v90_learned_256","stage1")}
        check(0<=t["v90_conflicts_256"]<=256,"Prefix overshoot")
        check(0<=t["v90_lbd2_256"]<=t["v90_lbd4_256"]<=t["v90_learned_256"],
              "Malformed LBD telemetry")
        check(t["stage1"]!=0 or t["v90_conflicts_256"]==256,
              "Unresolved prefix without exact snapshot")
        return t,round(time.monotonic()-start,6)
    except subprocess.TimeoutExpired:
        return None, PREFIX_CAP
def run(a):
    m=load(a.manifest)
    check(m["protocol"]==P and 0<=a.shard<SHARDS,"Wrong frozen protocol")
    cases=m["cases"][a.shard::SHARDS]
    check(len(cases)==N//SHARDS,"Wrong shard size")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu=next((l.split(":",1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
             if l.startswith("model name")),"unknown")
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    save(root/"meta.json",{"protocol":P,"shard":a.shard,
        "ids":[c["id"] for c in cases],"cpu":cpu,
        "probe_sha256":digest(a.probe),"drnas_sha256":digest(a.drnas),
        "kissat_sha256":digest(a.kissat)})
    rows=[]
    for c in cases:
        f=root/(c["id"]+".cnf")
        got=source.download_and_features(c["id"],f)
        check(got["sha256"]==c["sha256"] and got["features"]==c["features"],
              "Source SHA/features mismatch")
        t,pretime=prefix(a.probe,f,int(c["sha256"][:8],16))
        p=predict(t)
        outcomes=[]
        for rep in range(REPS):
            seed=(1322026+1009*rep+int(c["sha256"][:8],16))%(2**32)
            modes=list(MODES)
            random.Random(seed^132).shuffle(modes)
            for mode in modes:
                o=mini.trial(mode,f,seed,a.drnas,a.kissat,c["official_label"])
                check(o["status"]!="ERROR","Trial failed "+mode+":"+o["error"])
                outcomes.append({"mode":mode,"repetition":rep,**o})
                print("V132_MEASURE",a.shard,c["id"][:8],rep,mode,
                      o["status"],o["seconds"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"cohort":c["cohort"],
                     "label":c["official_label"],"prefix":t,
                     "prefix_s":pretime,"predicted_kissat_only":p,
                     "trials":outcomes})
        save(root/"rows.json",rows)
        f.unlink(missing_ok=True)
    check(len(rows)==len(cases),"Missing formula rows")
    print("V132_SHARD_PASS",a.shard,len(rows),flush=True)
def audit(a):
    m=load(a.manifest);check(m["protocol"]==P and len(m["cases"])==N,"Wrong protocol")
    src={c["id"]:c for c in m["cases"]}
    rows=[];bins=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"v132-shard-{shard}"/"results"
        meta=load(folder/"meta.json")
        expected=m["cases"][shard::SHARDS]
        check(meta["shard"]==shard and meta["ids"]==[c["id"] for c in expected],
              "Shard input drift")
        bins.add((meta["probe_sha256"],meta["drnas_sha256"],meta["kissat_sha256"]))
        part=load(folder/"rows.json");check(len(part)==len(expected),"Incomplete shard")
        rows.extend(part)
    check(len(rows)==N and len({r["id"] for r in rows})==N,
          "Wrong number of formulas")
    check(len(bins)==1,"Executables differ across shards")
    confusion=Counter();solved=Counter();costs=defaultdict(list);counts=Counter()
    for r in rows:
        check(r["id"] in src and src[r["id"]]["sha256"]==r["sha256"],
              "Formula provenance mismatch")
        t=r["prefix"]
        if t is not None:
            check(0<=t["v90_conflicts_256"]<=256,"Inconsistent prefix")
        check(r["predicted_kissat_only"]==predict(t),"Prediction not frozen")
        trials={(o["mode"],o["repetition"]):o for o in r["trials"]}
        check(len(trials)==4,"Missing paired trials")
        for mode in MODES:
            for rep in range(REPS):
                o=trials[(mode,rep)]
                check(o["status"] in LABELS+("TIMEOUT",) and not o["error"],
                      "Invalid paired status")
                check(o["status"]=="TIMEOUT" or o["status"]==r["label"],
                      "Wrong SAT/UNSAT label")
                solved[mode]+=int(o["status"]!="TIMEOUT")
                costs[mode].append(2*CAP if o["status"]=="TIMEOUT" else o["seconds"])
        kiss=sum(trials[("Kissat404",rep)]["status"]!="TIMEOUT" for rep in range(REPS))
        drnas=sum(trials[("DRNAS_Legacy",rep)]["status"]!="TIMEOUT" for rep in range(REPS))
        only=(kiss==2 and drnas==0)
        confusion["TP" if r["predicted_kissat_only"] and only else
                  "FP" if r["predicted_kissat_only"] and not only else
                  "FN" if only else "TN"]+=1
        counts["Kissat_only" if only else "DRNAS_only" if drnas==2 and kiss==0 else
               "Both" if drnas==2 and kiss==2 else "Neither" if drnas==0 and kiss==0
               else "Mixed"]+=1
        counts["predicted_positive"]+=int(r["predicted_kissat_only"])
        counts["prefix_exact"]+=int(t is not None and t["v90_conflicts_256"]==256)
        counts["prefix_early"]+=int(t is not None and t["v90_conflicts_256"]<256)
        counts["prefix_timeout"]+=int(t is None)
    tp,fp,fn,tn=(confusion[k] for k in ("TP","FP","FN","TN"))
    metrics={"precision":tp/(tp+fp) if tp+fp else None,
             "recall":tp/(tp+fn) if tp+fn else None,
             "specificity":tn/(tn+fp) if tn+fp else None,
             "balanced_accuracy":((tp/(tp+fn))+(tn/(tn+fp)))/2 if tp+fn and tn+fp else None}
    report={"protocol":P,"cases":N,"attempts":N*REPS*len(MODES),
      "rules":m["rule"],"scope":m["limits"],"confusion":dict(confusion),
      "metrics":metrics,"classes":dict(counts),
      "methods":{mode:{"solved":solved[mode],"total":N*REPS,
        "PAR2_s":round(statistics.mean(costs[mode]),6)} for mode in MODES},
      "rows":rows}
    save(a.out,report)
    lines=["# DRNAS V13.2 — Prospective pre-registered LBD4 signal validation","",
       "**Unnofficial diagnostic, not an integrated solver or world-record claim.**",
       f"{N} SHA-disjoint 2026 CNFs, {N*REPS*len(MODES)} matched solver trials, {CAP}s cap.",
       "Predicts Kissat-only class if first 256 conflict LBD4 fraction <0.20 and learned >=20.","",
       "| Metric | Value |","|---|---:|",
       f"| TP / FP / FN / TN | {tp} / {fp} / {fn} / {tn} |",
       f"| Predictions positive | {counts['predicted_positive']}/{N} |",
       f"| Strict prefix 256 | {counts['prefix_exact']}/{N} |",
       f"| Precision | {metrics['precision']} |",
       f"| Recall | {metrics['recall']} |","",
       "| Solver | Solved | PAR2 sec |","|---|---:|---:|"]
    for mode in MODES:
        d=report["methods"][mode];lines.append(f"| {mode} | {d['solved']}/{d['total']} | {d['PAR2_s']:.5f} |")
    lines+=["","Study only measures a correlation with solver outcomes, not a causal speedup."]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V132_AUDIT_PASS",N,dict(confusion),flush=True)
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    for q in ("prior131","prior_mini","prior100","scores","out"):
        f.add_argument("--"+q,required=True)
    r=sub.add_parser("run")
    for q in ("manifest","probe","drnas","kissat","out"):
        r.add_argument("--"+q,required=True)
    r.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for q in ("manifest","combined","out","md"): a.add_argument("--"+q,required=True)
    z=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(z),
     "run":lambda:run(z),"audit":lambda:audit(z)}[z.cmd]()
if __name__=="__main__":main()
