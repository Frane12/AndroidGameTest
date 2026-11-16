# DRNAS IPG7 — source-bound global exact-capacity configuration proof

## Research outcome and exact scope

IPG7 replaces the earlier IPG6B local-mutex closure path with a
GLOBAL exact-cover view of source-validated weighted bin packing.
It avoids the need to separately derive all 66 unproved Petersen
graph mutexes. It also avoids CDCL and DPLL variable branching.

**However, it uses O(2^n) enumeration of job subsets** to recover
the complete exact-capacity configurations. No general polynomial
PCMAX/P=NP claim is made. This is a research Python prototype, not
an integrated C++ DRNAS SAT guard. `main` is untouched.

## Theorem: exact-total three-machine packing

Let there be n jobs with positive integer durations p_j and
three identical machines each with capacity T. Suppose

  sum_{j=1}^n p_j = 3T.

Every feasible schedule must fill ALL three machines to EXACTLY T.
Let F = {S subseteq [n] : sum_{j in S}p_j = T}. Then

  SAT iff there exist A,B in F such that A intersect B is empty.

Proof: SAT implies first and second machines use disjoint exact-T
sets. Conversely, two disjoint exact-T sets A,B leave all remaining
jobs with total 3T-T-T=T, so complement(A union B) is the third bin.

In particular, if every two members of F intersect (including
the same member), the instance is UNSAT.

## Connection to the ORIGINAL CNF

The research generator is provided exact numerical job durations
and T as an explicitly frozen input manifest. It never assumes
that user-supplied numbers accurately describe the source.

An entirely SEPARATE source checker reconstructs the original
3-machine direct CNF by enumerating ALL inclusion-minimal
over-capacity job subsets and their three negative machine clauses,
plus ALL original exactly-one job selectors (positive ALO and
pairwise negative AMO). It compares the complete ORIGINAL CNF
multiset, not a filename or problem label. It also recomputes
every exact-T configuration independently via combinations.

Proof acceptance is a TWO-PART scientific claim:

  (A) Independent exhaustive SOURCE-CNF-to-configuration-
      semantics equivalence checker;

  (B) Independent external VeriPB 3.0.2 verifying the
      **DERIVED configuration-master CNF**, NOT the
      original weighted CNF directly.

**The combined bridge is a sound bespoke structural certificate,
not an original-source VeriPB/DRAT proof accepted as a single
standard SAT competition certificate.**

## Pure PB proof for the derived master

Suppose k exact-T configurations are found and EVERY two intersect.
Use new master variables a_i and b_j for the first and second
machines choosing configurations i and j, respectively.

The master CNF contains:

  sum_i a_i >= 1,
  sum_j b_j >= 1,
  ~a_i + ~b_j >= 1, for EVERY pair (i,j).

There are 2k master variables and exactly 2+k^2 clauses.
For fixed first-machine choice i, sum the k cross mutex clauses
and the second-machine ALO:

  k~a_i + sum_j~b_j + sum_j b_j >= k+1
  => k~a_i >= 1.

After integer division by k,

  ~a_i >= 1.

Do this for i=1..k and sum all these inequalities with the
first-machine ALO; the result is 0>=1. This is a standard
VeriPB 3.0 proof with **exactly k+1 `pol` lines**, 0 `rup`.

No SAT or CDCL/DPLL solver searches for the master proof.
The separate original subset enumeration is finite but
exponential O(2^n), explicitly bounded to n<=15.

## Grounded pilot data

The original weighted Petersen PCMAX source uses:

  SHA256 c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70
  15 jobs, 3 machines, T=29,524, 45 Boolean variables and 300 clauses.

All exact-T subsets (zero-based job indices):

- {0,2,9,10,11}
- {0,3,7,13,14}
- {1,3,5,11,12}
- {1,4,8,10,14}
- {2,4,6,12,13}
- {5,6,7,8,9}

Each exact-T configuration has exactly 5 jobs, and
every pair of the six intersects. The derived master
therefore has 12 variables, 38 CNF clauses and a
**7-line / 383-byte pure VeriPB proof**.

The new independent 5-job case has durations
  [13,20,23,8,20], T=28, total=84=3T.
Exact-T sets are {1,3} and {3,4}, both containing job 3.
The derived master has 4 variables, 6 clauses, and
a **3-line / 155-byte pure VeriPB proof**.

Two positive original-source controls:

- K4 cubic graph job durations p_(u,v)=3^u+3^v,
  capacity 40, six edges, three disjoint perfect matchings.
- Six jobs of duration 3, T=6, 15 exact-T bin configurations.

For both SAT controls the generator emits a COMPLETE original
assignment and the independent checker verifies EVERY
source CNF clause. A 7-job case with total load 3T but
ZERO exact-T subsets is conservatively UNKNOWN in this pilot
(the zero-configuration branch is not supported by its master).

## What we still lack

The original weighted Petersen formula already has a
standard source-VeriPB proof through IPG5-E; however that
100-line POL proof's structure was discovered by DPLL.

The new IPG7 global argument discovers the obstruction
without DPLL and has a 7-line pure-PB proof on the
projection. Its BESPOKE structural original-source checker
still needs an accepted translation to standard VeriPB
**directly against the 300 original clauses**, rather
than independent source-to-master equivalence checking.

Another engineering gate is a source-recognized C++ module
with strict budgets and prospective source-disjoint paired
verification-inclusive PAR2 against frozen DRNAS/CDCL
and Kissat/CaDiCaL/CryptoMiniSat. A one-case time cannot
establish an overall speed improvement.

## Reproduction

    cargo install veripb --version 3.0.2 --locked --root ./veripb-tool
    python3 -u research/ipg7_benchmark.py

The workflow output contains exact source CNFs, the
input manifest, generated SAT assignments, configuration
masters, pure PB proofs, independent bridge logs, and
the external VeriPB checker logs.

GitHub Actions run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43885487050
