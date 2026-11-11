#!/usr/bin/env python3
"""DRNAS CDCL 2x2 controlled cross: BLOCKER x C6 conservative retention.
100 SHA-new CNFs (20 families, 5 each; SATLIB 25 + synthetic 75).
3 repetitions, 5 arms, 8s E2E each, one pinned logical CPU per attempt.
Native DRNAS is tested as A, blocker, C6 keep and blocker+C6. Kissat ref.
Reported UNSAT and DRAT-checked original UNSAT are kept distinct. A DRAT
certificate produced by *reference Kissat* certifies the original CNF, not
the internal reasoning trace of a DRNAS arm.
"""
import argparse, collections, hashlib, json, os, pathlib, resource, subprocess, time
import drnas_atlas_wide500 as W
from drnas_atlas16_benchmark import verified_model

ROOT=pathlib.Path("mre_blocker_c6")
ROOT.mkdir(exist_ok=True)
SHARD=int(os.environ.get("BLOCKER_C6_SHARD","0"))
assert 0<=SHARD<20
ARMS=("A","BLOCKER","C6_KEEP","BLOCKER_C6_KEEP","KISSAT")
REPS=3
CAP=8.0
PROOF_CAP=9.0
MAX_PROOF_BYTES=16*1024*1024
BINARY_ROOT=(ROOT/"bin").resolve()
EXECUTABLES={"A":"drnas_atlas16","C6_KEEP":"drnas_atlas16",
             "BLOCKER":"drnas_atlas16_blocker","BLOCKER_C6_KEEP":"drnas_atlas16_blocker",
             "KISSAT":"kissat"}
POLICY={"uf250-1065":"0.85,0.90"}
DEFAULT_POLICY="1.0,0.85"

def source_set(smoke=False):
    sources=W.source_corpus(limit=90)
    out=[]
    for ci,category in enumerate(W.SOURCES+W.SYNTH):
        for offset in range(5):
            if (ci*5+offset)%20!=SHARD:continue
            index=85+offset
            if category in sources:
                n,clauses,sha,entry=sources[category][index]
                origin="SATLIB-original"
            else:
                n,clauses=W.synth_one(category,index)
                sha=hashlib.sha256(W.canonical(n,clauses)).hexdigest()
                entry=f"deterministic:{category}:{index}"
                origin="generated"
            out.append(dict(category=category,index=index,n=n,clauses=clauses,
                            sha256=sha,origin=origin,entry=entry))
    if len(out)!=5 or len({r["sha256"] for r in out})!=5:
        raise AssertionError("shard source partition is not five unique CNF")
    # Cross checks against all prior WIDE500 and prospective SHA cohorts.
    forbidden=set()
    for name,key in (("research/atlas_wide500_memory.json","train_samples"),
                     ("research/atlas_prospective_v1_summary.json","source_sha"),
                     ("research/drnas_blocker_blind100_r3_summary.json","source_sha256")):
        p=pathlib.Path(name)
        if p.is_file():
            forbidden.update(json.loads(p.read_text()).get(key,[]))
    if forbidden.intersection(s["sha256"] for s in out):
        raise AssertionError("historical original source SHA overlap")
    if not all(85<=s["index"]<=89 for s in out):
        raise AssertionError("unexpected source indices from ATLAS16 pass1/2")
    if smoke:
        # Exercise an original SAT source and an UNSAT proof source.
        r=out[0]
        n,c=W.synth_one("xor_chain_unsat",85+SHARD%5)
        sha=hashlib.sha256(W.canonical(n,c)).hexdigest()
        q=dict(category="xor_chain_unsat",index=85+SHARD%5,n=n,
               clauses=c,sha256=sha,origin="generated",entry="smoke-unsat")
        return [r,q]
    return out

def limit():
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(12,13))
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_PROOF_BYTES,MAX_PROOF_BYTES))

