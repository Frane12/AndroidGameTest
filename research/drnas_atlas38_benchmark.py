#!/usr/bin/env python3
"""ATLAS38 deterministic prefix replay: one reduction at 75% vs 100%.

This is not an in-memory clone. For the same SHA/seed/target, both native
runs execute identical 75%-quota policies before the selected reduction.
The emitted predecision fingerprints must match for causal eligibility.
"""
import argparse,hashlib,json,os,pathlib,re,resource,subprocess,sys,time
sys.path.insert(0,"research")
import drnas_atlas_wide500 as W
import drnas_atlas21_official as Verify

ROOT=pathlib.Path("mre_atlas38")
BIN=pathlib.Path("mre_atlas23/bin")
TARGETS=(5,15,30,45)
REPS=2
CAP=12
# Include troublesome SAT cases and an UNSAT (unverified) negative control.
SPECS=(("uf250-1065",10),("uf250-1065",11),("uuf250-1065",11))
METRICS=("conflicts","decisions","propagations","watch_visits",
         "atlas15_deleted","atlas36_attempts","atlas36_base_quota",
         "atlas36_effective_quota","atlas36_pressure_high","atlas36_pressure_low",
         "atlas38_seen","atlas38_applied","atlas38_pre_fingerprint",
         "atlas38_target","atlas38_pulse_pct","atlas16_maxrss_kb")

def sources(shard):
    corpus=W.source_corpus(limit=12)
    selected=([SPECS[0],SPECS[1]] if shard==0 else [SPECS[2]])
    out=[]
    for family,index in selected:
        n,clauses,sha,entry=corpus[family][index]
        raw=W.canonical(n,clauses)
        assert hashlib.sha256(raw).hexdigest()==sha
        p=ROOT/"cases"/f"{family}_{index}.cnf"
        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        out.append(dict(family=family,index=index,sha256=sha,
                        source_kind="SATLIB_original_SHA",
                        archive_entry=entry,path=str(p)))
    return out

