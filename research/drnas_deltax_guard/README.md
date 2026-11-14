# DRNAS DELTAX-GUARD1 — source proof gate and same-state clone A/B

**Branch:** experiment/drnas-deltax-guard1-paired-clone-20261114  
**Successful GitHub run:** 43596056826 (2026-11-14)  
**Status:** experimental, no main promotion or claimed speedup.

## What is actually protected?

DELTAX creates guarded equality candidates from a nonlinear separator witness.
GUARD1 performs two logically separate checks BEFORE any DELTAX clause is
added to the real CDCL solver:

1. **Soundness gate** — verify both ORIGINAL source parents, the exact
   resolution pivot, the unique-literal normalized resolvent, and the
   ORIGINAL reverse-implication clause. An invalid candidate is rejected
   before the original proof log, live trail, watches or clause database can
   be modified. Each admitted one-step resolvent is an original-source RUP
   consequence (and original SAT/UNSAT outcomes are independently checked).
2. **Search-policy gate** — two disposable, independent copies of EXACTLY
   the same current CDCL state are run, one with and one without the RUP
   candidate. Each has up to 128 new decisions, 96 conflicts and a 12-ms
   per-clone wall budget; maximum eight such candidate checks per solver
   run. The forecasts are used only to decide whether to COMMIT the safe
   clause to the real CDCL. They are never used to pronounce SAT or UNSAT.

The policy accepts only a nonregressing, meaningfully better probe or a
bounded successful probe where the baseline did not finish. Inconclusive,
regressing, unsafe and over-budget candidates are rejected. The original
solver remains untouched during speculative probes. Only approved clauses
are sent through the established DRAT-logging live CDCL bridge.

**Important limit:** This is **pre-commit checkpoint isolation**. It is
NOT a general post-hoc rollback of all learned clauses or of the whole
original solver after a candidate has been committed. Once a mathematically
sound clause is accepted, ordinary CDCL may retain it and its subsequent
learning; GUARD1 does not undo that history. Retrospective full-state
rollback would require running committed work in a separately owned solver
copy and committing it atomically, or restarting from a saved checkpoint.

A poor clone outcome is a heuristic risk signal, NOT proof that a correct
clause is useless. The guard can reject useful clauses.

## Fully verified HARD28 comparison

Dataset frozen from the previous DELTAX-HARD synthetic run, source manifest
SHA-256 dd9924240b970ab70a764cc8be6a260e141c0bc823b7601e5dc01df6ce123240.
28 generated original CNFs, four same-binary modes JOIN, DELTAX-SHADOW,
unrestricted DELTAX, DELTAX-GUARD. 112 paired trials, one logical CPU per
serial solver. Every SAT witness checked on ORIGINAL CNF, every UNSAT
verdict independently certified on ORIGINAL CNF with drat-trim.

### Main counters

| Arm | Verified | Decisions | Conflicts | DELTAX clauses | Genuine reason enqueues |
|-----|---------:|----------:|----------:|---------------:|------------------------:|
| JOIN | 28/28 | 43,570 | 37,204 | 0 | 0 |
| SHADOW | 28/28 | 43,570 | 37,204 | 0 | 0 |
| DELTAX unrestricted | 28/28 | 51,015 | 44,494 | 59 | 6,836 |
| DELTAX-GUARD1 | 28/28 | 43,518 | 37,200 | 5 | 7 |

DELTAX-GUARD1 examined 42 candidates, **accepted 5 and rejected 37**.
There were no exhausted candidate-count budgets, no conflicting clone
outcomes, and no invalid source-resolution emissions.

Compared with JOIN, GUARD1 had fewer conflicts in 3 sources, more in 0,
and fewer decisions overall by 52. This is a tiny in-sample difference,
not a universal advantage or statistically significant speed improvement.

### Crucial PHP safety check

| Formula | JOIN conflicts | unrestricted DELTAX | DELTAX-GUARD1 |
|---------|---------------:|--------------------:|--------------:|
| PHP 6/5 | 137 | 132 | 137 |
| PHP 7/6 | 627 | 692 | 627 |
| PHP 8/7 | 3,416 | 4,440 | 3,416 |
| PHP 9/8 | 27,931 | 34,143 | 27,931 |

The guard refused every DELTAX candidate in all four PHP cases, including
one previously beneficial PHP 6/5 case. That is a clear example of the
safety-versus-exploration tradeoff: GUARD1 prevented the tested PHP
regressions by reverting to baseline behavior, at the cost of rejecting
some mathematically useful clauses.

### Examples preserving useful intervention

- Planted 3-SAT n50 seed0: JOIN 40 decisions / 16 conflicts;
  GUARD1 31 / 15, with 2 source-RUP clause approvals.
- Planted 3-SAT n50 seed1: JOIN 40 / 25;
  GUARD1 34 / 24, with 2 approvals.
- Random 3-SAT n84 seed1: JOIN 145 / 68;
  GUARD1 108 / 66, with 1 approval.
- Source-clause proof and all original-CNF final SAT/UNSAT checks passed.

## Limitations and next controls

This is a targeted, retrospective synthetic set whose behavior we already
examined. Do NOT treat it as a blind generalization test. Real competition
CNFs may have different resource/structure distributions, and clone overhead
can be substantial; no wall-clock improvement is claimed.

The next independent step should use new sealed synthetic seeds and
source-disjoint real SAT formulas, with an additional mutation/fault-injection
test to verify that an intentionally wrong source parent or resolvent is
rejected before proof logging. An adaptive guarded policy may eventually
learn a less conservative decision boundary, but only with separate training,
validation, and untouched holdout. Do not merge into main until then.
