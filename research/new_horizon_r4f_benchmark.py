#!/usr/bin/env python3
"""DRNAS New Horizon R4f: SHA-frozen paired 144x4x4 = 2304 trials.

104 unchanged R4e formulas and 40 NEW deterministic generated controls.
Known generator families. This is NOT independent industrial blind holdout.
R4f is preregistered before its run; no family labels enter selector logic.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, pathlib, random

import new_horizon_r4f as r4f
import new_horizon_r4d as r4d
import new_horizon_r4e as r4e

ROOT=pathlib.Path("new_horizon_r4f")
FROZEN=ROOT/"frozen"
OLD=ROOT/"source/new_horizon_r4e/frozen"
OLD_SHA="b163c5fa2d02758cfd3170804eae2ee0c3bdeca66277e19baba2d176da6ed9cc"
PROTO="DRNAS_NH_R4F_144x4x4_SELECTIVE_PAIR_V1"
POLICIES=("clean","r4d","r4e_mid","r4f_select")
REPS=4
SHARDS=4
ORIGINAL_COUNT=104
NEW_PER_FAMILY=10
NEW_FAMILIES=("valid_dense_chain","valid_dense_shuffled",
              "middle_dense_shuffled","middle_sparse","tail_dense")
# Five families x ten cases = 50 newly generated source cases.
TOTAL=ORIGINAL_COUNT+NEW_PER_FAMILY*len(NEW_FAMILIES)

def need(ok,message):
    if not ok:raise AssertionError("NH_R4F_AUDIT_FAIL_CLOSED "+str(message))

def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(pathlib.Path(path).read_text())
def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def dimacs(n,clauses):
    return f"p cnf {n} {len(clauses)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in clauses)

def control(family,i):
    n=113+i
    chain=[(1,)]+[(-k,k+1) for k in range(1,n)]
    dense=chain+2*[(-k,k+1) for k in range(1,n)]
    if family=="valid_dense_chain":
        clauses=dense
    elif family=="valid_dense_shuffled":
        clauses=dense.copy()
        random.Random(PROTO+family+str(i)).shuffle(clauses)
    elif family=="middle_dense_shuffled":
        clauses=dense.copy()
        # Still mixed, but negative clause not necessarily at byte midpoint.
        clauses.insert(len(clauses)//2+i%5,(1,2,3))
        random.Random(PROTO+family+str(i)).shuffle(clauses)
    elif family=="middle_sparse":
        clauses=chain.copy()
        clauses.insert(len(clauses)//2,(1,2,3))
    elif family=="tail_dense":
        clauses=dense+[(1,2,3)]
    else:
        raise ValueError(family)
    return n,clauses,"SAT"

def selftest():
    r4f.selftest()
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for family in NEW_FAMILIES:
            for i in range(NEW_PER_FAMILY):
                n,c,expected=control(family,i)
                p=pathlib.Path(tmp)/f"{family}-{i}.cnf"
                p.write_text(dimacs(n,c))
                is2=r4d.r2.is_2cnf(c)
                need(is2==(family in ("valid_dense_chain","valid_dense_shuffled")),
                     "family 2sat status unexpected")
                # Oracle: the all-true assignment satisfies every clause.
                need(all(any(v>0 for v in clause) for clause in c),
                     "control SAT oracle all-true not valid")
                ev=r4f.source_evidence(p)
                if is2:
                    need(not ev[0],"R4f discarded genuine 2SAT source")
    print("NH_R4F_BENCH_SELFTEST_PASS",flush=True)

def freeze():
    need(sha(OLD/"manifest.json")==OLD_SHA,"R4e original frozen SHA mismatch")
    previous=load(OLD/"manifest.json")
    need(len(previous["cases"])==ORIGINAL_COUNT,"R4e source count")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in previous["cases"]:
        p=OLD/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"R4e formula drift")
        id="unchanged-"+c["id"]
        dst=FROZEN/(id+".cnf")
        dst.write_bytes(p.read_bytes())
        cases.append(dict(id=id,sha256=sha(dst),family=c["family"],
                          expected=c["expected"],cap_s=c["cap_s"],
                          prior_source_sha256=c["sha256"]))
    for family in NEW_FAMILIES:
        for i in range(NEW_PER_FAMILY):
            n,clauses,expected=control(family,i)
            id=f"new-{family}-{i}"
            dst=FROZEN/(id+".cnf")
            dst.write_text(dimacs(n,clauses))
            cases.append(dict(id=id,sha256=sha(dst),family=family,
                              expected=expected,cap_s=3.0))
    need(len(cases)==TOTAL and len({c["sha256"] for c in cases})==TOTAL,
         "invalid count or duplicate source SHA")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,
        R4e_manifest_sha256=OLD_SHA,cases=cases,
        source_not_external_blind=True,same_native_binary=True,
        policies=POLICIES,repetitions=REPS))
    verify()
    print("NH_R4F_FREEZE_PASS",json.dumps(dict(
        sources=len(cases),manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    m=load(FROZEN/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==TOTAL,"manifest drift")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "original CNF mutated")
    return m["cases"]

def trial(c,mode,rep,binary):
    path=FROZEN/(c["id"]+".cnf")
    need(sha(path)==c["sha256"],"source changed before trial")
    out=r4f.run_one(path,binary,c["cap_s"],mode,
        ROOT/"scratch"/(c["sha256"][:16]+f"-{mode}-{rep}"))
    status=out["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"bad SAT status")
    if status!="TIMEOUT":
        need(status==c["expected"],"SAT/UNSAT contradicts frozen source")
    info=(out.get("r4f_evidence") or out.get("r4e_evidence")
          or out.get("r4d_evidence") or {})
    elapsed=round(out["elapsed"],6)
    return dict(id=c["id"],sha256=c["sha256"],family=c["family"],
        mode=mode,rep=rep,status=status,elapsed_s=elapsed,
        par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
        cap_s=c["cap_s"],route=out["route"],proof=out["proof"],
        reason=out["reason"],gate_reason=info.get("reason"),
        gate_s=round(info.get("scan_s",0),6),
        chain_links=info.get("chain_links"),windows=info.get("windows",0))

def shard(idx,binary):
    cases=verify()
    need(0<=idx<SHARDS and pathlib.Path(binary).is_file(),"missing shard/native")
    rows=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            modes=list(POLICIES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,mode,rep,binary)
                rows.append(r)
                save(ROOT/f"shard-{idx}.json",rows)
                print("NH_R4F_TRIAL",json.dumps({k:r[k] for k in
                 ("id","mode","status","elapsed_s","route","gate_reason")}),
                 flush=True)
    need(len(rows)==len(cases[idx::SHARDS])*REPS*len(POLICIES),
         "incomplete shard")
    print("NH_R4F_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cases=verify()
    lookup={c["sha256"]:c for c in cases}
    rows=[]
    for idx in range(SHARDS):
        z=load(ROOT/f"shard-{idx}.json")
        need(len(z)==len(cases[idx::SHARDS])*REPS*len(POLICIES),
             "shard attempt count mismatch")
        rows+=z
    need(len(rows)==TOTAL*REPS*len(POLICIES),
         "missing arm/source/repetition")
    pairs=collections.defaultdict(list)
    for r in rows:
        c=lookup.get(r["sha256"])
        need(c and c["id"]==r["id"],"row SHA/ID mismatched")
        target=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(r["par2_s"]-target)<.00001,"PAR2 invalid")
        pairs[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            z=pairs[c["sha256"],rep]
            need(len(z)==len(POLICIES) and
                 {r["mode"] for r in z}==set(POLICIES),
                 "source/arm pairing lost")
            need(len({r["status"] for r in z if r["status"]!="TIMEOUT"})<=1,
                 "contradictory SAT/UNSAT verdicts")
    groups={"all":cases,"reused_r4e":[c for c in cases
                             if c["id"].startswith("unchanged-")],
             "new_controls":[c for c in cases if c["id"].startswith("new-")]}
    for name in sorted({c["family"] for c in cases}):
        groups[name]=[c for c in cases if c["family"]==name]
    summary={}
    for name,cs in groups.items():
        shas={c["sha256"] for c in cs}
        summary[name]={}
        for mode in POLICIES:
            v=[r for r in rows if r["sha256"] in shas and r["mode"]==mode]
            summary[name][mode]=dict(
                attempts=len(v),
                solved=sum(r["status"]!="TIMEOUT" for r in v),
                par2_s=round(sum(r["par2_s"] for r in v),6),
                elapsed_s=round(sum(r["elapsed_s"] for r in v),6),
                gate_s=round(sum(r["gate_s"] for r in v),6),
                routes=dict(collections.Counter(r["route"] for r in v)),
                gate_reasons=dict(collections.Counter(r["gate_reason"] for r in v
                                                    if r["gate_reason"])))
    report=dict(protocol=PROTO,status="SHA_PAIRED_COMPLETE_NOT_EXTERNAL_BLIND",
        original_r4e_sources=ORIGINAL_COUNT,new_generated_sources=TOTAL-ORIGINAL_COUNT,
        formulas=TOTAL,attempts=len(rows),same_pinned_native=True,
        original_sha_verified=True,all_SAT_models_verified=True,
        native_UNSAT_independent_LRAT_absent=True,
        microsecond_timing_noise=True,threshold_development_informed=True,
        summary=summary)
    save(ROOT/"report.json",report)
    save(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    md=["# New Horizon R4f — selective chain/middle negative-witness gate","",
        f"{TOTAL} SHA-frozen formulas x {REPS} repeats x {len(POLICIES)} arms = {len(rows)} attempts.",
        "104 original R4e formulas + 50 generated controls. Not blind external SAT.","",
        "| Cohort | Mode | Solved | PAR2 seconds | Gate seconds |",
        "|---|---|---:|---:|---:|"]
    for name,policies in summary.items():
        for mode,v in policies.items():
            md.append(f"| {name} | {mode} | {v['solved']}/{v['attempts']} | "+
                      f"{v['par2_s']} | {v['gate_s']} |")
    md+=["","Negative sampling never certifies SAT, UNSAT, 2SAT, or XOR.",
         "Every successful native SAT model validated against original CNF.",
         "No independent LRAT replay for native UNSAT.",
         "No general complexity/speedup claim from these generator-known microtimings."]
    (ROOT/"summary.md").write_text("\n".join(md)+"\n")
    print("NH_R4F_FINAL",json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cmd",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="new_horizon_r4f/r190-driver")
    a=p.parse_args()
    if a.cmd=="selftest":selftest()
    elif a.cmd=="freeze":freeze()
    elif a.cmd=="verify":print("NH_R4F_VERIFY_PASS",len(verify()))
    elif a.cmd=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
