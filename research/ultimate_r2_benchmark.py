#!/usr/bin/env python3
"""Ultimate R2 preregistered R153->certified GF2/CDCL integration test.

8 earlier original controls + 12 source-SHA-disjoint official 2026 originals.
5 modes * 2 repeats * 20 sources = 200 attempts, 5 CPU-paired shards.
New-to-Ultimate-R1, NOT globally unseen. No tuning after benchmark outcomes.
"""
import argparse, collections, csv, hashlib, json, os, pathlib, random
import re, signal, subprocess, sys, tempfile, time, platform
import ultimate_r1_benchmark as prior
import r195_dualkeep_real_benchmark as official
import r188_feedback_benchmark as helper
import ultimate_r2_fallback as bridge

ROOT=pathlib.Path("ultimate_r2")
FROZEN=ROOT/"frozen"
R1=pathlib.Path("ultimate_r1")
PROTO="DRNAS-ULTIMATE-R2-20261107-ORIGINAL-R153-TO-CERTIFIED-IPASIRUP-v1"
MODES=("r1a","r153","r2_clean","r2_shadow","r2_live")
REPS=2;SHARDS=5;NEW=12;DEV=8;CAP_DEV=20.;CAP_NEW=30.
OLD_MANIFEST=R1/"frozen"/"manifest.json"
R153=R1/"source_r153"/"r153"
REF=R1/"ultimate-dispatch"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
FALLBACK=pathlib.Path("research/ultimate_r2_fallback.py")
def need(x,msg):
    if not x: raise RuntimeError("ULTIMATE_R2_AUDIT_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def put(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def get(p):return json.loads(pathlib.Path(p).read_text())
def cpu():
    for l in pathlib.Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
        if l.startswith("model name"):return l.split(":",1)[1].strip()
    return platform.processor() or "unknown"
def selftest():
    need(len(MODES)==5 and DEV==8 and NEW==12 and SHARDS==5 and REPS==2,"protocol")
    with tempfile.TemporaryDirectory() as t:
        f=pathlib.Path(t)/"s.cnf"
        # Full x xor y=1 plus a residual clause and harmless repetition.
        f.write_text("p cnf 3 102\n1 2 0\n-1 -2 0\n1 3 0\n"+"1 3 0\n"*99)
        yes,_=bridge.cheap_probe(f)
        need(yes,"complete source parity prefix not detected")
    # DIMACS regression: source complete parity across 2..6 widths and formatting.
    for width in (2, 3, 4, 5, 6):
        with tempfile.TemporaryDirectory() as t:
            f=pathlib.Path(t)/"wide.cnf"
            clauses=[" ".join(str(-v if mask>>i&1 else v)
                             for i,v in enumerate(range(1,width+1)))+" 0"
                     for mask in range(1<<width) if mask.bit_count()%2==0]
            header="c "+"x"*350+"\n"+f"p cnf {width} {len(clauses)}\n"
            for body in ("\n".join(clauses), " ".join(clauses),
                         "\n".join(c.replace(" 0","\n 0") for c in clauses)):
                f.write_text(header+body+"\n")
                need(bridge.cheap_probe(f)[0],f"width-{width} wrapped DIMACS missed")
            f.write_text(header+"\n".join(clauses[:-1])+"\n")
            need(not bridge.cheap_probe(f)[0],f"width-{width} incomplete parity accepted")
    # On Linux, expensive full-source proof work must be preemptible.
    if hasattr(signal,"setitimer"):
        try:
            with bridge.preparation_budget(0.005): time.sleep(0.030)
        except bridge.PreparationBudgetExceeded:
            pass
        else:
            need(False,"preparation budget failed to preempt")
    print("ULTIMATE_R2_SELFTEST_PASS",flush=True)
def freeze():
    old_cases=get(OLD_MANIFEST)["cases"]
    need(len(old_cases)==45 and len({c["sha256"] for c in old_cases})==45,
         "R1 source benchmark not frozen")
    historical=[c for c in old_cases if c["cohort"]=="historical_r153_r195"]
    need(len(historical)==25,"historic count")
    # Precommit SHA-order selection of development controls, including one
    # designated prior R194 positive case. No result-dependent selection.
    preferred=next(c for c in historical if c["id"]==prior.R194_ID)
    rng=sorted((c for c in historical if c["id"]!=preferred["id"]),
               key=lambda x:hashlib.sha256((PROTO+x["sha256"]).encode()).hexdigest())
    selected=[preferred]+rng[:DEV-1]
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    allsha={c["sha256"] for c in old_cases};allids={c["id"] for c in old_cases}
    for c in selected:
        src=R1/"frozen"/(c["id"]+".cnf")
        need(sha(src)==c["sha256"],"historic SHA drift")
        (FROZEN/(c["id"]+".cnf")).write_bytes(src.read_bytes())
        cases.append(dict(id=c["id"],sha256=c["sha256"],cohort="development",
            source=c["source"],expected=c.get("expected","UNKNOWN"),cap_s=CAP_DEV,
            family=c.get("family","historical")))
    lines=official.download_bytes(official.URI,150000,14).decode("ascii").splitlines()
    urlset=sorted(set(x.strip() for x in lines if re.fullmatch(
        r"https?://benchmark-database\.de/file/[a-f0-9]{32}",x.strip())),
        key=lambda u:hashlib.sha256((PROTO+u).encode()).hexdigest())
    need(len(urlset)>100,"official source index unavailable")
    fetches=[];accepted=0
    for url in urlset:
        if accepted==NEW or len(fetches)>=150:break
        ident=url.split("/")[-1]
        if ident in allids:continue
        try:
            raw=official.decode_cnf(official.download_bytes(url,official.MAX_COMPRESSED,14))
            d=hashlib.sha256(raw).hexdigest()
            need(d not in allsha,"source SHA overlap with Ultimate R1")
            need(d not in {c["sha256"] for c in cases},"duplicate new SHA")
            # Precommitted byte bound, not chosen using solver outcomes.
            need(0<len(raw)<=12_000_000,"outside deterministic byte envelope")
            header=re.search(rb"(?m)^p\s+cnf\s+(\d+)\s+(\d+)\s*$",raw[:8192])
            need(header is not None,"original DIMACS header missing")
            need(0<int(header[1])<=150000 and 0<=int(header[2])<=160000,
                 "original outside R166x native parser bounds")
            (FROZEN/(ident+".cnf")).write_bytes(raw)
            cases.append(dict(id=ident,sha256=d,cohort="new_to_r1",
                source=url,expected="UNKNOWN",cap_s=CAP_NEW,family="official2026"))
            fetches.append(dict(id=ident,source_sha256=d,accepted=True))
            accepted+=1
            print("ULTIMATE_R2_FREEZE_ACCEPT",ident,d,flush=True)
        except Exception as exc:
            fetches.append(dict(id=ident,accepted=False,reason=str(exc)[:90]))
    need(accepted==NEW,"insufficient untested source SHA originals; fail closed")
    need(len(cases)==DEV+NEW and len({c["sha256"] for c in cases})==len(cases),"case duplicate")
    random.Random(PROTO).shuffle(cases)
    put(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
        provenance_run=42344094697,provenance_manifest_sha=sha(OLD_MANIFEST),
        original_source_unchanged=True,new_to_r1=True,globally_blind=False,
        source_selected_before_results=True,reps=REPS,modes=MODES,
        retrievals=fetches))
    verify()
    print("ULTIMATE_R2_FREEZE_PASS",json.dumps(dict(sources=len(cases),
        new=NEW,development=DEV,attempts=len(cases)*REPS*len(MODES),
        manifest_sha=sha(FROZEN/"manifest.json"))),flush=True)
