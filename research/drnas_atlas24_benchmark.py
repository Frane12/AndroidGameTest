#!/usr/bin/env python3
"""ATLAS24 native online A/C7 pressure switch, with optional source Gauss.

A, C7, C7_STABLE, V24_LIVE, V24_LIVE_GAUSS, Kissat, CMS.
Proof-first, original SHA SAT verification. Two original SATLIB cohorts
remain nonblind; separate fresh generated SHA group has no policy training.
"""
import argparse,hashlib,json,pathlib,resource,subprocess,sys,time
sys.path.insert(0,"research")
import drnas_atlas23_benchmark as Old
import drnas_atlas_wide500 as W

ROOT=pathlib.Path("mre_atlas24")
BIN=ROOT/"bin"
ARMS=("A","C7_ADAPT","V23_C7_STABLE","V24_LIVE","V24_LIVE_GAUSS","KISSAT","CMS")
Old.ROOT=ROOT
Old.BIN=BIN
Old.ARMS=ARMS

def sources(cohort):
    if cohort in ("regression","extension"):
        result=Old.source_set(cohort)
        for s in result:s["cohort"]=cohort
        return result
    assert cohort=="fresh"
    cats=("random3_uniform","random3_planted","xor3_sat","xor4_sat",
          "xor_chain_unsat","xor_hybrid","color3_unsat","pigeonhole_unsat")
    result=[]
    for family in cats:
        for i in (130,131):
            n,clauses=W.synth_one(family,i)
            raw=W.canonical(n,clauses)
            sha=hashlib.sha256(raw).hexdigest()
            path=ROOT/cohort/(family+"_"+str(i)+".cnf")
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
            result.append(dict(id=len(result),family=family,index=i,
                sha256=sha,archive_entry="generated:WIDE500:"+family+":"+str(i),
                source_kind="DETERMINISTIC_GENERATED",path=str(path),
                bytes=len(raw),cohort=cohort))
    assert len(result)==16 and len({s["sha256"] for s in result})==16
    return result

def run(source,arm,rep,cap):
    if not arm.startswith("V24_"):
        old=Old.run(source,arm,rep,cap)
        old["telemetry"].update(atlas24_live=0,atlas24_active=0,
            atlas24_on=0,atlas24_off=0,atlas24_windows=0)
        return old
    p=pathlib.Path(source["path"])
    assert hashlib.sha256(p.read_bytes()).hexdigest()==source["sha256"]
    cmd=[str(BIN/"drnas_atlas24"),str(p),"--mode",arm,
         "--time",str(cap),"--seed",str(rep+1)]
    def limits():
        cpu=int(cap)+4
        resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu+1))
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    t0=time.monotonic()
    try:
        child=subprocess.run(cmd,text=True,capture_output=True,
            timeout=cap,preexec_fn=limits)
        rc,out,err=child.returncode,child.stdout,child.stderr
    except subprocess.TimeoutExpired:
        rc,out,err=124,"","timeout"
    dt=round(time.monotonic()-t0,6)
    if rc not in (0,10,20,124,-9,-24,-25,15,-15):
        raise RuntimeError("ATLAS24 subprocess failure "+arm+
                           " rc="+str(rc)+" "+err[-400:])
    sat=rc==10 and Old.Verify.model_ok(p,out)
    if rc==10 and not sat:raise RuntimeError("INVALID original SAT witness "+arm)
    status="SAT_VERIFIED" if sat else "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN"
    metrics={}
    for l in out.splitlines():
        if l.startswith("ATLAS13_TRIAL "):
            metrics=dict(x.split("=",1) for x in l.split()[1:] if "=" in x)
    keys=("conflicts","decisions","propagations","watch_visits",
        "atlas15_deleted","atlas15_minimized","atlas16_compactions",
        "atlas16_maxrss_kb","atlas24_live","atlas24_active",
        "atlas24_on","atlas24_off","atlas24_windows")
    telemetry={k:int(float(metrics.get(k,0))) for k in keys}
    if rc in (10,20) and telemetry["atlas24_live"]!=1:
        raise AssertionError("Adaptive mode NOT enabled: "+arm)
    return dict(sha256=source["sha256"],family=source["family"],
        index=source["index"],cohort=source["cohort"],arm=arm,rep=rep,
        status=status,original_SAT_witness_verified=sat,
        independent_UNSAT_proof_verified=False,E2E_s=dt,
        PAR2_reported_s=dt if rc in (10,20) else 2*cap,
        PAR2_verified_s=dt if sat else 2*cap,telemetry=telemetry)

