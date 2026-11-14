# DELTAX-HARD — connected synthetic 3-SAT, parity and pigeonhole

Branch: experiment/drnas-deltax-hard-synthetic-20261114
Verified GitHub Actions run: 43593649514
Scope: **exploratory synthetic research**, one repeat of 28 generated CNFs,
three modes each (JOIN, DELTAX-SHADOW, DELTAX); never a blind holdout.

## What this tests

We deliberately connected 2–3 real-witness-derived, guarded-equivalence
gadgets to independently generated harder cores. Previously, tiny cases
showed only shorter propagation paths, with no different CDCL decisions.
Here we compare native CDCL decisions/conflicts and ACTUAL traced
DELTAX-origin reason enqueues.

The generated CNFs have 40–165 variables and 107–689 clauses; the hard
families are planted 3-SAT (10), unplanted random 3-SAT (8),
Tseitin inconsistent parity (6), and pigeonhole UNSAT (4). 74 guarded
nonlinear motifs were included across these sources. No source names,
labels, known solutions or feature-engineering metadata are supplied to
the actual solver.

All 84 solver attempts reported checked SAT models or independently
verified original-CNF UNSAT proofs (11 SAT, 17 UNSAT for each mode).
There are no WRONG SAT/UNSAT claims. No main changes or promotion.

## Source/proof-first causal findings

Across 28 DELTAX native runs:
- 56 original-source-RUP learned guard clauses were injected.
- 7,494 actual CDCL enqueues used a DELTAX-origin clause as their
  immediate propagation reason.
- JOIN and SHADOW had zero such reason enqueues by design.
- Five paired instances reduced decisions AND conflicts relative to JOIN;
  three increased both; the other 20 were unchanged.
- All 28 JOIN cases were nontrivial by the experiment's objective
  criterion: at least five conflicts or 20 decisions.

Specific verified examples (JOIN -> DELTAX):

* Planted3_n50_s0: decisions 40 -> 31, conflicts 16 -> 15.
* Planted3_n50_s1: decisions 40 -> 34, conflicts 25 -> 24.
* Planted3_n150_s1: decisions 404 -> 377, conflicts 301 -> 300.
* Random3_n84_s1: decisions 145 -> 103, conflicts 68 -> 66.
* PHP 6 pigeons / 5 holes: decisions 156 -> 154,
  conflicts 137 -> 132.

Critical adverse results (all UNSAT results independently certified):
* PHP 7/6: conflicts 627 -> 692.
* PHP 8/7: conflicts 3416 -> 4440.
* PHP 9/8: conflicts 27931 -> 37584.

The latter three dominated the aggregate:
- JOIN: 43,570 decisions; 37,204 conflicts.
- DELTAX: 55,004 decisions; 47,936 conflicts.
- Thus the experiment does NOT show an aggregate search improvement.
- No DELTAX clause was recorded as the direct CDCL conflict clause in
  this run, even though many DELTAX-origin clauses were used as
  propagation reasons and changed the subsequent search trajectory.

## Interpretation

The experiment establishes, for some harder *synthetic* cases, that
source-entailment-certified guarded equations can actually alter native
CDCL branching trajectories and reduce decisions/conflicts.
It also establishes that the very same mechanism may worsen hard UNSAT
search substantially. It does NOT establish a new mathematical theorem,
a general SAT speed benefit, or transferability to competition sources.

One repeat with limited related gadget families is not enough for
statistical confidence. It is an A/B causal intervention in this controlled
harness, not a representative broad-world SAT dataset.

## Next test

Investigate the PHP regressions rather than simply adding more clauses.
Measure decision- and conflict-trail divergence after the first DELTAX
injection and matched-source clause-reason utilization. Compare a
source-blind selective gate and OFF/SHADOW/ON under two new seeds, on
completely new synthetic cores, with a held-out test. Never read status
labels or source names inside the gating logic. Preserve original-CNF
SAT models and independent UNSAT DRAT checking. Do not promote into main.

Full JSON paired report and per-trial event logs were retained as
GitHub Actions artifacts for run 43593649514.
