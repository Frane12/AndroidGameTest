#!/usr/bin/env python3
"""R65x-Live V2: larger exact-parity source capacity and bounded adaptive cost.

Keep ALL original-source soundness guards and original/native XOR reason logic.
Old equation capacity 1600 made 2208-block SAT2025 original unable to enter
in-search GF(2). Expand static complete-source equation/basis cap to 4096.
Do not bypass hidden-resolvent guard, size guards or original row proofs.
Switch adaptivity from permanently 4-decision scans after first UIP use
to 16-decision scans, backed off to 64/256 with no evidence of utility.
Print guard information to diagnose cases still not producing rows.
Apply AFTER R32b, R32n, R32s, R32u, R84, R85, R65xl patches.
"""
import argparse
from pathlib import Path

def once(s,a,b,why):
    n=s.count(a)
    if n!=1:
        raise RuntimeError(f"R65XLV2_PATCH_{why} anchor count={n}")
    return s.replace(a,b,1)

def apply(root):
    src=root/"src"
    h=src/"r32b_shadow_core.h"
    s=h.read_text()
    s=once(s,"#define R32B_MAXEQ 1600","#define R32B_MAXEQ 4096","equation_basis_capacity")
    h.write_text(s)

    p=src/"parse.c"
    s=p.read_text()
    anchor="  if(!r32b_looked)r32b_discover();\n  // Restrict this first proof protocol"
    insert=(
        "  if(!r32b_looked)r32b_discover();\n"
        "  printf(\"c R65XLV2_SOURCE_GATE eq_capacity=%u observed_equations=%u\"\n"
        "         \" resolved=%u guard=%d vars=%u original_clauses=%u\\n\",\n"
        "         R32B_MAXEQ,r32b_neq,r32b_nresolved,r32b_guard,\n"
        "         r32b_varmax,r32b_nclause);\n"
        "  fflush(stdout);\n"
        "  // Restrict this first proof protocol")
    s=once(s,anchor,insert,"source_gate_after_discovery")
    p.write_text(s)

    p=src/"search.c"
    s=p.read_text()
    old=("    if(r85_first_uip_uses)next=4;\n"
         "    else if(r32u_probed<8)next=4;\n"
         "    else if(r32u_added==0)next=64;\n"
         "    else if(r32u_probed>=32)next=64;\n"
         "    else next=16;")
    new=("    if(r85_first_uip_uses)next=16;\n"
         "    else if(r32u_added==0 && r84_rows_visited>=2000000)next=256;\n"
         "    else if(r32u_probed<8)next=4;\n"
         "    else if(r32u_added==0)next=64;\n"
         "    else if(r32u_probed>=32)next=64;\n"
         "    else next=16;")
    s=once(s,old,new,"adaptive_no_permanent_max_scanning")
    s=once(s,
        "  printf(\"c R65XL_LIVE adaptive=%d interval=%u switches=%u rows=%u\"",
        "  printf(\"c R65XL_LIVE adaptive=%d interval=%u switches=%u rows=%u\"",
        "output_format_pinned_check") if False else s
    p.write_text(s)
    print("R65XLV2_WIDE_4096_BOUNDED_LIVE_PATCH_PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    apply(a.kissat_root)

if __name__=="__main__":
    main()