def verify():
    d=get(FROZEN/"manifest.json")
    need(d["protocol"]==PROTO and d["provenance_manifest_sha"]==sha(OLD_MANIFEST),
         "source provenance changed")
    cs=d["cases"]
    need(len(cs)==DEV+NEW and len({c["sha256"] for c in cs})==DEV+NEW,
         "source count/sha collision")
    need(collections.Counter(c["cohort"] for c in cs)==
         {"development":DEV,"new_to_r1":NEW},"cohort drift")
    for c in cs:
        need(c["cap_s"]==(CAP_DEV if c["cohort"]=="development" else CAP_NEW),"cap drift")
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"source file drift "+c["id"])
    return cs
def run_one(src,mode,cap,sha0):
    args=[str(R153.resolve()),str(src.resolve()),str((KISSAT if mode=="r153"
          else REF if mode=="r1a" else FALLBACK).resolve())]
    env=os.environ.copy()
    env.update(ULTIMATE_CAP_S=str(cap),ULTIMATE_SEED="11",ULTIMATE_PARITY="0",
       ULTIMATE_R2_MODE=mode.removeprefix("r2_"),
       ULTIMATE_R2_DEADLINE_NS=str(time.monotonic_ns()+int(cap*1e9)))
    t=time.perf_counter()
    p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env=env,start_new_session=True)
    watchdog=False
    try:out,err=p.communicate(timeout=cap)
    except subprocess.TimeoutExpired:
        watchdog=True;os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
    elapsed=time.perf_counter()-t
    if not watchdog and p.returncode not in (0,10,20):
        need(False,f"solver/process failure {mode} rc={p.returncode}: "+
             err[-900:].decode(errors="replace"))
    if watchdog or elapsed>=cap:
        status="TIMEOUT"
    elif p.returncode==10:status="SAT"
    elif p.returncode==20:status="UNSAT"
    elif p.returncode==0 and (b"ULTIMATE_R2_TIMEOUT" in out or
           b"R166X_RESULT mode=" in out or b"R182_STATUS status=TIMEOUT" in out):
        status="TIMEOUT"
    else:
        need(False,f"native execution error {mode}: {p.returncode} "+err[-900:].decode(errors="replace"))
    gate=re.search(rb"ULTIMATE_R2_GATE (\{[^\r\n]+\})",out)
    gate=json.loads(gate[1]) if gate else {}
    if mode.startswith("r2_") and b"R28_ROUTE fallback" in out and not gate:
        need(False,"missing r2 GF2-CDCL fallback telemetry")
    if gate:need(gate["source_sha256"]==sha0,"source source SHA telemetry drift")
    res=re.search(rb"R166X_RESULT ([^\r\n]+)",out)
    counters=dict(re.findall(rb"(\w+)=([^\s]+)",res[1])) if res else {}
    parsed={k.decode():v.decode(errors="replace") for k,v in counters.items()}
    if gate and mode.startswith("r2_"):
        expected_native=("gauss_cooldown" if mode=="r2_live" and gate.get("eligible")
                         else "clean")
        if parsed.get("mode") is not None:
            need(parsed["mode"]==expected_native,
                 f"native mode mismatch: expected {expected_native}, got {parsed['mode']}")
        elif status!="TIMEOUT":
            need(False,"native result telemetry missing for completed R2 fallback")
    return status,elapsed,out,gate,parsed,watchdog
