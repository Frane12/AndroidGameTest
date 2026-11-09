#!/usr/bin/env python3
"""X22 source-only certified parity-block and GF(2) inconsistency forensics.

A detected parity row is accepted ONLY when all 2^(k-1) forbidden CNF
sign patterns are present on EXACTLY the same variable support. Therefore the
source CNF logically entails the extracted XOR equation. Source-only Gaussian
inconsistency is a valid UNSAT derivation; it is NOT an LRAT certificate.
This is development research on six known X21 instances, not blind.
"""
import collections, hashlib, json, pathlib, random
import drnas_x22_exact_projection as x22

ROOT=pathlib.Path("mre_x22")
MAX_K=8

def analyze(nvars,clauses):
    groups=collections.defaultdict(set)
    lengths=collections.Counter()
    for clause in clauses:
        k=len(clause)
        lengths[k]+=1
        if not 2<=k<=MAX_K:continue
        ordered=tuple(sorted(clause,key=abs))
        support=tuple(abs(z) for z in ordered)
        if len(set(support))!=k:continue
        mask=sum(1<<i for i,z in enumerate(ordered) if z<0)
        groups[support].add(mask)
    rows=[];full_covers=[]
    for support,masks in groups.items():
        k=len(support)
        if len(masks)==1<<k:
            full_covers.append(dict(vars=support,width=k))
            continue
        if len(masks)!=(1<<(k-1)):continue
        p={z.bit_count()%2 for z in masks}
        if len(p)!=1:continue
        forbidden_parity=next(iter(p))
        expected={z for z in range(1<<k)
                  if z.bit_count()%2==forbidden_parity}
        if masks!=expected:continue
        rows.append(dict(vars=support,width=k,rhs=1-forbidden_parity,
                         masks=len(masks)))
    # Exact deterministic GF(2) elimination with source-row combination trace.
    basis={};contradiction=None;rank=0
    for i,row in enumerate(rows):
        mask=sum(1<<(v-1) for v in row["vars"])
        rhs=row["rhs"];dependency=1<<i
        while mask:
            pivot=mask.bit_length()-1
            if pivot not in basis:
                basis[pivot]=(mask,rhs,dependency)
                rank+=1
                break
            a,b,c=basis[pivot]
            mask^=a;rhs^=b;dependency^=c
        else:
            if rhs and contradiction is None:
                involved=[i for i in range(len(rows)) if dependency>>i&1]
                contradiction=dict(row_indexes=involved,
                    source_equations=len(involved),gf2_rhs=1,
                    check_xor_variables_cancel=True)
    hist=collections.Counter(r["width"] for r in rows)
    return dict(nvars=nvars,clauses=len(clauses),width_histogram=dict(sorted(lengths.items())),
        support_groups=len(groups),certified_xor_rows=len(rows),
        xor_width_histogram=dict(sorted(hist.items())),
        certified_xor_clause_coverage=sum(r["masks"] for r in rows),
        xor_rank=rank,full_support_unsat_blocks=len(full_covers),
        direct_source_GF2_contradiction=bool(full_covers or contradiction),
        gaussian_contradiction=contradiction,
        full_covers=full_covers[:3],
        sample_rows=rows[:10],
        confirmation_level="source block coverage + exact XOR algebra; not LRAT",
        research_only_not_blind=True)

def selftest():
    # Single XOR3: prohibit even patterns -> surviving odd parity.
    vars=(1,2,3)
    even=[tuple(-v if z>>i&1 else v for i,v in enumerate(vars))
          for z in range(8) if z.bit_count()%2==0]
    odd=[tuple(-v if z>>i&1 else v for i,v in enumerate(vars))
         for z in range(8) if z.bit_count()%2==1]
    a=analyze(3,even)
    assert a["certified_xor_rows"]==1 and not a["direct_source_GF2_contradiction"]
    # Forbid every one of the eight assignments => direct UNSAT.
    b=analyze(3,even+odd)
    assert b["full_support_unsat_blocks"]==1 and b["direct_source_GF2_contradiction"]
    # XOR (1,2)=0, XOR(2,3)=0, XOR(1,3)=1 are inconsistent.
    def row(vs,forbidden):
        return [tuple(-v if z>>i&1 else v for i,v in enumerate(vs))
                for z in range(1<<len(vs)) if z.bit_count()%2==forbidden]
    c=analyze(3,row((1,2),1)+row((2,3),1)+row((1,3),0))
    assert c["certified_xor_rows"]==3 and c["gaussian_contradiction"]
    print("X22_SOURCE_XOR_SELFTEST_PASS")

def main():
    selftest();out=[]
    for c in x22.cases():
        src=x22.x21.ROOT/c["filename"]
        assert x22.sha(src)==c["sha256"]
        n,clauses,count=x22.parse(src)
        result=analyze(n,clauses)
        result.update(gbd=c["gbd"],original_sha256=c["sha256"],
                      source_sha_verified=True,actual_declared_clauses=count,
                      raw_bytes=src.stat().st_size)
        out.append(result)
        print("X22_XOR_FORENSICS",json.dumps(result,sort_keys=True),flush=True)
    x22.save(ROOT/"xor-forensics.json",dict(protocol="X22-SOURCE-CERTIFIED-XOR-20261109-v1",
        source_count=len(out),cases=out,blind_holdout=False,
        independent_UNSAT_LRAT=False))
    print("X22_XOR_FORENSICS_FINAL",json.dumps(dict(
        cases=len(out),
        direct_contradictions=sum(r["direct_source_GF2_contradiction"] for r in out),
        total_rows=sum(r["certified_xor_rows"] for r in out),
        source_shas=[r["original_sha256"] for r in out])),flush=True)

if __name__=="__main__":main()
