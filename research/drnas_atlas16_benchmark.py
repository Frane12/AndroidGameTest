#!/usr/bin/env python3
"""ATLAS16 source-disjoint 500-CNF benchmark: 20 families, SHA-locked, one CPU.

Stages 1,2 use indices 35..59 and 60..84 (1000 unique CNFs);
stage 3 repeats stage 2 with policy from stage 2 (nonblind replay).
True E2E and PAR2(verified) are reported separately from reported UNSAT.
"""
import argparse,collections,hashlib,json,os,pathlib,resource,subprocess,time
import drnas_atlas_wide500 as W
from drnas_atlas15_benchmark import independently_verify_core

ROOT=pathlib.Path("mre_atlas16")
ROOT.mkdir(exist_ok=True)
ARMS=("A","C5_CDCL","C6_KEEP","C6_KEEP_GAUSS","KISSAT","CMS")
CAP=10.0
REPS=2
CATEGORIES=tuple(W.SOURCES+W.SYNTH)

def source_set(stage,shard,smoke=False):
    assert stage in (1,2,3) and 0<=shard<20
    start=35 if stage==1 else 60
    original=W.source_corpus(limit=85)
    dataset=[]
    for ci,cat in enumerate(CATEGORIES):
        for offset in range(25):
            if (offset+ci)%20 != shard:continue
            i=start+offset
            if cat in original:
                n,clauses,sha,entry=original[cat][i]
                origin="SATLIB-original"
            else:
                n,clauses=W.synth_one(cat,i)
                sha=hashlib.sha256(W.canonical(n,clauses)).hexdigest()
                entry=f"deterministic:{cat}:{i}"
                origin="generated"
            dataset.append(dict(category=cat,index=i,vars=n,
                  clauses_count=len(clauses),sha256=sha,entry=entry,
                  origin=origin,clauses=clauses))
    assert len(dataset)==25 and len({s["sha256"] for s in dataset})==25
    # Historical cohorts use indices 0..34 under this pinned generator:
    # training 0..19, prospective 20..29, BLOCKER blind100 30..34.
    # SHA-check any historical audit files that happen to be present.
    assert start>=35 and min(c["index"] for c in dataset)>=35
    forbidden=set()
    for name,key in (("research/atlas_wide500_memory.json","train_samples"),
                     ("research/atlas_prospective_v1_summary.json","source_sha"),
                     ("research/drnas_blocker_blind100_r3_summary.json","source_sha256")):
        p=pathlib.Path(name)
        if p.is_file():
            old=json.loads(p.read_text())
            forbidden.update(old.get(key,[]))
    assert not forbidden.intersection(x["sha256"] for x in dataset),"historical source overlap"
    return dataset[:2] if smoke else dataset

def verified_model(output,n,clauses):
    model={}
    for line in output.splitlines():
        if line.startswith("v "):
            for token in line.split()[1:]:
                lit=int(token)
                if not lit:continue
                if not 1<=abs(lit)<=n:return False
                if abs(lit) in model and model[abs(lit)]!=(lit>0):return False
                model[abs(lit)]=lit>0
    return len(model)==n and all(any(model[abs(lit)]==(lit>0) for lit in c) for c in clauses)

