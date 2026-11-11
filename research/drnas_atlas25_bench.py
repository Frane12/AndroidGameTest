#!/usr/bin/env python3
"""ATLAS25 paired NONBLIND replay of the exact 12 frozen ATLAS22/23 SATLIB SHA.

One logical CPU per arm, 12s wall-time cap, two seeds, verified SAT witnesses.
UNSAT is NEVER claimed certified without independent proof. No training on this
replay cohort and no modification of source CNFs or reference outcomes.
"""
import argparse,hashlib,json,pathlib,resource,subprocess,sys,time
sys.path.insert(0,"research")
import drnas_atlas22_mid_hard as S
import drnas_atlas21_official as B
import drnas_atlas_wide500 as W

CAP=12.0
OUT=pathlib.Path("mre_atlas25");OUT.mkdir(exist_ok=True)
ARMS=("A","C7_ADAPT","C23_RECENT","C24_GUARD","C25_REUSE3K","C25_REUSE6K","KISSAT","CMS")
FIELDS=("decisions","conflicts","propagations","watch_visits","atlas15_deleted",
        "atlas15_minimized","atlas16_compactions","atlas16_maxrss_kb",
        "atlas16_clause_alloc_bytes","atlas25_mode","atlas25_reason_uses",
        "atlas25_protected","atlas25_deleted","atlas25_high_cycles",
        "atlas25_low_cycles")

def sources():
    corp=W.source_corpus(limit=10)
    ss=[]
    for family in S.FAMILIES:
        for idx in range(6,10):
            n,clauses,sha,entry=corp[family][idx]
            raw=W.canonical(n,clauses)
            assert hashlib.sha256(raw).hexdigest()==sha
            path=OUT/f"{family}_{idx}.cnf"
            path.write_bytes(raw)
            ss.append(dict(id=len(ss),sha256=sha,archive_entry=entry,
                family=family,source_kind="SATLIB_normalized_original",
                bytes=len(raw),path=str(path)))
    assert len(ss)==12 and len({s["sha256"] for s in ss})==12
    (OUT/"manifest.json").write_text(json.dumps(ss,indent=2))
    print("ATLAS25_SOURCES "+json.dumps(ss),flush=True)
    return ss

def run(s,arm,rep):
    path=s["path"]
    assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()==s["sha256"]
    if arm=="KISSAT":
        cmd=["mre_atlas21/bin/kissat",path]
    elif arm=="CMS":
        cmd=["cryptominisat5","--threads=1","--verb=0",path]
    else:
        cmd=["mre_atlas21/bin/drnas_atlas21",path,"--mode",arm,
             "--time",str(CAP),"--seed",str(rep+1)]
        if arm!="A":cmd+=["--policy","1.0,0.85"]
    def limit():
        resource.setrlimit(resource.RLIMIT_CPU,(32,33))
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    t=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP,
                         preexec_fn=limit)
        rc,out,err=p.returncode,p.stdout,p.stderr
    except subprocess.TimeoutExpired:
        rc,out,err=124,"","timeout"
    elapsed=round(time.monotonic()-t,6)
    if rc not in (0,10,20,124,-9,-24,-25,15,-15):
        raise RuntimeError(f"ATLAS25 solver crash {arm} rc={rc} {err[-700:]}")
    sat=rc==10 and B.model_ok(path,out)
    if rc==10 and not sat:
        raise RuntimeError("ATLAS25 invalid SAT witness on original CNF "+arm)
    status="SAT_VERIFIED" if sat else "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN"
    stats={}
    for line in out.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            stats=dict(x.split("=",1) for x in line.split()[1:] if "=" in x)
    telemetry={k:int(float(stats.get(k) or 0)) for k in FIELDS}
    return dict(sha256=s["sha256"],source_id=s["id"],arm=arm,rep=rep,status=status,
       E2E_s=elapsed,PAR2_reported_s=elapsed if rc in (10,20) else 2*CAP,
       PAR2_verified_s=elapsed if sat else 2*CAP,
       independent_UNSAT=False,telemetry=telemetry)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true")
    args=parser.parse_args()
    ss=sources()
    rows=[]
    for s in (ss[:1] if args.smoke else ss):
        for rep in range(1 if args.smoke else 2):
            statuses=set()
            for arm in ARMS:
                r=run(s,arm,rep);rows.append(r)
                print("ATLAS25_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
                if r["status"]!="UNKNOWN":statuses.add(r["status"])
            assert not ("SAT_VERIFIED" in statuses and
                        "UNSAT_UNVERIFIED" in statuses),"SAT/UNSAT contradiction"
    document=dict(sources=ss[:1] if args.smoke else ss,rows=rows,
        cap_s=CAP,cohort="SATLIB_ATLAS22_23_24_NONBLIND_REPLAY",
        independent_UNSAT=False,one_logical_cpu=True)
    (OUT/("smoke.json" if args.smoke else "pilot.json")).write_text(
        json.dumps(document,indent=2))
    summary={}
    for arm in ARMS:
        ar=[r for r in rows if r["arm"]==arm]
        summary[arm]=dict(
           trials=len(ar),
           verified_SAT=sum(r["status"]=="SAT_VERIFIED" for r in ar),
           uncertified_UNSAT=sum(r["status"]=="UNSAT_UNVERIFIED" for r in ar),
           solved_verified=sum(r["status"]=="SAT_VERIFIED" for r in ar),
           E2E_s=round(sum(r["E2E_s"] for r in ar),4),
           PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in ar),4),
           PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in ar),4),
           deleted=sum(r["telemetry"]["atlas15_deleted"] for r in ar),
           reason_uses=sum(r["telemetry"]["atlas25_reason_uses"] for r in ar),
           protected=sum(r["telemetry"]["atlas25_protected"] for r in ar),
           high_cycles=sum(r["telemetry"]["atlas25_high_cycles"] for r in ar),
           low_cycles=sum(r["telemetry"]["atlas25_low_cycles"] for r in ar),
           rss_peak_kb=max((r["telemetry"]["atlas16_maxrss_kb"] for r in ar),default=0),
           clause_alloc_peak_bytes=max((r["telemetry"]["atlas16_clause_alloc_bytes"] for r in ar),default=0))
    print("ATLAS25_FINAL "+json.dumps(dict(smoke=args.smoke,trials=len(rows),
        summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":
    main()
