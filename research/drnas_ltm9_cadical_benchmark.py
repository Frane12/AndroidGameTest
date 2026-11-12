#!/usr/bin/env python3
"""DRNAS LTM9 wide, paired, offline synthetic E2E vs CaDiCaL.
Twenty-five generator families plus one known pigeonhole regression anchor.
One logical CPU; three sequential arms; source SHA, SAT witness audit;
UNSAT is NOT credited to verified PAR2 without an independent proof.
"""
import hashlib,json,os,pathlib,resource,subprocess,sys,time
sys.path.insert(0,"research")
import drnas_atlas13_generator as A
import drnas_atlas_wide500 as W

CAP=7.0
REPS=2
ARMS=(("BASE","A36_75"),("LTM9_KEEP50","LTM8_KEEP50"),("CaDiCaL",None))
ROOT=pathlib.Path("ltm9_results")
ROOT.mkdir(parents=True,exist_ok=True)
NATIVE=str(pathlib.Path("mre_atlas23/bin/drnas_ltm9").resolve())
CATEGORIES_A=tuple(A.CATEGORIES)
CATEGORIES_W=tuple(W.SYNTH)
assert len(CATEGORIES_A)==10 and len(CATEGORIES_W)==15

def generate():
    sources=[]
    for fam in CATEGORIES_A:
        n,clauses,_=A.build(fam,72)
        sources.append(("ATLAS13",fam,72,n,clauses))
    for fam in CATEGORIES_W:
        n,clauses=W.synth_one(fam,22)
        sources.append(("WIDE500",fam,22,n,clauses))
    n,clauses,_=A.build("pigeonhole_unsat",64)
    sources.append(("ATLAS13","pigeonhole_unsat",64,n,clauses))
    out=[]
    for origin,family,index,n,clauses in sources:
        raw=W.canonical(n,clauses)
        sha=hashlib.sha256(raw).hexdigest()
        p=ROOT/(sha+".cnf")
        p.write_bytes(raw)
        out.append(dict(provenance=origin,family=family,index=index,
                        nvars=n,nclauses=len(clauses),clauses=clauses,
                        sha256=sha,path=str(p.resolve())))
    assert len(out)==26 and len({a["sha256"] for a in out})==26
    return out

def model_ok(n,clauses,stdout):
    assign={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for token in line.split()[1:]:
            lit=int(token)
            if lit==0:continue
            v=abs(lit)
            if not (1<=v<=n) or (v in assign and assign[v]!=(lit>0)):
                return False
            assign[v]=lit>0
    return all(any(assign.get(abs(lit))==(lit>0) for lit in c) for c in clauses)

def parse_output(output):
    trial={};progress=[]
    for line in output.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            trial=dict(kv.split("=",1) for kv in line.split()[1:] if "=" in kv)
        elif line.startswith("LTM9_PROGRESS "):
            progress.append(dict(kv.split("=",1) for kv in line.split()[1:] if "=" in kv))
    return trial,progress

def run(case,rep,arm,mode):
    assert hashlib.sha256(pathlib.Path(case["path"]).read_bytes()).hexdigest()==case["sha256"]
    cmd=([NATIVE,case["path"],"--mode",mode,"--time",str(CAP),
           "--seed",str(rep+1),"--policy","1.0,0.85"]
         if mode else ["cadical","-q",case["path"]])
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(int(CAP)+2,int(CAP)+3))
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+0.1,
                         preexec_fn=limits)
        rc=p.returncode;stdout=p.stdout;stderr=p.stderr
    except subprocess.TimeoutExpired as ex:
        rc=124
        stdout=ex.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode("utf-8","replace")
        stderr=""
    elapsed=min(CAP,time.monotonic()-start)
    if rc not in (0,10,20,124,-24,-9,-15):
        raise RuntimeError(f"{arm} unexpected rc={rc} stderr={stderr[-700:]}")
    if rc==10:
        if not model_ok(case["nvars"],case["clauses"],stdout):
            raise RuntimeError(f"SAT witness invalid: {arm} {case['sha256']}")
        status="SAT_VERIFIED"
    elif rc==20:
        status="UNSAT_UNVERIFIED"
    else:
        status="UNKNOWN"
    trial,progress=parse_output(stdout)
    if arm!="CaDiCaL" and rc in (10,20) and not trial:
        raise RuntimeError(f"Missing native metrics for {arm} {case['sha256']}")
    latest=progress[-1] if progress else {}
    def value(k,backup=None):
        a=trial.get(k,latest.get(backup or k))
        return int(float(a)) if a is not None else None
    metrics=(dict(
        conflicts=value("conflicts"),
        decisions=value("decisions"),
        restarts=value("ltm9_restarts","restarts"),
        learned=value("ltm9_learned","learned"),
        minimized=value("atlas15_minimized","minimized"),
        deleted=value("atlas15_deleted","deleted"),
        lbd_le2=value("ltm9_lbd_le2","lbd_le2"),
        lbd_3to6=value("ltm9_lbd_3to6","lbd_3to6"),
        lbd_ge7=value("ltm9_lbd_ge7","lbd_ge7"),
        active_lbd=value("ltm9_active_lbd","active_lbd"),
        quota_attempts=value("atlas36_attempts","quota_attempts"),
        quota_effective=value("atlas36_effective_quota","quota_effective"),
        propagations=value("ltm9_propagations"),
        watch_visits=value("ltm9_watch_visits"),
        progress_checkpoints=len(progress),
        telemetry_complete=bool(trial),
    ) if mode else None)
    return dict(
        arm=arm,rep=rep,origin=case["provenance"],family=case["family"],
        index=case["index"],sha256=case["sha256"],nvars=case["nvars"],
        nclauses=case["nclauses"],status=status,
        e2e_s=round(elapsed,6),
        PAR2_verified_s=round(elapsed if status=="SAT_VERIFIED" else 2*CAP,6),
        PAR2_reported_s=round(elapsed if status in ("SAT_VERIFIED","UNSAT_UNVERIFIED") else 2*CAP,6),
        stats=metrics,
        independent_UNSAT_verified=False,
    )

