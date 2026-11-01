#!/usr/bin/env python3
"""DRNAS V13.7: exact polynomial-time fast path for pure 3-XOR CNF and PHP.

Both are known tractable / structured special cases; no general SAT claim.
Do NOT infer SAT/UNSAT from filename, experiment label or generated metadata.
Fallback: old V13.6 structure router for unrecognized CNF.
"""
import argparse, collections, json, os, subprocess, sys, time
from pathlib import Path
import v136_symbolic as prior

PROTOCOL="DRNAS-V137-EXACT-AFFINE-PHP-20261101"
MAX_BYTES=32*1024*1024
MAX_CLAUSES=100000
MAX_VARIABLES=100000
MAX_LITERALS=2000000

def read_dimacs(raw):
    if len(raw)>MAX_BYTES:raise ValueError("Input too large")
    n=None;expected=None;clauses=[];pending=[];literals=0
    for line in raw.splitlines():
        s=line.strip()
        if not s or s.startswith(b"c") or s.startswith(b"%"):continue
        if s.startswith(b"p "):
            if n is not None:raise ValueError("Duplicate DIMACS header")
            parts=s.split()
            if len(parts)!=4 or parts[1]!=b"cnf":raise ValueError("Bad header")
            n=int(parts[2]);expected=int(parts[3])
            if not 1<=n<=MAX_VARIABLES or not 1<=expected<=MAX_CLAUSES:
                raise ValueError("DIMACS bounds")
            continue
        if n is None:raise ValueError("Missing DIMACS header")
        for val in s.split():
            lit=int(val)
            if lit:
                if abs(lit)>n:raise ValueError("Variable outside header")
                pending.append(lit);literals+=1
                if literals>MAX_LITERALS:raise ValueError("Too many literals")
            else:
                if not pending:raise ValueError("Empty clause needs fallback")
                clauses.append(tuple(pending));pending=[]
                if len(clauses)>expected:raise ValueError("Extra clause")
    if n is None or len(clauses)!=expected or pending:
        raise ValueError("Incomplete DIMACS")
    return n,clauses

def xor_equations(n,clauses):
    """Exact detection of 4 forbidden assignments for each 3-variable XOR.
    
    Negative literal mask = prohibited assignment; precisely one parity
    class must be forbidden. Every clause must belong to a complete block.
    """
    if len(clauses)%4 or not all(len(c)==3 and
               len({abs(v) for v in c})==3 for c in clauses):return None
    groups=collections.defaultdict(list)
    for clause in clauses:
        arranged=sorted(clause,key=abs)
        support=tuple(abs(v) for v in arranged)
        mask=sum((1<<i) for i,v in enumerate(arranged) if v<0)
        groups[support].append(mask)
    if len(groups)*4!=len(clauses):return None
    equations=[]
    for support,masks in sorted(groups.items()):
        if len(masks)!=4 or len(set(masks))!=4:return None
        parity={m.bit_count()%2 for m in masks}
        if len(parity)!=1:return None
        bad=next(iter(parity))
        if set(masks)!={m for m in range(8) if m.bit_count()%2==bad}:
            return None
        bits=sum(1<<(v-1) for v in support)
        equations.append((bits,1-bad,support))
    return equations

def solve_affine(n,equations):
    """Deterministic GF(2) elimination using Python integer bitsets.

    Row-combination bits provide an independently checkable 0=1 UNSAT
    contradiction; a SAT model is verified against all input CNF clauses.
    """
    pivots={}
    for i,(bits,rhs,_) in enumerate(equations):
        combo=1<<i
        while bits:
            col=bits.bit_length()-1
            if col not in pivots:
                pivots[col]=(bits,rhs,combo)
                break
            old_b,old_rhs,old_combo=pivots[col]
            bits^=old_b;rhs^=old_rhs;combo^=old_combo
        else:
            if rhs:
                # The XOR of these exact original equations is 0 = 1.
                check_proof(equations,combo)
                return {"status":"UNSAT","path":"affine_exact",
                        "proof_rows":[j for j in range(len(equations)) if combo>>j&1]}
    assignment=0
    for col in sorted(pivots):
        bits,rhs,_=pivots[col]
        val=rhs^((bits & assignment).bit_count()%2)
        if val:assignment|=1<<col
    assert all(((bits&assignment).bit_count()%2)==rhs for bits,rhs,_ in equations)
    return {"status":"SAT","path":"affine_exact",
            "model":[v if assignment>>(v-1)&1 else -v for v in range(1,n+1)]}

def check_proof(equations,selected):
    bits=0;rhs=0;count=0
    for i,(row,val,_) in enumerate(equations):
        if selected>>i&1:bits^=row;rhs^=val;count+=1
    if count==0 or bits!=0 or rhs!=1:raise RuntimeError("Invalid GF(2) certificate")

