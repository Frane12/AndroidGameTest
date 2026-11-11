#!/usr/bin/env python3
"""ATLAS26: SHA-paired, single-CPU native SAT vs Kissat / CryptoMiniSat.

Frozen C7 and C7+GF2 controls; orthogonal 3k/6k native clause-use scoring.
UNSAT only verified if independently reconstructed source XOR contradiction
on the ORIGINAL CNF; never substitute reported UNSAT for certification.
Existing SATLIB cohorts are nonblind. New deterministic indices 170/171
are prospective RELATIVE to the prior index registry, not global blind.
"""
import argparse,hashlib,json,os,pathlib,resource,subprocess,sys,time
sys.path.insert(0,"research")
import drnas_atlas23_benchmark as Old
import drnas_atlas21_official as Verify
import drnas_atlas_wide500 as W
from drnas_atlas15_benchmark import independently_verify_core

ROOT=pathlib.Path("mre_atlas26")
BIN=ROOT/"bin"
ARMS=("A","C7_ADAPT","C7_ADAPT_GAUSS","C26_REUSE3K",
      "C26_REUSE6K","C26_REUSE6K_GF2","KISSAT","CMS")
REPS=2
CAP={"regression":10,"extension":12,"fresh":8,"smoke":3}
FIELDS=("conflicts","decisions","propagations","watch_visits",
        "atlas15_deleted","atlas15_minimized","atlas15_reductions",
        "atlas16_compactions","atlas16_clause_alloc_bytes",
        "atlas16_maxrss_kb","atlas17_pressure_cycles",
        "atlas17_low_cycles","atlas26_mode","atlas26_reason_uses",
        "atlas26_reused","atlas26_discounted","atlas26_deleted",
        "atlas26_tracked","atlas26_lbd_low","atlas26_live_metadata",
        "atlas26_compaction_moves","gauss_rows","gauss_rank",
        "xor_source_rows","xor_derived_rows","xor_implications")
NEW_INDICES=(170,171)
# All 15 synthetic families. No synthetic formula is claimed SAT or UNSAT
# from its name: results are based exclusively on original CNF validation.
NEW_FAMILIES=tuple(W.SYNTH)

def all_fresh():
    rows=[]
    for family in NEW_FAMILIES:
        for i in NEW_INDICES:
            n,clauses=W.synth_one(family,i)
            raw=W.canonical(n,clauses)
            sha=hashlib.sha256(raw).hexdigest()
            path=ROOT/"fresh"/f"{family}_{i}.cnf"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
            rows.append(dict(id=len(rows),family=family,index=i,sha256=sha,
              source_kind="DETERMINISTIC_GENERATED",path=str(path),
              archive_entry=f"wide500:{family}:{i}",bytes=len(raw),cohort="fresh"))
    assert len(rows)==30 and len({r["sha256"] for r in rows})==30
    return rows

def sources(cohort,shard,shards):
    if cohort=="smoke":
        first=Old.source_set("regression")[:1]
        fresh=all_fresh()
        select=next(s for s in fresh if s["family"]=="xor_chain_unsat")
        out=first+[select]
        for s in out:s["cohort"]="smoke"
        return out
    if cohort in ("regression","extension"):
        assert shard==0 and shards==1
        out=Old.source_set(cohort)
        for s in out:s["cohort"]=cohort
        return out
    assert cohort=="fresh" and 0<=shard<shards
    return [s for s in all_fresh() if s["id"]%shards==shard]

def stats_from_output(output):
    lines=[l for l in output.splitlines() if l.startswith("ATLAS13_TRIAL ")]
    if len(lines)>1:raise AssertionError("duplicate native trial telemetry")
    raw=dict(item.split("=",1) for item in lines[0].split()[1:] if "=" in item) if lines else {}
    # Missing data is explicitly null, NOT silently claimed to be zero.
    return {name:(int(float(raw[name])) if name in raw else None) for name in FIELDS}

