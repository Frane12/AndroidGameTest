# DRNAS ATLAS-MAP2 — live certified relation map for native CDCL

**Author:** Frane Drnas · **Date:** 2026-11-11  
**Experimental branch:** `experiment/drnas-atlasmap2-live-relations-20261111`  
**CI evidence:** [GitHub Actions run 42938394455](https://github.com/Frane12/AndroidGameTest/actions/runs/42938394455)

## Why MAP2 exists

ATLAS1 / ATLAS-X identified and rewrote small Boolean modules *before* CDCL.
ATLAS-MAP1 added a source-certified parity disjoint-set map and local
statistical memory, still primarily before search. ATLAS-MAP2 connects
a certified parity **relation map** directly to the original, independently
implemented DRNAS R3C CDCL assignment trail. The map itself is built
from source clauses before search; **interventions occur online**, after
assignments and at the BCP search loop.

This is **not** online discovery from arbitrary learned clauses or a new
independent UNSAT proof checker. The cheap cross-formula MAP1 statistics
are not currently used to control MAP2's live scheduler. That is separate
future work.

## Proof obligation — no guessed relations

A relation `x XOR y = r` is accepted only when the complete two-clause
CNF parity encoding occurs in the **original** DIMACS. The source XOR
detector already used in native R3C checks both required clauses; it
never accepts only one half of the encoding.

Transitive chains are combined using GF(2) parity DSU.
For every pair `x,y` inside the certified component, the derived
binary implication `NOT assigned(x) OR assigned_expected(y)` is
entailed by the original source chain. It is inserted into the native
CDCL clause database with an exact implication clause ID and used by
the solver's own 1-UIP analyzer; no foreign SAT backend is invoked.

A group must contain at least **three** variables (single direct binary
pairs already benefit from native watched BCP), at most 32 variables,
with bounded group/source counts and 250,000 group checks per solve.
On budget exhaustion or inconsistent parity cycles the controller
**abstains**: the original CDCL remains responsible for the solve.

On an assignment, the group enters a de-duplicated pending queue.
The group is inspected **before** normal watched BCP and again after
BCP, so genuine source-entailed implications can enter the trail and
change the search. The mechanism is also reconsidered at restarts.

## Experiment arms

| Mode | Behavior |
| --- | --- |
| `A` | Native R3C CDCL, unmodified original CNF |
| `ATLASX` | Existing pre-CDCL small truth-table/lazy expansion frontend |
| `MAP1` | Existing source-certified parity substitution + ATLAS-X fallback |
| `MAP2_SHADOW` | New live detector but **does not enqueue** proposed assignments |
| `MAP2_LIVE` | Injects only source-entailed binary CDCL reasons and implied values |
| `MAP2_COMBO` | MAP1 preprocessing first, then MAP2 live trail on original-source certified relations |

There is no change to the stable `main` branch. Source remains C++17
and uses the DRNAS native CDCL engine, not Kissat or CaDiCaL libraries.

## Local verification

```sh
mkdir -p mre_atlasmap2/bin
python3 research/drnas_atlas1_generate.py --out mre_atlasmap2/atlas1_table.hpp
g++ -std=c++17 -O2 -Wall -Wextra -I mre_atlasmap2 \
  research/drnas_atlasmap2.cpp -o mre_atlasmap2/bin/drnas_atlasmap2

mre_atlasmap2/bin/drnas_atlasmap2 --atlasmap2-selftest
python3 -u research/drnas_atlasmap2_smoke.py

mre_atlasmap2/bin/drnas_atlasmap2 sample.cnf --mode A --time 6
mre_atlasmap2/bin/drnas_atlasmap2 sample.cnf --mode MAP2_LIVE --time 6
mre_atlasmap2/bin/drnas_atlasmap2 sample.cnf --mode MAP2_SHADOW --time 6
```

The correctness CI compares **240 randomized small source-paired formulas**
in 3 modes (720 total) against an independent exhaustive truth-table SAT
oracle and checks every resulting SAT witness on the original CNF.
Additional tests verify a **real in-trail propagation and reason clause**,
shadow-mode nonintervention, incomplete-pair rejection, contradictory
parity-cycle fallback, and MAP1+MAP2 combination.

## Performance protocol

The benchmark uses SATLIB source-only SHA rank **58**, four uf-series
families, two repetitions, a 6-second cap, and one logical CPU per solver
arm. It records full E2E time, PAR-2, SAT model correctness, conflict
counts, shadow opportunities, actual injected implications, and
negative/control outcomes.

**Do not mix the two distinct cohorts:**

1. `original`: unmodified public SATLIB CNF, source SHA recorded.
2. `mixed_augmented`: intentionally **synthetically constructed**
   additional parity chain (6 new variables and 11 original new
   clauses), independent from the SATLIB core. This preserves SAT
   status and validates that MAP2 operates on a *mixed structure*, but
   is **not an untouched official benchmark** and cannot establish
   a general native solver speedup.

Kissat and CaDiCaL are included only as **reference comparator arms**;
they are not linked or invoked by native DRNAS source. A solver report
of UNSAT without an independent original-CNF LRAT certificate is
**not independently certified**. SAT claims require verification on
the exact original cohort CNF.

## Limitations and next steps

- Binary parity blocks alone are easy for existing watched BCP. MAP2 may
  merely *reorder* already available implications and impose overhead.
- Group counts and new clauses are causal **events**, not proof of
  reduced runtime, fewer conflicts or general competitiveness.
- The relation table is sourced at solve start; MAP2 does **not yet
  learn new equivalences from CDCL learned clauses during search**.
- Real mixed SAT and UNSAT original-source holdouts with independent
  UNSAT proof verification are needed; public SATLIB and synthetic
  positive controls are insufficient to claim a breakthrough.
- An independent original-CNF LRAT/FRAT emitter and checker remain open.
- Statistical transfer must use strictly disjoint training/holdout
  formulas with no leaking solution outcomes into the selector.

**Any improvement claim must use matched, original-source, one-logical-CPU
E2E results including MAP2 setup overhead, solved counts and PAR-2.**
