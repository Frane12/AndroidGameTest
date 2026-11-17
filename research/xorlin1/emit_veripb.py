#!/usr/bin/env python3
"""XOR-LIN1: source-supported GF2 contradictory subset -> standard VeriPB.

Accepts only a SHA-bound MATH5-compatible XOR-only certificate independently
verified against original CNF by check_math5.py. Selected XOR equation widths
2..6; selected source variables must occur an even (not necessarily two)
number of times, with odd summed RHS. Split wider XOR via fresh RED xor
extensions; derive all reduced clauses by RUP on each discarded variable,
then certify ternary and binary integer parity equations by RED/RUP/CP.
Sum and divide both global bounds by 2 to get 0>=1.

The emitted PBP is NOT a certificate until external VeriPB 3.0.2 accepts
on the unchanged original source. No assumptions based on family/filename,
no general SAT complexity claim and no change to frozen reference solvers.
"""
from collections import Counter
from itertools import product
from pathlib import Path
import argparse,hashlib,json,sys,time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/math5"))
from check_math5 import verify as independent_source_verify

class Unsupported(ValueError):pass

def require(cond,msg):
    if not cond:raise Unsupported(msg)

def parse_cnf(raw):
    require(len(raw)<=12_000_000,"original source bytes budget")
    nv=nc=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        toks=line.split()
        if not toks or toks[0]=="c":continue
        if toks[0]=="p":
            require(nv is None and len(toks)==4 and toks[1]=="cnf","header")
            nv,nc=int(toks[2]),int(toks[3])
            require(0<nv<=6000 and 0<=nc<=100000,"source checker limits")
            continue
        require(nv is not None,"missing header")
        for col in toks:
            x=int(col)
            require(abs(x)<=nv,"variable over header bound")
            if x:pending.append(x)
            else:clauses.append(tuple(pending));pending=[]
    require(nv is not None and not pending and len(clauses)==nc,"source count")
    return nv,clauses

class Proof:
    def __init__(self,source):
        self.lines=["pseudo-Boolean proof version 3.0",f"f {len(source)} ;"]
        self.index={}
        for row_id,row in enumerate(source,1):
            self.index.setdefault(frozenset(row),row_id)
        self.last=len(source)
        self.steps=Counter()
    @staticmethod
    def clause(lits):
        return " ".join("1 "+("~" if v<0 else "")+"x"+str(abs(v))
                        for v in lits)+" >= 1"
    def red(self,lits,variable,witness):
        self.lines.append("red "+self.clause(lits)+
                          f" : x{variable} -> {witness} ;")
        self.last+=1;self.steps["RED"]+=1
        self.index.setdefault(frozenset(lits),self.last)
        return self.last
    def rup(self,lits):
        self.lines.append("rup "+self.clause(lits)+" ;")
        self.last+=1;self.steps["RUP"]+=1
        self.index.setdefault(frozenset(lits),self.last)
        return self.last
    def pol(self,ops):
        self.lines.append("pol "+" ".join(map(str,ops))+" ;")
        self.last+=1;self.steps["CP"]+=1
        return self.last
    def add(self,ids):
        require(bool(ids),"cannot sum empty constraints")
        ops=[str(ids[0])]
        for line_id in ids[1:]:ops.extend((str(line_id),"+"))
        return self.pol(ops)

