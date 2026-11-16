# DRNAS IPG5 — first ORIGINAL-source Petersen parity/RUP proof without CDCL

**Status:** Independently source-RUP verified by DRAT-trim and VeriPB 3.0.2
on the original 45-variable / 300-clause weighted Petersen PCMAX CNF.

## Scientific objective

Unlike prior IPG4, whose short parity-driven VeriPB proof operated
on the equivalent **150-clause graph edge-coloring CNF** while the
original 300-clause proof was obtained from CDCL/MG7, IPG5-A
constructs a direct ORIGINAL-CNF proof **without ever invoking CDCL**.

The proof generator is an experimental Python research prototype
(`research/ipg5_structural_original_rup.py`), NOT yet an
in-process C++ IPG5 guard. That is the next implementation gate.

## Exact source

The literal source DIMACS has SHA-256
`c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70`,
45 variables and 300 clauses. We rederive these clauses from
Petersen graph edges e=(u,v), the job times p_e=3^u+3^v,
3 machines, and per-machine capacity sum_{v=0}^{9}3^v=29,524.

The source-to-graph correspondence and six fractional configurations
are independently checked by `research/ipg4_fractional_gap_checker.py`.
Six feasible perfect-matchings each contain five jobs, each
original job occurs exactly twice, and no two matchings are
disjoint. Hence ANY nonnegative weight vector w must satisfy
sum_j w_j <= 3 K(w), although the integer PCMAX problem is UNSAT.

## Mathematical proof architecture

1. The equivalent proper three-edge-coloring Petersen CNF has 150
   clauses: 60 one-hot clauses, and 90 adjacency / same-color
   forbidden-pair clauses.
2. All 60 one-hot clauses and 9 of the 90 adjacency clauses
   are already present literally in the source 300-clause CNF.
3. For each of the remaining 81 adjacency clauses, IPG5
   **constructs a source-RUP derivation** by bounded DPLL splitting.
   Branch order is by DECREASING exact integer job durations
   independently reconstructed from the Petersen graph.
4. At a source-UP-contradictory leaf under decisions D, derive
   the clause OR_{literal in D}(NOT literal). It is RUP by
   the source unit-propagation conflict under those decisions.
5. For a binary branch x, the two child clauses
   (NOT D OR x) and (NOT D OR NOT x) imply the parent
   (NOT D). Therefore each internal resolution-tree closure
   is again RUP. This emits 3,339 structural RUP steps.
6. Once the full graph encoding is a subset of the accumulated
   source plus justified lemmas, append the previous
   SOURCE-RUP-checked six-perfect-matching/odd-cycle parity
   proof of 59 RUP steps, including the empty clause.
7. Result: **3,398 consecutive source-RUP clauses** directly
   against the original 300-clause CNF, no CDCL, with the
   same source literal identities as the weighted instance.

This is a mathematically guided DPLL branch-and-resolution proof,
NOT a purely polynomial algorithm. Worst-case number of DPLL
branches is exponential even if this fixed case is small.

## Independent verification

1. Generator locally confirms RUP for every step against
   unchanged original clauses + previously produced lemmas.
2. Separate `research/ipg5_rup_to_veripb.py` replays every
   RUP step with a DIFFERENT source checker and converts it
   to VeriPB3.0. Its metadata does not guess proof provenance.
3. Independent pinned `drat-trim` on the exact 300-clause source
   accepted the trace (`s VERIFIED`).
4. Independent pinned VeriPB 3.0.2 on the exact original
   300-clause source accepted the standard PB proof
   (`s VERIFIED UNSATISFIABLE`).
5. SHA source mutation, a truncated RUP proof, and a
   satisfiable unrelated packing control must be rejected
   by the final green CI acceptance harness.

The verified proof has 79,681 RUP bytes and 173,129
standard VeriPB bytes. Proof sizes reflect the longer
mathematical source-to-graph bridge; the prior CDCL proof
was shorter (92 RUP steps), so IPG5 is NOT yet a speed
or proof-compression improvement.

## Reproduce

    cargo install veripb --version 3.0.2 --locked --root veripb-tool
    make -C drat-trim drat-trim
    python3 -u research/ipg5_original_veripb_benchmark.py

The CI intentionally does not compile or invoke any SAT/CDCL solver.
Only independent proof checkers are executed after the generator.

**GitHub branch:**
`experiment/drnas-ipg5-native-source-parity-20261116`

## Important limitations and follow-up

- One fixed original Petersen instance is recognized by source SHA,
  not a general automatically reconstructed graph class.
- Source-to-graph 81 mutex lemma derivations use bounded exponential
  decision splitting. Their proof is original-source sound,
  but NOT yet a polynomial structural source proof.
- A full general IPG-BDD3 3D-to-VeriPB compiler is still absent.
- The next valuable challenge: derive source graph incidence and
  parity lemmas using direct integer/PB cuts without 3,339
  individual branch-search RUP steps.
- Next engineering gate: port to native C++ and test source
  families, including SAT controls, prospective disjoint
  original benchmarks, PAR2 including proof validation,
  maxRSS, and no false SAT/UNSAT.

`main` and frozen solver references remain untouched.