def run(source,arm,rep,cap):
    p=pathlib.Path(source["path"])
    raw=p.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==source["sha256"],"CNF SHA drift"
    if arm=="KISSAT":
        cmd=[str(BIN/"kissat"),str(p)]
    elif arm=="CMS":
        cmd=["cryptominisat5","--threads=1","--verb=0",str(p)]
    else:
        cmd=[str(BIN/"drnas_atlas26"),str(p),"--mode",arm,
             "--time",str(cap),"--seed",str(rep+1)]
        if arm!="A":cmd+=["--policy","1.0,0.85"]
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(int(cap)+3,int(cap)+4))
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    start=time.monotonic()
    try:
        child=subprocess.run(cmd,text=True,capture_output=True,
                             timeout=cap,preexec_fn=limits)
        rc,out,err=child.returncode,child.stdout,child.stderr
    except subprocess.TimeoutExpired:
        rc,out,err=124,"","wall_timeout"
    run_sec=time.monotonic()-start
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    child_cpu=max(0.,after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime)
    if arm=="CMS" and rc in (-15,15) and run_sec>=cap-.5:rc=124
    if rc not in (0,10,20,124,-9,-24,-25,15,-15):
        raise RuntimeError(f"crash {arm} {source['sha256']} rc={rc} stderr={err[-500:]}")
    if rc in (15,-15) and run_sec<cap-.5:
        raise RuntimeError(f"early signal failure {arm} {source['sha256']}")
    gf2=False;proof_rows=0
    if rc==10 and not Verify.model_ok(p,out):
        raise AssertionError(f"invalid SAT witness on original CNF {arm} {source['sha256']}")
    if rc==20 and arm not in ("KISSAT","CMS"):
        core=[l for l in out.splitlines() if l.startswith("ATLAS13_GF2_CORE")]
        if len(core)>1:raise AssertionError("duplicate GF2 certificate")
        if core:
            _,clauses=W.parse_original(raw)
            ids=[int(x) for x in core[0].split()[1:]]
            if not independently_verify_core(clauses,ids):
                raise AssertionError(f"independent original CNF GF2 proof FAILURE {source['sha256']}")
            gf2=True
            proof_rows=len(ids)
    status=("SAT_VERIFIED" if rc==10 else
            "GF2_UNSAT_VERIFIED" if gf2 else
            "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN")
    elapsed=round(time.monotonic()-start,6)
    telemetry=stats_from_output(out) if arm not in ("KISSAT","CMS") else {}
    # For solved CDCL arms insist correct activation. A source-GF2 proof may
    # exit before any CDCL metrics; this is allowed only with independent proof.
    if arm.startswith("C26_") and rc in (10,20) and not gf2:
        required=1 if arm=="C26_REUSE3K" else 2
        if telemetry.get("atlas26_mode")!=required:
            raise AssertionError(f"native C26 mode activation failed: {arm}")
    if rc in (10,20) and arm not in ("KISSAT","CMS") and not gf2 and all(v is None for v in telemetry.values()):
        raise AssertionError("native completed result has no telemetry")
    return dict(sha256=source["sha256"],family=source["family"],
        index=source["index"],source_kind=source["source_kind"],
        cohort=source["cohort"],arm=arm,rep=rep,status=status,
        original_SAT_witness_verified=rc==10,
        independent_GF2_UNSAT_verified=gf2,
        independent_LRAT_UNSAT_verified=False,
        GF2_core_rows=proof_rows,E2E_s=elapsed,
        child_solver_s=round(run_sec,6),
        CPU_child_s=round(child_cpu,6),
        validation_s=round(max(0.,elapsed-run_sec),6),
        PAR2_verified_s=elapsed if status in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") else 2*cap,
        PAR2_reported_s=elapsed if rc in (10,20) else 2*cap,
        telemetry=telemetry)