def run_one(source,arm,rep,cnf):
    binpath=BINARY_ROOT/EXECUTABLES[arm]
    native=arm!="KISSAT"
    seed=int.from_bytes(hashlib.sha256(
        f"BLOCKER_C6_R3|{source['sha256']}|{rep}".encode()).digest()[:8],"big")
    policy=POLICY.get(source["category"],DEFAULT_POLICY)
    mode="C6_KEEP" if arm in ("C6_KEEP","BLOCKER_C6_KEEP") else "A"
    cmd=([str(binpath),str(cnf),"--mode",mode,"--time",str(CAP),"--seed",str(seed)]
         +(["--policy",policy] if mode!="A" else [])) if native else [str(binpath),str(cnf)]
    t=time.monotonic()
    try:
        proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,check=False,timeout=CAP+1.0,preexec_fn=limit)
        rc,out,err=proc.returncode,proc.stdout,proc.stderr
    except subprocess.TimeoutExpired:
        rc,out,err=124,"","process wall timeout"
    dt=round(time.monotonic()-t,6)
    if rc not in (0,10,20,124,-9,-24,-25):
        raise RuntimeError(f"solver crash {arm} sha={source['sha256']} return={rc} {err[-500:]}")
    sat=bool(rc==10 and verified_model(out,source["n"],source["clauses"]))
    if rc==10 and not sat:
        raise AssertionError("Invalid original SAT model "+arm+" "+source["sha256"])
    stats={}
    for line in out.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            stats=dict(chunk.split("=",1) for chunk in line.split()[1:] if "=" in chunk)
    if native and rc in (10,20) and not stats:
        raise AssertionError("missing native C6 stats "+arm+" "+source["sha256"])
    def stat(k):
        try:return int(float(stats.get(k) or 0))
        except ValueError:return 0
    return dict(arm=arm,rep=rep,source_sha256=source["sha256"],
       category=source["category"],index=source["index"],origin=source["origin"],
       status="SAT_VERIFIED" if sat else "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN",
       SAT_original_verified=sat,UNSAT_independent_DRAT=False,
       UNSAT_independent_LRAT=False,E2E_s=dt,
       PAR2_reported_s=dt if rc in (10,20) else CAP*2,
       PAR2_verified_s=dt if sat else CAP*2,
       decisions=stat("decisions"),conflicts=stat("conflicts"),
       learned_deleted=stat("atlas15_deleted"),
       learned_minimized=stat("atlas15_minimized"),
       reductions=stat("atlas15_reductions"),
       compactions=stat("atlas16_compactions"),
       reclaimed_slots=stat("atlas16_reclaimed_slots"),
       tombstones=stat("atlas16_tombstones"),
       clause_slots=stat("atlas16_clause_slots"),
       clause_alloc_bytes=stat("atlas16_clause_alloc_bytes"),
       maxrss_kb=stat("atlas16_maxrss_kb"),
       policy=policy if mode=="C6_KEEP" else "",
       seed=seed)

def verify_drat_if_unsat(source,cnf,rows):
    # Independent original CNF certificate from a reference solver. DRNAS
    # does not currently output its own LRAT/DRAT proof.
    if not any(x["status"]=="UNSAT_UNVERIFIED" for x in rows):
        return dict(status="not_needed",verified=False,proof_bytes=0)
    proof=ROOT/f"proof_{SHARD}.drat"
    proof.unlink(missing_ok=True)
    t=time.monotonic()
    try:
        run=subprocess.run([str(BINARY_ROOT/"kissat"),"--no-binary",str(cnf),str(proof)],
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,check=False,
            timeout=PROOF_CAP+0.8,preexec_fn=limit)
    except subprocess.TimeoutExpired:
        proof.unlink(missing_ok=True)
        return dict(status="proof_generation_timeout",verified=False,proof_bytes=0)
    if run.returncode!=20 or not proof.is_file():
        proof.unlink(missing_ok=True)
        return dict(status="reference_not_unsat",verified=False,proof_bytes=0)
    proof_size=proof.stat().st_size
    if proof_size==0 or proof_size>MAX_PROOF_BYTES:
        proof.unlink(missing_ok=True)
        return dict(status="proof_size_limit",verified=False,proof_bytes=proof_size)
    try:
        chk=subprocess.run([str(BINARY_ROOT/"drat-trim"),str(cnf),str(proof),"-t","10"],
            capture_output=True,text=True,check=False,timeout=12,preexec_fn=limit)
        transcript=chk.stdout+"\n"+chk.stderr
        verified=chk.returncode==0 and any(
            line.strip().startswith("s VERIFIED") for line in transcript.splitlines())
        status="original_drat_verified" if verified else "drat_verifier_rejected"
    except subprocess.TimeoutExpired:
        status="drat_verification_timeout";verified=False
    finally:
        proof.unlink(missing_ok=True)
    return dict(status=status,verified=verified,proof_bytes=proof_size,
                proof_elapsed_s=round(time.monotonic()-t,6),
                original_sha256=source["sha256"])