def summarize(rows):
    out={}
    for arm,_ in ARMS:
        sub=[x for x in rows if x["arm"]==arm]
        out[arm]=dict(trials=len(sub),SAT_verified=sum(x["status"]=="SAT_VERIFIED" for x in sub),
            UNSAT_unverified=sum(x["status"]=="UNSAT_UNVERIFIED" for x in sub),
            UNKNOWN=sum(x["status"]=="UNKNOWN" for x in sub),
            PAR2_verified_s=round(sum(x["PAR2_verified_s"] for x in sub),6),
            PAR2_reported_s=round(sum(x["PAR2_reported_s"] for x in sub),6),
            E2E_s=round(sum(x["e2e_s"] for x in sub),6),
            conflicts_observed=sum(x["stats"].get("conflicts") or 0 for x in sub if x["stats"]),
            learned_observed=sum(x["stats"].get("learned") or 0 for x in sub if x["stats"]),
            deleted_observed=sum(x["stats"].get("deleted") or 0 for x in sub if x["stats"]),
            incomplete_telemetry=sum(not x["stats"]["telemetry_complete"] for x in sub if x["stats"]))
    base=out["LTM9_KEEP50"]
    cd=out["CaDiCaL"]
    out["relative"]=dict(
        cadical_over_ltm9_verified_PAR2=round(cd["PAR2_verified_s"]/max(1e-8,base["PAR2_verified_s"]),6),
        cadical_over_ltm9_reported_PAR2=round(cd["PAR2_reported_s"]/max(1e-8,base["PAR2_reported_s"]),6))
    return out

def main():
    cases=generate()
    metadata=[{k:v for k,v in a.items() if k not in ("clauses","path")} for a in cases]
    (ROOT/"manifest.json").write_text(json.dumps(metadata,indent=2))
    print("LTM9_MANIFEST "+json.dumps(dict(cases=len(cases),families=25,reps=REPS,
        trials=len(cases)*REPS*len(ARMS),cap_s=CAP,arms=[a for a,_ in ARMS],
        sources="offline_deterministic_synthetic",one_cpu=True,original_sha=True,
        independent_unsat_proofs=False)),flush=True)
    rows=[]
    for case in cases:
        for rep in range(REPS):
            order=ARMS if rep==0 else tuple(reversed(ARMS))
            statuses=set()
            for arm,mode in order:
                rec=run(case,rep,arm,mode)
                rows.append(rec);statuses.add(rec["status"])
                print("LTM9_TRIAL "+json.dumps(rec,sort_keys=True),flush=True)
                (ROOT/"results.json").write_text(json.dumps(rows,indent=2))
            if "SAT_VERIFIED" in statuses and "UNSAT_UNVERIFIED" in statuses:
                raise RuntimeError("SAT-UNSAT disagreement across solver arms")
    s=summarize(rows)
    print("LTM9_FINAL "+json.dumps(s,sort_keys=True),flush=True)
    families={}
    for c in cases:
        a=[r for r in rows if r["sha256"]==c["sha256"]]
        families[c["provenance"]+":"+c["family"]+":"+str(c["index"])]={
          arm:dict(verified=sum(r["status"]=="SAT_VERIFIED" for r in a if r["arm"]==arm),
                   PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in a if r["arm"]==arm),6),
                   PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in a if r["arm"]==arm),6))
          for arm,_ in ARMS}
    (ROOT/"summary.json").write_text(json.dumps(dict(summary=s,by_case=families),indent=2))
    print("LTM9_BY_CASE "+json.dumps(families,sort_keys=True),flush=True)
    print("LTM9_AUDIT single_cpu=true paired=true SAT_original_verified=true "
          "UNSAT_independent_proof=false synthetic=true checkpoint_on_timeout=true "
          "learning_metrics_diagnostic_not_safety_proof=true",flush=True)
if __name__=="__main__":
    main()
