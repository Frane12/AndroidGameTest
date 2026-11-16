# DRNAS MATCH-2: source-CNF capacitated Hall audit (2026-11-16)

**Experimental only:** `experiment/drnas-match2-capacitated-hall-20261116`.
Based on STRUCTURE-1; no edits to `main`, frozen reference solvers, APKs
or production DRNAS. No external tools/subprocess/extra logical CPU during
solver run. This is a **Python research prototype**, not C++ integration.

## Precise mathematical rule

For each job j, original DIMACS contains a positive at-least-one clause
`x[j,1] v ... v x[j,r_j]`. The selected original ALO groups use pairwise
disjoint Boolean variables. Every selector belongs to precisely one
reconstructed resource r. An original negative unit `-x` removes that
choice. From actual SOURCE negative forbidding clauses, establish that
a resource r admits no more than c_r *different* jobs simultaneously:

For every (c_r+1)-tuple of available selector variables belonging to
different jobs and assigned to r, the original clause
`(-x_1 v ... v -x_{c_r+1})` must literally exist.

This condition suffices regardless of how many choices each job has.
For any job subset S, the number of distinct selected resources in r is
bounded by `min(c_r, number_of_S_jobs_allowed_in_r)`. Thus a witnessed

`|S| > sum_r min(c_r, |S intersect jobs_allowed_in_r|)`

proves UNSAT of the **original CNF**, because every job in S must have
at least one selected literal, and each resource can accommodate at most
its independently proved capacity. Other unexamined original clauses
cannot restore satisfiability.

The producer infers candidate resource clusters using connected
components of original all-negative forbidden tuples spanning distinct
jobs. That grouping is just a hypothesis; an entirely separate checker
re-verifies ALO clauses, every forbidden tuple required by each capacity,
the resource partition, unit exclusions, source SHA256, and Hall cut.

## Bounded implementation and limitations

* Job groups: 2..40, up to 128 distinct choice selectors.
* Source-CNF direct negative clauses, forbidden tuple rank <=4, budget
  50,000 checked tuples, exhaustive job subset search <=18 jobs.
* If any premise/budget fails, the result is UNKNOWN. SAT is never
  claimed by MATCH-2, and UNSAT is never accepted without separate check.
* Handles differing capacities and per-job variable/slot permutations,
  which MATCH-1 generally cannot see.
* It does NOT yet decode arbitrary BDD transitions or general pseudo-
  Boolean constraints. This is source-bound capacity reconstruction,
  not a general PCMAX algorithm or polynomial-time algorithm for NP-hard SAT.
* The project-specific checker is NOT a DRAT/LRAT/VeriPB standard
  checker. General proof export and C++ integration remain future work.

## Local frozen pilot (44 cases, one logical CPU)

`python3 research/match2_bench.py`

* 26 independently verified source-CNF UNSAT proofs.
* 6 covered by unchanged MATCH-1; **20 additional proofs** beyond MATCH-1.
* 17 SAT controls; 0 false UNSAT.
* 18 UNKNOWN, including original 45-variable/300-clause Petersen PCMAX.
* 21 small tests also checked by independent exact DPLL oracle.
* 18 intentionally forged or source-mutated certificates rejected.
* A weakened 7-job/three-machine capacity-2 formula made SAT by removal
  of one critical 3-selector forbidden clause correctly returns UNKNOWN.
* Every generated source CNF and JSON certificate is archived by CI.

These are synthetic/retrospective **family-targeted** cases, not
source-disjoint prospective blind real-world SAT Competition benchmarks.
The increase 6 -> 26 is new coverage on this generated corpus; it is not
a 4.3x speedup or a broad empirical claim. No verification-inclusive
PAR2 comparison with Kissat, CaDiCaL or CMS has been completed.

## Reproduction and next milestones

```sh
python3 -m py_compile research/match2.py research/match2_checker.py research/match2_bench.py
python3 -u research/match2_bench.py
python3 research/match2.py source.cnf --certificate proof.json
python3 research/match2_checker.py source.cnf proof.json
```

Next test the 45/300 original weighted Petersen encoding using a
direct source-bound BDD/PB-to-capacity proof bridge, keeping the existing
IPG-BDD1 checker and native C++ guard unchanged. Only count an UNSAT
after exact-source verification and, for competition-level claims, an
independently accepted standard proof. Then perform prospective,
source-disjoint blind original-CNF PAR2 with one CPU per arm.
