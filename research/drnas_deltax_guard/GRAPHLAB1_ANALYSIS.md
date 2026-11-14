# DELTAX GRAPH-LAB1 — 3-coloring semantic diagnosis, 2026-11-14

**Verified run**: https://github.com/Frane12/AndroidGameTest/actions/runs/43598771169
**Branch**: experiment/drnas-deltax-graphlab1-20261114
**Exact artifact**: deltax-graphlab1-final

## Protocol

20 original, generated 3-coloring CNFs, each solved in four serial modes of
the SAME frozen native DELTAX-GUARD1 solver from run 43596056826:
JOIN, DELTAX-SHADOW, DELTAX unrestricted, DELTAX-GUARD.
Four shards, one logical CPU per solver, 4-second cap.
All 80 attempts independently verified: 11 SAT models per arm satisfy
the original CNF, 9 UNSAT certificates per arm pass original-source DRAT.
20 distinct source SHA; no result-based selection. No main promotion.

Classes:
- planted, colorable random graph: six sources (+ one core-only control)
- K4-containing graph, provably not 3-colorable: four (+ one core-only)
- odd wheel: four 4-chromatic UNSAT sources
- even wheel: four 3-colorable SAT sources

The two core-only controls have NO extra guarded-equivalence motifs.
For the other cases, two or three verified-original-source motifs are
logically linked to ordinary graph variables representing vertex color
selection. The solver is NOT told graph family, coloring certificate or
the expected SAT/UNSAT label.

## Global outcome (GUARD versus JOIN, only 20 mutually verified cases)

| Metric | Result |
|---|---:|
| Sources / solver attempts | 20 / 80 |
| Verified SAT / UNSAT in every arm | 11 / 9 |
| GUARD candidate checks | 27 |
| Source-certified conditional clauses accepted | 21 |
| Candidates vetoed | 6 |
| Actual CDCL enqueues using new GUARD clauses | 26 |
| Fewer native CDCL decisions AND conflicts vs JOIN | 9 / 20 |
| More native decisions or conflicts vs JOIN | 0 / 20 |
| Unchanged native counts | 11 / 20 |
| False logical steps or contradictory certificates | 0 observed |

Acceptance is not synonymous with improvement. E.g. oddwheel_unsat_r7
accepted one guarded equality and used it twice as an actual propagation
reason but had exactly the same native decision/conflict totals as JOIN.

## Three reproducible solved examples, with exact source-role mapping

All vertex indices and color indices are ZERO-BASED below. The source
manifest records full graph edge lists and the random variable permutation.

### A. 20-vertex colorable random graph (42 edges)

Source: planted_v20_s1
JOIN: **9 decisions, 3 conflicts** -> GUARD: **6 decisions, 1 conflict**.
GUARD accepted **4** source-proved clauses, generated **4 genuine CDCL
reason enqueues** at decision levels 2 and 3.

A first nonlinear guarded motif has y = x5 equal (by two original
binary implication clauses) to the graph's color-selection Boolean
for vertex 5, color index 1 (core DIMACS x32, vertex degree 4).
Under active guard x3=0:
  x2 = x5, recorded source-RUP clause (-x2 OR x3 OR x5).
Under active guard x4=0:
  x1 = x5, recorded source-RUP clause (-x1 OR x4 OR x5).
A second motif connects gadget y = x10 to graph vertex 8, color index
2 (core DIMACS x42, vertex degree 4). The guard clauses also propagate
gadget variables x7, x6 along this second link.

Recorded actual CDCL reason-enqueues, not just proposed clauses:
  -x2 because of [-2,5,3]; -x1 because of [-1,5,4];
  -x7 because of [-7,10,8]; -x6 because of [-6,10,9].
This shows WHY graph structure receives the information: auxiliary
conditional equalities get attached to vertex-color indicator bits.

### B. 22-vertex graph containing K4 (52 edges, UNSAT)

Source: k4_unsat_v22_s1
JOIN: **13 decisions, 9 conflicts** -> GUARD: **10 decisions, 7 conflicts**.
Three clauses accepted, three actual CDCL reason-enqueues.
The first guarded motif is attached to vertex 16, color index 1
(degree 7); the second to vertex 8, color index 2 (degree 7).

A K4 has four mutually adjacent vertices; a 3-coloring is impossible.
The solver's UNSAT conclusion was **independently DRAT-certified on the
original CNF**. We do NOT infer unsatisfiability solely from DELTAX.

### C. 13-vertex even wheel (12-cycle plus hub, 24 edges, SAT)

Source: evenwheel_sat_r12
JOIN: **5 decisions, 3 conflicts** -> GUARD: **4 decisions, 2 conflicts**.
Two clauses accepted, two original-CDCL reason-enqueues.
A linked motif connects to rim vertex 6, color index 2 (degree 3).
A 12-cycle can alternate colors 1 and 2, while the hub takes color 0.
This is an explicit valid graph 3-coloring; the complete CNF SAT
assignment was also verified against the ORIGINAL formula.

### Negative controls

core_only_planted_v23: JOIN=GUARD 9 decisions, 0 conflicts.
core_only_k4_v27: JOIN=GUARD 11 decisions, 7 conflicts.
No guarded aliases accepted, no DELTAX causal reason enqueues.
These controls have different graph topologies from A/B/C. They rule out
false matching without gadgets, but do not yet isolate the gadget effect
on an IDENTICAL graph with and without motifs.

## Scientific interpretation and limitation

The accepted clauses produce conditional equalities attached to
vertex-color Booleans. Source-parent resolution plus an original reverse
binary implication make them logically sound; ordinary BCP can ultimately
reach the same closure. DELTAX can shorten implication paths and sometimes
change CDCL's conflict/decision trajectory.

Benefits occurred with linked vertex degrees 3, 4, 7 and 11. Thus high
degree ALONE is not an established predictive condition. Both colorable
and explicitly 4-chromatic graphs exhibited gains.

This experiment remains **synthetic**, includes a motif family developed
on prior data, has only one attempt per source, and does not establish
novel mathematics, general SAT performance or reliable speedup.
Our next controlled step should create *matched same-graph* ablations:
identical edges with/without active guarded motifs, and varied linkage
locations (low/high degree), then compare genuinely new source-seed
groups. Independent proof validation and frozen main remain mandatory.
