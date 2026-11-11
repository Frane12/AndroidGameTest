#!/usr/bin/env python3
"""DRNAS BLOCKER-BLIND100-R3.

100 unseen source SHA formulas: 20 families x five new indices 30..34.
One logical CPU per solver; 3 matched repetitions; 8s E2E cap.
A native vs BLOCKER native vs pinned Kissat reference; no profile, no
per-decision trace in performance builds. Native SAT original CNF verified;
UNSAT is reported but independently uncertified.
"""
import hashlib,json,os,pathlib,subprocess,time,collections
import drnas_atlas_wide500 as W

SHARD=int(os.environ.get("BLOCKER_BLIND_SHARD","0"))
assert 0<=SHARD<5
REPS=3
CAP=8.0
ARMS=("A","BLOCKER","KISSAT")
ROOT=pathlib.Path("mre_blocker_blind100")
ROOT.mkdir(exist_ok=True)
BINS={"A":ROOT/"bin/drnas_base","BLOCKER":ROOT/"bin/drnas_blocker",
      "KISSAT":ROOT/"bin/kissat"}

def frozen_sources():
    old_train=json.loads(pathlib.Path("research/atlas_wide500_memory.json").read_text())
    old_prospect=json.loads(pathlib.Path("research/atlas_prospective_v1_summary.json").read_text())
    old_sha=set(old_train["train_samples"])|set(old_prospect["source_sha"])
    corpus=W.source_corpus(limit=35)
    i=30+SHARD
    selection=[]
    for category in W.SOURCES+W.SYNTH:
        if category in corpus:
            n,clauses,sha,entry=corpus[category][i]
            source="original_satlib"
        else:
            n,clauses=W.synth_one(category,i)
            sha=hashlib.sha256(W.canonical(n,clauses)).hexdigest()
            entry=f"generated:{category}:{i}"
            source="deterministic_synthetic"
        if sha in old_sha:raise AssertionError("source SHA previously used in training or prospective eval")
        selection.append(dict(category=category,index=i,n=n,clauses=clauses,
            source=source,entry=entry,sha256=sha))
    if len(selection)!=20 or len({x["sha256"] for x in selection})!=20:
        raise AssertionError("source count/duplicates on shard")
    return selection

def decode_sat_model(output,n):
    model={}
    for line in output.splitlines():
        if line.startswith("v "):
            for word in line.split()[1:]:
                try:v=int(word)
                except ValueError:continue
                if v and abs(v)<=n:
                    model[abs(v)]=v>0
    return model

def run_one(case,arm,rep):
    cnf=ROOT/f"source_{SHARD}.cnf"
    cnf.write_bytes(W.canonical(case["n"],case["clauses"]))
    binpath=BINS[arm].resolve()
    command=([str(binpath),str(cnf.resolve()),"--mode","A","--time",str(CAP)]
             if arm!="KISSAT" else [str(binpath),str(cnf.resolve())])
    start=time.monotonic()
    try:
        p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,timeout=CAP+0.5,check=False)
        code=p.returncode;out=p.stdout;err=p.stderr
    except subprocess.TimeoutExpired:
        code=-9;out="";err="external_timeout"
    elapsed=round(time.monotonic()-start,6)
    if code not in (0,10,20,-9):
        raise RuntimeError(f"Solver process failure: arm={arm} SHA={case['sha256']} exit={code} {err[-600:]}")
    status={10:"SAT",20:"UNSAT_UNCERTIFIED"}.get(code,"UNKNOWN")
    model=decode_sat_model(out,case["n"]) if status=="SAT" else {}
    sat_verified=(status=="SAT" and len(model)==case["n"] and
        all(any(model.get(abs(lit))==(lit>0) for lit in clause)
            for clause in case["clauses"]))
    if status=="SAT" and not sat_verified:
        raise AssertionError("Invalid SAT original witness "+arm+" "+case["sha256"])
    meta={}
    if arm!="KISSAT":
        for line in out.splitlines():
            if line.startswith("ATLASMAP2_TRIAL "):
                meta=dict(item.split("=",1) for item in line.split()[1:] if "=" in item)
        if code in (10,20) and not meta:
            raise AssertionError("Missing native E2E telemetry "+arm+" "+case["sha256"])
    return {"arm":arm,"rep":rep,"status":status,
        "SAT_original_verified":bool(sat_verified),"UNSAT_independent_LRAT":False,
        "E2E_s":elapsed,
        "PAR2_reported_s":elapsed if status in ("SAT","UNSAT_UNCERTIFIED") else 2*CAP,
        "PAR2_verified_s":elapsed if sat_verified else 2*CAP,
        "decisions":int(meta.get("decisions",0)),
        "conflicts":int(meta.get("conflicts",0)),
        "propagations":int(meta.get("propagations",0)),
        "watch_visits":int(meta.get("watch_visits",0)),
        "learned":int(meta.get("learned",0)),
        "source_sha256":case["sha256"],"source":case["source"],
        "category":case["category"],"index":case["index"]}

