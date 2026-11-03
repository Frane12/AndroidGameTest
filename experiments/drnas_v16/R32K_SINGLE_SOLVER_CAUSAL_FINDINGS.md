# DRNAS R32k — what makes certified XOR units help or hurt one Kissat?

**Verified workflow:** https://github.com/Frane12/AndroidGameTest/actions/runs/41646235624  
**1920-trial artifact:** https://github.com/Frane12/AndroidGameTest/actions/runs/41646235624/artifacts/13233989618  
**Date:** 2026-11-03. All six Actions jobs succeeded; final `R32K_AUDIT_PASS`.

## Change in research strategy

We **abandoned watchdogs, concurrent solvers, helper processes and inter-solver
messages** in the SAT-solving algorithm. R32k executes **exactly one pinned
Kissat per benchmark attempt**, without any user-space worker portfolio.
The native C++/C extension is kept simple: before Kissat preprocessing,
insert a fixed subset of the *same mathematically certified original-CNF
GF(2) root units*. No CDCL policy edit, restart policy change, or learned
clause sharing.

Ablations: original clean Kissat, native instrumented OFF, all certified
units, first four units, first eight units, last four units. All
units and signs are independently checked against the untouched original CNF
prior to accepting a result. UNSAT and incomplete-XOR sources abstain.

Protocol: original upstream Kissat SHA `8af8e56f174b778aef3aa45af9f739b2a5f492c2`;
62 SHA-distinct original CNFs = **two previously measured diagnostic cases**
plus **60 new synthetic generator cases**; 10 repeats for old diagnostics and
5 repeats for each new case; 6 modes = **1,920 paired serial attempts**;
8s cap per attempt; 0 timeouts. 4 independent CI shards, each trial one
pinned CPU/core. SAT model checked against original CNF; UNSAT compared with
source label, not a certified LRAT proof. All tested inputs synthetic.

## Primary causal evidence (same two formulas, same clauses and variables)

| Previously seen R32e formula | Native OFF conflicts | First4 | First8 | Last4 | Full | OFF median wall | Full median wall |
|---|---:|---:|---:|---:|---:|---:|---:|
| `r32e_stress_consistent_visible_51.cnf` | 21 | 49 | 21 | 42 | **56** | 32.994 ms | 33.542 ms |
| `r32e_stress_consistent_mixed_53.cnf` | 27 | **0** | **0** | 46 | **0** | 24.505 ms | 16.302 ms |

All versions of the above formulas have **448 variables, 2,055 clauses, 12
root GF(2) units**, 36 recovered equations and no hidden resolvents. The
exact inferred unit list is identical: `[4,8,12,16,20,24,28,32,36,40,44,48]`.
The root-unit clause occurrence counts are also identical, 32/31/30 each
and 28/27/26 cross-background appearances in groups.

Important label caveat: the R31 generator's `consistent_visible` and
`consistent_mixed` cases use the *same construction branch* with different
family-specific random seeds. Therefore those **labels are not evidence of
different algebraic construction classes**. The opposite conflict result
depends on more subtle placement/topology of the seeded background clauses.

## Original-CNF implication graph proxy: different global topology

For a *diagnostic proxy*, assume all certified w_i=1 and explicit z_i=0,
simplify clauses, and create 2-SAT implication edges from every resulting
binary clause. This does **not** claim to reconstruct Kissat's actual
internal simplification, but tests deeper source topology than clause counts.

Both known instances yield **368 binary clauses** under that full
assignment. Yet their undirected implication-graph component sizes differ:

- Previously seen visible-seed instance: largest 362 nodes, next 100 and 96.
- Previously seen mixed-seed instance: largest 336 nodes, next 88, 21 and 21.
- With **only first eight** w_i assigned, largest proxy component sizes
  are 44 versus 70 respectively.

Thus equal equation count, degree distribution and exact root-unit set
can correspond to sharply different graph connectivity and CDCL response.
Connectivity is a **hypothesis-generating signal**, not a confirmed
predictor. A controlled held-out test is required.

## New synthetic holdout performance

60 new original SHA-distinct synthetic CNFs (42 baseline generated sources
and 18 additional coupled-stress sources), 5 repeats, 300 trials per mode.

| Mode | Summed wall / PAR2 seconds | vs native OFF | Total CDCL conflicts |
|---|---:|---:|---:|
| Clean Kissat | 6.150508 | - | instrumentation absent |
| Native OFF | **6.147271** | reference | **122125** |
| All source-certified root units | **5.991948** | **-2.5267%** | **121755** |
| First eight units | 6.029682 | -1.9129% | 122060 |
| First four units | 6.207498 | +0.9797% | 121970 |
| Last four units | 6.246067 | +1.6072% | 121740 |

Across **60 held-out formulas** using individual source median conflict
counts: all-unit intervention yielded fewer conflicts on **10**, equal
on **48**, and more on **2**. Because many of these tasks are millisecond
scale and substantial sources have zero usable GF2 units, the *time*
difference must be interpreted cautiously. Source-bootstrap 95% interval
of the all-unit median effect is approximately **[-6.105%, -0.047%]**:
just below zero on the limited synthetic generator distribution, not
evidence of a general SAT solver advantage. First8 interval
[-6.028%, +0.062%] crosses zero.

One important additional counterexample: fresh
`r32k_stress_consistent_visible_261.cnf` reduced **39 → 0 conflicts**,
but its median wall time increased **24.439 → 24.696 ms**. Fewer conflicts
do not imply less wall time (propagations, preprocessing, decisions,
overheads and measurement variance matter).

## Next falsifiable scientific test (not a new benchmark claim)

Do not tune a structural selector on the 60 held-out results. Build one
native Kissat instrumented for **early CDCL decisions, unit propagation,
and first-conflict-to-first-learned-clause telemetry**. Use the development
cases to formulate an *immutable* structural hypothesis linking XOR unit
position to original-CNF binary-implication connectivity. Validate on
a NEW untouched set of SAT/Crypto/industrial sources with second-scale
completion times and identical timing instrumentation. Verify UNSAT
correctness with LRAT/DRAT proofs where possible.

For the present research branch, no watchdog, no parallel worker races,
no disruptive restarts, and no claim of a world record or P=NP progress.
