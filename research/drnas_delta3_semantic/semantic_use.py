#!/usr/bin/env python3
"""Independent semantic-use certificate for a REAL SAT2024 nonlinear witness.

No timing, no solver promotion, no SAT/UNSAT claim from a local table.
Shows guarded equalities and original-CNF proof reasons, with reversible aliases.
"""
import argparse, hashlib, itertools, json
from pathlib import Path

SHA="ead2a1c2fb44d173d3a24bab1212f07adf571f4fc7563392d434e0f58386939b"
LEFT={"vars":[1,3,771,777],"cnf":[[1,-3,771],[3,-771],[-1,-771],
                                  [-1,-3,777],[1,-777],[3,-777]]}
RIGHT={"vars":[1,3,772],"cnf":[[-1,3,772],[1,-772],[-3,-772]]}
VARS=[1,3,771,772,777]
GUARDS={771:False,772:False}

def canon(c):
    return tuple(sorted(set(c)))

def source(path):
    raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SHA,"ORIGINAL_SHA_MISMATCH"
    clauses=[];current=[];n=m=None
    for line in raw.decode("ascii").splitlines():
        if not line.strip() or line.startswith("c"):continue
        if line.startswith("p "):
            _,kind,n,m=line.split()[:4]
            assert kind=="cnf";n=int(n);m=int(m);continue
        for tok in line.split():
            lit=int(tok)
            if lit:current.append(lit)
            else:clauses.append(tuple(current));current=[]
    assert not current and len(clauses)==m and n==3790 and m==11331
    return clauses

def eval_block(b,values):
    return all(any(values[abs(l)]==(l>0) for l in c) for c in b["cnf"])

def table(b):
    result=[]
    for mask in range(1<<len(b["vars"])):
        values={v:bool(mask&(1<<i)) for i,v in enumerate(b["vars"])}
        if any(v in values and values[v]!=bit for v,bit in GUARDS.items()):continue
        if eval_block(b,values):result.append(mask)
    return result

def hull(points):
    if not points:return set()
    origin=points[0];span={0}
    for p in points:
        span|={x^(p^origin) for x in tuple(span)}
    return {x^origin for x in span}

def proj(mask,small):
    return sum(((mask>>VARS.index(v))&1)<<j for j,v in enumerate(small))

def rup(clauses,candidate):
    # Unit propagation of original CNF plus the negation of candidate.
    values={}
    for lit in (-x for x in candidate):
        key=abs(lit);bit=lit>0
        if key in values and values[key]!=bit:return True
        values[key]=bit
    while True:
        changed=False
        for c in clauses:
            if any(abs(l) in values and values[abs(l)]==(l>0) for l in c):continue
            free=[l for l in c if abs(l) not in values]
            if not free:return True
            if len(free)==1:
                lit=free[0];key=abs(lit);bit=lit>0
                if key in values and values[key]!=bit:return True
                if key not in values:values[key]=bit;changed=True
        if not changed:return False

class AliasTrail:
    def __init__(self):
        self.parent={v:v for v in (1,3,777)}
        self.size={v:1 for v in self.parent}
        self.log=[]
    def root(self,v):
        while v!=self.parent[v]:v=self.parent[v]
        return v
    def mark(self):return len(self.log)
    def union(self,a,b):
        a=self.root(a);b=self.root(b)
        if a==b:return
        if self.size[a]<self.size[b]:a,b=b,a
        self.log.append((a,b,self.size[a]))
        self.parent[b]=a;self.size[a]+=self.size[b]
    def undo(self,mark):
        while len(self.log)>mark:
            a,b,size=self.log.pop()
            self.parent[b]=b;self.size[a]=size
    def count(self):return len({self.root(v) for v in self.parent})

