#!/usr/bin/env python3
"""R148: frozen R135 policy equivalence + exploratory paired pilot on reused CNFs."""
import argparse,collections,csv,hashlib,json,os,pathlib,random,re,statistics,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r135_nonxor_portfolio as old

ROOT=pathlib.Path("r148")
PROTO="DRNAS-R148-EXACT-R135-FAST-NATIVE-DIAGNOSTIC-20261105-v1"
SOURCE_SHA="619665dd5f4ba6680b11200a63ac77ecc706c9897317b5452dbf22a82ef4b787"
FILTER=ROOT/"r148_selector"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
MODES=("kissat","cadical","r135","r148")
CATEGORIES=("official","external_application","external_xor","external_nonxor")
CAP=15.0;REPS=2;SHARDS=8

def need(ok,why):
    if not ok:raise RuntimeError("R148_AUDIT_REFUSED "+str(why))
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def write(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def sources():
    old.ROOT=ROOT
    old.KISSAT=KISSAT;old.CADICAL=CADICAL;old.CAP=CAP
    need(old.BINARY_THRESHOLD==0.30 and old.HORN_THRESHOLD==0.55,"R135 thresholds drifted")
    m,cases=old.read_sources()
    need(m==SOURCE_SHA and len(cases)==400,"not exact original R135 400 source")
    need(len({r["sha256"] for r in cases})==400,"duplicate CNF SHA")
    return cases

def native(src):
    start=time.perf_counter()
    p=subprocess.run([str(FILTER.resolve()),str(src.resolve())],capture_output=True,text=True,timeout=5)
    need(p.returncode==0,"selector failed "+str(src)+" "+p.stderr[-500:])
    line=next((s for s in p.stdout.splitlines() if s.startswith("c R148_SELECTOR ")),None)
    need(line,"missing selector telemetry "+str(src))
    f=dict(re.findall(r"([A-Za-z_]+)=([^\s]+)",line))
    need(f.get("route") in ("CADICAL","KISSAT"),"unrecognized native route")
    return f,round(time.perf_counter()-start,6)

def pilot_cases(cases):
    by={k:[] for k in CATEGORIES}
    for c in cases:
        need(c["cohort"] in by,"invalid source cohort "+str(c["cohort"]))
        by[c["cohort"]].append(c)
    for cat in CATEGORIES:need(len(by[cat])==100,"expected 100 originals per cohort")
    # PRECOMMITTED 25 per cohort, every fourth sorted SHA. NO runtime filtering.
    return sorted([x for cat in CATEGORIES for x in sorted(by[cat],key=lambda c:c["sha256"])[::4]],key=lambda c:c["sha256"])

def parity():
    need(FILTER.is_file(),"native selector not built")
    cases=sources();pilot=pilot_cases(cases)
    data=[];mismatch=[]
    for i,c in enumerate(cases):
        src=pathlib.Path(c["id"])
        need(sha(src)==c["sha256"],"CNF hash drift "+c["sha256"])
        target,reason,features,old_cost=old.choose(src)
        new,new_cost=native(src)
        row=dict(sha256=c["sha256"],cohort=c["cohort"],r135_target=target,
                 r135_reason=reason,r135_scan_s=old_cost,
                 r148_target=new["route"],r148_reason=new["reason"],r148_dispatch_s=new_cost,
                 native_full_scan=new["fully_scanned"])
        data.append(row)
        if target.upper()!=new["route"]:mismatch.append(row)
        if i%50==49:print("R148_PARITY_PROGRESS",i+1,"mismatches",len(mismatch),flush=True)
    report=dict(protocol=PROTO,source_manifest_sha256=SOURCE_SHA,formulas=len(data),
                pilot_formulas=len(pilot),full_route_agreement=len(mismatch)==0,
                mismatches=mismatch[:25],native_target_counts=dict(collections.Counter(r["r148_target"] for r in data)),
                r135_target_counts=dict(collections.Counter(r["r135_target"] for r in data)),
                r148_reason_counts=dict(collections.Counter(r["r148_reason"] for r in data)),
                old_scan_median_s=statistics.median(r["r135_scan_s"] for r in data),
                new_dispatch_median_s=statistics.median(r["r148_dispatch_s"] for r in data),
                old_scan_total_s=sum(r["r135_scan_s"] for r in data),
                new_dispatch_total_s=sum(r["r148_dispatch_s"] for r in data),
                status="PASS" if not mismatch else "FAIL",
                caveat="Retrospective route parity, NOT new blind SAT performance or UNSAT proof")
    write(ROOT/"parity.json",report)
    with (ROOT/"parity.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    print("R148_FULL_400_DECISION_PARITY",json.dumps({k:v for k,v in report.items() if k not in ("mismatches",)},sort_keys=True),flush=True)
    need(not mismatch,"native R148 mismatches R135; DO NOT benchmark")

def run_one(src,mode,rep):
    if mode!="r148":return old.invoke(src,mode,rep)
    st=time.perf_counter()
    gate,probe_s=native(src)
    route=gate["route"]
    cmd=[str((KISSAT if route=="KISSAT" else CADICAL).resolve()),str(src.resolve())]
    elapsed=time.perf_counter()-st
    status="TIMEOUT";proof="timeout"
    if elapsed<CAP:
        try:
            p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP-elapsed)
            elapsed=time.perf_counter()-st
            need(p.returncode in (10,20),"invalid backend exit "+str(p.returncode)+" "+p.stderr[-100:].decode(errors="replace"))
            if elapsed<CAP:
                status="SAT" if p.returncode==10 else "UNSAT"
                if status=="SAT":
                    old.witness.check_original_sat(p.stdout,src)
                    proof="source_SAT_witness_verified"
                else:proof="UNSAT_without_independent_LRAT_proof"
        except subprocess.TimeoutExpired:elapsed=CAP
    elapsed=min(elapsed,CAP)
    return dict(mode="r148",repeat=rep,status=status,seconds=round(elapsed,6),
                par2=30.0 if status=="TIMEOUT" else round(elapsed,6),proof=proof,
                selector_target=route.lower(),selector_reason=gate["reason"],selector_cost_s=probe_s,
                binary_ratio=float(gate["binary_fraction"]),horn_ratio=float(gate["horn_fraction"]),
                fully_scanned=gate["fully_scanned"]=="1")

def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    need(FILTER.is_file() and KISSAT.is_file() and CADICAL.is_file(),"missing pinned binaries")
    cases=pilot_cases(sources())
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    pins={str(p):sha(p) for p in (FILTER,KISSAT,CADICAL)}
    pins["source_python_sha256"]=sha("research/r135_nonxor_portfolio.py")
    cpu=next((v for v in pathlib.Path("/proc/cpuinfo").read_text().splitlines() if v.startswith("model name")),"unknown")
    rows=[]
    for i,c in enumerate(cases):
        if i%SHARDS!=shard:continue
        src=pathlib.Path(c["id"]);need(sha(src)==c["sha256"],"input SHA drift")
        target,*_=old.choose(src);new,_=native(src)
        need(target.upper()==new["route"],"parity drift on trial input")
        for rep in range(REPS):
            order=list(MODES);random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            votes=set()
            for mode in order:
                result=run_one(src,mode,rep)
                row=dict(protocol=PROTO,source_manifest_sha256=SOURCE_SHA,shard=shard,
                         id=c["id"],cohort=c["cohort"],sha256=c["sha256"],**result)
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"]);need(len(votes)==1,"SAT/UNSAT disagreement")
                print("R148_PAIRED",json.dumps(row,sort_keys=True),flush=True)
                write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,source_manifest_sha256=SOURCE_SHA,
                                                      runner_cpu=cpu,pinned_sha256=pins,rows=rows))
    need(len(rows)==len(cases[shard::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("R148_SHARD_PASS",shard,len(rows),flush=True)

def audit():
    cases=pilot_cases(sources());bysha={x["sha256"]:x for x in cases}
    parity_report=json.loads((ROOT/"parity.json").read_text())
    need(parity_report["status"]=="PASS" and parity_report["formulas"]==400,"400-route parity not certified")
    shards=[json.loads((ROOT/f"shard-{i}.json").read_text()) for i in range(SHARDS)]
    need(all(x["protocol"]==PROTO and x["source_manifest_sha256"]==SOURCE_SHA for x in shards),"manifest/protocol drift")
    need(len({json.dumps(x["pinned_sha256"],sort_keys=True) for x in shards})==1,"pinned binary mismatch")
    rows=[r for sh in shards for r in sh["rows"]]
    need(len(rows)==len(cases)*REPS*len(MODES),"not 800 paired measurements")
    idx={}
    for r in rows:
        need(r["sha256"] in bysha and r["cohort"]==bysha[r["sha256"]]["cohort"],"case outside pilot")
        need(r["mode"] in MODES and r["repeat"] in range(REPS),"bad mode/repeat")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"unknown status")
        need(abs(r["par2"]-(30 if r["status"]=="TIMEOUT" else r["seconds"]))<1e-4,"PAR2 mismatch")
        if r["status"]=="SAT":need(r["proof"]=="source_SAT_witness_verified","missing SAT witness")
        if r["status"]=="UNSAT":need(r["proof"]=="UNSAT_without_independent_LRAT_proof","UNSAT proof tier")
        key=(r["sha256"],r["repeat"],r["mode"])
        need(key not in idx,"duplicate paired row");idx[key]=r
    need(len(idx)==800,"missing unique pairs")
    for c in cases:
        for rep in range(REPS):
            ss={idx[(c["sha256"],rep,m)]["status"] for m in MODES}-{"TIMEOUT"}
            need(len(ss)<=1,"SAT UNSAT contradiction")
            a=idx[(c["sha256"],rep,"r135")]["selector_target"]
            b=idx[(c["sha256"],rep,"r148")]["selector_target"]
            need(a==b,"post-measure routing mismatch")
    stats={}
    for m in MODES:
        a=[r for r in rows if r["mode"]==m]
        stats[m]=dict(attempts=len(a),solved=sum(r["status"]!="TIMEOUT" for r in a),
                      SAT=sum(r["status"]=="SAT" for r in a),UNSAT_unverified=sum(r["status"]=="UNSAT" for r in a),
                      timeout=sum(r["status"]=="TIMEOUT" for r in a),PAR2_s=round(sum(r["par2"] for r in a),6),
                      scan_median_s=round(statistics.median(r["selector_cost_s"] for r in a),6) if m in ("r135","r148") else None)
    report=dict(protocol=PROTO,source_manifest_sha256=SOURCE_SHA,formula_count=len(cases),measurements=len(rows),
                source_400_sha_distinct=True,full_400_decision_parity=True,cohorts={k:25 for k in CATEGORIES},
                report_type="RETROSPECTIVE_DIAGNOSTIC_REUSED_400_NOT_BLIND",
                summary=stats,change_R148_vs_R135_PAR2_s=round(stats["r135"]["PAR2_s"]-stats["r148"]["PAR2_s"],6),
                Kissat_gain_R148_pct=round(100*(stats["kissat"]["PAR2_s"]/stats["r148"]["PAR2_s"]-1),6),
                independent_UNSAT_proof=False,verdict="NO_PROMOTION_UNTIL_INDEPENDENT_UNSAT_CERTIFICATION")
    write(ROOT/"report.json",report)
    fieldnames=sorted({k for r in rows for k in r})
    with (ROOT/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader();w.writerows(rows)
    print("R148_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=("parity","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    {"parity":parity,"run":lambda:run(a.shard),"audit":audit}[a.action]()
