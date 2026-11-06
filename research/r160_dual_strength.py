#!/usr/bin/env python3
"""R160: preregistered sequential, single-core dual-strength solver portfolio.

The two published R159 spotlight formulas are DEVELOPMENT ONLY; the other 22
formulas form a transfer set from an earlier R151 corpus, not globally blind.
No file names, case SHA or family is ever used to select a solver or a budget.
V15.3.1 native C++ source is never modified. No claims of faster DRNAS core.
"""
import argparse,csv,hashlib,json,os,platform,random,resource,signal,subprocess,sys,time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0,"experiments/drnas_v16")
import r17_external_transfer as ext
from r11_restart_timing import base,set_cpu_affinity

ROOT=Path("r160")
SOURCE=Path("r159-r151-source/holdout")
OLD=Path("r159-reused/r159/frozen/manifest.json")
FREEZE=ROOT/"frozen"/"manifest.json"
CAP=8.0
REPS=3
SHARDS=4
MODES=("drnas","cadical","portfolio100","portfolio250")
PROTO="R160-ONECORE-SEQUENTIAL-DUAL-20261106-v1"
DRNAS=Path("/tmp/drnas-r6-v1531")
KISSAT=Path("/tmp/kissat-r6-original/build/kissat")
CADICAL=Path("built/bin/cadical_3_0_1")
CA_SHA="c9ddc4b19d6b78ffbb837cd9a9fc3ffd5e1004ed057b15441b0cfb372f3b9cd7"
FOCUS=("official2026-006.cnf","cryptography-001.cnf")

def need(c,s):
    if not c: raise RuntimeError("R160_FAIL_CLOSED: "+s)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""): h.update(b)
    return h.hexdigest()
def dump(p,o):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(o,indent=2,sort_keys=True)+"\n")
def csvread(p):
    with Path(p).open(newline="") as f:return list(csv.DictReader(f))
def csvwrite(p,rs):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    keys=list(dict.fromkeys(k for x in rs for k in x))
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rs)

def freeze():
    src=json.loads((SOURCE/"manifest.json").read_text())
    prior=json.loads(OLD.read_text())
    need(len(src["cases"])==40 and len(prior["cases"])==16,"wrong input corpus size")
    need(prior["phase"]=="FIXED_BEFORE_R159_SOLVES","R159 old freeze drift")
    lookup={x["id"]:x for x in src["cases"]}
    need(len(lookup)==40,"duplicate input IDs")
    entries=[];used=set()
    for x in prior["cases"]:
        y=lookup.get(x["id"])
        need(y is not None and y["sha256"]==x["sha256"],"R159 SHA differs")
        entries.append(y);used.add(x["sha256"])
    cohorts=("official2026","official2025","miter","cryptography")
    for group in cohorts:
        options=sorted((x for x in src["cases"] if x["cohort"]==group
            and x["sha256"] not in used and x["variables"]<=5000
            and x["bytes"]<=5000000 and x["clauses"]<=250000),
            key=lambda x:(x["variables"],x["sha256"]))
        need(len(options)>=2,"insufficient transfer cases "+group)
        entries.extend(options[:2]);used.update(x["sha256"] for x in options[:2])
    need(len(entries)==24 and len(used)==24,"bad 24 case freeze")
    for x in entries:
        p=SOURCE/x["id"]
        need(p.is_file() and sha(p)==x["sha256"],"original byte SHA mismatch "+x["id"])
        n,cls=ext.parse_original(p)
        need(n==x["variables"] and len(cls)==x["clauses"],"DIMACS full parse mismatch")
    obj=dict(protocol=PROTO,original_formulas=24,repetitions=REPS,cap_seconds=CAP,
        selected_before_R160_timings=True,
        already_seen_R159_formulas=16,additional_not_in_R159_formulas=8,
        globally_unseen=False,source_run=42094754907,old_R159_audit_run=42134974748,
        source_sha256=sha(SOURCE/"manifest.json"),old_sha256=sha(OLD),
        primary_policy="portfolio100",secondary_diagnostic="portfolio250",
        schedule="one CPU; DRNAS first for max 100 ms, if unsolved remaining to CaDiCaL",
        no_identity_based_routing=True,focus_development=list(FOCUS),
        all_others_exploratory_transfer_not_globally_blind=True,
        modes=list(MODES),cases=[dict(x,split=("spotlight_development" if x["id"] in FOCUS else "transfer")) for x in entries])
    dump(FREEZE,obj)
    print("R160_FROZEN",json.dumps({"count":24,"sha":sha(FREEZE),"focus":list(FOCUS)}),flush=True)

