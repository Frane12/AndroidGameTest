# DRNAS IPG6 / IPG6B — original-weighted PCMAX higher-rank PB source cuts

## Status 2026-11-16

**Main untouched, no APK, source-frozen experimental branches only.**

Completed GitHub runs:
- IPG6 rank2: https://github.com/Frane12/AndroidGameTest/actions/runs/43879954686
- IPG6B rank4: https://github.com/Frane12/AndroidGameTest/actions/runs/43881441900

All source-PB derivations are on the EXACT 45-variable, 300-clause
weighted Petersen PCMAX source SHA-256:
`c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70`.

## Mathematically new source statements

The earlier IPG5-E study independently verified **exact rational
countermodels for all 81 source-absent graph mutexes** in the
continuous original CNF PB relaxation, so these mutexes cannot
be inferred by mere nonnegative linear combinations of the
original 300 unrounded PB constraints.

New IPG6 finds genuine Chvátal–Gomory derivations:

1. Original same-machine binary conflicts among job IDs (zero-based)
   9, 12, 14 imply the valid triangle at-most-one constraint via
   summing 3 original clauses and integer dividing by 2. Three
   machine-specific source rank1 cuts.
2. For selected other jobs a,b, source clauses include
   (~x_a,m OR ~x_b,m OR ~x_j,m) for EACH j in {9,12,14},
   plus the three original exactly-one ALO clauses for each j.
   Add those SIX original constraints and the TWO previously
   derived triangle at-most-one bounds from OTHER machines.
   Divide by 3. The result is the NEW source-implied mutex
   ~x_a,m + ~x_b,m >= 1. This gives **9 new source rank2 mutexes**.

An explicit original-source representative is the source
VeriPB3 input IDs

  pol 139 241 + 271 + 2 d ;
  pol 140 242 + 272 + 2 d ;
  pol 141 243 + 273 + 2 d ;

followed by

  pol 37 49 + 57 + 106 + 166 + 265 + 302 + 303 + 3 d ;

which yields ~x25 + ~x34 >= 1. Before this PB rounding,
the continuous source relaxation admits a rational model
setting both x25=x34=1; the integer cut is nontrivial.

IPG6B iterates the same mathematically justified pattern.
The derived mutexes form a second machine-specific triangle
among jobs (zero-based) 8,11,13. The triangle requires just
three further CP/2 derivations, one per machine:

  pol 304 307 + 310 + 2 d ;
  pol 305 308 + 311 + 2 d ;
  pol 306 309 + 312 + 2 d ;

The new triangle bounds enable source original-ALO + original
ternary cover + previously proven triangle constraint CP/3
steps on two more job pairs, (7,12) and (10,12), on all
three machines: **6 additional rank4 source mutexes**.

## Verified direct-PB closure

| Stage | New POL steps | New source-absent graph mutex clauses |
|---|---:|---:|
| Original-source triangle capacity (rank1) | 3 | 0 |
| First machine pair inference (rank2) | 9 | 9 |
| Derived second triangle (rank3) | 3 | 0 |
| Second machine pair inference (rank4) | 6 | 6 |
| **TOTAL** | **21** | **15** |

This is 15 of 81 non-source Petersen graph adjacency constraints.
An automatic source-CNF scan reaches closure after 3 bounded
rounds. No DPLL, CDCL, LP solver, SAT oracle, symbolic model
label, or external proof search is used to derive THESE 21 PB
steps. Every antecedent is an actual original source constraint
or a previously source-derived CP inequality.

A separate independent checker
`research/ipg6b_independent_source_pb_checker.py` replays
the first 21 statements using arbitrary-precision signed
integer arithmetic and checks the 6 triangle inequalities,
15 distinct new same-machine mutexes, source SHA and support.
Both tampered source bytes and forged proof metadata are rejected.

## Standard VeriPB validation and important limitation

The source-only 21-step derivation is independently accepted
as the first 21 steps of a **121 `pol` / 0 `rup` proof**
against the ORIGINAL 300 source clauses. External VeriPB 3.0.2
returns 0 and `s VERIFIED UNSATISFIABLE`.

**Crucial limitation:** The remaining 100 `pol` steps are
retained from the previous IPG5-E source-RUP-to-POL translation.
Those 100 lines were FOUND by bounded structural DPLL search.
The source-only 21-step PB closure does NOT, by itself, prove
the full original PCMAX UNSAT. Calling the entire IPG6B
algorithm DPLL-free would be inaccurate.

The full proof is 12,632 bytes. No speedup claim is made
against the frozen DRNAS CDCL/MG7 reference, which already
had a short source-checked UNSAT certificate for this instance.
No blind source-disjoint large-PCMAX PAR2 has been run here.

## Reproduce

    cargo install veripb --version 3.0.2 --locked --root ./veripb-tool
    make -C drat-trim drat-trim
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target drnas-ipg5b-jobbranch -j2
    python3 -u research/ipg6_rank2_benchmark.py
    python3 -u research/ipg6b_iterative_benchmark.py

The emitted `source_only_rank4_21_pol.txt` consists of the
original-source mathematical source-CG statements alone.
The combined proof `IPG6B_21_SOURCE_CG_PLUS_100_POL.pbp`
must be verified using

    veripb-tool/bin/veripb --cnf
    results/ipg6_rank2/original_weighted_petersen_45v300c.cnf
    results/ipg6b_rank4/IPG6B_21_SOURCE_CG_PLUS_100_POL.pbp

## Next scientific problem

Can a more general source-derived machine capacity PB
strengthening or LP/CG-based search derive the remaining 66
source-absent graph mutexes, or a stronger global counting
contradiction without enumerating DPLL cases?

The earlier exact-rational witnesses show linear-only inference
is insufficient on all 81 original missing edges, and 72 survive
the first three source CG cuts. The new iterative higher-rank
source cuts are a nontrivial but partial exact step toward
a search-free original-weighted PCMAX refutation.

No general polynomial-time SAT, PCMAX or P=NP result is claimed.
