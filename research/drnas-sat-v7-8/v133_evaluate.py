#!/usr/bin/env python3
"""V13.3 fixed-rule evaluation on 36 constructive + 6 frozen official-2026 CNFs.

Diagnostic, not a competitive score. Six families are generated without using
solver outcomes; the official 2026 six are source-disjoint from V13.1 but were
already used in V13.2. Distinguish synthetic and previously measured cohorts.
"""
import argparse,hashlib,json,os,random,statistics,time
from pathlib import Path
from collections import Counter,defaultdict
import v133_constructive_formulas as construct
import v132_lbd4_prospective as predecessor
import official_shortlong_select as source
import official_2026_mini_sim as mini

PROTOCOL="DRNAS-V133-FIXED-LBD4-SIX-FAMILIES-AND-2026-PILOT-20261101"
SHARDS=6;N_SYNTH=36;N_OFFICIAL=6;REPS=2;CAP=12.0
MODES=("DRNAS_Legacy","Kissat404")
mini.CAP=CAP;mini.MEMORY_GIB=3
source.RAW_CAP=96*1024**2;source.CNF_CAP=96*1024**2
source.VARIABLE_CAP=1000000;source.CLAUSE_CAP=4000000

def check(cond,msg):
    if not cond:raise RuntimeError(msg)
def load(path):return json.loads(Path(path).read_text())
def save(path,x):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def frozen(a):
    prev=load(a.previous)
    check(prev["protocol"]==predecessor.P and len(prev["cases"])==6,
          "Unexpected previous six-case manifest")
    synthetic=[construct.make(f,i)[0] for i in range(6)
               for f in construct.FAMILIES]
    official=[{"id":c["id"],"source":"official2026_prior_pilot",
               "official_label":c["official_label"],"sha256":c["sha256"],
               "original_cohort":c["cohort"],"features":c["features"]}
              for c in prev["cases"]]
    check(len(synthetic)==36 and len(official)==6,"Wrong frozen sizes")
    check(len({x["sha256"] for x in synthetic+official})==42,
          "SHA collision or overlap")
    # Interleave six old official cases with all six constructively defined families
    # to distribute the 42 formulas reproducibly across 6 parallel shards.
    seq=[]
    for i in range(6):
        seq.extend(x for x in synthetic if x["index"]==i)
        seq.append(official[i])
    check(len(seq)==42,"Wrong scheduled size")
    save(a.out,{"protocol":PROTOCOL,"cases":seq,"shards":SHARDS,
        "reps":REPS,"cap_seconds":CAP,"prefix_limit_s":14.0,
        "prior_frozen_manifest_sha256":sha(a.previous),
        "fixed_rule":{"feature":"fraction of learned clauses with LBD <= 4 at exact conflict 256",
                      "strictly_less_than":0.20,"minimum_learned":20,
                      "target":"Kissat-only: 2 successes vs 0 DRNAS successes"},
        "cohorts":{"constructive_new":36,"official2026_prior_pilot":6},
        "warnings":[
            "Synthetic formulas have constructive mathematical truth; not official 2026.",
            "Six official 2026 formulas were already attempted in V13.2; not fresh holdout.",
            "The LBD rule is unchanged from V13.2; first-256 CaDiCaL probe uses separate run.",
            "No training or rejection by current solver outcomes.",
            "PAR2 below uses a 12 s timeout, 3 GiB, and two repetitions.",
            "SAT witness for constructive SAT checked directly; UNSAT based on pigeonhole / parity proof.",
            "No independent proof certificates of solver outputs; labels crosschecked.",
            "Not a solver speedup or official SAT Competition score."]})
    print("V133_FREEZE_PASS",len(seq),flush=True)
def selftest():
    construct.selftest()
    predecessor.selftest()
    check(SHARDS==6 and CAP==12.0 and REPS==2,"Bad fixed settings")
    print("V133_SELFTEST_PASS",flush=True)
