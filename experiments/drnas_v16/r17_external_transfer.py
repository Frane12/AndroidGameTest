#!/usr/bin/env python3
"""R17 external transfer on ORIGINAL previously-measured R150 CNFs.
Precommitted SHA-stratified 24 cases from existing official/catalogue and GBD
sources. Not new blind holdout. Native R17 C/Python audited, no CNF rewrite.
"""
import argparse,csv,gzip,hashlib,json,math,os,platform,random,statistics,sys
from pathlib import Path
from collections import defaultdict,Counter
sys.path.insert(0,"experiments/drnas_v16")
import r17_abstain_benchmark as b
from r11_restart_timing import run_one as execute,features,set_cpu_affinity,base
import r11_restart_timing as r11

OUT=Path("r17-external")
ORIGINAL=Path("r150/holdout")
FREEZE=OUT/"frozen"
PROTOCOL=Path("experiments/drnas_v16/r17_external_frozen_protocol.json")
MODES=("monitor","r11_2048_50","r16_live50","r17_agree50","r17_guarded50","original_kissat","stable_v1531")
CAP=15;REPS=2;SHARDS=4

def need(x,why):
    if not x:raise RuntimeError("R17_EXTERNAL_FAIL_CLOSED "+str(why))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def cfg():
    c=json.loads(PROTOCOL.read_text())
    need(c["protocol"]=="R17-external-transfer-reused-R150-SHA-20261105-v1","protocol drift")
    need(c["modes"]==list(MODES) and c["repeats"]==REPS and c["source_count"]==24
         and c["cap_seconds"]==CAP,"mode/cap drift")
    b.load_protocol()
    return c

def parse_original(src):
    # Non-mutating DIMACS parser: split clauses across lines without rewriting.
    n=declared=None;clauses=[];clause=[]
    with Path(src).open("rb") as f:
        for raw in f:
            line=raw.strip()
            if not line or line.startswith(b"c") or line.startswith(b"%"):continue
            if line.startswith(b"p "):
                tokens=line.split()
                need(n is None and len(tokens)==4 and tokens[1]==b"cnf","invalid original header")
                n=int(tokens[2]);declared=int(tokens[3])
                need(0<n<=1000000 and 0<declared<=1000000,"too many DIMACS vars or clauses")
                continue
            need(n is not None,"clauses before header")
            for token in line.split():
                lit=int(token)
                if lit:
                    need(0<abs(lit)<=n,"DIMACS literal outside declared vars")
                    clause.append(lit)
                else:
                    clauses.append(clause);clause=[]
                    need(len(clauses)<=declared,"too many clauses")
    need(n is not None and not clause and len(clauses)==declared,
         "incomplete/mismatched original DIMACS source")
    return n,clauses

def prepare():
    c=cfg()
    m=json.loads((ORIGINAL/"manifest.json").read_text())
    need(len(m["cases"])==55,"expected 55 R150 frozen originals")
    prior=b.history_shas()
    chosen=[]
    for cohort in c["cohorts"]:
        matches=sorted((x for x in m["cases"] if x["cohort"]==cohort),
                       key=lambda x:x["sha256"])
        need(len(matches)>=6,"missing frozen cohort "+cohort)
        taken=0
        for x in matches:
            if x["sha256"] in prior:continue
            src=ORIGINAL/x["id"]
            need(src.is_file() and sha(src)==x["sha256"],"source SHA mismatch")
            n,clauses=parse_original(src)
            need(n==x["variables"] and len(clauses)==x["clauses"],"declared CNF dimensions drift")
            chosen.append(dict(id=x["id"],cohort=cohort,sha256=x["sha256"],
                source_url=x["source_url"],source_catalog=x["source_catalog"],
                variables=n,clauses=len(clauses),bytes=src.stat().st_size))
            taken+=1
            if taken==6:break
        need(taken==6,"not enough independently hashed original CNFs "+cohort)
    need(len(chosen)==24 and len(set(x["sha256"] for x in chosen))==24,
         "frozen source count / duplicate hash")
    FREEZE.mkdir(parents=True,exist_ok=True)
    manifest=dict(protocol=c["protocol"],phase="FROZEN_FROM_EXISTING_R150_55_BEFORE_R17_TRANSFER",
        source_r150_sha256=sha(ORIGINAL/"manifest.json"),
        r16_history_sha256=sha(b.HISTORY),r17_protocol_sha256=sha(PROTOCOL),
        previously_measured_by_R150=True,
        new_native_transfer_solver_measurements=0,
        entries=chosen,source_splits=dict(Counter(x["cohort"] for x in chosen)))
    dump(FREEZE/"manifest.json",manifest)
    print("R17_EXTERNAL_FREEZE",json.dumps({k:v for k,v in manifest.items() if k!="entries"},sort_keys=True),flush=True)

