#!/usr/bin/env python3
"""DRNAS MRE6 fresh-seed pilot: CPU feedback + proof-certified CNF quotient.

4 NEW deterministic seed values (not in prior MRE5 CPU calibration).
7 arms: XOR-only; A; B; A+B; canonical CNF control; certified
variable quotient x224:=x12 with source XOR transformed; same quotient
without source-XOR import. Each has two CPU clean OFF runs and one
ON watcher-scan run for native cause telemetry: 84 measurements.

NOT a blind formula holdout: one previously used SAT2026 original.
Proof replay is mandatory before quotient generation, SAT witness is
reconstructed then independently checked on ORIGINAL CNF. No LRAT claims.
"""
from __future__ import annotations

import argparse,hashlib,json,os,pathlib,random,subprocess,sys,tempfile,time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre4_trace_pilot as mre4
import mre5_cpu_watch_cost as mre5
import mre6_principles as principles
import mre1_cross_representation as mre1
import mre2_impact_gate as mre2
import r195_native_cms_benchmark as r195

PROTO="DRNAS-MRE6-QUOTIENT-CPU-HOLDOUT-v1"
ROOT=pathlib.Path("mre6")
MODES=("xor","a","b","both","canonical","quotient","quotient_no_xor")
REPS=2
SHARDS=4
CAP=26.0
TRACE_FLAGS=(0,1)
SOURCE_CMS_SHA="3b709118fd08eb1d15f25e0e239dbc596f967b60"


def need(ok,msg):
    if not ok:raise RuntimeError("MRE6_PILOT_FAIL_CLOSED "+str(msg))


def native_seed(sha,idx):
    need(idx in range(SHARDS),"shard outside seed cohort")
    return int(hashlib.sha256(("MRE6-FRESH-SEED-v1|"+sha+"|"+str(idx)).encode()
                              ).hexdigest()[:8],16)


def make_sources(shared,work):
    case,source,n,original,rows,proofs,selected,tags=shared
    available=principles.build_principles(original,rows,proofs)
    targeted=[p for p in available if p["keep"]==12 and p["remove"]==224]
    need(len(targeted)==1,"expected independently proof-certified x12=x224")
    pr=targeted[0]
    need(tuple(pr["proof_lemma_a"])==tuple(tags[0]) and
         tuple(pr["proof_lemma_b"])==tuple(tags[1]),
         "MRE6 quotient certificate does not match tagged A/B")
    # Every mode gets its own file; preserve original clause order in XOR arms.
    variants={}
    raw=list(original)
    can,cstats=principles.canonical(raw)
    quotient,quot_rows,qstats=principles.apply_quotient(raw,rows,pr)
    for mode in MODES:
        if mode=="xor":cls,xx=raw,rows
        elif mode=="a":cls,xx=raw+[tuple(selected[0]["clause"])],rows
        elif mode=="b":cls,xx=raw+[tuple(selected[1]["clause"])],rows
        elif mode=="both":cls,xx=raw+[tuple(q["clause"]) for q in selected],rows
        elif mode=="canonical":cls,xx=can,rows
        elif mode=="quotient":cls,xx=quotient,quot_rows
        else:cls,xx=quotient,[]
        cnf=work/("source-"+mode+".cnf")
        xor=work/("source-"+mode+".tsv")
        mre1.write_cnf(cnf,n,cls,[])
        mre1.write_xors(xor,xx)
        variants[mode]=dict(cnf=cnf,xor=xor,clauses=len(cls),
            source_rows=len(xx),imported=int(mode in ("a","b"))+
            (2 if mode=="both" else 0),
            quotient=mode.startswith("quotient"),original=mode in ("xor","a","b","both"),
            base_count=len(original) if mode in ("xor","a","b","both") else len(cls))
    return variants,dict(principle=pr,canonical_stats=cstats,quotient_stats=qstats,
                         original_clauses=len(raw),original_xors=len(rows),
                         quotient_clauses=len(quotient),
                         quotient_source_xors=len(quot_rows))