def summary(rows):
    out={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        field=lambda k:sum((r["telemetry"].get(k) or 0) for r in subset)
        out[arm]=dict(trials=len(subset),
            verified_SAT=sum(r["status"]=="SAT_VERIFIED" for r in subset),
            verified_GF2_UNSAT=sum(r["status"]=="GF2_UNSAT_VERIFIED" for r in subset),
            unverified_UNSAT=sum(r["status"]=="UNSAT_UNVERIFIED" for r in subset),
            unknown=sum(r["status"]=="UNKNOWN" for r in subset),
            verified_solved=sum(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") for r in subset),
            verified_PAR2_s=round(sum(r["PAR2_verified_s"] for r in subset),4),
            reported_PAR2_s=round(sum(r["PAR2_reported_s"] for r in subset),4),
            E2E_s=round(sum(r["E2E_s"] for r in subset),4),
            CPU_child_s=round(sum(r["CPU_child_s"] for r in subset),4),
            deleted=field("atlas15_deleted"),reused=field("atlas26_reused"),
            discounted=field("atlas26_discounted"),reason_uses=field("atlas26_reason_uses"),
            tracked=field("atlas26_tracked"),lbd_low=field("atlas26_lbd_low"),
            compaction_moves=field("atlas26_compaction_moves"),
            watch_visits=field("watch_visits"),propagations=field("propagations"),
            conflicts=field("conflicts"),
            max_rss_kb=max((r["telemetry"].get("atlas16_maxrss_kb") or 0 for r in subset),default=0),
            max_clause_alloc_bytes=max((r["telemetry"].get("atlas16_clause_alloc_bytes") or 0 for r in subset),default=0))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort",choices=(*CAP,),required=True)
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--shards",type=int,default=1)
    a=ap.parse_args()
    assert a.shards>0 and 0<=a.shard<a.shards
    if a.cohort in ("smoke","regression","extension"):
        assert a.shards==1 and a.shard==0
    cap=CAP[a.cohort]
    ss=sources(a.cohort,a.shard,a.shards)
    assert ss and len({s["sha256"] for s in ss})==len(ss)
    trials=[]
    manifest=dict(cohort=a.cohort,shard=a.shard,shards=a.shards,
        source_shas=[s["sha256"] for s in ss],arms=list(ARMS),cap_s=cap,
        reps=1 if a.cohort=="smoke" else REPS,
        one_cpu=len(os.sched_getaffinity(0))==1,
        source_sha_checked=True,
        global_blind_claim=False,
        new_generated_relative_to_registry=a.cohort=="fresh")
    assert manifest["one_cpu"],"workflow runner must be pinned to ONE CPU"
    digest=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    print("ATLAS26_MANIFEST "+json.dumps(dict(manifest,manifest_sha256=digest),sort_keys=True),flush=True)
    for source in ss:
        for rep in range(manifest["reps"]):
            verdicts=set()
            for arm in ARMS:
                r=run(source,arm,rep,cap)
                trials.append(r)
                print("ATLAS26_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
                if r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED","UNSAT_UNVERIFIED"):
                    verdicts.add("SAT" if r["status"]=="SAT_VERIFIED" else "UNSAT")
            if len(verdicts)>1:
                raise AssertionError("cross-solver original CNF SAT/UNSAT contradiction")
    assert len(trials)==len(ss)*manifest["reps"]*len(ARMS)
    payload=dict(manifest=manifest,manifest_sha256=digest,
        sources=ss,rows=trials,summary=summary(trials))
    dest=ROOT/a.cohort/f"shard_{a.shard}"
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"results.json").write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n")
    print("ATLAS26_FINAL "+json.dumps(dict(cohort=a.cohort,shard=a.shard,
        manifest_sha256=digest,sources=len(ss),trials=len(trials),
        summary=payload["summary"]),sort_keys=True),flush=True)

if __name__=="__main__":main()