def compile_source(raw,cert):
    t=time.perf_counter()
    checked=independent_source_verify(raw,cert)
    require(checked["status"]=="UNSAT_MATH5_CERTIFICATE_VERIFIED",
            "independent original-CNF checker rejected proof")
    require(cert.get("format")=="drnas-math5-eo-xor-unit-v1","bad proof format")
    require(not cert.get("exact_one_groups") and not cert.get("root_units"),
            "not pure XOR source certificate")
    rows=cert.get("xor_rows")
    require(type(rows) is list and 1<=len(rows)<=1500,"XOR source row budget")
    require(all(type(r)==dict and 2<=len(r["vars"])<=6 for r in rows),
            "only XOR widths 2..6 supported")
    degrees=Counter(v for row in rows for v in row["vars"])
    require(bool(degrees) and all(degree%2==0 for degree in degrees.values()),
            "selected source XOR variables must have even incidence")
    require(sum(1-row["forbidden_parity"] for row in rows)%2==1,
            "selected parity sum not contradictory")

    nv,clauses=parse_cnf(raw)
    pb=Proof(clauses)
    fresh=nv
    transformed=[]
    widths=Counter()
    def falsify(vars,bits):
        return tuple(-v if bit else v for v,bit in zip(vars,bits))
    for row in rows:
        variables=tuple(row["vars"])
        width=len(variables)
        rhs=1-row["forbidden_parity"]
        widths[width]+=1
        require(len(set(variables))==width,"duplicate source XOR variable")
        for bits in product((0,1),repeat=width):
            if sum(bits)%2!=rhs:
                require(frozenset(falsify(variables,bits)) in pb.index,
                        "missing forbidden original source XOR clause")
        cur=variables
        while len(cur)>3:
            x,y,*rest=cur
            fresh+=1
            q=fresh
            # Source-independent q<->x XOR y extension: RED witnesses.
            for bx,by in product((0,1),repeat=2):
                xor=bx^by
                pb.red(falsify((x,y,q),(bx,by,1-xor)),q,xor)
            transformed.append(((x,y,q),0))
            next_vars=(q,*rest)
            # Each new (w-1)-XOR source row is derived from the previous
            # w-XOR clauses, with resolution on x using 3 RUP steps.
            for bits in product((0,1),repeat=len(next_vars)):
                if sum(bits)%2==rhs:continue
                guard=falsify(next_vars,bits)
                pb.rup(guard+(x,))
                pb.rup(guard+(-x,))
                pb.rup(guard)
            cur=next_vars
        transformed.append((cur,rhs))

    expanded=Counter(v for vars,_ in transformed for v in vars)
    require(all(d%2==0 for d in expanded.values()),
            "transformed source/fresh XOR degrees not even")
    require(sum(rhs for _,rhs in transformed)%2==1,"transformed rhs no longer odd")
    lower=[];upper=[]
    for vars,rhs in transformed:
        if len(vars)==2:
            x,y=vars
            if rhs==1:
                lower.append(pb.index[frozenset((x,y))])
                upper.append(pb.index[frozenset((-x,-y))])
                continue
            fresh+=1;tvar=fresh
            first=pb.red((-tvar,x),tvar,0)
            second=pb.red((-tvar,y),tvar,0)
            pb.red((tvar,-x,-y),tvar,1)
            lower.append(pb.pol((first,second,"+")))
            first=pb.rup((-x,tvar))
            second=pb.rup((-y,tvar))
            upper.append(pb.pol((first,second,"+")))
            continue
        x,y,z=vars
        fresh+=1;tvar=fresh
        if rhs==1:
            forward=[pb.red((-tvar,v),tvar,0) for v in vars]
            pb.red((tvar,-x,-y,-z),tvar,1)
            source_alo=pb.index[frozenset(vars)]
            total=pb.add(forward)
            lo=pb.pol((total,2,"*",source_alo,"+",3,"d"))
            pairs=[pb.rup((-a,-b,tvar))
                   for a,b in ((x,y),(x,z),(y,z))]
            total=pb.add(pairs)
            hi=pb.pol((total,2,"d"))
        else:
            pairs=((x,y),(x,z),(y,z))
            forward=[pb.red((-tvar,a,b),tvar,0) for a,b in pairs]
            for a,b in pairs:pb.red((tvar,-a,-b),tvar,1)
            total=pb.add(forward)
            lo=pb.pol((total,2,"d"))
            singles=[pb.rup((-v,tvar)) for v in vars]
            total=pb.add(singles)
            no111=pb.index[frozenset((-x,-y,-z))]
            hi=pb.pol((total,2,"*",no111,"+",3,"d"))
        lower.append(lo);upper.append(hi)
    low=pb.add(lower);high=pb.add(upper)
    low_cut=pb.pol((low,2,"d"))
    high_cut=pb.pol((high,2,"d"))
    pb.pol((low_cut,high_cut,"+"))
    pb.lines.extend(("output NONE ;","conclusion UNSAT ;",
                     "end pseudo-Boolean proof ;"))
    require(sum(pb.steps.values())<=120000,"proof step budget")
    proof="\n".join(pb.lines)+"\n"
    require(len(proof.encode("ascii"))<=8_000_000,"proof byte budget")
    meta={"status":"PROOF_EMITTED_EXTERNAL_VERIPB_REQUIRED",
          "source_sha256":hashlib.sha256(raw).hexdigest(),
          "source_vars":nv,"source_clauses":len(clauses),
          "selected_xor_rows":len(rows),"source_widths":dict(widths),
          "source_degrees":dict(Counter(degrees.values())),
          "transformed_rows":len(transformed),"fresh_vars":fresh-nv,
          "proof_bytes":len(proof.encode("ascii")),"steps":dict(pb.steps),
          "emitter_elapsed_s":round(time.perf_counter()-t,6),
          "external_standard_checker_required":True}
    return proof,meta

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=Path)
    p.add_argument("--certificate",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--meta",required=True,type=Path)
    a=p.parse_args()
    try:
        proof,meta=compile_source(a.cnf.read_bytes(),
                                  json.loads(a.certificate.read_text()))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(proof)
        a.meta.write_text(json.dumps(meta,sort_keys=True,indent=2)+"\n")
        print("XORLIN1_VERIPB_EMITTED "+json.dumps(meta,sort_keys=True),flush=True)
        return 0
    except (Unsupported,ValueError,KeyError,TypeError,IndexError,
            UnicodeError,OverflowError,OSError,AssertionError) as exc:
        a.output.unlink(missing_ok=True)
        a.meta.unlink(missing_ok=True)
        print("XORLIN1_SAFE_UNKNOWN "+str(exc),flush=True)
        return 2
if __name__=="__main__":
    raise SystemExit(main())