def one(shared,variants,pr,seed_index,repeat,mode,trace,binary):
    case,source,n,original,rows,proofs,selected,tags=shared
    v=variants[mode]
    seed=native_seed(case["sha256"],seed_index)
    start=time.perf_counter()
    env=os.environ.copy()
    env["DRNAS_TRACE_ENABLED"]=str(trace)
    env["DRNAS_ORIG_COUNT"]=str(v["base_count"])
    env["DRNAS_TAG_0"]=",".join(map(str,tags[0]))
    env["DRNAS_TAG_1"]=",".join(map(str,tags[1]))
    status="TIMEOUT";cpu=None;watch=None;tag=None;native={}
    wrapper=None
    with tempfile.TemporaryDirectory(prefix="mre6-empty-") as tmp:
        empty=pathlib.Path(tmp)/"empty.tsv"
        empty.write_text("")
        try:
            p=subprocess.run([
                str(pathlib.Path(binary).resolve()),str(v["cnf"].resolve()),
                str(v["xor"].resolve()),str(empty.resolve()),
                "source_xor_no_gauss",str(seed)
            ],text=True,capture_output=True,env=env,timeout=CAP,check=False)
        except subprocess.TimeoutExpired:p=None
        wrapper=time.perf_counter()-start
        if p is not None:
            need(p.returncode==0,
                 "native CMS invalid SAT witness or bridge error: "+p.stderr[-1400:])
            status,model,native,tag,ledger,cpu,watch=mre5.parse_native(p.stdout)
            need(status==case["expected"]=="SAT","original verdict mismatch")
            expected_tag=(int(mode in ("a","both")),int(mode in ("b","both")))
            need(ledger["original_count"]==v["base_count"] and
                 ledger["total_count"]==v["clauses"],"native CNF clause audit")
            for k in (0,1):
                need(ledger["marked%d"%k]==tag[k]["attached"]==expected_tag[k],
                     "native tagged clause did not attach")
            if v["quotient"]:
                model=principles.reconstruct(model,pr)
            r195.verify_model(source,model)
            need(cpu["enabled"]==trace and watch["enabled"]==trace,
                 "trace CPU mode incorrectly set")
            if trace==0:
                need(watch["visits"]==0 and
                     all(item["visits"]==0 for item in tag.values()),
                     "native event counters unexpectedly enabled")
            else:
                need(watch["visits"]==watch["units"]+watch["conflicts"]+
                     watch["satisfied"],"binary watch event classifications corrupt")
    elapsed=time.perf_counter()-start
    if elapsed>=CAP:status="TIMEOUT"
    return dict(protocol=PROTO,mode=mode,rep=seed_index,repeat=repeat,
       trace_enabled=trace,seed=seed,source_sha256=case["sha256"],
       status=status,original_sat_witness_verified=(status=="SAT"),
       wrapper_wall_s=round(elapsed,6),
       native_subprocess_wall_s=round(wrapper,6) if wrapper is not None else None,
       par2_s=round(CAP*2 if status=="TIMEOUT" else elapsed,6),
       cpu=cpu,all_binary_watchers=watch,
       tag_watchers={str(k):v for k,v in tag.items()} if tag else None,
       native_cdcl_propagations=native.get("propagations"),
       native_cdcl_decisions=native.get("decisions"),
       native_cdcl_conflicts=native.get("conflicts"),
       otf_gauss=False,
       native_original_clause_count=v["base_count"],
       transformed_clause_count=v["clauses"],
       source_xor_rows=v["source_rows"],imported_derived=v["imported"],
       variable_quotient=bool(v["quotient"]),
       witness_reconstruction_applied=bool(v["quotient"]),
       certified_equivalence_id=pr["principle_id"],
       instrumented_CMS_upstream_sha=SOURCE_CMS_SHA,
       git_sha=os.environ.get("GITHUB_SHA","local"))


def shard(seed_index,binary):
    need(seed_index in range(SHARDS),"invalid shard")
    shared=mre4.setup()
    case=shared[0]
    ROOT.mkdir(parents=True,exist_ok=True)
    # Fail closed: calibration dataset uses different numeric native seeds.
    frozen=json.loads((ROOT/"frozen_feedback.json").read_text())
    need(frozen["online_policy"]=="xor" and
         frozen["training_sources"]==1,
         "unsafe online CPU feedback promotion")
    previous=json.loads((ROOT/"calibration"/"seed-0.json").read_text())+\
             json.loads((ROOT/"calibration"/"seed-1.json").read_text())
    old_seeds={q["seed"] for q in previous}
    need(native_seed(case["sha256"],seed_index) not in old_seeds,
         "new seed duplicates calibration")
    with tempfile.TemporaryDirectory(prefix="mre6-quotient-") as temp:
        start=time.perf_counter()
        variants,meta=make_sources(shared,pathlib.Path(temp))
        construction_s=time.perf_counter()-start
        print("MRE6_PRINCIPLE_CONSTRUCTED",json.dumps(
           dict(seed_index=seed_index,construction_wall_s=construction_s,
                provenance=meta),sort_keys=True),flush=True)
        observations=[]
        for repeat in range(REPS):
            specs=[(m,0) for m in MODES]
            if repeat==0:
                specs += [(m,1) for m in MODES]
            random.Random(PROTO+str(seed_index)+":"+str(repeat)).shuffle(specs)
            for mode,trace in specs:
                rec=one(shared,variants,meta["principle"],
                        seed_index,repeat,mode,trace,binary)
                observations.append(rec)
                (ROOT/("seed-%d.json"%seed_index)).write_text(
                    json.dumps(observations,sort_keys=True)+"\n")
                print("MRE6_TRIAL",json.dumps(rec,sort_keys=True),flush=True)
    need(len(observations)==len(MODES)*3==21,
         "incomplete seed shard measurements")
    print("MRE6_SHARD_PASS",seed_index,21,flush=True)


def selftest():
    principles.selftest()
    need(len(MODES)==7 and REPS==2 and SHARDS==4,
         "unexpected seed/mode protocol")
    known1=int(hashlib.sha256((mre2.PROTO+
          "b2c2008e5d24a7aa82499d1486af2550a53a7167e46836c4b9977846204ad483"
          +str(0)).encode()).hexdigest()[:8],16)
    known2=int(hashlib.sha256((mre2.PROTO+
          "b2c2008e5d24a7aa82499d1486af2550a53a7167e46836c4b9977846204ad483"
          +str(1)).encode()).hexdigest()[:8],16)
    need(all(native_seed(
       "b2c2008e5d24a7aa82499d1486af2550a53a7167e46836c4b9977846204ad483",i)
       not in (known1,known2) for i in range(SHARDS)),
       "new seeds overlap frozen MRE5 calibration")
    print("MRE6_PILOT_SELFTEST_PASS",PROTO,flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","shard"))
    ap.add_argument("--seed",type=int,default=0)
    ap.add_argument("--binary",default="mre5/native")
    a=ap.parse_args()
    if a.action=="selftest":selftest()
    else:shard(a.seed,a.binary)
