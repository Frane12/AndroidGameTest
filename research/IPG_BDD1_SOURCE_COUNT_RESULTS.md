# DRNAS IPG-BDD1 — source-bound two-class BDD count-profile proof

## Status (2026-11-16)

Experimental research branch only. Native C++ source-extractor + Python polynomial
count-profile producer + separate original-CNF verifier are implemented and
tested. **Not yet linked into the production DRNAS C++ solving loop**.
main and frozen previous solver versions remain unchanged.

Final GitHub Actions source-frozen pilot:
https://github.com/Frane12/AndroidGameTest/actions/runs/43835608861

- 16 generated ORIGINAL BDD-CNF scheduling formulas (2/3 machines), with
  independent exact scheduling oracle labels.
- 12/12 synthetic UNSAT source-count certificates independently accepted.
- 4/4 synthetic SAT controls returned UNKNOWN, no false UNSAT.
- 8 source-frozen authentic PCMAX SAT benchmark originals tested.
- 7/8 original BDD machines successfully extracted from source.
- **1/8 ORIGINAL PCMAX UNSAT verified:**
  pcmax-scheduling-m11-1517-6802-UNSAT.sanitized.cnf
  SHA-256 c55ab8fe2c9e10f0579f806802bc32d04913f12cd6ce28e6662b8d59d114c174.
  The discovered source-bound argument uses 16 of 21 eligible job groups;
  1,250 source-grounded BDD transition rows on 11 machines.
- Remaining 7 authentic sources remained UNKNOWN; no unsupported SAT claim.
- 0 test failures, including tampering with source hashes, clauses, source
  transition graph, profile tables and target counts.

These are retrospective source-frozen results, NOT blind PAR2. The original
m11 UNSAT was already verified by the earlier BDD capacity module; the
new BDD-count proof is a separate derivation, not a novel additional
solved benchmark or new mathematical theorem.

## Proven mathematical rule

Let each selected source positive clause represent a job that must choose
one machine selector. The native extractor exposes, for each machine i,
an ordered BDD whose root is asserted TRUE by the source, whose TRUE
terminal is asserted TRUE and FALSE terminal FALSE, and whose transition
implications are literally present in the original CNF:

 (-parent OR +selector OR false_branch)
 (-parent OR -selector OR true_branch).

The independent checker verifies EVERY source BDD edge and unit, plus
the complete pairwise at-most-one source clauses for each selected job.
It validates that all selected selectors belong to exactly one BDD
machine's ordered variable list; other clauses remain unexamined (relaxation).

Divide ANY source-verified subset of these jobs into two classes A and B.
Unselected jobs have zero weight and therefore remain unrestricted.
For each machine i, compute the exact polynomial profile P_i of all
attainable count pairs (#A, #B) on BDD-accepting paths. When a BDD
transition skips levels, all intervening selector assignments are
conservatively left free (both 0 and 1). A false terminal contributes
no count pair. The producer uses FORWARD propagation through BDD
states; the independent checker re-derives every profile BACKWARD.

Starting with R_0={(0,0)}, compute

 R_(i+1) = {r+p : r in R_i, p in P_i,
                         r_A+p_A <= |A|, r_B+p_B <= |B|}.

If (|A|,|B|) not in R_m, there cannot exist a satisfying assignment to
the original CNF. Every original SAT model must choose exactly one
source-group selector and follow a BDD-accepting path on its machine.

**The procedure is polynomial in the explicitly extracted BDD graph
size and number of selected jobs for a FIXED two-count-class dimension.**
It is incomplete, imposes hard resource limits, and does not establish
polynomial performance for general PCMAX (which may require exponentially
large BDDs). Even on solvable original CNFs it reports UNKNOWN, never SAT.

The structural certificate is SOURCE-BOUND but **NOT VeriPB, LRAT or DRAT**.
An independent source-verifying Python checker is included. A future
standard proof trace is needed before entering competition-certified PAR2.

## Reproduction

 cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
 cmake --build build --target drnas-ipg-bdd-extract -j2
 ./build/drnas-ipg-bdd-extract exact_source.cnf --output graph.json
 python3 research/ipg_bdd_profiles.py --graph graph.json --certificate result.json
 python3 research/ipg_bdd_checker.py --cnf exact_source.cnf --graph graph.json --certificate result.json

The final checker returns 0 only on fully verified original-source UNSAT.
For a fallback UNKNOWN no result may be presented as solved.

## Engineering improvements needed for IPG-BDD2

1. Integrate the SOURCE-CHECKED BDD count recurrence as a bounded
   in-process C++ guard, with no additional CPU core or portfolio.
2. Expand to richer fixed-count signatures using polynomial state-space
   products and short proof traces; do not assume all jobs are identical.
3. Export compact count-profile proof into a standard VeriPB checker
   so verification-inclusive PAR2 becomes scientifically comparable.
4. Run a prospective source-disjoint original benchmark against
   unchanged DRNAS, Kissat, CaDiCaL and CryptoMiniSat.

Do not merge into main unless verified proofs, correctness and holdout
performance pass the frozen acceptance criteria.
