# DRNAS MATCH-2 × IPG-BDD — bounded exact job-mask proof (2026-11-16)

Branch: `experiment/drnas-match2-ipg-bdd-mask1-20261116` only.
No production C++ solver, main, APK, frozen solver, or references changed.

## Summary: what is and is not integrated

MATCH2 used a **scalar Hall capacity** per resource. IPG-BDD1 used
**two-dimensional count profiles** across source-verifiable BDD paths.
This new bridge replaces scalar/count-only summaries by **exact job-set
(bitmask) profiles** inferred from source clauses. It uses implicit
BDD-like subset propagation but does **NOT** invoke the native IPG-BDD1
graph extractor or its standard graph-format verifier. Those remain
separate modules. The new source verifier is independent Python.

The method is exponential in the number of jobs. The explicit
source-grounded job-mask pilot limits to n<=15 jobs, <=5 machines and
<=5000 source clauses; it is **not** a polynomial solution to general
PCMAX, SAT or NP-complete problems.

## Proof statement

Let `G_j = {x_{j,1}, ..., x_{j,m}}` be disjoint source positive
ALO clauses. The checker also requires every pairwise negative
AMO clause `(-x_{j,r} OR -x_{j,s})`; thus each job must choose exactly
one of its machine selectors. A source-inferred resource partition
`M_1,...,M_m` must cover these variables without overlaps and contain
exactly one selector from every job.

For each machine i, collect every original all-negative clause with
all its variables in M_i. The clause `(-x_{j1,i} OR ... OR -x_{jk,i})`
forbids every local job set containing {j1,...,jk}. We compute the exact
set `A_i` of locally admissible job masks under this **subset of original
CNF clauses**.

Starting from `R_0 = {empty}`, convolve:
```text
R_(i+1) = {u union v : u in R_i, v in A_(i+1), u intersect v = empty}.
```

If the full job set `{1,...,n}` is not in `R_m`, the ORIGINAL CNF is
UNSAT. Every genuine original-CNF model necessarily chooses one selector
per job and must avoid all included negative clauses; omitting other
original clauses can only enlarge the relaxation and never create a
false UNSAT.

Independent checker:
`research/match2_bdd_mask1_checker.py`
re-reads original source bytes, validates each ALO/AMO clause, every
selector mapping, source SHA, source negative clause-derived profile
sizes, and performs a separately coded disjoint-cover DP. Do NOT count
an `UNSAT_UNCHECKED` producer output as verified.

## Local mathematical pilot, source SHA frozen

Original generated PCMAX Petersen source:
`research/ipg1_fixtures.py:petersen()`

* SHA-256: `c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70`
* CNF: 45 variables, 300 clauses; 15 job groups × three machines
* Each resource contains 80 original all-negative subset constraints
  spanning distinct jobs
* Exact admissible local job sets: `[7036,7036,7036]`
* Global exact covered-mask counts: `[1,7036,25694,32766]`
* All-jobs target bitmask: missing after three machines (UNSAT)

These numerical values were reproduced locally by two independent
DP traversal strategies. The source-generated original formula was
already known UNSAT from prior IPG1; this is a second proof route.
The end-to-end standalone GitHub Actions bench audits full source
verification and tamper controls before any workflow success claim.

## GitHub Actions benchmark

`python3 -u research/match2_bdd_mask1_bench.py`

Includes 45/300 original, two independently renumbered/shuffled
versions, direct capacity 2 scheduling SAT/UNSAT instances, original
with all weighted forbidden clauses removed (SAT model), single-missing
forbidden triple (SAT model), original SHA checks, forged certificate
mutations and changed-source rejection.

The SAT controls are verified by evaluating their models on every
literal of every original clause; UNSAT needs independent proof checker.

Benchmarks are **retrospective generated source** and NOT official blind
SAT2024/2025/2026 holdouts. No production verified PAR2 improvement,
no comparison to Kissat/CaDiCaL/CMS, and no standard DRAT/LRAT/VeriPB
certificate is claimed. A successful workflow validates only this
restricted pilot.

## Next research tasks

1. Connect source-verified existing IPG-BDD1 graph extraction to
   compact bounded *sparse* bitmask profiles, without falsely replacing
   verification with inference from source comments.
2. Use Hall/MATCH2 capacity cuts to shrink mask DP or selectively
   promote a multi-count profile when a cap is exceeded.
3. Attempt standard proof traces (VeriPB or DRAT/LRAT) and verify
   source-byte SHA plus independent checker outcomes.
4. Run source-disjoint prospective real PCMAX and mixed SAT CNFs with
   fixed CPU, same cap, SAT-model checking and verification-inclusive
   E2E PAR2 before consideration for main.
