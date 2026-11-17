#!/usr/bin/env python3
"""Standard VeriPB 3.0 source-bound mixed XOR2/XOR3/XOR4 parity proof.

For XOR4(x,y,z,w)=b, introduce fresh q=x XOR y with four RED
definition clauses. Via three independently RUP-checked steps for
each forbidden 3-XOR assignment, derive XOR3(q,z,w)=b from the
*original* XOR4 source and the fresh definition. Emit two 3-XOR rows:
XOR3(x,y,q)=0 and XOR3(q,z,w)=b. Fresh q occurs exactly twice.

XOR2(b=1) uses its two original clauses; XOR2(b=0) introduces
a fresh AND carry with RED and derives its reverse implications
using RUP. All XOR3 rows use the previously VeriPB-accepted
carry RED/RUP/CP procedure. Every source and fresh variable must
occur exactly twice across the transformed rows, and all RHS
values sum to odd parity. Final CP division produces 0>=1.

This source is not trusted by itself: only external VeriPB 3.0.2
acceptance on the original unchanged CNF earns strict UNSAT.
"""
import argparse
from collections import Counter
from itertools import product
from pathlib import Path
import hashlib,json,sys,time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"/"math5"))
from check_math5 import verify as independent_source_check

class Unsupported(ValueError):pass

def need(ok,message):
    if not ok:raise Unsupported(message)

def ordered_dimacs(raw):
    need(len(raw)<=12_000_000,"original CNF size limit")
    nv=nc=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        fields=line.split()
        if not fields or fields[0]=="c":continue
        if fields[0]=="p":
            need(nv is None and len(fields)==4 and fields[1]=="cnf","bad source header")
            nv,nc=map(int,fields[2:])
            need(0<nv<=6000 and 0<=nc<=100000,"source variable/clause budget")
            continue
        need(nv is not None,"missing DIMACS header")
        for token in fields:
            lit=int(token)
            need(abs(lit)<=nv,"source literal beyond DIMACS header")
            if lit:pending.append(lit)
            else:
                clauses.append(tuple(pending));pending=[]
    need(nv and not pending and len(clauses)==nc,"source clause count mismatch")
    return nv,clauses

class Proof:
    def __init__(self,source_clauses):
        self.lines=["pseudo-Boolean proof version 3.0",
                    f"f {len(source_clauses)} ;"]
        self.ids={}
        for idx,clause in enumerate(source_clauses,1):
            self.ids.setdefault(frozenset(clause),idx)
        self.last=len(source_clauses)
        self.count=Counter()
    @staticmethod
    def clause(lits):
        return " ".join("1 "+("~" if lit<0 else "")+"x"+str(abs(lit))
                        for lit in lits)+" >= 1"
    def red(self,lits,var,val):
        self.lines.append("red "+self.clause(lits)+f" : x{var} -> {val} ;")
        self.last+=1;self.count["RED"]+=1
        self.ids.setdefault(frozenset(lits),self.last)
        return self.last
    def rup(self,lits):
        self.lines.append("rup "+self.clause(lits)+" ;")
        self.last+=1;self.count["RUP"]+=1
        self.ids.setdefault(frozenset(lits),self.last)
        return self.last
    def pol(self,ops):
        self.lines.append("pol "+" ".join(map(str,ops))+" ;")
        self.last+=1;self.count["CP"]+=1
        return self.last
    def summation(self,ids):
        need(bool(ids),"empty proof sum")
        ops=[str(ids[0])]
        for line_id in ids[1:]:ops.extend((str(line_id),"+"))
        return self.pol(ops)