def cases(shard):
    m=json.loads(FREEZE.read_text())
    need(m["protocol"]==PROTO and m["original_formulas"]==24 and len(m["cases"])==24,"freeze protocol")
    need(m["source_sha256"]==sha(SOURCE/"manifest.json") and m["old_sha256"]==sha(OLD),"corpus changed")
    out=[]
    for x in m["cases"][shard::SHARDS]:
        p=SOURCE/x["id"]
        need(sha(p)==x["sha256"],"SHA changed "+x["id"])
        n,cls=ext.parse_original(p)
        need(n==x["variables"] and len(cls)==x["clauses"],"DIMACS drift")
        out.append(dict(path=p.resolve(),formula=x["id"],n=n,clauses=cls,
            formula_sha256=x["sha256"],category=x["cohort"],split=x["split"],
            expected="UNKNOWN"))
    need(len(out)==6,"incomplete shard")
    return out

def stage(command,case,budget):
    need(budget>0,"nonpositive budget")
    t=time.perf_counter()
    p=subprocess.Popen(command,text=True,errors="replace",stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,start_new_session=True)
    try:
        out,err=p.communicate(timeout=budget)
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
    except subprocess.TimeoutExpired:
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        out,err=p.communicate()
        status="TIMEOUT"
    wall=time.perf_counter()-t
    payload=None
    for line in out.splitlines():
        if line.startswith("DRNAS_HYBRID_RESULT\t"):
            payload=json.loads(line.split("\t",1)[1])
    if payload:status=payload.get("status","ERROR").upper()
    error=""
    if status=="SAT" and base.check_witness(case,out,payload) is not True:
        error="INVALID_OR_MISSING_SAT_WITNESS"
    if status not in ("SAT","UNSAT","TIMEOUT"):
        error="EXIT_ERROR "+str(p.returncode)+" "+err[-200:]
    return dict(status=status,wall=wall,exit=p.returncode,error=error,
        checked=(status=="SAT" and not error),stdout=out)

def run_case(case,rep,mode,runner):
    begin=time.perf_counter()
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    cmd_d=[str(DRNAS),str(case["path"]),str(KISSAT),"1"]
    cmd_c=[str(CADICAL.resolve()),str(case["path"])]
    first=None;second=None
    if mode=="drnas":first=stage(cmd_d,case,CAP)
    elif mode=="cadical":first=stage(cmd_c,case,CAP)
    else:
        tiny=0.100 if mode=="portfolio100" else 0.250
        first=stage(cmd_d,case,tiny)
        if first["status"]=="TIMEOUT" and not first["error"]:
            remaining=CAP-(time.perf_counter()-begin)
            if remaining>0.025:
                second=stage(cmd_c,case,remaining)
    chosen=second or first
    total=time.perf_counter()-begin
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
    error=first["error"] or (second["error"] if second else "")
    status=chosen["status"] if not error else "ERROR"
    route=("cadical_fallback" if second else
           "drnas_first" if mode.startswith("portfolio") else mode)
    return dict(formula=case["formula"],sha256=case["formula_sha256"],
        cohort=case["category"],split=case["split"],repeat=rep,mode=mode,
        status=status,wall_s=round(total,6),cpu_s=round(cpu,6),
        par2_s=round(total,6) if status in ("SAT","UNSAT") else 2*CAP,
        first_stage_wall_s=round(first["wall"],6),
        fallback_stage_wall_s=round(second["wall"],6) if second else "",
        route=route,runner=runner,checked=(chosen["checked"] if status=="SAT" else ""),
        unsat_certificate=False,error=error)

