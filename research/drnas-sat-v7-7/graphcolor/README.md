# DRNAS SAT v7.7 — 60 original graph coloring tests

**Live GitHub Actions:** https://github.com/Frane12/AndroidGameTest/actions/runs/41210111867

## Goal

Compare original **DRNAS SAT v7.7 `quality_guided`** to the exact
same CaDiCaL 3.0.1 C++ solver with no external hints (`plain`), a matching
callback-only control (`quality_plain`), and random-polarity controls
(`quality_random`); add unmodified Kissat 4.0.4 as a separate reference.

The comparator **ZykovColor** is a specialized exact graph-coloring
algorithm, NOT a normal CNF SAT solver. Its official build requires
**Gurobi, Boost >=1.88, Open-WBO, exactcolors and CliSAT**, according to its
upstream README and CMakeLists.txt:
https://github.com/trewes/ZykovColor

**The ordinary GitHub-hosted Ubuntu runner has no licensed Gurobi
library**. The dependency preflight saves this fact to a separate workflow
artifact. We do NOT claim to have measured ZykovColor and do NOT replace
its performance data with a surrogate algorithm. The optional
`optional_zykovcolor.py` runner is supplied for an environment with the
legitimate, unmodified ZykovColor binary and dependencies.

## Source graph collection and mathematical identity

The original SATLIB `flat200-479` archive is authenticated with
SHA256 = `a27f57132377dc6be4fd11a938c78e6ec245e65fb33fa7a86579ef986c7c242b`,
as in previously published DRNAS study metadata.

Its 100 member files encode decisions whether 200-vertex graphs, with
479 edges, are **3-colorable** (all expected SAT). We choose the first
60 members in deterministic SHA256-name order with **no timing-based
selection or replacements**. Two samples are smoke tests; the other 58
are the fixed main evaluation.

Each original SATLIB `.cnf` is converted into a `.col` graph input
ONLY when its **entire clause multiset** is provably identical to the
standard three-color CNF of the recovered graph:
- exactly one positive size-three clause for each vertex (three
  colors) and every variable appears in exactly one positive triple;
- all three mutually-exclusive negative pair clauses per vertex;
- exactly one same-color negative binary clause per graph edge/color,
  three per original edge;
- no additional or missing clauses, no duplicate/mismatched edges.

If any original CNF fails this proof, the suite halts and **never
substitutes** a different graph. This guarantees that pure SAT and
ZykovColor's fixed `k=3` solver are solving mathematically equivalent
decision problems. It does not turn exact minimum-color optimization
into the same problem.

## Runtime protocol

- GitHub Actions Ubuntu 24.04, six parallel independent main shards.
- **15 seconds** process limit per attempt, **two randomized-order
  repeats** for each method and graph.
- Four same-CaDiCaL variants `plain`, `quality_plain`,
  `quality_guided`, `quality_random` and independent `kissat404`.
- 58 main graphs × 5 methods × 2 repeats = **580 actual solve attempts**.
- **Local PAR-2**: completed run elapsed wall time; each timeout/error
  contributes 30 seconds. All instances are counted in complete
  per-graph score medians.
- SAT models are verified against the **original CNF** by the native
  DRNAS CaDiCaL wrapper and the independent Kissat witness checker.
- All Graph Coloring problems are SAT; this benchmark by itself does
  NOT assess UNSAT certification, chromatic number optimization, or
  modern difficult DIMACS instances beyond the SATLIB 3-color family.
- The `flat200-479` corpus was used by earlier DRNAS experiments, so
  this is a cross-solver **fixed-source replication**, NOT a new blind
  independent holdout or a broadly representative graph-color benchmark.
- A native ZykovColor run, if it becomes possible, must use
  `SingleK`/fixed **three colors**, not the default chromatic-number
  optimization, and must use the identical `.col` graph hashes.
  The supplied optional runner sets explicit `--encoding 5 --strategy 2 --num-colors 3`.
  This configuration should itself be validated against a known test
  graph before publication.

## Sources

- SATLIB paper: https://www.cs.ubc.ca/~hoos/Publ/sat2000-satlib.pdf
- ZykovColor: https://github.com/trewes/ZykovColor
- DRNAS v7.7 main previous run: https://github.com/Frane12/AndroidGameTest/actions/runs/41207669683

Report the actual PAR-2 measurements, error and timeout counts, and
bootstrapped casewise confidence intervals. A single unusually fast
case is not evidence of general dominance over graph coloring solvers.
