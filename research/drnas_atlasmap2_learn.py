#!/usr/bin/env python3
"""DRNAS MAP2-L: persistent, evidence-gated strategy memory, never a proof cache.

TRAIN: run matched A/SHADOW/LIVE on the same original CNF; update memory only
after independently verifying both SAT models and a useful matched outcome.
EVAL: choose A or LIVE using *frozen* training memory, never update it.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

VERSION=1
ARMS={"A":"A","SHADOW":"MAP2_SHADOW","LIVE":"MAP2_LIVE"}
TELEMETRY=re.compile(r"^ATLASMAP2_TRIAL (.+)$",re.M)

def read_cnf(path):
    raw=Path(path).read_bytes()
    n=None; declared=None; clauses=[]; pending=[]
    for line in raw.decode("ascii").splitlines():
        line=line.strip()
        if not line or line.startswith("c"):continue
        if line.startswith("%"):break
        if line.startswith("p "):
            parts=line.split()
            if len(parts)!=4 or parts[1]!="cnf" or n is not None:
                raise ValueError("bad DIMACS header")
            n=int(parts[2]);declared=int(parts[3]);continue
        if n is None:raise ValueError("missing DIMACS header")
        for token in line.split():
            lit=int(token)
            if lit and not 1<=abs(lit)<=n:raise ValueError("literal out of range")
            if lit:pending.append(lit)
            else:clauses.append(pending);pending=[]
    if pending or n is None or len(clauses)!=declared:
        raise ValueError("incomplete DIMACS")
    return raw,n,clauses

def features(n,clauses):
    # Exact source-pair count, no unverified assumption of an equivalence.
    binary=set()
    for c in clauses:
        if len(c)!=2 or abs(c[0])==abs(c[1]):continue
        a,b=c
        if abs(a)>abs(b):a,b=b,a
        binary.add((a,b))
    complete=set()
    for a,b in binary:
        if (-a,-b) not in binary:continue
        x,y=abs(a),abs(b)
        complete.add((x,y,1^(a<0)^(b<0)))
    parent=list(range(n+1));rank=[0]*(n+1);parity=[0]*(n+1)
    def find(x):
        p=0
        while parent[x]!=x:
            p^=parity[x];x=parent[x]
        return x,p
    inconsistent=False
    for x,y,rhs in sorted(complete):
        a,pa=find(x);b,pb=find(y)
        if a==b:
            if pa^pb^rhs:inconsistent=True
        else:
            if rank[a]<rank[b]:a,b=b,a
            parent[b]=a;parity[b]=pa^pb^rhs
            if rank[a]==rank[b]:rank[a]+=1
    groups={}
    for v in range(1,n+1):
        r,_=find(v)
        groups[r]=groups.get(r,0)+1
    active=[k for k in groups.values() if 3<=k<=32]
    bucket=lambda v: 0 if v<32 else 1 if v<128 else 2 if v<512 else 3 if v<2048 else 4
    binary_ratio=round(100*len(binary)/max(1,len(clauses)))
    return {
      "variables":n,"clauses":len(clauses),"binary_source_clauses":len(binary),
      "complete_source_pairs":len(complete),"eligible_groups":len(active),
      "eligible_group_variables":sum(active),"contradictory_cycle":inconsistent,
      "signature":f"v{bucket(n)}c{bucket(len(clauses))}b{binary_ratio//20}g{min(4,len(active))}p{min(4,len(complete)//4)}"
    }

def verify_sat(stdout,n,clauses):
    assignment={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for token in line.split()[1:]:
            lit=int(token)
            if lit==0:continue
            if not 1<=abs(lit)<=n:return False
            if abs(lit) in assignment and assignment[abs(lit)]!=(lit>0):return False
            assignment[abs(lit)]=lit>0
    return len(assignment)==n and all(
        any(assignment[abs(l)]==(l>0) for l in c) for c in clauses)

def solve(binary,cnf,arm,cap,n,clauses):
    command=[str(Path(binary).resolve()),str(Path(cnf).resolve()),
             "--mode",ARMS[arm],"--time",str(cap)]
    start=time.monotonic()
    try:
        p=subprocess.run(command,text=True,capture_output=True,timeout=cap+2)
        rc,stdout,stderr=p.returncode,p.stdout,p.stderr
    except subprocess.TimeoutExpired:
        rc,stdout,stderr=124,"","wall timeout"
    elapsed=time.monotonic()-start
    if rc not in (0,10,20,124,-9,-24):
        raise RuntimeError(f"MAP2 binary failed ({arm}, rc={rc}): {stderr[-500:]}")
    status={10:"SAT",20:"UNSAT"}.get(rc,"UNKNOWN")
    if status=="SAT" and not verify_sat(stdout,n,clauses):
        raise RuntimeError(f"unverified original SAT model in {arm}")
    telemetry={}
    match=TELEMETRY.search(stdout)
    if match:
        telemetry=dict(kv.split("=",1) for kv in match.group(1).split()
                       if "=" in kv)
    if status=="SAT" and telemetry.get("SAT_original_verified")!="1":
        raise RuntimeError("native original model verification flag missing")
    return {"arm":arm,"status":status,"E2E_s":round(elapsed,6),
            "PAR2_s":round(elapsed if status!="UNKNOWN" else 2*cap,6),
            "SAT_original_verified":status=="SAT",
            "UNSAT_independent_LRAT":False,
            "decisions":int(telemetry.get("decisions",0)),
            "conflicts":int(telemetry.get("conflicts",0)),
            "live_implications":int(telemetry.get("map2_implications",0)),
            "live_reasons":int(telemetry.get("map2_reasons",0)),
            "shadow_opportunities":int(telemetry.get("map2_shadow_opportunities",0)),
            "map2_groups":int(telemetry.get("map2_groups",0))}

def load(path):
    if not Path(path).exists():
        return {"version":VERSION,"method":"source-certified-XOR2-parity-DSU-live-CDCL",
                "signatures":{},"samples":{}}
    data=json.loads(Path(path).read_text())
    if data.get("version")!=VERSION or not isinstance(data.get("samples"),dict):
        raise ValueError("incompatible MAP2 learning memory")
    return data

def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".map2-memory-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(data,f,indent=2,sort_keys=True)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def aggregate(data,sig):
    samples=[s for s in data["samples"].values() if s["signature"]==sig]
    # No cross-formula proof is cached. Evidence is aggregated across
    # distinct original source SHA only, not repeated easy cases.
    valid=[s for s in samples if s["usable"]]
    speed=[s["A"]["E2E_s"]/max(1e-9,s["LIVE"]["E2E_s"]) for s in valid]
    speed.sort()
    median=speed[len(speed)//2] if speed else 0
    savings=sorted(s["A"]["E2E_s"]-s["LIVE"]["E2E_s"] for s in valid)
    median_saved=savings[len(savings)//2] if savings else 0
    regress=sum(s["LIVE"]["E2E_s"]>s["A"]["E2E_s"]*1.15 for s in valid)
    causal=sum(s["LIVE"]["live_implications"]>0 for s in valid)
    decisions=sum(s["LIVE"]["decisions"]<s["A"]["decisions"] for s in valid)
    # Conservative activation: three independent positive source CNFs,
    # median >10% faster, no severe regression, and actual live work.
    activate=(len(valid)>=3 and median>=1.10 and median_saved>=0.005 and
              regress==0 and causal>=3)
    return {"distinct_source_sha":len(samples),"verified_pairs":len(valid),
            "median_A_over_LIVE":round(median,5),
            "median_absolute_saved_s":round(median_saved,6),
            "regressions_over_15pct":regress,
            "cases_with_live_implications":causal,
            "cases_with_fewer_decisions":decisions,
            "selected":"LIVE" if activate else "A",
            "method":"paired-original-CNF-E2E-PAR2-with-causal-live-reasons",
            "why":("at_least_3_independent_verified_source_SHA_median_10pct_and_5ms_E2E_gain_no_15pct_regression"
                   if activate else
                   "insufficient_independent_verified_causal_speed_evidence_or_regression")}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("cnf")
    p.add_argument("--binary",default="mre_atlasmap2/bin/drnas_atlasmap2")
    p.add_argument("--memory",required=True)
    p.add_argument("--phase",choices=("train","eval"),required=True)
    p.add_argument("--cap",type=float,default=6)
    p.add_argument("--report")
    a=p.parse_args()
    if not math.isfinite(a.cap) or not 0<a.cap<=3600:raise ValueError("invalid cap")
    raw,n,clauses=read_cnf(a.cnf)
    sha=hashlib.sha256(raw).hexdigest()
    feat=features(n,clauses)
    data=load(a.memory)
    sig=feat["signature"]
    prior=aggregate(data,sig)
    if a.phase=="train":
        # Do not double-count repeated formulas as independent evidence.
        if sha in data["samples"]:
            result={"phase":"train","sha256":sha,"duplicate":True,
                    "features":feat,"decision":prior,"updated":False}
        else:
            attempts={arm:solve(a.binary,a.cnf,arm,a.cap,n,clauses)
                      for arm in ("A","SHADOW","LIVE")}
            # Unknown, unproven UNSAT or mismatched status cannot train
            # a "faster" claim. Both source SAT witnesses must verify.
            usable=(attempts["A"]["status"]=="SAT" and
                    attempts["LIVE"]["status"]=="SAT" and
                    attempts["SHADOW"]["status"]=="SAT" and
                    attempts["LIVE"]["map2_groups"]>0 and
                    attempts["LIVE"]["live_implications"]>0 and
                    attempts["LIVE"]["live_reasons"]>=attempts["LIVE"]["live_implications"])
            reason=("both_original_SAT_witnesses_and_shadow_verified_with_source_entailed_live_CDCL_reasons"
                    if usable else
                    "no_matched_verified_SAT_and_source_entailed_live_reasons")
            data["samples"][sha]={"signature":sig,"features":feat,
                "A":attempts["A"],"LIVE":attempts["LIVE"],
                "SHADOW":attempts["SHADOW"],"usable":usable,
                "explanation":{
                  "method":"exact_original_XOR2_source_pair_to_parity_DSU_to_binary_CDCL_reason",
                  "mechanism":"a transitive source-certified parity relation supplies an implication on the native CDCL trail",
                  "observed_benefit":reason,
                  "E2E_gain_A_over_LIVE":round(attempts["A"]["E2E_s"]/max(1e-9,attempts["LIVE"]["E2E_s"]),5),
                  "decision_delta_A_minus_LIVE":attempts["A"]["decisions"]-attempts["LIVE"]["decisions"],
                  "conflict_delta_A_minus_LIVE":attempts["A"]["conflicts"]-attempts["LIVE"]["conflicts"],
                  "caution":"positive live implication counts are not proof of faster search; all claims require paired original E2E"}
                }
            data["signatures"][sig]=aggregate(data,sig)
            save(a.memory,data)
            result={"phase":"train","sha256":sha,"duplicate":False,
                    "features":feat,"attempts":attempts,
                    "explanation":data["samples"][sha]["explanation"],
                    "decision":data["signatures"][sig],"updated":True}
    else:
        # EVAL is immutable: no evaluation results or SHA enter memory.
        selected=prior["selected"]
        attempt=solve(a.binary,a.cnf,selected,a.cap,n,clauses)
        result={"phase":"eval","sha256":sha,"features":feat,
                "selected":selected,"attempt":attempt,
                "decision":prior,"updated":False,
                "memory_frozen":True}
    if a.report:
        Path(a.report).parent.mkdir(parents=True,exist_ok=True)
        Path(a.report).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ATLASMAP2_LEARN "+json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
