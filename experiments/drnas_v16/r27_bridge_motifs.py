#!/usr/bin/env python3
"""R27b: distinguish aggregate 4:1 bridge-count identity from true per-var degree."""
import argparse, hashlib, json, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0,str(Path(__file__).resolve().parent))
from r27_xor_residual_links import clauses, signature, first_pass, sha256

def inspect(path):
    n, total, widths, groups,patterns,repeated,partial=first_pass(path)
    xvars=set(v for sup in groups for v in sup)
    xor_var_occ=Counter()
    bridge_var_occ=Counter()
    touched=Counter()
    crossing_widths=Counter()
    xor_lits_per_cross=Counter()
    nonxor_lits_per_cross=Counter()
    external_widths=Counter()
    sample_motifs=Counter()
    crossing=0
    residual=0
    for _, cl in clauses(path):
        sig=signature(cl)
        if sig is not None and sig[0] in groups:
            xor_var_occ.update(abs(x) for x in cl)
            continue
        residual+=1
        variables=[abs(x) for x in cl]
        xor=[v for v in variables if v in xvars]
        nonxor=[v for v in variables if v not in xvars]
        if xor:
            touched["residual_touch"]+=1
            if nonxor:
                crossing+=1
                bridge_var_occ.update(xor)
                crossing_widths[len(cl)]+=1
                xor_lits_per_cross[len(xor)]+=1
                nonxor_lits_per_cross[len(nonxor)]+=1
                sample_motifs[(len(cl),len(xor),len(nonxor))]+=1
        else:
            external_widths[len(cl)]+=1
    interface=list(bridge_var_occ)
    hist=Counter(bridge_var_occ.values())
    xorhist=Counter(xor_var_occ[v] for v in interface)
    # Direct independent check whether ALL bridge vars have exactly 4 occurrences.
    regular_bridge=(bool(interface) and set(hist)=={4})
    single_xor_cross=(bool(xor_lits_per_cross) and set(xor_lits_per_cross)=={1})
    return dict(n=n,total_clauses=total,xor_blocks=len(groups),
                xor_group_widths=dict(Counter(len(x) for x in groups)),
                crossing_residual_clauses=crossing,
                interface_variables=len(interface),
                crossing_per_interface=crossing/max(1,len(interface)),
                crossing_widths=dict(crossing_widths),
                xor_literals_per_crossing_clause=dict(xor_lits_per_cross),
                external_literals_per_crossing_clause=dict(nonxor_lits_per_cross),
                bridge_occurrence_histogram=dict(hist),
                xor_occurrence_histogram_on_interface=dict(xorhist),
                all_bridge_variables_degree_4=regular_bridge,
                every_crossing_clause_one_xor_variable=single_xor_cross,
                motif_counts=[dict(clause_width=w,xor_vars=x,nonxor_vars=z,count=c)
                    for (w,x,z),c in sample_motifs.most_common(15)],
                external_only_widths=dict(external_widths),
                top_interface=[
                    dict(variable=v,residual_occ=bridge_var_occ[v],xor_occ=xor_var_occ[v])
                    for v in sorted(interface,key=lambda v:(bridge_var_occ[v],xor_var_occ[v]),reverse=True)[:10]],
                residual_clauses=residual)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--inputs",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    root=Path(args.inputs)
    manifest=json.loads((root/"manifest.json").read_text())
    formulas=[r for r in manifest["cases"] if
              r["family"]=="polynomial_gbd_original"]
    assert len(formulas)==10
    records=[]
    for row in formulas:
        source=root/row["path"]
        assert sha256(source)==row["sha256"]
        r=inspect(source)
        r.update(id=row["id"],sha256=row["sha256"])
        records.append(r)
        print("R27_MOTIF",json.dumps({
            "id":r["id"],"xor_blocks":r["xor_blocks"],
            "interface":r["interface_variables"],
            "crossing":r["crossing_residual_clauses"],
            "motifs":r["motif_counts"][:4],
            "bridge_hist":r["bridge_occurrence_histogram"],
            "all_bridges_degree_4":r["all_bridge_variables_degree_4"],
            "one_xor_per_cross":r["every_crossing_clause_one_xor_variable"]
        }),flush=True)
    out=dict(protocol="R27b-exact-interface-clause-degree-audit",
             orte= "Original SHA-pinned GBD polynomials, no solver timing",
             invariants={
                "all_crossing_equal_4_times_interface":all(
                  x["crossing_residual_clauses"]==4*x["interface_variables"] for x in records),
                "each_interface_var_has_degree_4_all_cases":all(
                  x["all_bridge_variables_degree_4"] for x in records),
                "every_mixed_clause_contains_one_xor_variable":all(
                  x["every_crossing_clause_one_xor_variable"] for x in records)
             },records=records)
    Path(args.out).write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("R27_MOTIF_INVARIANTS",json.dumps(out["invariants"],sort_keys=True),flush=True)

if __name__=="__main__":
    main()