def model(out):
    truth={}
    for line in out.decode(errors="replace").splitlines():
        if not line.startswith("v "):continue
        for v in map(int,line[2:].split()):
            if not v:continue
            need(abs(v) not in truth or truth[abs(v)]==(v>0),"contradictory SAT witness")
            truth[abs(v)]=v>0
    need(truth,"missing original SAT model")
    return truth
def trial(c,rep,mode):
    src=FROZEN/(c["id"]+".cnf");need(sha(src)==c["sha256"],"source SHA")
    status,elapsed,out,gate,native,watchdog=run_one(src,mode,c["cap_s"],c["sha256"])
    proof="CAP"
    if status=="SAT":
        helper.gf.sat_check(helper.gf.dimacs(src)[1],model(out))
        proof="SAT_WITNESS_CHECKED_ORIGINAL_SHA"
    elif status=="UNSAT":
        if b"R28_ROUTE certified_xor_contradiction" in out:
            need(prior.replay_gf2_unsat(src,out),"R153 GF2 contradiction failed replay")
            proof="GF2_UNSAT_ORIGINAL_REPLAY"
        else: proof="NATIVE_UNSAT_NO_INDEPENDENT_LRAT"
    if c["expected"] in ("SAT","UNSAT") and status!="TIMEOUT":
        need(status==c["expected"],"known source SAT/UNSAT mismatch")
    return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
        family=c["family"],mode=mode,rep=rep,cap_s=c["cap_s"],
        status=status,elapsed_s=round(min(elapsed,c["cap_s"]),6),
        par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
        proof=proof,cpu=cpu(),watchdog=watchdog,
        r2_gate=gate, native_mode=native.get("mode"),
        native_reasons=native.get("reason_clauses_completed"),
        native_proposals=native.get("direct_proposals"),
        native_conflicts=native.get("conflicts"))