def run(a):
    m=load(a.manifest)
    check(m["protocol"]==PROTOCOL and 0<=a.shard<SHARDS,"Wrong frozen protocol")
    subset=m["cases"][a.shard::SHARDS]
    check(len(subset)==7,"Wrong shard size")
    allowed=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(allowed)})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cpu=next((l.split(":",1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
             if l.startswith("model name")),"unknown")
    save(out/"meta.json",{"protocol":PROTOCOL,"shard":a.shard,
         "case_ids":[c["id"] for c in subset],"cpu":cpu,
         "bin_sha256":{v:sha(getattr(a,v)) for v in ("probe","drnas","kissat")}})
    rows=[]
    for c in subset:
        path=out/(hashlib.sha256(c["id"].encode()).hexdigest()[:20]+".cnf")
        if c["source"]=="synthetic":
            recomputed,raw=construct.make(c["family"],c["index"])
            check(recomputed==c,"Generator source drift")
            path.write_bytes(raw)
        else:
            details=source.download_and_features(c["id"],path)
            check(details["sha256"]==c["sha256"] and
                  details["features"]==c["features"],"Official CNF drift")
        check(sha(path)==c["sha256"],"CNF checksum mismatch")
        t,prefix_elapsed=predecessor.prefix(a.probe,path,int(c["sha256"][:8],16))
        pred=predecessor.predict(t)
        trials=[]
        for rep in range(REPS):
            seed=(1332026+1009*rep+int(c["sha256"][:8],16))%(2**32)
            modes=list(MODES);random.Random(seed^133).shuffle(modes)
            for mode in modes:
                x=mini.trial(mode,path,seed,a.drnas,a.kissat,c["official_label"])
                check(x["status"]!="ERROR",f"Solver trial error: {c['id']} {mode} {x['error']}")
                trials.append({"mode":mode,"repetition":rep,**x})
                print("V133_TRIAL",a.shard,c["id"],mode,rep,x["status"],
                      x["seconds"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"source":c["source"],
                     "family":c.get("family","official2026_prior_pilot"),
                     "label":c["official_label"],"predicted_kissat_only":pred,
                     "prefix":t,"prefix_wall_s":prefix_elapsed,"trials":trials})
        save(out/"rows.json",rows)
        path.unlink(missing_ok=True)
    check(len(rows)==7,"Incomplete shard")
    print("V133_SHARD_PASS",a.shard,len(rows),flush=True)

def summarize(rows):
    groups=defaultdict(list)
    for r in rows:
        groups["all"].append(r)
        groups["constructive" if r["source"]=="synthetic" else "official2026_prior_pilot"].append(r)
        groups[r["family"]].append(r)
    summary={}
    for name,v in groups.items():
        conf=Counter();classes=Counter();solved=Counter();costs=defaultdict(list)
        for r in v:
            t=r["prefix"];check(r["predicted_kissat_only"]==predecessor.predict(t),
                               "Rule mutated")
            pairs={(o["mode"],o["repetition"]):o for o in r["trials"]}
            check(len(pairs)==4,"Missing mode/repetition")
            for mode in MODES:
                for rep in range(REPS):
                    o=pairs[(mode,rep)]
                    check(o["status"] in ("SAT","UNSAT","TIMEOUT") and
                          not o["error"],"Invalid solver status")
                    check(o["status"]=="TIMEOUT" or o["status"]==r["label"],
                          "Wrong SAT/UNSAT answer")
                    solved[mode]+=int(o["status"]!="TIMEOUT")
                    costs[mode].append(2*CAP if o["status"]=="TIMEOUT" else o["seconds"])
            kiss=sum(pairs["Kissat404",i]["status"]!="TIMEOUT" for i in (0,1))
            drnas=sum(pairs["DRNAS_Legacy",i]["status"]!="TIMEOUT" for i in (0,1))
            only=kiss==2 and drnas==0
            classes["Kissat_only" if only else "DRNAS_only" if drnas==2 and kiss==0 else
                    "Both" if kiss==2 and drnas==2 else "Neither" if kiss==0 and drnas==0
                    else "Mixed"]+=1
            conf["TP" if only and r["predicted_kissat_only"] else
                 "FP" if r["predicted_kissat_only"] else
                 "FN" if only else "TN"]+=1
            classes["positive"]+=int(r["predicted_kissat_only"])
            classes["exact256"]+=int(t is not None and t["v90_conflicts_256"]==256)
            classes["early"]+=int(t is not None and t["v90_conflicts_256"]<256)
            classes["probe_timeout"]+=int(t is None)
        tp,fp,fn,tn=(conf[k] for k in ("TP","FP","FN","TN"))
        summary[name]={
          "formulas":len(v),"classes":dict(classes),"confusion":dict(conf),
          "precision":tp/(tp+fp) if tp+fp else None,
          "recall":tp/(tp+fn) if tp+fn else None,
          "solvers":{m:{"solved":solved[m],"attempts":len(v)*2,
                       "par2_s":round(statistics.mean(costs[m]),6)} for m in MODES}}
    return summary

def audit(a):
    m=load(a.manifest);check(m["protocol"]==PROTOCOL,"Wrong audit input")
    rows=[];bins=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"v133-shard-{shard}"
        meta=load(folder/"meta.json")
        part=load(folder/"rows.json")
        expected=m["cases"][shard::SHARDS]
        check(meta["protocol"]==PROTOCOL and meta["shard"]==shard and
              meta["case_ids"]==[c["id"] for c in expected],"Wrong shard provenance")
        check(len(part)==7 and [x["id"] for x in part]==[x["id"] for x in expected],
              "Wrong shard cases")
        bins.add(json.dumps(meta["bin_sha256"],sort_keys=True))
        rows.extend(part)
    check(len(bins)==1,"Different executable SHA across runners")
    check(len(rows)==42 and len({r["sha256"] for r in rows})==42,"Incomplete sample")
    index={c["id"]:c for c in m["cases"]}
    for row in rows:
        c=index[row["id"]]
        check(row["sha256"]==c["sha256"] and row["label"]==c["official_label"],
              "Input identity mismatch")
    summ=summarize(rows)
    check(summ["all"]["formulas"]==42 and
          summ["constructive"]["formulas"]==36 and
          summ["official2026_prior_pilot"]["formulas"]==6,
          "Missing required cohort")
    save(a.out,{"protocol":PROTOCOL,"source_manifest_sha256":sha(a.manifest),
                "comparison":"fixed preexisting V13.2 rule, no tuning",
                "warnings":m["warnings"],"summary":summ,"rows":rows})
    lines=["# DRNAS V13.3 — pre-locked LBD4 signal across constructive SAT families","",
       "**Unofficial diagnostic. Synthetic truth is constructive; 2026 six cases were previously measured.**",
       "42 cases, 168 paired solver attempts, 12s cap, 3GiB per attempt, one CPU pinned.",
       "Rule unchanged: LBD4/learned < 0.20 with learned >=20 at exact conflict 256.",""]
    for name in ("all","constructive","official2026_prior_pilot")+construct.FAMILIES:
        d=summ[name];c=d["confusion"];cl=d["classes"]
        lines +=[f"## {name} — {d['formulas']} formulas","",
         "| Solver | Solved | PAR2 s |","|---|---:|---:|"]
        for mode in MODES:
            z=d["solvers"][mode]
            lines.append(f"| {mode} | {z['solved']}/{z['attempts']} | {z['par2_s']:.5f} |")
        lines +=["",f"TP={c.get('TP',0)}, FP={c.get('FP',0)}, FN={c.get('FN',0)}, TN={c.get('TN',0)}.",
                f"Predicted positives: {cl.get('positive',0)}. Exact 256: {cl.get('exact256',0)}.",
                ""]
    lines += ["## Limitations"]+["- "+w for w in m["warnings"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("V133_AUDIT_PASS",len(rows),json.dumps(summ["all"]),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    for k in ("previous","out"):f.add_argument("--"+k,required=True)
    r=sub.add_parser("run")
    for k in ("manifest","probe","drnas","kissat","out"):r.add_argument("--"+k,required=True)
    r.add_argument("--shard",type=int,required=True)
    au=sub.add_parser("audit")
    for k in ("manifest","combined","out","md"):au.add_argument("--"+k,required=True)
    a=p.parse_args()
    {"selftest":selftest,"freeze":lambda:frozen(a),"run":lambda:run(a),
     "audit":lambda:audit(a)}[a.cmd]()
if __name__=="__main__":main()
