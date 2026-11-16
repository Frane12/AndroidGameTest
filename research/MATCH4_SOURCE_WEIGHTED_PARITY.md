# DRNAS MATCH4 — Original-source weighted PCMAX to cubic-graph parity bridge (2026-11-16)

## Scope and scientific status

Experimental Python source-bound mathematical proof prototype on
\`experiment/drnas-match4-source-parity-bridge1-20261116\`.
It does not modify main, frozen solver references or native C++ solver.
It does **not** establish P=NP, a polynomial general PCMAX algorithm,
general source-independent discovery of processing times, or faster
competitive SAT solving.

The previous DRNAS IPG5-B already produces a **standard VeriPB 3.0.2**
verified original-Petersen proof with 100 RUP steps, but its C++ generator
is gated to one literal SHA and one known source. MATCH4 tests a
different architectural claim: does a small *hinted* weighted graph
certificate remain independently valid for original CNF **after**
variable renumbering, source-clause reordering, and deletion of hints?

## Mathematical sufficient condition

1. From the actual original source clauses, require n disjoint positive
   three-selector ALO job clauses, complete same-job negative pairwise
   AMO clauses, and a partition into three resources, each holding
   exactly one selector per job. The resource partition is only
   proposed by a negative-clause graph heuristic. The checker
   re-validates the source premises independently.
2. A *candidate* nonnegative integer duration vector is proposed.
   The producer may read a source comment \`c Item sizes:\`, or
   accept \`--weights-json\`. **This is an untrusted hypothesis.**
   An independent checker ignores all comments and validates everything
   from the original DIMACS clauses and certificate.
3. Every candidate job weight must equal \`3^u + 3^v\` with u != v.
   These candidates encode edges of a simple 3-regular graph G on
   V <= 12 consecutive vertices. Thus n=3V/2, all job weights
   sum to exactly 3T, where \`T=sum(3^i, i=0..V-1)\`.
4. For each machine/resource i, collect only its original all-negative
   source clauses. For every job subset S (bounded n<=15), check that
   if \`sum(j in S) p_j > T\`, the original CNF directly forbids S
   by a negative clause whose selector jobs are a subset of S.
   This verifies the **SOURCE entailment** of each machine's
   pseudo-Boolean upper capacity: \`sum p_j*x_{j,i} <= T\`.
   The full 2^n check is deliberately exponential, and currently
   is NOT replaced by a compact standard PB proof.
5. Suppose a satisfying assignment exists. ALO+AMO implies exactly
   one machine/job; the source-verified PB bounds and total demand
   3T force exactly T per machine. Because each graph vertex has
   degree 3, base-three digits of the exact load T imply by
   induction no carries and exactly one incident edge per graph
   vertex on every machine. Hence its three color classes are
   disjoint perfect matchings of G.
6. Enumerate all perfect matchings (bounded, independently redone by
   the checker), and for each exhibit a simple odd cycle in the
   complementary two-regular graph. That disproves every possible
   three-edge-coloring. Thus the ORIGINAL CNF is UNSAT.

The independent verifier checks original source SHA bytes, 3-way ALO,
same-job AMO, every selector resource mapping, candidate weight
digits, cubic graph, all source-derived PB upper bounds, completeness
of perfect-matching enumeration and each odd-cycle witness.

This proof is mathematically **sound only when the independent
source checker accepts**, and is project-specific. It is NOT a
standard DRAT/LRAT/VeriPB certificate or a proof generator competitive
with the current IPG5-B C++ implementation.

## Local deterministic pilot and subsequent CI

\`python3 -u research/match4_source_parity_bench.py\` generates the
historical original Petersen SHA
\`c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70\`
(45 variables, 300 clauses), four independently permuted and
reordered variants, and a no-comments variant requiring explicit
untrusted weight candidates. It separately checks a SAT K3,3
edge-colorable weighted scheduling source, SAT source with weighted
clauses removed, one-clause-deleted rejection, wrong-weight rejection,
and nine forged/altered certificate controls.

Local pilot result before GitHub CI: 10 original-CNF cases,
6 source-verified UNSAT, 2 model-checked SAT, 2 UNKNOWN,
0 false UNSAT; 9/9 forged/altered certificates rejected.
The Petersen source has six perfect matchings and exactly
[7036,7036,7036] source-admissible single-machine job sets.

The "six verified" cases are one original and five transformed
versions of **the same mathematical Petersen problem**, not six
independently discovered UNSAT families. This is a robustness check,
not a blind benchmark or a speedup claim.

## Next steps

- Remove external candidate weight hints by inferring durations from
  original clauses or replace candidate reliance with source-validated
  PB/BDD reconstruction.
- Replace O(2^n) source-bound enumeration with compact independently
  verified VeriPB/DRAT/LRAT upper-bound derivations.
- Generalize to other non-3-regular graphs and different machine counts.
- Compare verification-inclusive E2E PAR2, memory, source-disjoint
  blind mixed instances against frozen native DRNAS, Kissat, CaDiCaL,
  and CryptoMiniSat before considering production integration.

## Commands

    python3 -m py_compile research/match4_source_parity*.py
    python3 -u research/match4_source_parity_bench.py
    python3 research/match4_source_parity.py original.cnf --certificate proof.json
    python3 research/match4_source_parity_checker.py original.cnf proof.json

If the source omits weight comments, provide an untrusted JSON list
of job weights via \`--weights-json hypothesis.json\`. The checker
does not consume the hypothesis file or source comments.