def summary(rows):
    data={}
    for arm in ARMS:
        r=[x for x in rows if x["arm"]==arm]
        data[arm]=dict(trials=len(r),
          SAT_original_verified=sum(x["SAT_original_verified"] for x in r),
          UNSAT_original_DRAT_verified=sum(x["UNSAT_independent_DRAT"] for x in r),
          UNSAT_reported_unverified=sum(x["status"]=="UNSAT_UNVERIFIED" and
                                         not x["UNSAT_independent_DRAT"] for x in r),
          UNKNOWN=sum(x["status"]=="UNKNOWN" for x in r),
          PAR2_reported_s=round(sum(x["PAR2_reported_s"] for x in r),6),
          PAR2_verified_s=round(sum(x["PAR2_verified_s"] for x in r),6),
          E2E_s=round(sum(x["E2E_s"] for x in r),6),
          conflicts=sum(x["conflicts"] for x in r),
          decisions=sum(x["decisions"] for x in r),
          deleted=sum(x["learned_deleted"] for x in r),
          minimized=sum(x["learned_minimized"] for x in r),
          compactions=sum(x["compactions"] for x in r),
          maxrss_kb=max((x["maxrss_kb"] for x in r),default=0),
          max_clause_alloc_bytes=max((x["clause_alloc_bytes"] for x in r),default=0))
    return data

