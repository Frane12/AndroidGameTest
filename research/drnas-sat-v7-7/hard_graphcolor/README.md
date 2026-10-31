# DRNAS SAT v7.7 — Harder DIMACS Graph Coloring, 60-second PAR-2

**Live run:** https://github.com/Frane12/AndroidGameTest/actions/runs/41211011195

## Purpose

Our previous `flat200-479` benchmark (run
[41210111867](https://github.com/Frane12/AndroidGameTest/actions/runs/41210111867))
had 58 easy, SAT-only graph colorability formulas, with a total solve
time under two seconds per solver. Though frozen DRNAS `quality_guided`
was 9.565% faster than plain CaDiCaL 3.0.1, `quality_random` was faster
than NeuroFlow guidance, and the clustered uncertainty interval
included zero. This is not proof of a better graph coloring algorithm.

The new experiment uses **harder, independent DIMACS Challenge graph
families**, crossing five different graph-structure families with a
frozen pair of color limits on every original graph.

### Source and pre-registered decisions

Source: `Kaluginaec/graph-coloring-instances` DIMACS collection
(forked from the public graph coloring benchmark archive),
**Git commit** `83b4e11b5d83bcf44feb628d1e4f7a994de0a0cf`.

All ten filename/expected Git blob SHA-1 and both `k` values are
specified in `frozen_graphs.json`, committed before any trial.
No replacement, performance-based filtering, tuning or external
status labels are used.

| Family | Original graph | Frozen k decision questions |
|---|---|---|
| Mycielski | myciel5 | 5, 6 |
| Mycielski | myciel6 | 6, 7 |
| Mycielski | myciel7 | 7, 8 |
| Leighton | le450_15a | 14, 15 |
| Leighton | le450_15c | 14, 15 |
| Planted flat | flat300_28_0 | 27, 28 |
| DSJC random | DSJC125.5 | 17, 18 |
| DSJC random | DSJC250.5 | 27, 29 |
| Queen | queen8_8 | 8, 9 |
| Queen | queen9_9 | 9, 10 |

These questions may be SAT, UNSAT, or UNKNOWN within our local
timeout. **The algorithm is never given the true result**, and known
chromatic-number assumptions are not used to assign measured outcomes.

### Graph parsing validity

The DIMACS source data uses *inconsistent historical edge-count
conventions*:

- `myciel6.col` declares 755 and has 755 edge lines / 755 unique edges.
- `DSJC125.5.col` declares **7782** but has 3891 lines and 3891
  unique edges.
- `queen8_8.col` declares **1456** and has 1456 edge lines, but only
  **728 unique undirected edges** because both orientations are given.

Our parser validates both the raw Git blob hash AND that the reported
edge count equals either edge-line count or twice the actual number of
unique undirected edges, with every vertex ID and self-loop checked.
We then deduplicate undirected edges **without losing any constraints**,
and archive raw and normalized graph SHA-256.

### Mathematically equivalent CNF conversion

For each vertex `v` and color `c` define a Boolean variable
`x[v,c]`. Exactly-one-per-vertex encoding:
- Positive at-least-one clause `x[v,1] OR ... OR x[v,k]`;
- Negative at-most-one clauses for all unordered pairs of colors;
- For each undirected edge `(u,v)` and each color `c`, add
  `¬x[u,c] OR ¬x[v,c]`.

This is the standard direct SAT encoding, with
`n*k` variables and
`n + n*k*(k-1)/2 + |E|*k` clauses. It is exactly equisatisfiable to
whether the *original graph is k-colorable*. No extra heuristics,
clause removals or solver-specific changes.

### Frozen solver comparison

**Identical binary and CaDiCaL 3.0.1** for:
`plain`, `quality_plain` (same learner observer, no phase),
`quality_guided` (DRNAS 7.7 frozen short-clause gate),
`quality_random` (random phase negative control).
Unmodified **Kissat 4.0.4** is an independent strong SAT baseline.

- 20 decisions × 5 methods × 2 counterbalanced repetitions = **200
  independent process runs**, on ten GitHub Ubuntu 24.04 runner shards.
- Each run has an **unconditional 60-second process cutoff**.
  PAR-2 assigns **120 seconds** to every timeout or error.
- Full elapsed times include starting the executable, reading DIMACS,
  memory initialization, and the solver itself.
- All completed native SAT models checked against the exact original
  CNF in C++; every Kissat SAT model checked twice: original CNF
  and original graph's proper-coloring constraints.
- Completed SAT and UNSAT statuses must agree across methods.
  If no method finishes a decision, it remains UNKNOWN.
  **UNSAT proof certificates are not independently checked.**
- Report complete data, solved and timeout counts, local PAR-2,
  family breakdown (SAT / UNSAT / unresolved), and exploratory
  bootstrap with **original graph** as clustering unit because
  two `k` choices for one graph are correlated.
- These are known public challenge graphs, so this is a new dataset
  family relative to our `flat200-479` tests, but **not a
  new unpublished blind challenge**. It is not official
  SAT Competition or DIMACS ranking.
- We are NOT benchmarking ZykovColor here: its upstream build requires
  licensed Gurobi and other dependencies absent on standard GitHub
  Actions. A separate comparator can be added only when a legitimate
  ZykovColor binary is available.

## Scientific success criterion

A genuine improvement must be visible not just versus `plain`,
but also versus matched no-guidance `quality_plain`, random-phase
`quality_random`, and preferably independent Kissat. A bootstrap
interval spanning zero, a smaller solved count, or repeated regressions
means **inconclusive**, not a demonstrated gain.

No optimization should be retuned on these 20 fixed cases and then
claimed as a holdout validation of the same cases.