def evaluate(path):
    clauses=source(path);present={canon(c) for c in clauses}
    for block in (LEFT,RIGHT):
        assert all(canon(c) in present for c in block["cnf"]),"NON_SOURCE_BLOCK"
    a=table(LEFT);b=table(RIGHT)
    joined=[];approx=[]
    for mask in range(1<<len(VARS)):
        l=proj(mask,LEFT["vars"]);r=proj(mask,RIGHT["vars"])
        if l in a and r in b:joined.append(mask)
        if l in hull(a) and r in hull(b):approx.append(mask)
    assert joined==[0,19] and len(approx)==4
    assert 1 in approx and 1 not in joined  # original Delta2 counterexample
    # Both new clauses are derived from SOURCE clauses by one resolution step.
    proofs=[
       {"guard":-772,"alias":[1,777],"pivot":-3,
        "parents":[[-1,-3,777],[-1,3,772]],"consequence":[-1,772,777],
        "reverse_source":[1,-777]},
       {"guard":-771,"alias":[3,777],"pivot":1,
        "parents":[[1,-3,771],[-1,-3,777]],"consequence":[-3,771,777],
        "reverse_source":[3,-777]}
    ]
    for record in proofs:
        x,y=record["parents"];pivot=record["pivot"]
        assert canon(x) in present and canon(y) in present and pivot in x and -pivot in y
        resolved=canon([l for l in x if l!=pivot]+[l for l in y if l!=-pivot])
        assert resolved==canon(record["consequence"]) and resolved not in present
        assert not any(-lit in resolved for lit in resolved)
        assert canon(record["reverse_source"]) in present
        assert rup(clauses,resolved),"INVALID_ORIGINAL_RUP"
        record["independent_original_rup"]=True
    # Verify both guarded equalities for every local assignment.
    for mask in range(1<<len(VARS)):
        vals={v:bool(mask&(1<<i)) for i,v in enumerate(VARS)}
        if not (eval_block(LEFT,vals) and eval_block(RIGHT,vals)):continue
        for record in proofs:
            g=record["guard"]
            if vals[abs(g)]==(g>0):
                u,v=record["alias"]
                assert vals[u]==vals[v],"UNSOUND_GUARDED_ALIAS"
    trail=AliasTrail()
    mark0=trail.mark();assert trail.count()==3
    trail.union(3,777);assert trail.count()==2
    mark1=trail.mark()
    trail.union(1,777);assert trail.count()==1
    trail.undo(mark1);assert trail.count()==2
    trail.undo(mark0);assert trail.count()==3
    cert={"status":"PASS","source_sha256":SHA,
          "source_id":30,"source_family":"hardware-miter",
          "derived_clauses":proofs,"conditions":[-771,-772],
          "conditioned_exact_models":len(joined),
          "conditioned_separate_affine_models":len(approx),
          "nonlinear_gap_bits":1,
          "conditioned_relation":"x1=x3=x777",
          "conditioned_local_choice_states_before":8,
          "conditioned_local_choice_states_after":2,
          "conditional_alias_representatives_before":3,
          "conditional_alias_representatives_after":1,
          "guarded_alias_backtrack":"PASS",
          "original_cnf_rup_certificates":2,
          "new_math_theorem_claim":False,"speed_test":False,
          "warning":"Local search compression is not an end-to-end solving gain."}
    return cert

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path)
    p.add_argument("--output",type=Path,default=Path("delta3_semantic/semantic_certificate.json"))
    args=p.parse_args()
    if args.source:src=args.source
    else:
        files=list(Path("real36_frozen/cases").glob("030_*.cnf"))
        assert len(files)==1,"MISSING_PINNED_REAL36_SOURCE"
        src=files[0]
    result=evaluate(src)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DELTA3_SEMANTIC_USE_PASS",json.dumps({
       "original_sha":result["source_sha256"],"proofs":result["original_cnf_rup_certificates"],
       "local_models":result["conditioned_exact_models"],
       "affine_models":result["conditioned_separate_affine_models"],
       "backtracking":result["guarded_alias_backtrack"]},sort_keys=True))

if __name__=="__main__":main()