def run(shard):
    need(0<=shard<SHARDS,"bad shard")
    core=set_cpu_affinity()
    need(sha(CADICAL)==CA_SHA,"CaDiCaL 3.0.1 binary drift")
    need(DRNAS.is_file() and KISSAT.is_file(),"pinned native DRNAS/Kissat missing")
    runner=os.getenv("RUNNER_NAME","unknown")+"/cpu"+str(core)+"/"+platform.processor()
    result=[]
    for case in cases(shard):
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(case["formula_sha256"][:12],16)+rep+160).shuffle(order)
            for mode in order:
                r=run_case(case,rep,mode,runner)
                result.append(r)
                print("R160_MEASURE",case["formula"],rep,mode,r["status"],
                    r["wall_s"],r["route"],flush=True)
                need(not r["error"],"solver error "+str(r))
            statuses={x["status"] for x in result if x["formula"]==case["formula"]
                and x["status"] in ("SAT","UNSAT")}
            need(len(statuses)<=1,"contradiction on source case")
    folder=ROOT/f"shard-{shard}";folder.mkdir(parents=True,exist_ok=True)
    csvwrite(folder/"results.csv",result)
    dump(folder/"manifest.json",dict(protocol=PROTO,shard=shard,
        entries=len(result),runner=runner,freeze_sha=sha(FREEZE),
        binary_sha={"drnas":sha(DRNAS),"kissat":sha(KISSAT),"cadical":sha(CADICAL)},
        commit=os.getenv("GITHUB_SHA","local"),cases=[x["formula_sha256"] for x in cases(shard)]))
    need(len(result)==72,"wrong shard count")
    print("R160_SHARD_PASS",shard,flush=True)

def audit():
    manifest=json.loads(FREEZE.read_text())
    entries=[];metas=[]
    for shard in range(SHARDS):
        folder=Path("r160-download")/f"r160-shard-{shard}"
        x=json.loads((folder/"manifest.json").read_text())
        rows=csvread(folder/"results.csv")
        need(x["protocol"]==PROTO and x["freeze_sha"]==sha(FREEZE),"wrong shard provenance")
        need(len(rows)==72 and x["entries"]==72 and x["shard"]==shard,"partial shard")
        for r in rows:
            need(not r["error"] and r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad mode result")
            need(r["runner"]==x["runner"],"runner mismatch")
            need(r["checked"]=="True" if r["status"]=="SAT" else True,"SAT witness invalid")
            need(abs(float(r["par2_s"])-(16.0 if r["status"]=="TIMEOUT" else float(r["wall_s"])))<0.0001,
                "PAR-2 accounting error")
        entries+=rows;metas.append(x)
    need(len(entries)==288,"missing paired trials")
    grp=defaultdict(dict)
    for r in entries:
        k=(r["formula"],int(r["repeat"]))
        need(r["mode"] not in grp[k],"duplicate mode in pair")
        grp[k][r["mode"]]=r
    need(len(grp)==72 and all(set(g)==set(MODES) for g in grp.values()),"incomplete paired arms")
    for g in grp.values():
        need(len({r["runner"] for r in g.values()})==1,"unpaired CPU runner")
        need(len({r["status"] for r in g.values() if r["status"] in ("SAT","UNSAT")})<=1,
            "contradictory outcomes")
    summary={}
    for mode in MODES:
        rr=[r for r in entries if r["mode"]==mode]
        summary[mode]=dict(solved=sum(r["status"] in ("SAT","UNSAT") for r in rr),
            par2_s=round(sum(float(r["par2_s"]) for r in rr),6),
            fallback=sum(r["route"]=="cadical_fallback" for r in rr),
            timeout=sum(r["status"]=="TIMEOUT" for r in rr))
    focal={}
    for name in FOCUS:
        focal[name]={mode:dict(solved=sum(r["status"] in ("SAT","UNSAT") for r in entries
            if r["formula"]==name and r["mode"]==mode),
            wall_s=[float(r["wall_s"]) for r in entries if r["formula"]==name and r["mode"]==mode])
            for mode in MODES}
    transfer=[r for r in entries if r["split"]=="transfer"]
    transfer_stats={mode:dict(solved=sum(r["status"] in ("SAT","UNSAT") for r in transfer if r["mode"]==mode),
        par2_s=round(sum(float(r["par2_s"]) for r in transfer if r["mode"]==mode),6))
        for mode in MODES}
    result=dict(protocol=PROTO,status="AUDIT_PASS",measurements=len(entries),
        original_formulas=24,known_focus=2,other_formulas=22,
        reused_R151_not_globally_blind=True,
        known_formulas_not_used_as_proof_of_generalization=True,
        primary="portfolio100",summary=summary,focus=focal,transfer=transfer_stats,
        binary_shas=[x["binary_sha"] for x in metas],
        source_sha256=sha(FREEZE),
        independent_UNSAT_certificate=False)
    dump(ROOT/"report"/"report.json",result)
    csvwrite(ROOT/"report"/"all_results.csv",entries)
    print("R160_FINAL "+json.dumps({k:result[k] for k in
        ("status","summary","focus","transfer")},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("step",choices=("freeze","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    {"freeze":freeze,"run":lambda:run(a.shard),"audit":audit}[a.step]()
