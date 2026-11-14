# DELTAX GRAPH-ABLATION1 — matched identical-graph controls

**Verified GitHub Actions run:** https://github.com/Frane12/AndroidGameTest/actions/runs/43600050200  
**Branch:** experiment/drnas-deltax-graph-ablation1-20261114  
**Status:** complete, one-logical-CPU, no main edits or binary promotion.

## Question and controls

Does the guarded equality help because of its position in a 3-coloring graph,
its number of connections, or merely the extra gadget's presence?

Twelve new graph cores (three each: planted 3-colorable, K4 UNSAT,
odd wheels UNSAT, even wheels SAT) generate six sources per *identical*
graph with exactly the same core edges:

1. core — graph alone (separate dimension/control reference);
2. off — three identical guarded nonlinear motifs connected to private
   dummy Boolean variables, NOT to the graph;
3. low1 / high1 — one motif linked to a low/high-degree vertex-color bit;
4. low3 / high3 — three motifs linked to low/high-degree vertex-color bits.

The FIVE motif variants have the SAME exact number of variables and
clauses, the same 3-coloring graph and the same source clause order
permutation. Between these variants, only the two binary connection
clauses for each rewired motif are changed. Full-source SAT extensions for
planted colorings and graph-theoretic UNSAT obstructions were independently
checked by the generator, with solver SAT models checked against original
CNF and UNSAT independently verified with original-CNF DRAT.

Four solver modes of the exact same frozen GUARD1 executable, two repeats,
6 * 12 * 4 * 2 = **576 solver attempts**. No SAT label or vertex degree
information is passed into the solver. The test is synthetic and the
motif/policy was developed earlier; do not call it a blind real-world test.

## Fully checked outcome

| Statistic | Result |
|---|---:|
| Distinct graphs / distinct CNFs | 12 / 72 |
| Verified SAT/UNSAT attempts | 576 / 576 |
| Per-arm verified SAT / UNSAT | 72 / 72 |
| GUARD clone checks | 75 |
| GUARD accepted source-proven clauses | 32 |
| GUARD rejected candidate probes | 43 |
| DELTAX-origin native CDCL propagations under GUARD | 49 |
| Invalid proof steps / contradictory models observed | 0 |
| Unique graphs with any verified decision/conflict improvement | 4 / 12 |
| Graphs with no improvement | 8 / 12 |
| Matched graph-variant-repeat pairs where GUARD helped conflict count | 22 / 96 |
| Matched graph-variant-repeat pairs where GUARD worsened conflict count | 0 / 96 |

The 96 pairs are 12 unique graphs * four linked variants * two repeats:
the independent graph sample is only 12, NOT 96.

### Improvements per graph-variant (two repeats each)

| Matched variant | Fewer decisions / 24 attempts | More decisions | Mean reduction in decisions / attempt |
|---|---:|---:|---:|
| off (same gadget, disconnected) | 0 | 0 | 0 |
| low1 | 6 | 0 | 0.333 |
| high1 | 6 | 0 | 0.583 |
| low3 | 2 | 0 | 0.167 |
| high3 | 6 | 0 | 1.167 |

The core-only variant also showed 0 improvements/regressions. Both OFF and
CORE controls provide evidence that the observed source-level reductions
depend on connection to the graph, rather than just the presence of
standalone guarded gadgets.

### Reproduced example pairs (rep 0; all certified)

- **Colorable planted graph of 34 vertices, high3:** three graph links
  on vertices of degree 12, 11 and 10; JOIN 23 decisions / 3 conflicts,
  GUARD 17 / 2. Two guarded RUP clauses were accepted and the actual
  live propagation reason was linked to the degree-12 vertex.
- **Even wheel rim 18, high3:** graph hub degree 18 plus two rim vertices
  degree 3; JOIN 14 decisions / 3 conflicts, GUARD 8 / 2.
  Crucially only ONE guarded clause was accepted: three links do NOT
  mean three clauses contributed.
- **Odd wheel rim 9, high1:** hub degree 9; JOIN 13 / 9,
  GUARD 11 / 8.
- **Even wheel rim 10, low3:** three rim vertices of degree 3;
  JOIN 14 / 3, GUARD 12 / 2.

The off variant of these same graph cores had identical JOIN and GUARD
decisions/conflicts, and no accepted GUARD clauses. All K4 graph groups
and the two smaller planted random graphs showed no decision improvement
on this controlled cohort.

## What can and cannot be concluded

**Supported:** some source-RUP-certified conditional equalities, when
linked to actual 3-coloring vertex/colour indicator variables, change
native CDCL propagation and *sometimes* reduce decisions/conflicts,
whereas source-identical graph cores linked only to isolated dummy bits
had no such gains in this test. Variable link placement and link count
affect the observed outcome.

**NOT supported:** high-degree connectivity alone as a universal
selection condition. LOW1 and HIGH1 each improved six *repeated
attempts*, and LOW3 sometimes lost benefits seen with LOW1. "high3"
had the largest descriptive average, but gains occurred on only four
graph cores. Also a three-link variant may receive only one accepted
source-RUP clause, so any effect can include ordinary CDCL branch-order
changes caused by the additional graph links.

This is an experimental comparative intervention, not proof of a new
mathematical theorem or general SAT speed gain. Clone acceptance uses a
wall-clock budget and can change across CI runs; it is not an infallible
search-direction oracle. One important next control would repeat this
paired cohort with more independent graph seeds and a CPU/instruction-
bounded (rather than wall-clock-based) probe policy, then try a
source-disjoint original competition holdout.

No changes were made to main or frozen reference binaries.

## Reproduction and artifacts

Use the GitHub run above, artifact **deltax-graph-ablation1-final** for
JSON report and all 576 trial rows; artifact
**deltax-graph-ablation1-frozen** for original generated CNFs and
source/manifest hashes. Four shard artifacts include proof telemetry
and the accepted source RUP/resolvent events.
