#!/usr/bin/env python3
"""R32t: independently certified short XOR consequences of original 2026 CNFs.

Only complete original CNF parity blocks are axioms, no SAT labels, timing,
learned clauses, or source metadata can enter the derivation. GF(2) Gaussian
elimination with a source-equation provenance bitset yields entailed parity
rows. New short rows are encoded as additional REDUNDANT clauses appended
to the untouched original clause sequence (no solver or process portfolio).
Every resultant clause can be justified through explicitly recorded GF2
source-combination certificate, independently checked before acceptance.

This is a source-level research prototype, not yet native CDCL-XOR propagation.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,shutil
from pathlib import Path
CAP_BYTES=12*1024*1024
CAP_VARIABLES=3000
CAP_CLAUSES=150000
MAX_AXIOMS=3000
MAX_NEW_EQUATIONS=64
MAX_NEW_CLAUSES=1024
MAX_NEW_WIDTH=5

def ok(test,why):
    if not test:raise RuntimeError("R32T_CERTIFICATE_FAILURE "+str(why))
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for buf in iter(lambda:f.read(1<<20),b""):h.update(buf)
    return h.hexdigest()
def load_original(path):
    path=Path(path)
    if path.stat().st_size>CAP_BYTES:
        return None, "source_over_12MiB"
    n=header_clause_count=None;clause=[];groups={};units=[];count=0
    with path.open(encoding="ascii",errors="strict") as f:
        for line in f:
            t=line.strip()
            if not t or t[0] in ("c","%"):continue
            if t.startswith("p "):
                hdr=t.split()
                ok(n is None and len(hdr)==4 and hdr[1]=="cnf","Invalid source header")
                n=int(hdr[2]);header_clause_count=int(hdr[3])
                if n>CAP_VARIABLES or header_clause_count>CAP_CLAUSES:
                    return None,"source_vars_or_clauses_guard"
                continue
            ok(n is not None,"Original DIMACS header absent")
            for word in t.split():
                lit=int(word)
                ok(abs(lit)<=n,"Original literal exceeds declared variable count")
                if lit:
                    clause.append(lit)
                    ok(len(clause)<=100000,"Excessive clause width")
                else:
                    count+=1
                    if len(clause)==1:
                        literal=clause[0]
                        units.append(((abs(literal),),int(literal>0)))
                    if 2<=len(clause)<=6:
                        vars_=tuple(sorted(abs(x) for x in clause))
                        if len(vars_)==len(set(vars_)):
                            negatives={-x for x in clause if x<0}
                            negative_mask=sum(1<<i for i,v in enumerate(vars_)
                                              if v in negatives)
                            groups[vars_]=groups.get(vars_,0)|(1<<negative_mask)
                    clause=[]
        ok(n is not None and not clause and count==header_clause_count,
           "Original DIMACS declaration does not match clauses")
    return dict(n=n,clauses=count,groups=groups,original_units=units),None

def complete_parity_axioms(source):
    groups=source["groups"];equations=[]
    for variables,bitset in sorted(groups.items()):
        k=len(variables)
        for rhs in (0,1):
            # False assignments of an entailed XOR parity have opposite
            # assignment parity. Each forbidden assignment must exist as an
            # original clause on exactly these variables.
            forbidden=sum(1<<mask for mask in range(1<<k)
                          if (mask.bit_count()&1)!=rhs)
            if bitset&forbidden==forbidden:
                equations.append((variables,rhs))
    return equations

def to_bitrow(variables):
    return sum(1<<(v-1) for v in variables)
def indices_of_bits(bits):
    while bits:
        lo=bits&-bits
        yield lo.bit_length()-1
        bits^=lo

def certificates(n,equations):
    # Source-aware elimination: every row is XOR of listed original axioms.
    basis={};dependencies=0
    for i,(variables,rhs) in enumerate(equations):
        bits=to_bitrow(variables);provenance=1<<i;right=rhs
        while bits:
            pivot=(bits&-bits).bit_length()
            if pivot not in basis:
                basis[pivot]=(bits,right,provenance)
                break
            row,r,pr=basis[pivot]
            bits^=row;right^=r;provenance^=pr
        else:
            dependencies+=1
            ok(right==0,"Contradictory parity axioms; no valid SAT superformula")
    for pivot in sorted(basis,reverse=True):
        row,r,pr=basis[pivot]
        for earlier in sorted([k for k in basis if k<pivot]):
            b,br,bpr=basis[earlier]
            if b&(1<<(pivot-1)):
                basis[earlier]=(b^row,br^r,bpr^pr)
    existing=set(equations)
    proposals=[]
    for bits,rhs,proof in basis.values():
        k=bits.bit_count()
        if not 2<=k<=MAX_NEW_WIDTH:continue
        variables=tuple(i+1 for i in indices_of_bits(bits))
        if (variables,rhs) in existing:continue
        proposals.append((variables,rhs,proof))
    proposals.sort(key=lambda r:(len(r[0]),r[0],r[1]))
    rows=[];clauses_budget=0
    for variables,rhs,proof in proposals:
        k=len(variables);new_clauses=1<<(k-1)
        if len(rows)>=MAX_NEW_EQUATIONS:break
        if clauses_budget+new_clauses>MAX_NEW_CLAUSES:continue
        rows.append((variables,rhs,proof))
        clauses_budget+=new_clauses
    return dict(rank=len(basis),dependencies=dependencies,
                candidates=len(proposals),chosen=rows,total_clauses=clauses_budget)

def reconstruct_and_verify(equations,derived):
    for variables,right,proof in derived:
        x=0;rhs=0
        source_ids=list(indices_of_bits(proof))
        ok(bool(source_ids),"Empty Gaussian proof")
        for index in source_ids:
            ok(index<len(equations),"Outside original source axiom indices")
            vs,r=equations[index]
            x^=to_bitrow(vs)
            rhs^=r
        ok(x==to_bitrow(variables) and rhs==right,
           "Candidate parity is not XOR of complete original source blocks")
    return True

def encode_parity(variables,rhs):
    k=len(variables)
    for bad_assignment in range(1<<k):
        if (bad_assignment.bit_count()&1)==rhs:continue
        clause=[-v if (bad_assignment>>i)&1 else v
                for i,v in enumerate(variables)]
        # Such a clause is falsified only at a parity-violating assignment.
        ok((bad_assignment.bit_count()&1)!=rhs,"Invalid parity CNF encoding")
        yield clause

def build(source,augmented,certificate):
    source=Path(source);augmented=Path(augmented)
    info,error=load_original(source)
    record=dict(original=source.name,sha256_original=digest(source),
                derivation_guard=error,axioms=0,rank=0,free=None,
                new_short_candidates=0,chosen_short_equations=0,
                added_clauses=0,certificates=[],augmented_file=augmented.name)
    if error:
        shutil.copyfile(source,augmented)
    else:
        equations=complete_parity_axioms(info)
        ok(len(equations)<=MAX_AXIOMS,"More than 3000 certified XOR axioms")
        result=certificates(info["n"],equations)
        reconstruct_and_verify(equations,result["chosen"])
        record.update(axioms=len(equations),rank=result["rank"],
                      free=info["n"]-result["rank"],
                      new_short_candidates=result["candidates"],
                      chosen_short_equations=len(result["chosen"]),
                      added_clauses=result["total_clauses"])
        for variables,rhs,proof in result["chosen"]:
            sources=list(indices_of_bits(proof))
            record["certificates"].append(dict(
                 variables=list(variables),rhs=rhs,axiom_ids=sources,
                 encoded_clauses=(1<<(len(variables)-1))))
        if not result["chosen"]:
            shutil.copyfile(source,augmented)
        else:
            # Preserve every original clause in original order, change only
            # the p cnf clause count and append *entailed* CNF consequences.
            replaced=0
            with source.open(encoding="ascii") as src,augmented.open("w",encoding="ascii") as dst:
                for line in src:
                    if line.lstrip().startswith("p cnf "):
                        ok(replaced==0,"Multiple original DIMACS headers")
                        dst.write(f'p cnf {info["n"]} {info["clauses"]+result["total_clauses"]}\n')
                        replaced+=1
                    else:dst.write(line)
                ok(replaced==1,"Missing original source CNF header")
                for variables,rhs,proof in result["chosen"]:
                    for clause in encode_parity(variables,rhs):
                        dst.write(" ".join(map(str,clause))+" 0\n")
    record["sha256_augmented"]=digest(augmented)
    if record["added_clauses"]==0:
        ok(record["sha256_original"]==record["sha256_augmented"],
           "Inactive algebra altered original source")
    certificate.write_text(json.dumps(record,indent=2)+"\n")
    print("R32T_CERT_PASS",record["original"],"xor_axioms",record["axioms"],
          "rank",record["rank"],"short_new",record["new_short_candidates"],
          "selected",record["chosen_short_equations"],
          "added_clauses",record["added_clauses"],flush=True)
    return record

def audit(original,augmented,proof_path):
    record=json.loads(Path(proof_path).read_text())
    ok(digest(original)==record["sha256_original"],"Original CNF SHA drift")
    ok(digest(augmented)==record["sha256_augmented"],"Augmented CNF SHA drift")
    info,error=load_original(original)
    ok(error==record["derivation_guard"],"Changed input eligibility")
    if error:
        ok(not record["certificates"] and
           record["sha256_original"]==record["sha256_augmented"],
           "Guarded CNF modified")
        return record
    axioms=complete_parity_axioms(info)
    ok(len(axioms)==record["axioms"],"Original GF2 axioms drift")
    rows=[(tuple(c["variables"]),c["rhs"],sum(1<<i for i in c["axiom_ids"]))
          for c in record["certificates"]]
    reconstruct_and_verify(axioms,rows)
    added=sum(1<<(len(r[0])-1) for r in rows)
    ok(added==record["added_clauses"],"Wrong added clause count")
    if not added:
        ok(digest(original)==digest(augmented),"Inactive CNF changed")
        return record
    # Reconstruct augmented source completely and byte-compare its SHA.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        copy=Path(d)/"augmented.cnf"
        count=0
        with open(original,encoding="ascii") as src,copy.open("w",encoding="ascii") as dst:
            for line in src:
                if line.lstrip().startswith("p cnf "):
                    dst.write(f'p cnf {info["n"]} {info["clauses"]+added}\n');count+=1
                else:dst.write(line)
            for variables,rhs,_ in rows:
                for clause in encode_parity(variables,rhs):
                    dst.write(" ".join(map(str,clause))+" 0\n")
        ok(count==1 and digest(copy)==digest(augmented),
           "Augmented source does not match individually certified parity cuts")
    return record

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="action",required=True)
    q=subs.add_parser("build")
    for f in ("original","augmented","certificate"):
        q.add_argument("--"+f,required=True)
    q=subs.add_parser("audit")
    for f in ("original","augmented","certificate"):
        q.add_argument("--"+f,required=True)
    args=p.parse_args()
    if args.action=="build":
        build(args.original,args.augmented,Path(args.certificate))
    else:
        audit(args.original,args.augmented,args.certificate)
        print("R32T_INDEPENDENT_CERTIFICATE_AUDIT_PASS",args.original,flush=True)

if __name__=="__main__":main()