def getcases():
    d=json.loads((FREEZE/"manifest.json").read_text())
    c=cfg()
    need(d["phase"]=="FROZEN_FROM_EXISTING_R150_55_BEFORE_R17_TRANSFER"
         and d["protocol"]==c["protocol"],"frozen source manifest drift")
    need(d["source_r150_sha256"]==sha(ORIGINAL/"manifest.json"),"source catalog changed")
    need(d["r16_history_sha256"]==sha(b.HISTORY)
         and d["r17_protocol_sha256"]==sha(PROTOCOL),"prior protocol drift")
    need(len(d["entries"])==24,"frozen 24 entries missing")
    cases=[]
    for item in d["entries"]:
        path=(ORIGINAL/item["id"]).resolve()
        need(sha(path)==item["sha256"],"original hash changed")
        n,clauses=parse_original(path)
        feature=features(clauses,n)
        cases.append(dict(path=path,formula=item["id"],n=n,clauses=clauses,
            formula_sha256=item["sha256"],expected="UNKNOWN",category=item["cohort"],
            metadata={"fold":"external_transfer","seed":int(item["sha256"][:10],16),
                      "features":feature,"cohort":item["cohort"]}))
    return cases

def run_one(case,rep,mode,runner):
    # r11 executor uses original CNF and re-checks SAT witness against all clauses.
    old={k:os.environ.get(k) for k in ("DRNAS_R16_GINI","DRNAS_R16_POLARITY","DRNAS_R13_N","DRNAS_R12_DEGREE_CV")}
    os.environ["DRNAS_R16_GINI"]=format(case["metadata"]["features"]["degree_gini"],".17g")
    os.environ["DRNAS_R16_POLARITY"]=format(case["metadata"]["features"]["polarity_imbalance"],".17g")
    os.environ["DRNAS_R13_N"]=str(case["n"])
    os.environ["DRNAS_R12_DEGREE_CV"]=format(case["metadata"]["features"]["degree_cv"],".17g")
    try:row,trace=execute(case,rep,mode,runner)
    finally:
        for k,v in old.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
    if mode in b.NEW_MODES:
        row,trace=b.independent_decision(case,mode,row,trace)
    if mode=="r16_live50":
        native=trace.get("early",{}).get("r16_event",{})
        if native:
            model=json.loads(b.MODEL.read_text())["models"]["trajectory"]["r11_2048_50"]
            x=b.r16.py_feature_vector(case,trace,model)
            expected=b.r16.score_from_features(model,x) if x else None
            selected=bool(expected is not None and case["n"]>=220 and expected>.25)
            need((native["selected"]=="1")==selected
              and expected is not None and abs(float(native["score"])-expected)<=.00002,
                 "R16 native score parity")
            if row["switch_at"]:need(selected and int(row["switch_at"])>=2048,"R16 illegal switch")
    return row,trace

