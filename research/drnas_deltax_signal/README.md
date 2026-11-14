# DRNAS DELTAX-SIGNAL1: source-blind implication reach as a utility prefilter

**Branch** experiment/drnas-deltax-signal1-20261114  
**Successful full CI** https://github.com/Frane12/AndroidGameTest/actions/runs/43601959681  
**Purpose** learn *when to spend search effort checking a proved guarded equivalence*, without ever weakening SAT/UNSAT correctness.

## Mathematics and enforcement

A DELTAX candidate already passes the independent original-source
one-pivot-resolvent check and original reverse binary implication.
When its local guard is FALSE, it represents a sound conditional
Boolean equality. The new SIGNAL1 policy does **not** assert anything:
it counts the distinct currently *unassigned* variables reachable in
at most **3 ORIGINAL binary-implication steps** from both polarities of
the candidate's unassigned endpoint variables. Traversal is strictly
bounded to 160 visited implication states. Learned clauses and deleted
binary implications are excluded.

Let this source-CNF feature be R(F,trail,candidate). SIGNAL1 cheaply
rejects a candidate before running the old GUARD A/B cloned-CDCL test if
R < theta. Otherwise the original GUARD1 pairs of same-state bounded
clones evaluate the clause exactly as before. Even after signal approval,
the original source proof gate remains mandatory. No parallel solver,
no speculative SAT/UNSAT promotion, and one process/logical CPU.

The threshold theta is **learned**, rather than hardcoded based on a
graph name, degree, known answer, or benchmark family.

## Experimental separation

60 new graph cores; 180 distinct matched CNF sources (OFF dummy-link
control, LOW1 low-degree graph link, HIGH1 high-degree graph link).
Graphs are divided BEFORE execution and SHA-pinned:
- 30 distinct train graphs / 90 original CNFs
- 15 distinct validation graphs / 45 original CNFs
- 15 distinct untouched holdout graphs / 45 original CNFs

The four graph families are planted colorable, K4 UNSAT, odd wheel UNSAT,
and even wheel SAT. Graphs and seeds are new relative to GRAPH-ABLATION1,
with an explicit historical SHA-disjoint check. All variants of a
particular graph stay in the SAME partition (no graph leakage).

The selection criterion compares **graph-level**, not duplicated
formula-level, native CDCL decision/conflict differences vs JOIN, with
a regression penalty and a modest penalty for extra expensive clone
checks. The only thresholds considered are 0, 4, 8, and 16.

Four fitted choices (train data ONLY):

| Threshold | Train graph groups improved | Regressed | Clone checks | Training score |
|---|---:|---:|---:|---:|
| 0 | 3 | 0 | 28 | 29.44 |
| 4 | 3 | 0 | 24 | 29.52 |
| **8** | **3** | **0** | **7** | **29.86** |
| 16 | 3 | 0 | 4 | 19.92 |

The selected threshold theta=8 is frozen in policy JSON with its binary
and train/validation/holdout source SHA hashes BEFORE the validation or
holdout starts. Neither split affects fitting or refitting.

## Independently checked results

All **810 native solver attempts** in training/validation/holdout were
independently verified on their ORIGINAL CNF: original SAT models or
UNSAT DRAT, with zero observed contradictory certificates, invalid
source resolutions or inconsistent speculative clone outcomes.

In both validation and holdout, the new signal policy produced the
**EXACT same CDCL decision and conflict counts for EACH original CNF**
as the old unfiltered DELTAX-GUARD1 policy.

| Split | Unique graph groups | GUARD1 expensive checks | SIGNAL1 expensive checks | Graph groups improved vs JOIN | Regressed vs JOIN |
|---|---:|---:|---:|---:|---:|
| Train | 30 | 26 | 7 | 3 | 0 |
| Validation | 15 | 6 | 2 | 1 | 0 |
| Holdout | 15 | 12 | 4 | 2 | 0 |

The signal skipped **2/3 of the expensive clone checks** on the untouched
holdout (12 -> 4), and 2/3 on validation (6 -> 2), without losing ANY
observed native search outcome relative to existing GUARD1. The original
unfiltered GUARD still achieves the same graph gains; SIGNAL1 has not yet
improved decision/conflict quality BEYOND GUARD1.

A useful source-blind structural distinction in the holdout:
- OFF dummy-only candidates: observed binary reach was exactly 5 in
  all 6 logged examples, **below threshold 8**.
- LOW1 linked candidates: reaches 5 to 9; some pass, others fail.
- HIGH1 linked candidates: reaches 5 to 40; some pass, others fail.
This supports the interpretation that SIGNAL1 detects whether the new
relation is actually connected to a larger implication structure,
rather than using source labels.

### Three concrete cases

Validation graph: K4_new_07. The signal retained improvements in two
linked variants: HIGH1 gained 2 decisions and 1 conflict versus JOIN;
LOW1 gained 1 decision and 1 conflict.

Untouched holdout graph even_wheel_new_12: HIGH1 gained 5 decisions / 1
conflict vs JOIN, LOW1 gained 1 / 1.

Untouched holdout planted_new_14: HIGH1 gained 2 / 1, LOW1 1 / 1.
All six positives had the same outcome with unfiltered GUARD1.

## Boundaries and risks

1. This proves *selective screening of cloned candidate evaluations*,
   not a new theorem, a universally superior SAT strategy, or a
   statistically robust speed increase.
2. The total graph sample is 60 independent graph seeds, but each
   graph's OFF/LOW1/HIGH1 variants are correlated.
3. Timing is not a certified gain. Sources are short (~few ms) and
   CI jitter can swamp benefits; on the holdout, observed total
   solver wall time was slightly higher for SIGNAL1 than GUARD1 in
   single executions despite fewer clone checks.
4. The maximum reach threshold 8 is an empirical, source-blind training
   result. New families could require different thresholds. Learn
   only from separated train splits.
5. The same-state clone guard remains an imperfect heuristic, and
   source-certified learned clauses are not magically undoable from
   an already-committed main solver state.
6. **No main edits, frozen reference changes, or solver promotion.**

## Next mathematical milestone

Use the structural reach score together with a *measured bounded BCP
propagation-frontier gain* or reason-graph LBD (both source-blind),
and test whether the combination predicts **which** guard-proved
clauses genuinely reduce future CDCL decisions/conflicts, rather than
merely reducing the number of speculative checks. Use source-disjoint
mixed formulas and independent real SAT competition instances.
