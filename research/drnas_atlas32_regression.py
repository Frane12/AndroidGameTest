#!/usr/bin/env python3
"""ATLAS32 prospective end-to-end conservative PHP theorem gate + strongest ATLAS25 DRNAS V23 baseline.
Gate emits theorem-backed UNSAT only on exact checked subformula; otherwise calls native V23.
No claim of LRAT certification. One CPU, frozen source SHA and paired repetitions.
"""
import argparse,hashlib,json,pathlib,sys,time,subprocess,resource,random
sys.path.insert(0,"research")
import drnas_atlas_wide500 as W
import drnas_atlas25_benchmark as B
from drnas_atlas26_php import prove_php
ROOT=pathlib.Path("mre_atlas32")
FAMILIES=("pigeonhole_unsat","pigeonhole_sat","random3_uniform")
INDICES=tuple(range(800,812))
ARMS=("V23_C7_STABLE","V23_PHP","KISSAT")
CAP=15
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--shard",type=int,required=True,choices=range(4));args=ap.parse_args()
    B.ARMS=ARMS;B.Old.ARMS=ARMS
    legacy=B.BIN/"drnas_atlas23"
    if not legacy.exists():legacy.symlink_to("drnas_atlas25")
    sources=[]
    for family in FAMILIES:
        for idx in INDICES:
            n,cls=W.synth_one(family,idx)
            # Alternate definitional encoding on half of the PHP cases.
            # For each positive pigeon clause (x1|...|xh), replace it by
            # unit y and (-y|x1|...|xh). This is equisatisfiable and
            # hides the original all-positive clause from the exact detector.
            # Negative pairwise constraints remain untouched.
            if family.startswith("pigeonhole") and idx % 2 == 0:
                encoded=[]
                for clause in cls:
                    if len(clause)>=2 and all(lit>0 for lit in clause):
                        n+=1
                        encoded.append([n])
                        encoded.append([-n]+list(clause))
                    else:encoded.append(list(clause))
                cls=encoded
            # Prospective transformation frozen before solver outcomes:
            # random bijective variable renaming, clause and literal permutations,
            # and redundant copies of existing negative constraints.
            rng=random.Random(int.from_bytes(hashlib.sha256(
                f"ATLAS32|{family}|{idx}|frozen-v1".encode()).digest()[:8],"big"))
            permutation=list(range(1,n+1));rng.shuffle(permutation)
            transformed=[[(-1 if lit<0 else 1)*permutation[abs(lit)-1]
                          for lit in clause] for clause in cls]
            for clause in transformed:rng.shuffle(clause)
            negatives=[clause for clause in transformed if len(clause)==2 and all(x<0 for x in clause)]
            if negatives:
                transformed += [list(rng.choice(negatives)) for _ in range(min(8,len(negatives)))]
            rng.shuffle(transformed)
            cls=transformed
            raw=W.canonical(n,cls)
            sources.append((family,idx,raw,cls))
    # Previously used external SATLIB regression and extension cohorts.
    # Source files and SHA are supplied by the frozen ATLAS23 source registry.
    B.Old.ROOT=ROOT;B.Old.BIN=B.BIN
    for cohort in ("regression","extension"):
        for item in B.Old.source_set(cohort):
            raw=pathlib.Path(item["path"]).read_bytes()
            cls=[]
            for line in raw.decode().splitlines():
                if line.startswith(("c","p","%")):continue
                vals=[int(x) for x in line.split()]
                if vals and vals[-1]==0:cls.append(vals[:-1])
            sources.append(("satlib_"+item["family"],item["index"],raw,cls))
    assert len(sources)==52 and len({hashlib.sha256(x[2]).hexdigest() for x in sources})==52
    rows=[]
    for family,idx,raw,cls in sources[args.shard*13:(args.shard+1)*13]:
        path=ROOT/"cases"/f"{family}_{idx}.cnf"
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest()
        source=dict(path=str(path),sha256=sha,family=family,index=idx,cohort="atlas32")
        for rep in range(2):
            for arm in ARMS:
                t0=time.monotonic()
                cert=prove_php(cls) if arm=="V23_PHP" else None
                detection=time.monotonic()-t0 if arm=="V23_PHP" else 0
                if arm=="V23_PHP":
                    cmd=[str(B.BIN/"drnas_php_native"),str(path),
                         str(B.BIN/"drnas_atlas23"),"--mode","V23_C7_STABLE",
                         "--time",str(CAP),"--seed",str(rep+1),
                         "--policy","1.0,0.85"]
                    def limits():
                        resource.setrlimit(resource.RLIMIT_CPU,(CAP+4,CAP+5))
                        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
                    try:
                        child=subprocess.run(cmd,text=True,capture_output=True,
                            timeout=CAP,preexec_fn=limits)
                        rc=child.returncode
                        if rc not in (10,20,124,-9,-24,-25,15,-15):
                            raise RuntimeError("native PHP failed rc="+str(rc)+" "+child.stderr[-300:])
                        if rc==10:
                            assert B.Old.Verify.model_ok(path,child.stdout),"invalid SAT witness"
                        status=("SAT_VERIFIED" if rc==10 else
                                "UNSAT_THEOREM" if rc==20 and "ATLAS28_PHP_THEOREM" in child.stdout else
                                "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN")
                    except subprocess.TimeoutExpired:
                        status="UNKNOWN"
                    elapsed=time.monotonic()-t0
                    par2=elapsed if status!="UNKNOWN" else 2*CAP
                    fallback=status!="UNSAT_THEOREM"
                    if status=="UNSAT_THEOREM" and cert is None:cert={"kind":"native_unit_php_structural","independent_LRAT":False}
                    else:cert=None
                else:
                    rr=B.run(source,arm,rep,CAP)
                    elapsed=rr["E2E_s"]
                    status=rr["status"]
                    par2=rr["PAR2_reported_s"]
                    fallback=False
                row=dict(sha256=sha,family=family,index=idx,arm=arm,rep=rep,
                    status=status,E2E_s=round(elapsed,6),PAR2_reported_s=round(par2,6),
                    detector_s=round(detection,6),fallback=fallback,
                    theorem_certificate=cert,independent_UNSAT_LRAT=False)
                rows.append(row)
                print("ATLAS32_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    summary={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        summary[arm]=dict(trials=len(rr),
            par2_s=round(sum(r["PAR2_reported_s"] for r in rr),6),
            sat_verified=sum(r["status"]=="SAT_VERIFIED" for r in rr),
            theorem_unsat=sum(r["status"]=="UNSAT_THEOREM" for r in rr),
            unverified_unsat=sum(r["status"]=="UNSAT_UNVERIFIED" for r in rr),
            unknown=sum(r["status"]=="UNKNOWN" for r in rr),
            fallback=sum(r["fallback"] for r in rr),
            detector_s=round(sum(r["detector_s"] for r in rr),6))
    result=dict(shard=args.shard,rows=rows,summary=summary,
        theorem_not_LRAT=True,single_logical_cpu=True,sha_locked=True)
    out=ROOT/f"results_{args.shard}.json"
    out.write_text(json.dumps(result,sort_keys=True,indent=2))
    print("ATLAS32_FINAL "+json.dumps(dict(shard=args.shard,summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":main()
