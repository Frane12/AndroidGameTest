# DRNAS SAT v7.7 — CaDiCaL and Kissat on original SAT Competition 2026 CNFs

**Experiment**: https://github.com/Frane12/AndroidGameTest/actions/runs/41208564932

## Frozen methods

**DRNAS SAT v7.7** is the existing source `research/drnas-sat-v7-7/v77_single.cpp`, unchanged relative to the successfully tested SHA256-pinned v7.7 SATLIB experiment, [run 41207669683](https://github.com/Frane12/AndroidGameTest/actions/runs/41207669683). It uses the public `CaDiCaL::Learner::learning(int size)` callback to observe clauses *offered for export* during a 256-conflict probe. These are **not** guaranteed to be all learned clauses or LBD scores. The fixed predeclared rule is to extend initial decision polarity hints for up to another 768 conflicts only if there are 32+ offered clauses, of which at least ten have size <=5 and at least 20% are size <=5; otherwise it unphases the solver and resumes without rebuilding it.

The comparison uses **exactly the same original CaDiCaL 3.0.1**, compiled from `arminbiere/cadical rel-3.0.1`, for the following methods:

- `plain`: CaDiCaL without external phase hints.
- `majority`: initial majority-phase hints without any probe.
- `v76_guided`: earlier count-based adaptive control.
- `quality_plain`: matching two-stage pause/resume and learner observer without hints.
- `quality_guided`: actual v7.7 clause-shortness-guided phase extension.
- `quality_random`: same observer and gate, but signs randomly selected on the eligible variables.

The **separate** seventh arm, `kissat404`, is unmodified `arminbiere/kissat rel-4.0.4`, compiled independently. It is a meaningful strong reference solver but its compiler flags, search strategy, preprocessing and library are not identical to CaDiCaL; this is *not* a controlled isolation of DRNAS's overhead.

## Frozen official input set

Uses the **same twenty successfully downloaded original SAT Competition 2026 Main Track CNFs** from earlier research run [41204322891](https://github.com/Frane12/AndroidGameTest/actions/runs/41204322891). That run selected twenty-four official GBD IDs **before** measurements, with four skipped as oversized. The archived official source manifest and exact original SHA256 hashes are downloaded again from its artifact, and the inputs are re-downloaded directly from the official GBD by hash. Both original names and content hashes must match: no newly substituted CNF files, no performance-based selection.

**These 20 inputs have been examined previously by older DRNAS versions. They are a fixed-source replication for the new v7.7 release, not a pristine holdout for the wider project.** V7.7 was developed and tested on the separate SATLIB source, not by training on these official inputs in this run.

## Local evaluation (NOT an official competition submission)

- Ubuntu 24.04 GitHub Actions x86_64 runner, 10 parallel shards, two official CNFs per shard.
- **60 seconds per process attempt**, two randomly ordered repetitions per method and file.
- **20 CNFs × 2 repeats × 7 methods = 280 attempted solves**.
- **Local PAR-2**: for a completed SAT/UNSAT run, elapsed process wall time; a TIMEOUT/ERROR incurs 2 × 60 = 120 seconds. Score reported as sum of per-CNF medians, two repeats each, together with solved and errors counts.
- SAT models from DRNAS's CaDiCaL backend are checked against original clauses; Kissat's printed SAT witness is re-evaluated against original DIMACS clauses. SAT statuses are compared across completed methods and disagreement aborts the test.
- **UNSAT proofs are not independently checked**: this does not meet the official main-track proof criterion.
- The official competition evaluated up to **400 original instances with a 5000-second limit** on competition hardware. The present size-limited 20-instance 60s reproduction must NEVER be called an official competition ranking.
- Bootstrap confidence intervals resample **CNF instances**, not the duplicated timing measurements independently.
- Differences between this experiment and the earlier DRNAS NP 1.0 pilot are **not comparable** directly because that pilot used system `libcadical` 1.x and only two strategies with a different runtime limit.

## Interpretation decision

The main comparison is frozen v7.7 `quality_guided` against same-backend `plain`, `quality_plain` and `quality_random`. Report all completions, errors, and local PAR-2, without highlighting only individual strong wins. The Kissat 4.0.4 comparison provides an additional competitive target. If the bootstrap intervals include zero or there are fewer solved CNFs than plain, describe the result as inconclusive or unfavorable; do not claim a general SAT breakthrough.
