# DRNAS IPG5-C / IPG5-D — source-recognized RUP and pure PB research (2026-11-16)

**Experimental branch only. `main` and all frozen references remain untouched.**

## IPG5-C: source-structure recognition replaces Petersen's hard-coded SHA gate

New native `research/ipg5c_native_onehot.cpp` recognizes 3-selector
exactly-one job groups from ACTUAL original CNF clauses (positive ALO
and all three negative binary AMO clauses), rather than treating a
known source digest as proof of an expected outcome. It requires
all source variables to be covered by disjoint exactly-one groups
with 3–15 jobs (at most 45 Boolean variables).

Only SOURCE unit propagation + bounded **three-way job assignment
DPLL** is used. Every emitted clause is internally replayed for
RUP against original CNF. An UNKNOWN source never results in a proof.
No CDCL, second SAT solver, second process or parallel portfolio.

External `drat-trim`, independently source-bound
`research/ipg5c_source_rup_to_veripb.py`, and pinned VeriPB 3.0.2
all confirm every accepted original-CNF UNSAT certificate.

One-CPU source-frozen audit:
https://github.com/Frane12/AndroidGameTest/actions/runs/43867211249

| Trial family | Number | Independent source UNSAT accepted |
|---|---:|---:|
| Original weighted Petersen 45v/300c | 1 | 1 |
| Permutations of SAME Petersen formula | 12 | 12 |
| Cardinality packing with 7,8,9 jobs (three permutations each) | 9 | 9 |
| Different graph coloring UNSAT: W5,W7,K4 (two permutations each) | 6 | 6 |
| Genuine SAT controls: packing, wheel6, K3,3 | 13 | 0 false UNSAT |
| Unsupported CNF controls | 2 | 0 false claims |
| **TOTAL** | **43** | **28 source-verified UNSAT** |

**Accuracy caveat:** the Petersen permutations are NOT 12
independent mathematical problems. The 9 packing sources are
three different problem sizes with three permutations each, and
the graph sources include three new structural types. These
are small, retrospective/synthetic cases, not blind original
SAT Competition performance or a comparison to DRNAS/Kissat.

For the unmodified original Petersen, generalized source-only
heuristics produced 169 accepted RUP clauses; frozen tuned IPG5-B
produced 100 on the SAME source. Source generalization currently
costs some proof compression; no speed improvement is claimed.

## IPG5-C source Chvatal–Gomory odd-cycle cuts

The original-source negative binary conflict graph is constructed
ONLY from actual source clause IDs and excludes within-job AMO
clauses. A simple odd cycle of length 2k+1 gives

  2 sum_(v in cycle) ~x_v >= 2k+1

and the rank-one integer division cut

  sum_(v in cycle) ~x_v >= k+1.

The separate source-bound PB producer
`research/ipg5c_oddcycle_cuts.py` finds odd cycles of lengths
3,5,7 and emits standard VeriPB 'pol' clauses referencing
ONLY actual source clause IDs. The resulting proof uses these
CP lines PLUS a structural source-RUP suffix. The CP cuts
ALONE are not claimed to prove UNSAT in this experiment.

Examples: wheel5 generated 18 length-5 cuts; wheel7
generated 24 length-7 cuts; both verified WITH the RUP suffix.

## IPG5-D: new complete **pure cutting-planes** proof for odd-wheel CNFs

New standalone `research/ipg5d_pure_oddwheel_pb.py` identifies
an explicit graph 3-coloring ODD WHEEL directly in the source:

- Exact original 3-way positive one-hot ALO clauses (and AMO).
- Source binary mutex clauses that bijectively identify each
  'same color' selector across two adjacent vertex groups.
- A source-supported hub adjacent to every other vertex.
- An odd rim forming ONE simple cycle; every rim edge has
  original source mutex clauses in all three grounded colors.

The generator does NOT rely on job labels, known source hashes,
variable order, or guessed graph structure, and fails closed
when any required source clause is missing.

Let n=2k+1 be the odd rim length, with x_(v,c) indicating
rim vertex v uses color c and h_c indicating hub uses c.
From original rim-edge exclusion clauses for each color c:

  sum_(v in rim) (~x_(v,c)+~x_(next(v),c)) >= n

so after integer division by two:

  sum_(v in rim) ~x_(v,c) >= k+1,

or equivalently sum_(v in rim) x_(v,c) <= k.

From the original one-hot clauses on all n rim vertices:

  sum_(v in rim,c) x_(v,c) >= n.

Adding the odd-cycle capacity bounds for the OTHER TWO colors
implies every single color c must appear at least once:

  sum_(v in rim) x_(v,c) >= n - 2k = 1.

For color c the n original hub/rim mutex clauses imply

  n ~h_c + sum_(v in rim) ~x_(v,c) >= n.

Adding the above color-presence inequality cancels all rim
literals and yields n ~h_c >= 1, then integer division by n
gives ~h_c >= 1. Repeat for all three colors.

Summing the three hub-exclusion inequalities with the source
hub ALO h_0+h_1+h_2>=1 yields **0>=1**, UNSAT.

The ENTIRE derivation consists of **14 `pol` steps and
zero `rup` steps**, for arbitrary supported odd rim length
within the source-recognizer's stated size gate. Complexity
and proof length are polynomial in the EXPLICIT source length;
the number of proof lines is constant, while each line
references O(n) original clauses.

**This is a limited polynomial original-source proof of an
explicit recognizable odd-wheel 3-coloring subclass only.**
It is not a proof for the original WEIGHTED Petersen PCMAX
300-clause encoding, not a general odd-cycle 3-colorability
algorithm, and not an algorithm for all NP-complete SAT/PCMAX.

### Completed independent VeriPB3.0.2 audit

https://github.com/Frane12/AndroidGameTest/actions/runs/43868313721

- 9/9 original source CNF odd-wheel cases W5, W7, W9 accepted
  by independent external VeriPB 3.0.2 (three variable/ordering
  permutations each).
- Every proof has EXACTLY 14 `pol` and ZERO `rup` steps.
- Source proof size: 443–593 bytes.
- External VeriPB verifier time roughly 0.0026–0.0027 s
  per case on this single GitHub runner; startup included.
- 5 controls: SAT W6, SAT W8, SAT K3,3, unsupported UNSAT K4,
  unsupported original weighted Petersen -> all UNKNOWN, no proof.
- Source-byte SHA tampering and deletion of a required hub/rim
  mutex clause were rejected.
- Single logical CPU, no CDCL/DPLL/portfolio in the pure PB producer.

## Reproduce the two scoped workflows

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target drnas-ipg5c-onehot -j2
    python3 -u research/ipg5c_general_benchmark.py
    python3 -u research/ipg5d_pure_pb_benchmark.py

Both benchmarks expect pinned external VeriPB 3.0.2; the
IPG5-C benchmark also expects pinned drat-trim.

## Research consequence

The three-class, source-clause-driven viewpoint produces an
EXPLICIT limited family where integer PB cuts alone finish
UNSAT without any search-generated RUP, unlike IPG5-B's
100 DPLL/RUP steps. Our next problem is to discover source
graph structures like odd wheels automatically in other
CNFs, and then to derive source-supported PB cuts for
non-wheel and original PCMAX structural obstructions.

Do NOT treat Petersen semantic permutations as source-disjoint;
do NOT claim proven general P=NP or verified competitor PAR2.
Source proofs are not production DRNAS until further integration
and prospective mixed holdout validation.