def summarize(rows):
    result={}
    for arm in ARMS:
        selected=[r for r in rows if r["arm"]==arm]
        result[arm]={"trials":len(selected),
           "SAT_original_verified":sum(x["SAT_original_verified"] for x in selected),
           "UNSAT_reported_uncertified":sum(x["status"]=="UNSAT_UNCERTIFIED" for x in selected),
           "UNKNOWN":sum(x["status"]=="UNKNOWN" for x in selected),
           "E2E_s":round(sum(x["E2E_s"] for x in selected),6),
           "PAR2_reported_s":round(sum(x["PAR2_reported_s"] for x in selected),6),
           "PAR2_verified_s":round(sum(x["PAR2_verified_s"] for x in selected),6),
           "decisions":sum(x["decisions"] for x in selected),
           "conflicts":sum(x["conflicts"] for x in selected),
           "watch_visits":sum(x["watch_visits"] for x in selected)}
    return result

def main():
    cases=frozen_sources()
    manifest=[{k:v for k,v in c.items() if k!="clauses"} for c in cases]
    (ROOT/f"manifest_{SHARD}.json").write_text(json.dumps(manifest,indent=2,sort_keys=True))
    print("BLOCKER_BLIND100_SOURCES "+json.dumps({"shard":SHARD,"source_count":len(cases),
        "original_satlib":sum(c["source"]=="original_satlib" for c in cases),
        "synthetic":sum(c["source"]=="deterministic_synthetic" for c in cases),
        "reps":REPS,"arms":ARMS,"cap_s":CAP,"one_logical_cpu":True,
        "unseen_sha":True},sort_keys=True),flush=True)
    rows=[]
    for case in cases:
        for rep in range(REPS):
            result={}
            for arm in ARMS:
                row=run_one(case,arm,rep)
                rows.append(row);result[arm]=row
                print("BLOCKER_BLIND100_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
            # Independently verified SAT across arms must not conflict with
            # reported UNSAT on same source; flag a solver soundness problem.
            statuses={x["status"] for x in result.values()}
            if "SAT" in statuses and "UNSAT_UNCERTIFIED" in statuses:
                raise AssertionError("Solver SAT/UNSAT contradiction: "+case["sha256"])
    summary=summarize(rows)
    (ROOT/f"audit_{SHARD}.json").write_text(json.dumps({"shard":SHARD,
        "sources":manifest,"rows":rows,"summary":summary,
        "no_profile_or_trace":True,"one_cpu":True,
        "UNSAT_independent_LRAT":False},indent=2))
    print("BLOCKER_BLIND100_FINAL "+json.dumps({"shard":SHARD,
        "summary":summary,"sources":len(cases),"repetitions":REPS},sort_keys=True),flush=True)

def merge(directory):
    reports=[json.loads((directory/f"audit_{i}.json").read_text()) for i in range(5)]
    rows=sum((a["rows"] for a in reports),[])
    sources=sum((a["sources"] for a in reports),[])
    if len(sources)!=100 or len({s["sha256"] for s in sources})!=100:
        raise AssertionError("not exactly 100 SHA distinct original sources")
    categories=collections.Counter(s["category"] for s in sources)
    if len(categories)!=20 or any(count!=5 for count in categories.values()):
        raise AssertionError("not five sources in each of twenty categories")
    if sum(s["source"]=="original_satlib" for s in sources)!=25:
        raise AssertionError("wrong original-source balance")
    if len(rows)!=900:
        raise AssertionError("not exactly 900 trials")
    pairs=collections.defaultdict(dict)
    for r in rows:
        key=(r["source_sha256"],r["rep"])
        if r["arm"] in pairs[key]:
            raise AssertionError("duplicated arm on same source and repeat")
        pairs[key][r["arm"]]=r
    if len(pairs)!=300 or any(set(v)!=set(ARMS) for v in pairs.values()):
        raise AssertionError("non-matched pairs")
    for p in pairs.values():
        statuses={v["status"] for v in p.values()}
        if "SAT" in statuses and "UNSAT_UNCERTIFIED" in statuses:
            raise AssertionError("cross-arm model contradiction")
    original=json.loads(pathlib.Path("research/atlas_wide500_memory.json").read_text())
    previous=json.loads(pathlib.Path("research/atlas_prospective_v1_summary.json").read_text())
    old=set(original["train_samples"])|set(previous["source_sha"])
    if set(s["sha256"] for s in sources)&old:
        raise AssertionError("prospective/training SHA overlap")
    family={}
    for category in categories:
        subset=[r for r in rows if r["category"]==category]
        family[category]=summarize(subset)
    basic=summarize(rows)
    ratio=(basic["A"]["PAR2_reported_s"]/
           basic["BLOCKER"]["PAR2_reported_s"])
    report={"experiment":"BLOCKER-BLIND100-R3",
        "source_count":100,"repetitions":REPS,"attempts":900,
        "families":20,"source_original_satlib":25,"source_synthetic":75,
        "original_sha_disjoint":True,"one_logical_cpu":True,"cap_s":CAP,
        "UNSAT_independent_LRAT":False,"profile_trace_disabled":True,
        "summary":basic,"PAR2_reported_A_over_BLOCKER":round(ratio,5),
        "categories":family,"source_sha256":[s["sha256"] for s in sources]}
    pathlib.Path("research/drnas_blocker_blind100_r3_summary.json").write_text(
        json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("BLOCKER_BLIND100_MERGED "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    import argparse
    a=argparse.ArgumentParser()
    a.add_argument("--merge-dir")
    options=a.parse_args()
    if options.merge_dir:merge(pathlib.Path(options.merge_dir))
    else:main()