def run():
    smoke=os.environ.get("BLOCKER_C6_SMOKE","0")=="1"
    cases=source_set(smoke=smoke)
    rows=[];proofs=[]
    source_manifest=[{k:v for k,v in s.items() if k!="clauses"} for s in cases]
    print("BLOCKER_C6_MANIFEST "+json.dumps(dict(shard=SHARD,smoke=smoke,
      sources=source_manifest,oneCPU=True,reps=REPS if not smoke else 1,
      arms=ARMS,cap_s=CAP,branch="BLOCKER_C6_CROSS")),flush=True)
    for ci,source in enumerate(cases):
        cnf=(ROOT/f"source_{SHARD}.cnf").resolve()
        original=W.canonical(source["n"],source["clauses"])
        if hashlib.sha256(original).hexdigest()!=source["sha256"]:
            raise AssertionError("canonical source SHA drift")
        cnf.write_bytes(original)
        current=[]
        for rep in range(REPS if not smoke else 1):
            ordered=list(ARMS)
            rotate=(ci+rep*2)%len(ordered)
            ordered=ordered[rotate:]+ordered[:rotate]
            for arm in ordered:
                result=run_one(source,arm,rep,cnf)
                current.append(result)
            statuses={r["status"] for r in current}
            if "SAT_VERIFIED" in statuses and "UNSAT_UNVERIFIED" in statuses:
                raise AssertionError("cross-arm SAT/UNSAT contradiction "+source["sha256"])
        certificate=verify_drat_if_unsat(source,cnf,current)
        proofs.append(certificate)
        if certificate["verified"]:
            for row in current:
                if row["status"]=="UNSAT_UNVERIFIED":
                    row["UNSAT_independent_DRAT"]=True
                    row["PAR2_verified_s"]=row["E2E_s"]
        for row in current:
            rows.append(row)
            print("BLOCKER_C6_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
        print("BLOCKER_C6_PROOF "+json.dumps(dict(category=source["category"],
           sha256=source["sha256"],**certificate),sort_keys=True),flush=True)
    report=dict(shard=SHARD,smoke=smoke,rows=rows,proofs=proofs,
        source_manifest=source_manifest,oneCPU=True,cap_s=CAP,
        independent_drat_proves_original_unsat_not_native_trace=True,
        summary=summary(rows))
    if not smoke:
        (ROOT/f"audit_{SHARD}.json").write_text(json.dumps(report,sort_keys=True,indent=2))
    print("BLOCKER_C6_FINAL "+json.dumps(dict(shard=SHARD,smoke=smoke,
       unique_sources=len(cases),summary=report["summary"],proof_verified=sum(p["verified"] for p in proofs)),
       sort_keys=True),flush=True)

def merge(directory):
    audits=[json.loads((directory/f"audit_{i}.json").read_text()) for i in range(20)]
    manifest=[v for audit in audits for v in audit["source_manifest"]]
    rows=[v for audit in audits for v in audit["rows"]]
    assert len(manifest)==100 and len({x["sha256"] for x in manifest})==100
    assert len(rows)==1500
    assert len({(x["source_sha256"],x["rep"],x["arm"]) for x in rows})==len(rows)
    assert set(x["index"] for x in manifest)==set(range(85,90))
    family=collections.Counter(x["category"] for x in manifest)
    assert len(family)==20 and all(v==5 for v in family.values())
    assert sum(x["origin"]=="SATLIB-original" for x in manifest)==25
    pairs=collections.defaultdict(dict)
    for x in rows:
        pairs[(x["source_sha256"],x["rep"])][x["arm"]]=x
    assert len(pairs)==300 and all(set(p)==set(ARMS) for p in pairs.values())
    old_train=json.loads(pathlib.Path("research/atlas_wide500_memory.json").read_text())
    old_pro=json.loads(pathlib.Path("research/atlas_prospective_v1_summary.json").read_text())
    old_b=json.loads(pathlib.Path("research/drnas_blocker_blind100_r3_summary.json").read_text())
    forbidden=set(old_train["train_samples"])|set(old_pro["source_sha"])|set(old_b["source_sha256"])
    assert forbidden.isdisjoint(x["sha256"] for x in manifest)
    categories={cat:summary([x for x in rows if x["category"]==cat]) for cat in family}
    totals=summary(rows)
    b=totals["A"]["PAR2_verified_s"]
    combo=totals["BLOCKER_C6_KEEP"]["PAR2_verified_s"]
    out=dict(experiment="DRNAS-BLOCKER-C6-CROSS",sources=100,
      original_SATLIB=25,synthetic=75,source_sha_disjoint=True,
      families=20,repeat=3,attempts=1500,shards=20,cap_s=CAP,
      one_logical_cpu=True,not_trained_on_holdout=True,
      UNSAT_independent_LRAT=False,
      DRAT_proofs_original_cnf_only=True,
      source_proof_count=sum(p["verified"] for a in audits for p in a["proofs"]),
      verified_PAR2_A_over_combo=round(b/combo,5),
      reported_PAR2_A_over_combo=round(
        totals["A"]["PAR2_reported_s"]/
        totals["BLOCKER_C6_KEEP"]["PAR2_reported_s"],5),
      summary=totals,categories=categories,
      source_sha256=sorted(x["sha256"] for x in manifest))
    pathlib.Path("research/drnas_blocker_c6_cross_summary.json").write_text(
        json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("BLOCKER_C6_MERGED "+json.dumps(out,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--merge-dir",type=pathlib.Path)
    args=ap.parse_args()
    if args.merge_dir:merge(args.merge_dir)
    else:run()
