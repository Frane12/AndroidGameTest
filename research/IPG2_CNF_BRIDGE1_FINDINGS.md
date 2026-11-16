# IPG2-CNF bridge 1 — verified findings (16 November 2026)

## Objective and method

Source-bound proof pilot on exact DIMACS CNFs. Recognize FULL, disjoint
one-hot groups for m = 2 or 3 machines with no auxiliary variables,
then extract only direct all-negative source clauses of width <= 3
from one machine. Two job classes are guessed conservatively;
each claimed forbidden count-vector is validated against ALL
source selections in the class. If no global count-state DP can assign
every job, original CNF is UNSAT. A separate checker re-reads the
original source, recomputes every claimed forbidden pattern, and
independently recomputes the count DP. The detector never outputs SAT.

Source constraints, not job names or benchmark labels, are proof premises.
Polynomial complexity is restricted to the direct one-hot layout,
two count classes and fixed forbidden pattern arity <= 3. This
is a sufficient UNSAT test only; it does not solve all PCMAX instances.
The proof format is structural source-based, NOT DRAT/LRAT/VeriPB.

## Outcome on frozen pilot

- 70 exact-generated direct scheduling CNFs on 2 and 3 machines
  (each source uses original one-hot + minimal overweight clauses).
- 60/60 oracle-UNSAT accepted by the independent source checker.
- 10/10 oracle-SAT never incorrectly classified as UNSAT.
- 8 authentic, SHA-frozen official original PCMAX BDD CNFs:
  0 independently verified by THIS new bridge, 8 UNKNOWN.
- Earlier 45-var/300-clause Petersen packing CNF: UNKNOWN.
- The targeted mixed-size source [6,6,6,3,3,3,3], T=10,
  m=3, was independently certified UNSAT using source-implied
  restrictions (0,2) and (2,1) on job-count classes [4,3].
- Forged count vectors, tampered source hashes and falsified
  reachability claims were rejected by the independent checker.

CI: https://github.com/Frane12/AndroidGameTest/actions/runs/43832802808

## Why authentic BDD originals remain UNKNOWN

The current bridge has a hard variable cutoff of 144 and recognizes
only full one-hot 2/3-machine direct encodings. All eight
source-frozen originals exceed this cutoff and use a BDD encoding
with auxiliary variables. Their unsupported result is a gated
UNKNOWN, NOT evidence that the count approach fails mathematically.

Inspection of exact original DIMACS bytes reveals the more specific
obstacle below. For each row the widest positive clause group was
used as a candidate selection of job-assignment variables;
all rows show ZERO directly source-present all-negative
same-position selector clauses of arity 1 to 3. Those restrictions
are encoded through BDD helper variables rather than directly
as source selector nogoods.

| Frozen original index | Vars | Candidate group width | Groups | Selectors | Other vars | Direct same-position negative patterns (<=3) |
|---|---:|---:|---:|---:|---:|---:|
| 00 | 1516 | 11 | 20 | 220 | 1296 | 0 |
| 02 | 1654 | 13 | 10 | 130 | 1524 | 0 |
| 05 | 3639 | 14 | 4 | 56 | 3583 | 0 |
| 10 | 4134 | 20 | 17 | 340 | 3794 | 0 |
| 01 | 8048 | 12 | 25 | 300 | 7748 | 0 |
| 06 | 2351 | 15 | 17 | 255 | 2096 | 0 |
| 11 | 6056 | 23 | 24 | 552 | 5504 | 0 |
| 12 | 17854 | 24 | 43 | 1032 | 16822 | 0 |

These candidate groups need not enumerate ALL jobs, especially
in BDD encodings with restricted assignment domains. Only a
source-checked extractor may promote their interpretation to
a sound machine assignment constraint.

## Next technically meaningful step

1. Reuse the existing PCMAX native BDD extractor but expose its
   exact source-validated per-machine automata independently of
   a capacity contradiction. Do NOT treat guessed helper-variable
   semantics as axioms.
2. Compute count-pattern support via an automaton product of
   BDD states with two small job-count counters, accounting for
   skipped selector levels and early TRUE terminal semantics.
3. Compute a polynomial (in extracted BDD size and job count)
   *relaxed* count profile; only original-CNF-entailed restrictions
   may eliminate global DP states.
4. For every UNSAT claim generate a source-bound certificate
   checked independently; aim to produce standard VeriPB proofs.
5. Run prospective source-disjoint originals and verification-inclusive
   PAR2 before any merge into main.

Nothing in this experiment proves a general polynomial PCMAX solver
or a gain over the already source-verified specialized BDD guard.