def run(source,arm,rep,target=None):
    p=pathlib.Path(source["path"])
    assert hashlib.sha256(p.read_bytes()).hexdigest()==source["sha256"]
    if arm=="KISSAT":cmd=[str(BIN/"kissat"),str(p)]
    else:
        mode=("A36_75" if arm=="A36_75" else
              f"A38_PULSE{arm[-3:]}_{target}" if arm=="PULSE100" else
              f"A38_PULSE75_{target}")
        # The label in the output is stable; mode is a concrete parser token.
        if arm=="PULSE100":mode=f"A38_PULSE100_{target}"
        cmd=[str(BIN/"drnas_atlas38"),str(p),"--mode",mode,
             "--time",str(CAP),"--seed",str(rep+1),
             "--policy","1.0,0.85"]
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(CAP+3,CAP+4))
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    start=time.monotonic()
    try:
        child=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP,
                             preexec_fn=limits)
        rc,out,err=child.returncode,child.stdout,child.stderr
    except subprocess.TimeoutExpired as e:
        rc=124
        out=e.stdout or b""
        err=e.stderr or b""
        if isinstance(out,bytes):out=out.decode("utf-8","replace")
        if isinstance(err,bytes):err=err.decode("utf-8","replace")
    elapsed=round(time.monotonic()-start,6)
    if rc not in (0,10,20,124,-9,-24,-25,15,-15):
        raise RuntimeError(f"crash {arm} rc={rc} {err[-500:]}")
    model=(rc==10 and Verify.model_ok(p,out))
    if rc==10 and not model:raise AssertionError("invalid SAT witness")
    status="SAT_VERIFIED" if model else "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN"
    pattern=r"ATLAS38_PRE target=(\d+) pct=(\d+) state_hash=(\d+) conflicts=(\d+) decisions=(\d+) propagations=(\d+) watch_visits=(\d+) deleted=(\d+) clauses=(\d+) trail=(\d+)"
    matches=re.findall(pattern,err)
    assert len(matches)<=1,"duplicate intervention"
    pre=None
    if matches:
        keys=("target","pct","hash","conflicts","decisions","propagations",
              "watch_visits","deleted","clauses","trail")
        pre=dict(zip(keys,map(int,matches[0])))
        assert pre["target"]==target
        assert pre["pct"]==(100 if arm=="PULSE100" else 75)
    if arm.startswith("PULSE") and rc in (10,20) and pre is None and target is not None:
        # No reduction at this target before solving is legitimate.
        pass
    native=[l for l in out.splitlines() if l.startswith("ATLAS13_TRIAL ")]
    raw=dict(x.split("=",1) for x in native[-1].split()[1:] if "=" in x) if native else {}
    metrics={field:(int(raw[field]) if field in raw else None)
             for field in METRICS}
    if arm.startswith("PULSE") and pre is not None and rc in (10,20):
        assert metrics["atlas38_applied"]==1
        assert metrics["atlas38_pre_fingerprint"]==pre["hash"]
    return dict(sha256=source["sha256"],family=source["family"],
        index=source["index"],rep=rep,arm=arm,target=target,
        status=status,E2E_s=elapsed,
        PAR2_reported_s=elapsed if rc in (10,20) else 2*CAP,
        PAR2_verified_s=elapsed if model else 2*CAP,
        original_SAT_witness_verified=model,
        independent_UNSAT_LRAT=False,
        pre=pre,telemetry=metrics,timeout_partial_stderr_available=bool(err),
        command_mode=(mode if arm!="KISSAT" else "KISSAT"))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--shard",type=int,choices=(0,1),required=True)
    a=ap.parse_args()
    cases=sources(a.shard)
    assert len(os.sched_getaffinity(0))==1
    print("ATLAS38_MANIFEST "+json.dumps(dict(shard=a.shard,
      sources=[x["sha256"] for x in cases],reps=REPS,targets=TARGETS,
      cap=CAP,one_cpu=True,global_blind=False,
      pair_type="deterministic_replay_not_memory_clone",
      primary_question="single_quota_100_vs_75"),sort_keys=True),flush=True)
    rows=[]
    for case in cases:
        for rep in range(REPS):
            base=run(case,"A36_75",rep)
            kissat=run(case,"KISSAT",rep)
            rows.extend([base,kissat])
            for target in TARGETS:
                p75=run(case,"PULSE75",rep,target)
                p100=run(case,"PULSE100",rep,target)
                rows.extend((p75,p100))
                if p75["pre"] is None or p100["pre"] is None:
                    verdict="NOT_REACHED"
                elif p75["pre"]["hash"]!=p100["pre"]["hash"]:
                    raise AssertionError("predecision fingerprint drift "+case["sha256"])
                elif {k:v for k,v in p75["pre"].items() if k!="pct"} != {
                      k:v for k,v in p100["pre"].items() if k!="pct"}:
                    raise AssertionError("predecision metrics drift")
                else:verdict="MATCHED_PRESTATE"
                rec=dict(family=case["family"],index=case["index"],rep=rep,
                    sha256=case["sha256"],target=target,
                    control75_s=p75["E2E_s"],pulse100_s=p100["E2E_s"],
                    control75_status=p75["status"],pulse100_status=p100["status"],
                    control75_PAR2=p75["PAR2_reported_s"],
                    pulse100_PAR2=p100["PAR2_reported_s"],verdict=verdict,
                    pre=p75["pre"] if verdict=="MATCHED_PRESTATE" else None,
                    delta_conflicts=(p100["telemetry"]["conflicts"]-
                        p75["telemetry"]["conflicts"]
                        if all(x["telemetry"]["conflicts"] is not None for x in (p75,p100)) else None))
                print("ATLAS38_PAIR "+json.dumps(rec,sort_keys=True),flush=True)
            print("ATLAS38_CASE "+json.dumps(dict(family=case["family"],index=case["index"],
                sha=case["sha256"],rep=rep,base=base["E2E_s"],
                base_status=base["status"],kissat=kissat["E2E_s"]),
                sort_keys=True),flush=True)
    out=ROOT/"results"/f"shard_{a.shard}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dict(shard=a.shard,sources=cases,rows=rows),
        sort_keys=True,indent=2)+"\n")
    print("ATLAS38_FINAL "+json.dumps(dict(shard=a.shard,trials=len(rows),
      matched_prestate=sum(1 for r in rows if r["arm"]=="PULSE75" and r["pre"] is not None),
      sources=len(cases)),sort_keys=True),flush=True)

if __name__=="__main__":main()
