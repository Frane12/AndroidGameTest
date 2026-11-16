#!/usr/bin/env python3
"""Independent original-byte verifier for all UNION prefix certificates.

Trust only checkers that re-read ORIGINAL DIMACS. Absence of a standard
DRAT/LRAT/VeriPB certificate is recorded as STRUCTURAL_CUSTOM.
"""
import argparse,hashlib,json,sys
from collections import defaultdict,deque
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RESEARCH))
from structure1_checker import check as verify_structure1
from match2_checker import verify as verify_match2
from match2_bdd_mask1_checker import check as verify_mask1
from ipg_bdd_checker import read_source

def independent_binary_check(raw,cert):
    n,_,clauses=read_source(raw)
    if cert.get("witness")=="EMPTY_SOURCE_CLAUSE":
        if frozenset() not in clauses:raise ValueError("empty source clause missing")
        return {"binary_empty_source_clause":True}
    if cert.get("witness")!="CONTRADICTORY_IMPLICATION_CYCLE":
        raise ValueError("unknown 2CNF witness")
    v=cert.get("variable")
    if type(v)!=int or not 1<=v<=n:raise ValueError("invalid conflict variable")
    adj=defaultdict(set)
    for clause in clauses:
        if len(clause)==1:
            lit=next(iter(clause))
            adj[-lit].add(lit)
        elif len(clause)==2:
            a,b=tuple(clause)
            adj[-a].add(b)
            adj[-b].add(a)
    def reaches(src,dst):
        todo=deque([src]);seen={src}
        while todo:
            w=todo.popleft()
            if w==dst:return True
            for nxt in adj[w]:
                if nxt not in seen:
                    seen.add(nxt);todo.append(nxt)
        return False
    if not (reaches(v,-v) and reaches(-v,v)):
        raise ValueError("source binary clauses do not imply contradiction")
    return {"contradiction_variable":v,"forward_and_reverse_paths":True}

def check(raw,cert):
    if cert.get("format")!="DRNAS-UNION-PRECHECK-V1":
        raise ValueError("wrong outer certificate format")
    if cert.get("source_sha256")!=hashlib.sha256(raw).hexdigest():
        raise ValueError("original input bytes differ")
    if cert.get("status")!="UNSAT_UNCHECKED":
        raise ValueError("not a proof")
    method=cert.get("method")
    if method=="SOURCE_BINARY_SUBSET":
        info=independent_binary_check(raw,cert)
    else:
        inner=cert.get("inner")
        if not isinstance(inner,dict) or inner.get("status")!="UNSAT_UNCHECKED":
            raise ValueError("missing inner proof")
        if method=="STRUCTURE1":info=verify_structure1(raw,inner)
        elif method=="MATCH2":info=verify_match2(raw,inner)
        elif method=="MASK1":info=verify_mask1(raw,inner)
        else:raise ValueError("unknown method")
    return {"status":"UNION_PRECHECK_VERIFIED","method":method,
            "source_sha256":hashlib.sha256(raw).hexdigest(),"proof":info}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("cnf",type=Path);parser.add_argument("certificate",type=Path)
    args=parser.parse_args()
    try:
        result=check(args.cnf.read_bytes(),json.loads(args.certificate.read_text()))
        print("UNION_PRECHECK_VERIFIED "+json.dumps(result,sort_keys=True),flush=True)
    except (ValueError,KeyError,TypeError,IndexError,OSError,OverflowError,UnicodeError) as error:
        print("UNION_PRECHECK_REJECTED "+str(error),flush=True)
        raise SystemExit(1)