def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    cfg();r11.CAP=CAP
    core=set_cpu_affinity()
    cases=getcases()
    cases=cases[shard::SHARDS]
    runner=os.environ.get("RUNNER_NAME","unknown")+" / core "+str(core)+"/ "+platform.processor()
    pins={str(x):sha(x) for x in (base.ORIGINAL,base.PATCHED,base.STABLE,b.MODEL,PROTOCOL)}
    rows=[];traces=[]
    folder=OUT/f"shard-{shard}";folder.mkdir(parents=True,exist_ok=True)
    for case in cases:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(case["metadata"]["seed"]+rep).shuffle(order)
            for mode in order:
                row,trace=run_one(case,rep,mode,runner)
                row["original_source_sha256"]=case["formula_sha256"]
                row["r17_source_cohort"]=case["metadata"]["cohort"]
                rows.append(row);traces.append(trace)
                print("R17_EXTERNAL_PAIRED",json.dumps({
                    "formula":case["formula"],"sha256":case["formula_sha256"],
                    "cohort":case["metadata"]["cohort"],"mode":mode,"repeat":rep,
                    "status":row["status"],"par2":row["par2_s"],
                    "switch":row["switch_at"],"error":row["error"]},sort_keys=True),flush=True)
                if row["error"]:raise RuntimeError("R17_EXTERNAL_NATIVE_ERROR "+row["error"])
    need(len(rows)==len(cases)*REPS*len(MODES),"expected complete shard attempts")
    with (folder/"measurements.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader();w.writerows(rows)
    (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
    dump(folder/"manifest.json",dict(protocol=cfg()["protocol"],
        runner=runner,shard=shard,rows=len(rows),cpu_affinity=sorted(os.sched_getaffinity(0)),
        source_sha256=sha(FREEZE/"manifest.json"),binary_sha256=pins,
        original_cnfs=[{"sha256":x["formula_sha256"],"id":x["formula"]}
                       for x in cases],source_commit=os.environ.get("GITHUB_SHA","local")))
    print("R17_EXTERNAL_SHARD_COMPLETE",shard,len(rows),flush=True)

def quantile(a,p):
    a=sorted(a);t=(len(a)-1)*p;lo=int(t)
    return a[lo]*(1-t+lo)+a[min(lo+1,len(a)-1)]*(t-lo)
def bootstrap(per,mode):
    rng=random.Random(170017)
    g=defaultdict(list)
    for p in per:g[p["cohort"]].append(p)
    vals=[]
    for _ in range(2500):
        chosen=[rng.choice(group) for group in g.values() for j in range(len(group))]
        baseline=sum(x["monitor"] for x in chosen)
        treatment=sum(x[mode] for x in chosen)
        vals.append(100*(baseline-treatment)/baseline if baseline else 0)
    return [round(quantile(vals,.025),6),round(quantile(vals,.975),6)]
def audit():
    c=cfg();original=getcases()
    identities={x["formula_sha256"] for x in original}
    rows=[];traces={};shards=[]
    for i in range(SHARDS):
        folder=Path("r17-external-download")/(f"r17-external-shard-{i}")
        m=json.loads((folder/"manifest.json").read_text())
        sub=list(csv.DictReader((folder/"measurements.csv").open()))
        t=[json.loads(x) for x in (folder/"traces.jsonl").read_text().splitlines()]
        need(m["protocol"]==c["protocol"] and m["shard"]==i,"artifact source mismatch")
        need(m["source_sha256"]==sha(FREEZE/"manifest.json"),"frozen input SHA drift")
        need(len(sub)==6*REPS*len(MODES) and len(t)==len(sub),"incomplete external shard")
        need(m["binary_sha256"][str(b.MODEL)]==sha(b.MODEL),"frozen model changed")
        for row in sub:
            need(not row["error"],"SAT / C parity ERROR")
            if row["status"]=="SAT":need(row["sat_model_checked"]=="True","bad SAT witness")
            need(row["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid SAT status")
            need(row["original_source_sha256"] in identities,"unexpected CNF")
            need(abs(float(row["par2_s"])-(2*CAP if row["status"]=="TIMEOUT" else float(row["wall_s"])))<1e-4,"PAR2 mismatch")
        for trow in t:
            key=(trow["category"],trow["formula"],str(trow["repeat"]),trow["mode"])
            need(key not in traces,"duplicate trace")
            traces[key]=trow
        rows.extend(sub);shards.append(dict(shard=i,runner=m["runner"],
            measurements_sha256=sha(folder/"measurements.csv"),
            traces_sha256=sha(folder/"traces.jsonl"),manifest_sha256=sha(folder/"manifest.json")))
    need(len(rows)==24*REPS*len(MODES) and len(traces)==len(rows),"incomplete external run")
    groups=defaultdict(dict)
    for row in rows:
        key=(row["formula"],row["repeat"])
        need(row["mode"] not in groups[key],"duplicate paired mode")
        groups[key][row["mode"]]=row
    need(len(groups)==48,"paired original CNF count")
    for key,ms in groups.items():
        need(set(ms)==set(MODES),"missing arm")
        need(len({v["runner"] for v in ms.values()})==1,"CPU runner mismatch")
        need(len({v["status"] for v in ms.values() if v["status"] in ("SAT","UNSAT")})<=1,
             "SAT/UNSAT mismatch")
        btrace={int(r["conflict"]):r for r in traces[(ms["monitor"]["category"],*key,"monitor")]["points"] if int(r["conflict"])<=1024}
        for mode in ("r11_2048_50","r16_live50","r17_agree50","r17_guarded50"):
            ttrace={int(r["conflict"]):r for r in traces[(ms[mode]["category"],*key,mode)]["points"] if int(r["conflict"])<=1024}
            need(set(ttrace)==set(btrace),"prefix checkpoint drift "+mode)
            for checkpoint in btrace:
                need(all(ttrace[checkpoint].get(f)==btrace[checkpoint].get(f)
                   for f in ("restarts","decisions","propagations","learned","glue","stable")),
                   "prefix counter mismatch")
    per=[]
    for case in original:
        by=[r for r in rows if r["formula"]==case["formula"]]
        need(len(by)==len(MODES)*REPS,"missing formula reps")
        cost={m:sum(float(x["par2_s"]) for x in by if x["mode"]==m) for m in MODES}
        per.append(dict(formula=case["formula"],sha256=case["formula_sha256"],
            cohort=case["metadata"]["cohort"],n=case["n"],**cost))
    summary={}
    for mode in MODES:
        total=sum(x[mode] for x in per);reference=sum(x["monitor"] for x in per)
        summary[mode]=dict(PAR2_s=round(total,6),
            gain_vs_monitor_pct=round(100*(reference-total)/reference,6),
            formula_bootstrap95_gain_pct=bootstrap(per,mode) if mode!="monitor" else [0,0],
            solved=sum(r["status"]!="TIMEOUT" for r in rows if r["mode"]==mode),
            wins2x=sum(x["monitor"]>2*x[mode] for x in per),
            regressions2x=sum(x[mode]>2*x["monitor"] for x in per))
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"paired_external.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(per[0]));w.writeheader();w.writerows(per)
    report=dict(protocol=c["protocol"],phase="EXTERNAL_ALREADY_USED_R150_TRANSFER_NOT_BLIND",
        formulas=24,attempts=len(rows),raw_shards=shards,summary=summary,
        preintervention_mismatches=0,original_CNF_unchanged=True,
        frozen_source_manifest_sha256=sha(FREEZE/"manifest.json"),
        R17_protocol_sha256=sha(b.RULE),
        warnings=["R150 previously measured these exact external formulas",
         "Source catalog labelled official is not an official SAT Competition ranking",
         "UNSAT has no independently certified LRAT",
         "This exploratory transfer cannot be used to fit the R17 gate or promote a solver"])
    dump(OUT/"report_external.json",report)
    print("R17_EXTERNAL_FINAL",json.dumps({k:v for k,v in report.items() if k!="raw_shards"},sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("step",choices=("freeze","run","audit"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    {"freeze":prepare,"run":lambda:run(args.shard),"audit":audit}[args.step]()