def compile_source(raw,certificate):
    started=time.perf_counter()
    checked=independent_source_check(raw,certificate)
    need(checked.get("status")=="UNSAT_MATH5_CERTIFICATE_VERIFIED",
         "independent original source checker rejected proof")
    need(certificate.get("format")=="drnas-math5-eo-xor-unit-v1",
         "unexpected certificate format")
    need(not certificate.get("exact_one_groups") and
         not certificate.get("root_units"),
         "not a pure XOR source certificate")
    rows=certificate.get("xor_rows")
    need(isinstance(rows,list) and 1<=len(rows)<=1500,
         "XOR source row bound")
    need(all(2<=len(row["vars"])<=4 for row in rows),
         "XOR rows must have width 2, 3, or 4")
    degrees=Counter(var for row in rows for var in row["vars"])
    need(set(degrees.values())=={2},
         "selected original XOR variable must occur exactly twice")
    need(sum(1-row["forbidden_parity"] for row in rows)%2==1,
         "selected XOR equations have no odd parity contradiction")
    nv,original=ordered_dimacs(raw)
    p=Proof(original)
    next_var=nv
    transformed=[]
    widths=Counter()
    def forbidding_clause(variables,bits):
        return tuple(-v if bit else v for v,bit in zip(variables,bits))
    for row in rows:
        vars=tuple(row["vars"])
        width=len(vars)
        rhs=1-row["forbidden_parity"]
        widths[width]+=1
        need(len(set(vars))==width,"source XOR duplicate variable")
        for bits in product((0,1),repeat=width):
            if sum(bits)%2!=rhs:
                need(frozenset(forbidding_clause(vars,bits)) in p.ids,
                     "original XOR clause missing")
        if width<=3:
            transformed.append((vars,rhs))
            continue
        x,y,z,w=vars
        next_var+=1;q=next_var
        # Introduce fresh q=x XOR y using four VeriPB RED clauses.
        for bx,by in product((0,1),repeat=2):
            value=bx^by
            invalid=forbidding_clause((x,y,q),(bx,by,1-value))
            p.red(invalid,q,value)
        transformed.append(((x,y,q),0))
        # Source plus definition entails XOR3(q,z,w)=rhs.
        # Prove each of its four clauses via bounded RUP resolution on x.
        for bq,bz,bw in product((0,1),repeat=3):
            if (bq+bz+bw)%2==rhs:continue
            guarded=forbidding_clause((q,z,w),(bq,bz,bw))
            p.rup(guarded+(x,))
            p.rup(guarded+(-x,))
            p.rup(guarded)
        transformed.append(((q,z,w),rhs))
    counts=Counter(var for variables,_ in transformed for var in variables)
    need(set(counts.values())=={2},
         "transformed original/fresh XOR variable degrees are not two")
    need(sum(rhs for _,rhs in transformed)%2==1,
         "transformed XOR parity changed")
    lowers=[];uppers=[]
    for vars,rhs in transformed:
        if len(vars)==2:
            x,y=vars
            if rhs==1:
                lowers.append(p.ids[frozenset((x,y))])
                uppers.append(p.ids[frozenset((-x,-y))])
                continue
            next_var+=1;t=next_var
            first=p.red((-t,x),t,0)
            second=p.red((-t,y),t,0)
            p.red((t,-x,-y),t,1)
            lowers.append(p.pol((first,second,"+")))
            first=p.rup((-x,t))
            second=p.rup((-y,t))
            uppers.append(p.pol((first,second,"+")))
            continue
        x,y,z=vars
        next_var+=1;t=next_var
        if rhs==1:
            defs=[p.red((-t,v),t,0) for v in vars]
            p.red((t,-x,-y,-z),t,1)
            alo=p.ids[frozenset(vars)]
            summed=p.summation(defs)
            lower=p.pol((summed,2,"*",alo,"+",3,"d"))
            opposite=[p.rup((-a,-b,t))
                      for a,b in ((x,y),(x,z),(y,z))]
            summed=p.summation(opposite)
            upper=p.pol((summed,2,"d"))
        else:
            pairs=((x,y),(x,z),(y,z))
            defs=[p.red((-t,a,b),t,0) for a,b in pairs]
            for a,b in pairs:
                p.red((t,-a,-b),t,1)
            summed=p.summation(defs)
            lower=p.pol((summed,2,"d"))
            opposite=[p.rup((-v,t)) for v in vars]
            summed=p.summation(opposite)
            minus_all=p.ids[frozenset((-x,-y,-z))]
            upper=p.pol((summed,2,"*",minus_all,"+",3,"d"))
        lowers.append(lower)
        uppers.append(upper)
    # Since every original/fresh XOR graph variable has degree 2
    # and the RHS parity is odd, divide both global bounds by 2.
    lower=p.summation(lowers);upper=p.summation(uppers)
    cutlower=p.pol((lower,2,"d"))
    cutupper=p.pol((upper,2,"d"))
    p.pol((cutlower,cutupper,"+"))
    p.lines.extend(("output NONE ;","conclusion UNSAT ;",
                    "end pseudo-Boolean proof ;"))
    need(sum(p.count.values())<=120000,"proof step budget")
    output="\n".join(p.lines)+"\n"
    need(len(output.encode("ascii"))<=6_000_000,"proof bytes budget")
    return output,{
        "status":"EMITTED_EXTERNAL_VERIPB_REQUIRED",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "source_vars":nv,"source_clauses":len(original),
        "source_xor_rows":len(rows),"source_xor_widths":dict(widths),
        "transformed_rows":len(transformed),
        "fresh_vars":next_var-nv,"steps":dict(p.count),
        "proof_bytes":len(output.encode("ascii")),
        "emission_s":round(time.perf_counter()-started,6),
        "source_proof_independently_checked_before_emission":True,
        "external_standard_verifier_required":True,
        "no_general_SAT_claim":True}

def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("--cnf",required=True,type=Path)
    arg.add_argument("--certificate",required=True,type=Path)
    arg.add_argument("--output",required=True,type=Path)
    arg.add_argument("--meta",type=Path)
    a=arg.parse_args()
    try:
        raw=a.cnf.read_bytes()
        cert=json.loads(a.certificate.read_text())
        pb,meta=compile_source(raw,cert)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(pb)
        if a.meta:
            a.meta.write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n")
        print("MATH5_XOR234_VERIPB_EMITTED "+json.dumps(meta,sort_keys=True),
              flush=True)
        return 0
    except (Unsupported,ValueError,TypeError,KeyError,IndexError,
            UnicodeError,OverflowError,OSError,AssertionError) as err:
        a.output.unlink(missing_ok=True)
        if a.meta:a.meta.unlink(missing_ok=True)
        print("MATH5_XOR234_VERIPB_UNSUPPORTED "+str(err),flush=True)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