def shard(i):
    cases=verify();need(0<=i<SHARDS,"bad shard")
    pin=get(ROOT/"build-pin.json")
    for path,s in pin["binaries"].items():need(sha(path)==s,"binary SHA drift "+path)
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]
    for c in cases[i::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                z=trial(c,rep,mode);rows.append(z)
                put(ROOT/f"shard-{i}.json",rows)
                print("ULTIMATE_R2_TRIAL",json.dumps({k:z[k] for k in
                  ("id","cohort","mode","rep","status","elapsed_s","par2_s",
                   "native_mode","native_reasons","r2_gate")},sort_keys=True),flush=True)
    need(len(rows)==len(cases[i::SHARDS])*REPS*len(MODES),"short shard")
    print("ULTIMATE_R2_SHARD_PASS",i,len(rows),flush=True)
def audit():
    cases=verify(); rows=[]
    for i in range(SHARDS):
        data=get(ROOT/f"shard-{i}.json")
        need(len(data)==len(cases[i::SHARDS])*REPS*len(MODES),"missing shard "+str(i))
        rows.extend(data)
    need(len(rows)==(DEV+NEW)*REPS*len(MODES),"incomplete trial count")
    blocks=collections.defaultdict(dict);orig={c["sha256"]:c for c in cases}
    for r in rows:
        c=orig.get(r["sha256"])
        need(c and r["id"]==c["id"] and r["cohort"]==c["cohort"],"source identity mismatch")
        key=(r["sha256"],r["rep"])
        need(r["mode"] not in blocks[key],"duplicate paired mode")
        blocks[key][r["mode"]]=r
        need(abs(r["par2_s"]-(2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]))<1e-5,"PAR2 mismatch")
        if r["status"]=="SAT":need(r["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL_SHA","SAT unchecked")
        if r["proof"]=="GF2_UNSAT_ORIGINAL_REPLAY":need(r["status"]=="UNSAT","GF2 proof wrong")
    for arms in blocks.values():
        need(set(arms)==set(MODES),"missing arm")
        need(len({r["cpu"] for r in arms.values()})==1,"different CPU within pair")
        need(len({r["status"] for r in arms.values() if r["status"]!="TIMEOUT"})<=1,"contradictory solver result")
    report={}
    for cohort in ("all","development","new_to_r1"):
        group=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
        report[cohort]={}
        for mode in MODES:
            sample=[r for r in group if r["mode"]==mode]
            report[cohort][mode]=dict(n=len(sample),solved=sum(r["status"]!="TIMEOUT" for r in sample),
              sat=sum(r["status"]=="SAT" for r in sample),
              unsat=sum(r["status"]=="UNSAT" for r in sample),
              par2_s=round(sum(r["par2_s"] for r in sample),6),
              live_selected=sum(r["r2_gate"].get("eligible",False) and r["mode"]=="r2_live" for r in sample),
              live_activated=sum(r["mode"]=="r2_live" and r["native_mode"]=="gauss_cooldown" for r in sample),
              native_result_missing=sum(r["mode"]=="r2_live" and r["r2_gate"].get("eligible",False)
                                        and r["native_mode"] is None for r in sample),
              derived_rows=sum(r["r2_gate"].get("derived_rows",0) for r in sample),
              delivered_reasons=sum(int(r["native_reasons"] or 0) for r in sample))
    comparisons={}
    for ref,cand in (("r1a","r2_live"),("r2_clean","r2_live"),("r2_shadow","r2_live"),("r153","r2_live")):
        delta=[(arms[ref]["par2_s"]-arms[cand]["par2_s"]) for arms in blocks.values()]
        comparisons[cand+"_vs_"+ref]=dict(wins=sum(x>0.005 for x in delta),
            losses=sum(x<-.005 for x in delta),ties=sum(abs(x)<=.005 for x in delta),
            par2_gain_s=round(sum(delta),6))
    result=dict(status="ULTIMATE_R2_SOURCE_PAIRED_AUDIT_PASS_NOT_GLOBAL_BLIND",
        sources=DEV+NEW,original_SHA_verified=True,
        source_disjoint_to_r1=NEW,globally_blind=False,attempts=len(rows),
        two_way_ipasirup="R166x native reasons available only on confirmed live paths",
        generated_unit_and_row_proofs_replayed=True,models_checked_original=True,
        independent_LRAT_for_native_UNSAT=False,
        non_active_control="r2_shadow: certified-preparation-only; clean native CDCL, no shadow row scanning",
        source_provenance_sha=sha(FROZEN/"manifest.json"),
        results=report,comparisons=comparisons)
    put(ROOT/"report.json",result);put(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader()
        for r in rows:
            z=dict(r);z["r2_gate"]=json.dumps(z["r2_gate"],sort_keys=True);w.writerow(z)
    with (ROOT/"summary.md").open("w") as fh:
        fh.write("# Ultimate R2 — source-certified GF2 / CDCL experiment\n\n")
        fh.write("12 official original CNFs new to R1; eight development controls; 2 repeats; 5 arms = 200 trials. Not globally blind.\n\n")
        fh.write("| Cohort | Arm | Solved | PAR2 (s) | Live selected | Native confirmed | Missing native telemetry | Reason clauses |\n|---|---|---:|---:|---:|---:|---:|---:|\n")
        for cohort,x in report.items():
            for mode,v in x.items():fh.write(f"| {cohort} | {mode} | {v['solved']}/{v['n']} | {v['par2_s']} | {v['live_selected']} | {v['live_activated']} | {v['native_result_missing']} | {v['delivered_reasons']} |\n")
        fh.write("\n"+json.dumps(comparisons,indent=2)+"\n\nSAT models checked against unchanged originals. No independent native LRAT.\n")
    print("ULTIMATE_R2_FINAL",json.dumps(dict(status=result["status"],results=report,
          comparisons=comparisons),sort_keys=True),flush=True)
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    a.add_argument("--shard",type=int,default=0);x=a.parse_args()
    {"selftest":selftest,"freeze":freeze,"verify":lambda:print("ULTIMATE_R2_VERIFY_PASS",len(verify()),flush=True),
     "shard":lambda:shard(x.shard),"audit":audit}[x.action]()
