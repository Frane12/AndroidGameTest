#!/usr/bin/env python3
"""R7 independent exact GPR unit tests and frozen 48/64 biological audit."""
from __future__ import annotations
import argparse
import ast
import itertools
import json
import math
from pathlib import Path
import statistics

SHA="13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f"
GMCSPY="4567a6d14bd2e5517e7a86b17aebefb0f285544c"
ARMS=("r7_flux_witness_sat","r6_sat_candidate_glpk","published_gMCSpy_staged_lazy")

def unit_test():
    from gmispy_r7_witness import GPRCNF
    formulas={
        "AND":"a and b",
        "OR":"a or b",
        "NEST":"(a and b) or c",
        "UNSELECTED":"d and (a or c)",
        "NEVER":"d or a",
        "ALWAYS":"d"
    }
    rules={rid:(source,ast.parse(source,mode="eval").body,None)
           for rid,source in formulas.items()}
    encoded=GPRCNF(("a","b","c"),rules)
    assert "ALWAYS" not in encoded.disabled
    def truth(lit,values):
        return values[abs(lit)] if lit>0 else not values[abs(lit)]
    for bits in itertools.product((False,True),repeat=3):
        vals0={i+1:bits[i] for i in range(3)}
        extensions=[]
        for extra in itertools.product((False,True),repeat=encoded.top-3):
            vals=vals0|{4+i:b for i,b in enumerate(extra)}
            if all(any(truth(lit,vals) for lit in clause)
                   for clause in encoded.clauses):
                extensions.append(vals)
        if len(extensions)!=1:
            raise AssertionError("Non-functional GPR encoding")
        vals=extensions[0]
        for rid,expression in formulas.items():
            original=bool(eval(expression,{"__builtins__":{}},
                {"a":not bits[0],"b":not bits[1],"c":not bits[2],"d":True}))
            disabled=encoded.disabled.get(rid)
            if (truth(disabled,vals) if disabled is not None else False)!= (not original):
                raise AssertionError("Incorrect GPR formula "+rid)
    return {"GPR_truth_table":"PASS","KO_patterns":8,
            "Tseitin_clauses":len(encoded.clauses)}

def validate(info):
    n=info.get("cohort")
    if n not in (48,64) or info.get("source_sha256")!=SHA:
        raise AssertionError("Biological model / cohort changed")
    if info.get("original_gMCSpy_commit")!=GMCSPY:
        raise AssertionError("Original competitor changed")
    if info.get("max_k")!=3 or info.get("native_drnas") is not False:
        raise AssertionError("Misrepresented experiment")
    genes=info["genes"]
    if len(genes)!=n or len(set(genes))!=n or not all(
        g.startswith("b") and len(g)==5 and g[1:].isdigit() for g in genes):
        raise AssertionError("Gene cohort contains invalid locus")
    oracle=info["independent_reference"]
    count=18472 if n==48 else 43744
    expected={frozenset(s) for s in oracle["minimal_solutions"]}
    n_min=25 if n==48 else 70
    if len(expected)!=n_min or oracle["candidates"]!=count or (
        oracle["gene_and_reaction_FBA"]!=2*count or
        oracle["monotonicity_checks"]!=count):
        raise AssertionError("Missing independent exhaustive GPR-FBA reference")
    if len(info["trials"])!=9 or not info.get("certified"):
        raise AssertionError("Incomplete three-repetition benchmark")
    timing={}
    for arm in ARMS:
        rows=[x for x in info["trials"] if x["method"]==arm]
        if {x["repeat"] for x in rows}!={0,1,2}:
            raise AssertionError("Repeat mismatch: "+arm)
        if any(x.get("all_solutions_verified") is not True or
               x.get("wall_s",0)<=0 for x in rows):
            raise AssertionError("Unverified run: "+arm)
        if arm==ARMS[0]:
            for row in rows:
                found=[frozenset(s) for s in row["solutions"]]
                if (len(found)!=len(set(found)) or set(found)!=expected or
                    row["lp_calls"]!=row["viable_lp"]+row["lethal_lp"] or
                    row["flux_cuts"]<1):
                    raise AssertionError("R7 output/LP accounting invalid")
        elif arm==ARMS[1]:
            if any(x.get("crosscheck")!="PASS" or
                   x["minimal_sets"]!=n_min for x in rows):
                raise AssertionError("R6 baseline wrong")
        else:
            for row in rows:
                found=[frozenset(s) for s in row.get("solutions",[])]
                if (row.get("status")!="returned" or
                    row.get("upstream_commit")!=GMCSPY or
                    len(found)!=len(set(found)) or set(found)!=expected):
                    raise AssertionError("Original specialist wrong/incomplete")
        timing[arm]=statistics.median(r["wall_s"] for r in rows)
        if not math.isclose(timing[arm],info["median_wall_s"][arm],
                            rel_tol=1e-7,abs_tol=1e-7):
            raise AssertionError("Median timing mismatch")
    return dict(cohort=n,status="PASS_EXACT",candidate_gene_KOs=count,
                minimal_gene_KOs=n_min,three_repeats_per_arm=True,
                median_s=timing,
                r7_vs_r6=timing[ARMS[1]]/timing[ARMS[0]],
                r7_vs_original_gMCSpy=timing[ARMS[2]]/timing[ARMS[0]])

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--unit-only",action="store_true")
    p.add_argument("--cohort48",type=Path)
    p.add_argument("--cohort64",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    test=unit_test()
    if args.unit_only:
        print("DRNAS_MEDICAL_R7_GPR_UNIT",json.dumps(test,sort_keys=True))
    else:
        if not args.cohort48 or not args.cohort64 or not args.out:
            p.error("--cohort48, --cohort64, --out required")
        data=[validate(json.loads(pth.read_text()))
              for pth in (args.cohort48,args.cohort64)]
        result=dict(status="PASS",gpr_unit=test,cohorts=data,
                    clinical_claims=False,full_gMISpy=False,
                    native_drnas=False)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print("DRNAS_MEDICAL_R7_CERTIFIED",json.dumps(result,sort_keys=True))