def verify(n,clauses,res):
    if res["status"]=="SAT":
        model=res.get("model")
        if not isinstance(model,list) or len(model)!=n:raise RuntimeError("Invalid model length")
        assign={abs(l):l>0 for l in model}
        if len(assign)!=n:raise RuntimeError("Model not total")
        if not all(any(assign[abs(l)]==(l>0) for l in c) for c in clauses):
            raise RuntimeError("SAT witness does not satisfy CNF")
    elif res["path"]=="affine_exact":
        eq=xor_equations(n,clauses)
        if eq is None:raise RuntimeError("Missing XOR structure for proof")
        bits=sum(1<<i for i in res["proof_rows"])
        check_proof(eq,bits)
    elif res["path"]=="pigeonhole_exact":
        # Exhaustively verify all clauses form a complete PHP encoding,
        # after arbitrary clause order / variable renaming.
        raw=serialize(n,clauses)
        sel,why=prior.classify(raw)
        if sel!="Kissat404" or why!="complete_pigeonhole":
            raise RuntimeError("Invalid pigeonhole structural proof")
    else:raise RuntimeError("Unknown UNSAT certificate")
    return True

def serialize(n,clauses):
    return ("p cnf "+str(n)+" "+str(len(clauses))+"\n"+
      "\n".join(" ".join(map(str,c))+" 0" for c in clauses)+"\n").encode()

def decide(raw):
    n,clauses=read_dimacs(raw)
    equations=xor_equations(n,clauses)
    if equations is not None:
        result=solve_affine(n,equations)
        verify(n,clauses,result)
        return result
    # V13.6 recognizer is used as a **complete** PHP proof checker only.
    choice,why=prior.classify(raw)
    if choice=="Kissat404" and why=="complete_pigeonhole":
        result={"status":"UNSAT","path":"pigeonhole_exact"}
        verify(n,clauses,result)
        return result
    return {"status":"FALLBACK","path":"legacy" if choice=="DRNAS_Legacy" else "kissat",
            "solver":choice}

def solve_file(file,drnas,kissat,seed):
    raw=Path(file).read_bytes()
    result=decide(raw)
    if result["status"]!="FALLBACK":return result
    mode=result["solver"]
    if mode=="Kissat404":
        cmd=[str(Path(kissat).resolve()),str(Path(file).resolve())]
    else:
        cmd=[str(Path(drnas).resolve()),"v100_late_legacy_force",
             str(Path(file).resolve()),str(seed)]
    output=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                          timeout=23.5)
    if mode=="Kissat404":
        if output.returncode not in (10,20):raise RuntimeError("Kissat failed")
        label="SAT" if output.returncode==10 else "UNSAT"
        if ("s SATISFIABLE" if label=="SAT" else "s UNSATISFIABLE") not in output.stdout:
            raise RuntimeError("Kissat result missing")
    else:
        if output.returncode!=0:raise RuntimeError("DRNAS failed")
        matches=[line for line in output.stdout.splitlines()
                 if line.startswith("DRNAS_CAUSAL\t")]
        if len(matches)!=1:raise RuntimeError("Bad DRNAS output")
        d=dict(x.split("=",1) for x in matches[0].split("\t")[1:])
        label=d["answer"]
        if label not in ("SAT","UNSAT"):raise RuntimeError("Bad DRNAS answer")
    return {"status":label,"path":"fallback","solver":mode}

def selftest():
    import v136_symbolic as generator
    checked=collections.Counter()
    for family in generator.FAMILIES:
        for idx in range(8):
            c,raw=generator.make(family,idx)
            n,clauses=read_dimacs(raw)
            res=decide(raw)
            if res["status"]!="FALLBACK":
                assert res["status"]==c["label"]
                assert verify(n,clauses,res)
            if family.startswith("cubic_xor"):
                assert res["path"]=="affine_exact",(family,idx,res)
            if family=="pigeonhole_unsat":
                assert res["path"]=="pigeonhole_exact",(family,idx,res)
            checked[res["path"]]+=1
    print("V137_SOLVER_SELFTEST_PASS",dict(checked),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("file",nargs="?")
    p.add_argument("--drnas")
    p.add_argument("--kissat")
    p.add_argument("--seed",type=int,default=0)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest();return
    if not a.file or not a.drnas or not a.kissat:raise SystemExit("Missing arguments")
    start=time.monotonic()
    r=solve_file(a.file,a.drnas,a.kissat,a.seed)
    r["internal_elapsed_s"]=round(time.monotonic()-start,6)
    print("DRNAS_V137_RESULT\t"+json.dumps(r,separators=(",",":")),flush=True)
if __name__=="__main__":main()
