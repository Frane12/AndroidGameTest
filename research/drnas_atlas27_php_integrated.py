#!/usr/bin/env python3
"""ATLAS27 end-to-end conservative PHP theorem gate + last best DRNAS V23 baseline.
Gate emits theorem-backed UNSAT only on exact checked subformula; otherwise calls native V23.
No claim of LRAT certification. One CPU, frozen source SHA and paired repetitions.
"""
import argparse,hashlib,json,pathlib,sys,time
sys.path.insert(0,"research")
import drnas_atlas_wide500 as W
import drnas_atlas25_benchmark as B
from drnas_atlas26_php import prove_php
ROOT=pathlib.Path("mre_atlas27")
FAMILIES=("pigeonhole_unsat","pigeonhole_sat","random3_uniform")
INDICES=(130,131,330,331,332,333,334,335,336,337,338,339)
ARMS=("V23_C7_STABLE","V23_PHP","KISSAT")
CAP=10
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--shard",type=int,required=True,choices=range(4));args=ap.parse_args()
    B.ARMS=ARMS;B.Old.ARMS=ARMS
    legacy=B.BIN/"drnas_atlas23"
    if not legacy.exists():legacy.symlink_to("drnas_atlas25")
    sources=[]
    for family in FAMILIES:
        for idx in INDICES:
            n,cls=W.synth_one(family,idx)
            raw=W.canonical(n,cls)
            sources.append((family,idx,raw,cls))
    rows=[]
    for family,idx,raw,cls in sources[args.shard*9:(args.shard+1)*9]:
        path=ROOT/"cases"/f"{family}_{idx}.cnf"
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest()
        source=dict(path=str(path),sha256=sha,family=family,index=idx,cohort="atlas27")
        for rep in range(2):
            for arm in ARMS:
                t0=time.monotonic()
                cert=prove_php(cls) if arm=="V23_PHP" else None
                detection=time.monotonic()-t0 if arm=="V23_PHP" else 0
                if cert:
                    status="UNSAT_THEOREM";elapsed=time.monotonic()-t0
                    par2=elapsed
                    fallback=False
                else:
                    actual="V23_C7_STABLE" if arm=="V23_PHP" else arm
                    rr=B.run(source,actual,rep,max(0.001,CAP-detection))
                    elapsed=(time.monotonic()-t0) if arm=="V23_PHP" else rr["E2E_s"]
                    status=rr["status"]
                    par2=round(elapsed,6) if status!="UNKNOWN" else 2*CAP
                    fallback=arm=="V23_PHP"
                row=dict(sha256=sha,family=family,index=idx,arm=arm,rep=rep,
                    status=status,E2E_s=round(elapsed,6),PAR2_reported_s=round(par2,6),
                    detector_s=round(detection,6),fallback=fallback,
                    theorem_certificate=cert,independent_UNSAT_LRAT=False)
                rows.append(row)
                print("ATLAS27_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
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
    print("ATLAS27_FINAL "+json.dumps(dict(shard=args.shard,summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":main()
