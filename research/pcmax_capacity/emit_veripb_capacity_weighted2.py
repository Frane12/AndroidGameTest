#!/usr/bin/env python3
"""Experimental weighted source-bound VeriPB 3.0 proofs via BDD-state PB induction.

No SAT oracle, CDCL fallback, or trusted Python verdict is used to certify UNSAT.
Every emitted proof MUST be checked against unchanged original CNF by VeriPB 3.
Source BDD edges, roots, terminals, groups, and SHA are checked independently.
Proof by contradiction at each BDD node avoids exponential cover enumeration.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from check_capacity import check as structural_check
from emit_veripb_capacity1 import dimacs

def expr(terms, rhs):
    assert rhs > 0
    s=" ".join(f"{int(coeff)} {'~' if negative else ''}x{int(var)}"
               for coeff,var,negative in terms if coeff)
    return f"{s} >= {rhs}"

class Proof:
    def __init__(self, out, nclauses, clause_ids):
        self.fd=out
        self.last=nclauses
        self.index=clause_ids
        self.pbc_count=0
        self.dead_count=0
        self.pol_count=0
        self.fd.write("pseudo-Boolean proof version 3.0\n")
        self.fd.write(f"f {nclauses} ;\n")

    def pol(self, tokens):
        if not tokens:
            raise ValueError("empty CP derivation")
        self.fd.write("pol "+" ".join(map(str,tokens))+" ;\n")
        self.last+=1
        self.pol_count+=1
        return self.last

    def dead(self, node):
        self.fd.write(f"rup 1 ~x{node} >= 1 ;\n")
        self.last+=1
        self.dead_count+=1
        return self.last

    @staticmethod
    def add_literal(tokens, var, coeff=1, negated=True):
        if coeff<1: return
        tokens.append(("~" if negated else "")+"x"+str(var))
        if coeff!=1:tokens.extend([str(coeff),"*"])
        tokens.append("+")

    @staticmethod
    def add_id(tokens, cid, factor=1):
        if factor<1: return
        tokens.append(str(cid))
        if factor!=1:tokens.extend([str(factor),"*"])
        tokens.append("+")

    def bdd_machine(self, machine, weight):
        order=machine["variable_order"]
        rank={v:i for i,v in enumerate(order)}
        if len(rank)!=len(order):
            raise ValueError("nonunique BDD order")
        transitions={a:(v,lo,hi) for a,v,lo,hi in machine["transitions"]}
        root=machine["root"]; true=machine["true_terminal"]; false=machine["false_terminal"]
        n=len(order)
        vrank={p:rank[t[0]] for p,t in transitions.items()}
        vrank[true]=vrank[false]=n
        prefix=[0]
        for v in order:prefix.append(prefix[-1]+weight.get(v,0))
        best={true:0,false:None}
        parents=sorted(transitions, key=lambda p:vrank[p],reverse=True)
        for p in parents:
            selector,lo,hi=transitions[p]
            r=rank[selector]
            choices=[]
            for child,chosen in ((lo,0),(hi,weight.get(selector,0))):
                if child not in best: raise ValueError("BDD node not ordered")
                if best[child] is not None:
                    skip=prefix[vrank[child]]-prefix[r+1]
                    choices.append(best[child]+skip+chosen)
            best[p]=max(choices) if choices else None
        expected_cap=prefix[vrank[root]]+best[root] if best[root] is not None else None
        if expected_cap!=machine["capacity"]:
            raise ValueError(f"BDD machine capacity differs from source certificate {expected_cap} != {machine['capacity']}")
        finite={} # q -> (constraint ID, deficit)
        dead={}   # q -> source/derived unit constraint ID
        dead[false]=self.index[frozenset((-false,))]
        for p in parents:
            current=best[p]
            if current is None:
                # Dead state: both branches force a dead child, so reverse unit propagation derives ~p.
                if any(best[ch] is not None for ch in transitions[p][1:]):
                    raise ValueError("inconsistent dead BDD node")
                dead[p]=self.dead(p)
                continue
            r=vrank[p]
            suffix_weight=prefix[n]-prefix[r]
            D=suffix_weight-current
            if D<0:
                raise ValueError("negative BDD deficit")
            if D==0:
                continue
            x,lo,hi=transitions[p]
            wx=weight.get(x,0)
            if p in dead:
                raise ValueError("contradictory state classification")
            negp_id=self.last+1
            terms=[(D,p,True)]+[(weight.get(v,0),v,True) for v in order[r:]]
            self.fd.write("pbc "+expr(terms,D)+" : subproof\n")
            # The negation of pbc's target gets an ID scoped to this subproof.
            self.last+=1

            def branch_tokens(child, high):
                next_rank=vrank[child]
                if best[child] is None:
                    B=max(1, D if high else D-wx)
                    cid=dead[child]
                    mult=B
                else:
                    B=prefix[n]-prefix[next_rank]-best[child]
                    if B<0: raise ValueError("negative child deficit")
                    if B:
                        if child not in finite:
                            raise ValueError("missing inductive child PB bound")
                        cid=finite[child][0];mult=1
                    else:
                        cid=None;mult=0
                tokens=[str(negp_id)]
                if cid is not None:
                    self.add_id(tokens,cid,mult)
                for pos in range(r+1,next_rank):
                    v=order[pos]
                    self.add_literal(tokens,v,weight.get(v,0))
                if B:
                    edge=((-p,-x,child) if high else (-p,x,child))
                    tid=self.index.get(frozenset(edge))
                    if tid is None: raise ValueError("transition not from original CNF")
                    self.add_id(tokens,tid,B)
                tokens.extend([f"x{p}","w"])
                return tokens,B

            low,A=branch_tokens(lo,False)
            if D> A+wx:
                raise ValueError("invalid low-case potential")
            self.pol_count+=1
            low.extend([str(wx+A),"d"]) if wx+A>1 else None
            self.fd.write("pol "+" ".join(low)+" ;\n")
            self.last+=1
            left_id=self.last

            high,B=branch_tokens(hi,True)
            if D>B:
                raise ValueError("invalid high-case potential")
            if B>wx:
                if B-wx>1: high.extend([str(B-wx),"d"])
            self.fd.write("pol "+" ".join(high)+" ;\n")
            self.last+=1
            self.pol_count+=1
            right_id=self.last
            if B>wx:
                self.pol([str(left_id),str(right_id),"+"])
            # Otherwise the high-case CP line itself is a contradiction.
            self.fd.write("qed;\n")
            self.last+=1
            finite[p]=(self.last,D)
            self.pbc_count+=1

        owned=[v for v in order if weight.get(v,0)>0]
        if not owned:
            if machine["capacity"]!=0:
                raise ValueError("empty selected machine has nonzero capacity")
            return None
        D=prefix[n]-machine["capacity"]
        if D<0: raise ValueError("machine > total selected weight")
        if D:
            root_id,root_d=finite[root]
            if root_d!=D:raise ValueError("root capacity mismatch")
            tokens=[str(root_id)]
            root_unit=self.index[frozenset((root,))]
            self.add_id(tokens,root_unit,D)
        else:
            # Vacuous 0-deficit bound, made explicit by literal axioms.
            v=owned[0]
            tokens=["~x"+str(v)]
            if weight[v]>1:tokens += [str(weight[v]),"*"]
            owned=owned[1:]
        for v in owned[:0] if D==0 else []:
            pass
        # For positive deficit, the root inequality has suffix selectors only,
        # and the input root unit discharges its state literal.
        # For zero deficit, a literal-axiom sum is already a valid bound.
        lead=order[:vrank[root]] if D else owned
        for v in lead:
            self.add_literal(tokens,v,weight.get(v,0))
        # If D==0 the first owned literal was already added above.
        return self.pol(tokens)

    def finish(self, weighted_group_ids, machine_bounds):
        tokens=[]
        for clause_id,weight in weighted_group_ids:
            if not tokens:
                tokens=[str(clause_id)]
                if weight>1: tokens += [str(weight),"*"]
            else:
                self.add_id(tokens,clause_id,weight)
        for mid in machine_bounds:
            if mid is None:continue
            if not tokens:tokens=[str(mid)]
            else:self.add_id(tokens,mid)
        if not tokens: raise ValueError("empty contradiction proof")
        self.pol(tokens)
        self.fd.write("output NONE ;\n")
        self.fd.write("conclusion UNSAT ;\n")
        self.fd.write("end pseudo-Boolean proof ;\n")


def generate(cnf_path,certificate_path,output_path):
    started=time.perf_counter()
    raw=Path(cnf_path).read_bytes()
    cert=json.loads(Path(certificate_path).read_text())
    sha=hashlib.sha256(raw).hexdigest()
    if cert.get("source_sha256")!=sha:
        raise ValueError("original CNF hash mismatch")
    outcome=structural_check(raw,cert)
    if outcome.get("status")!="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED":
        raise ValueError("structural checker rejected source")
    nvar,clauses=dimacs(raw)
    index={}
    for i,c in enumerate(clauses,1):index.setdefault(frozenset(c),i)
    groups=cert["selected_groups"]
    weights=cert["group_weights"]
    if len(groups)!=len(weights) or not groups or any(type(w)!=int or w<1 for w in weights):
        raise ValueError("unsupported nonpositive or inconsistent weights")
    owner={}
    wsel={}
    for group,w in zip(groups,weights):
        if frozenset(group) not in index:raise ValueError("group clause absent in original CNF")
        for v in group:
            if v in owner:raise ValueError("overlapping selected groups")
            owner[v]=1
            wsel[v]=w
    machines=cert["machines"]
    machine_vars=set(v for m in machines for v in m["variable_order"])
    if not set(owner).issubset(machine_vars):
        raise ValueError("uncovered group selector")
    if sum(weights)<=sum(m["capacity"] for m in machines):
        raise ValueError("no strict capacity contradiction")
    output=Path(output_path)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("w") as fd:
        proof=Proof(fd,len(clauses),index)
        bounds=[proof.bdd_machine(m,wsel) for m in machines]
        weighted_groups=[(index[frozenset(g)],w) for g,w in zip(groups,weights)]
        proof.finish(weighted_groups,bounds)
        bytes_written=fd.tell()
        result={
            "status":"EMITTED_UNCHECKED","format":"VeriPB3.0",
            "source_sha256":sha,"source_variables":nvar,"source_clauses":len(clauses),
            "required":sum(weights),"capacity_sum":sum(m["capacity"] for m in machines),
            "group_weights_distinct":sorted(set(weights)),
            "machine_count":len(machines),
            "bdd_transitions":sum(len(m["transitions"]) for m in machines),
            "pbc_state_lemmas":proof.pbc_count,"dead_state_rup":proof.dead_count,
            "pol_steps":proof.pol_count,"proof_bytes":bytes_written,
            "generator_s":round(time.perf_counter()-started,6),
        }
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--cnf",type=Path,required=True)
    parser.add_argument("--certificate",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        result=generate(args.cnf,args.certificate,args.output)
        print("PCMAX_WEIGHTED_PB_EMITTED "+json.dumps(result,sort_keys=True),flush=True)
    except (OSError,ValueError,AssertionError,KeyError,TypeError) as exc:
        print("PCMAX_WEIGHTED_PB_UNKNOWN "+str(exc),flush=True)
        Path(args.output).unlink(missing_ok=True)
        return 1
    return 0

if __name__=="__main__":
    sys.exit(main())