def summarize(rows):
    ans={}
    for arm in ARMS:
        rr=[x for x in rows if x["arm"]==arm]
        ans[arm]=dict(trials=len(rr),
          SAT_verified=sum(x["status"]=="SAT_VERIFIED" for x in rr),
          UNSAT_unverified=sum(x["status"]=="UNSAT_UNVERIFIED" for x in rr),
          timeouts=sum(x["status"]=="UNKNOWN" for x in rr),
          PAR2_reported_s=round(sum(x["PAR2_reported_s"] for x in rr),6),
          PAR2_verified_s=round(sum(x["PAR2_verified_s"] for x in rr),6),
          E2E_s=round(sum(x["E2E_s"] for x in rr),6),
          conflicts=sum(x["telemetry"].get("conflicts",0) for x in rr),
          watch_visits=sum(x["telemetry"].get("watch_visits",0) for x in rr),
          on=sum(x["telemetry"].get("atlas24_on",0) for x in rr),
          off=sum(x["telemetry"].get("atlas24_off",0) for x in rr),
          windows=sum(x["telemetry"].get("atlas24_windows",0) for x in rr))
    return ans

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort",choices=("smoke","regression","extension","fresh"),required=True)
    args=ap.parse_args()
    cohort="regression" if args.cohort=="smoke" else args.cohort
    cap=3 if args.cohort=="smoke" else 10 if cohort=="regression" else 12 if cohort=="extension" else 8
    ss=sources(cohort)
    if args.cohort=="smoke": ss=ss[:1]
    # Frozen ATLAS23 benchmark runner names its native executable drnas_atlas23.
    # Keep that runner unchanged; both reference and adaptive arms call the
    # same compiled ATLAS24 binary under their respective --mode flags.
    legacy=BIN/"drnas_atlas23"
    if not legacy.exists():legacy.symlink_to("drnas_atlas24")
    rows=[]
    print("ATLAS24_MANIFEST "+json.dumps(dict(cohort=args.cohort,
      arms=list(ARMS),sources=len(ss),cap_s=cap,
      repetitions=1 if args.cohort=="smoke" else 2,
      single_logical_cpu=True,original_SHA_locked=True,
      no_holdout_feedback=True,global_blind_claim=False),sort_keys=True),flush=True)
    for source in ss:
        for rep in range(1 if args.cohort=="smoke" else 2):
            verdicts=set()
            for arm in ARMS:
                r=run(source,arm,rep,cap)
                rows.append(r)
                print("ATLAS24_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
                if r["status"]!="UNKNOWN":verdicts.add(r["status"])
            if {"SAT_VERIFIED","UNSAT_UNVERIFIED"}<=verdicts:
                raise AssertionError("SAT vs UNSAT contradiction "+source["sha256"])
    payload=dict(cohort=args.cohort,cap_s=cap,sources=ss,
        rows=rows,summary=summarize(rows),original_sha_verified=True,
        independent_UNSAT_LRAT=False)
    path=ROOT/args.cohort/"results.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n")
    print("ATLAS24_FINAL "+json.dumps(dict(cohort=args.cohort,
      sources=len(ss),trials=len(rows),summary=payload["summary"]),sort_keys=True),flush=True)

if __name__=="__main__":main()