def run_solver(source,arm,rep,policy):
    raw=W.canonical(source["vars"],source["clauses"])
    f=ROOT/"current.cnf";f.write_bytes(raw)
    assert hashlib.sha256(raw).hexdigest()==source["sha256"]
    seed=int.from_bytes(hashlib.sha256(f"ATLAS16|{source['sha256']}|{rep}".encode()).digest()[:8],"big")
    native=str((ROOT/"bin/drnas_atlas16").resolve())
    if arm in ("KISSAT","CMS"):
        cmd=([str((ROOT/"bin/kissat").resolve()),str(f.resolve())] if arm=="KISSAT"
            else ["cryptominisat5","--threads=1","--verb=0","--maxtime=10",str(f.resolve())])
    else:
        cmd=[native,str(f.resolve()),"--mode",arm,"--time",str(CAP),"--seed",str(seed)]
        if arm!="A":cmd+=["--policy",policy]
    def limit():
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(12,13))
    start=time.monotonic()
    try:
        proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                  text=True,timeout=CAP+1.25,check=False,preexec_fn=limit)
        rc,out,err=proc.returncode,proc.stdout,proc.stderr
    except subprocess.TimeoutExpired:
        rc,out,err=124,"","timeout"
    dt=round(time.monotonic()-start,6)
    # CryptoMiniSat --maxtime sends SIGTERM at its own time limit. On
    # POSIX this can surface as +15 (shell-style) or -15 (Python signal).
    # Only normalize a near-cap termination: an early SIGTERM remains a
    # genuine error, never a solved SAT/UNSAT result.
    if arm=="CMS" and rc in (15,-15) and dt>=CAP-0.5:
        rc=124
    if rc not in (0,10,20,124,-9,-24,-25):
        raise RuntimeError(f"Crash {arm} {source['sha256']} rc={rc} stderr={err[-800:]}")
    stats={}
    for line in out.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            stats=dict(chunk.split("=",1) for chunk in line.split()[1:] if "=" in chunk)
    if arm not in ("KISSAT","CMS") and rc in (10,20) and not stats:
        raise AssertionError("missing native E2E metrics "+source["sha256"])
    sat=bool(rc==10 and verified_model(out,source["vars"],source["clauses"]))
    if rc==10 and not sat:raise AssertionError("original SAT model invalid "+arm+" "+source["sha256"])
    gf2=False
    if rc==20 and arm not in ("KISSAT","CMS"):
        core=next((line for line in out.splitlines() if line.startswith("ATLAS13_GF2_CORE")),None)
        if core:
            coreids=[int(x) for x in core.split()[1:]]
            if not independently_verify_core(source["clauses"],coreids):
                raise AssertionError("GF2 contradiction proof mismatch "+source["sha256"])
            gf2=True
    status="SAT_VERIFIED" if sat else "GF2_UNSAT_VERIFIED" if gf2 else "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN"
    return dict(arm=arm,rep=rep,seed=seed,status=status,
       E2E_s=dt,PAR2_verified_s=dt if sat or gf2 else 2*CAP,
       PAR2_reported_s=dt if rc in (10,20) else 2*CAP,
       native_telemetry={key:int(float(stats.get(key) or 0)) for key in (
          "decisions","conflicts","atlas15_deleted","atlas15_minimized",
          "atlas15_reductions","atlas16_compactions","atlas16_reclaimed_slots",
          "atlas16_reclaimed_capacity_bytes","atlas16_clause_slots",
          "atlas16_tombstones","atlas16_clause_alloc_bytes","atlas16_maxrss_kb")},
       source_sha=source["sha256"],category=source["category"],
       index=source["index"],source=source["origin"],policy=policy if arm not in ("KISSAT","CMS","A") else "",
       UNSAT_independent_LRAT=False)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage",type=int,required=True,choices=(1,2,3))
    ap.add_argument("--shard",type=int,required=True)
    ap.add_argument("--smoke",action="store_true")
    args=ap.parse_args()
    cases=source_set(args.stage,args.shard,args.smoke)
    manifest=[{k:v for k,v in s.items() if k!="clauses"} for s in cases]
    raw=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
    ms=hashlib.sha256(raw).hexdigest()
    if args.stage>1 and not args.smoke:
        p=pathlib.Path("prior/policy_next.json")
        assert p.exists(),"missing prior aggregate/policy; sequential stages required"
        policies=json.loads(p.read_text())["policy_by_family"]
    else:policies={}
    default=(pathlib.Path("training/ATLAS15_POLICY.txt").read_text().strip() if
             pathlib.Path("training/ATLAS15_POLICY.txt").exists() else "1.0,0.85")
    print("ATLAS16_MANIFEST "+json.dumps(dict(stage=args.stage,shard=args.shard,
         cases=len(cases),total=500,manifest_sha256=ms,run="nonblind_replay" if args.stage==3 else "prospective",
         source_index_range=[35,59] if args.stage==1 else [60,84],
         frozen_policy=default,arms=ARMS,cap_s=CAP,reps=REPS)),flush=True)
    rows=[]
    events=ROOT/f"events_s{args.stage}_h{args.shard}.jsonl"
    with events.open("w",buffering=1) as journal:
        for j,s in enumerate(cases):
            result={}
            # Rotate arm order across cases/reps to reduce systematic warm-cache bias.
            for rep in range(REPS):
                order=list(ARMS)
                turn=(j+rep*3)%len(order)
                order=order[turn:]+order[:turn]
                for arm in order:
                    policy=policies.get(s["category"],default) if arm.startswith("C6_") else default
                    value=run_solver(s,arm,rep,policy)
                    record=dict(stage=args.stage,shard=args.shard,**value)
                    rows.append(record);result[arm]=value
                    journal.write(json.dumps(dict(event="trial_completed",**record),sort_keys=True)+"\n")
                    print("ATLAS16_TRIAL "+json.dumps(record,sort_keys=True),flush=True)
                statuses={r["status"] for r in result.values()}
                if "SAT_VERIFIED" in statuses and ("UNSAT_UNVERIFIED" in statuses or "GF2_UNSAT_VERIFIED" in statuses):
                    raise AssertionError("SAT vs UNSAT solver disagreement "+s["sha256"])
            print("ATLAS16_PROGRESS "+json.dumps(dict(stage=args.stage,shard=args.shard,completed=j+1,total=len(cases))),flush=True)
    expected=len(cases)*REPS*len(ARMS)
    assert len(rows)==expected
    summary={a:dict(trials=len([r for r in rows if r["arm"]==a]),
                    solved=sum(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") for r in rows if r["arm"]==a),
                    SAT=sum(r["status"]=="SAT_VERIFIED" for r in rows if r["arm"]==a),
                    GF2_UNSAT=sum(r["status"]=="GF2_UNSAT_VERIFIED" for r in rows if r["arm"]==a),
                    UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in rows if r["arm"]==a),
                    PAR2_s=round(sum(r["PAR2_verified_s"] for r in rows if r["arm"]==a),4),
                    PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in rows if r["arm"]==a),4),
                    E2E_s=round(sum(r["E2E_s"] for r in rows if r["arm"]==a),4),
                    deleted=sum(r["native_telemetry"]["atlas15_deleted"] for r in rows if r["arm"]==a),
                    compactions=sum(r["native_telemetry"]["atlas16_compactions"] for r in rows if r["arm"]==a),
                    peak_rss_kb=max([r["native_telemetry"]["atlas16_maxrss_kb"] for r in rows if r["arm"]==a] or [0]))
             for a in ARMS}
    audit=dict(stage=args.stage,shard=args.shard,source_manifest=manifest,manifest_sha256=ms,
               policy_upstream_sha=hashlib.sha256(json.dumps(policies,sort_keys=True).encode()).hexdigest(),
               rows=rows,summary=summary,uncertified_unsat_not_credited=True,
               replay_nonblind=args.stage==3)
    (ROOT/f"audit_s{args.stage}_h{args.shard}.json").write_text(json.dumps(audit,sort_keys=True,indent=2))
    print("ATLAS16_FINAL "+json.dumps(dict(stage=args.stage,shard=args.shard,summary=summary),sort_keys=True),flush=True)

if __name__=="__main__":main()
