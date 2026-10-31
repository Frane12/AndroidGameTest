# DRNAS SAT V7.5.1 — official SAT Competition 2026 CNFs, 60-second local PAR-2

## Exact setup

- **DRNAS version:** V7.5.1 from `research/drnas-sat-v7-5/v75_single.cpp` and
  the matched control workflow on the existing `research/drnas-sat-neuroflow-v7-5-controls` branch.
- **CaDiCaL:** *unmodified official* `rel-3.0.1`, compiled in CI from source.
  This is NOT system libcadical 1.7.4 used in the earlier DRNAS NP v1.0
  official mini-benchmark; **do not compare the two runs' wall times as a
  controlled version speedup**.
- **Exact official input cases:** the twenty READY CNFs from previous
  run [41204322891](https://github.com/Frane12/AndroidGameTest/actions/runs/41204322891),
  selected out of 24 predeclared original SAT Competition 2026 Main Track
  GBD hash IDs. Four previously oversized CNFs remain excluded. The
  *previous* source manifest is downloaded from the actual CI artifact;
  every original GBD ID's decompressed DIMACS SHA256 is validated again.
  **No resampling or replacement**.
- **Local runtime cutoff:** **60s** per attempt, five times the previous
  12-second pilot. Local PAR-2 charges **120s** for each unsolved or
  failed attempt. The official competition 5000s time limit and competition
  hardware are NOT reproduced.
- **8 unmodified methods:** `plain`, `majority`, `split_plain256`,
  `split_plain1024`, `guided256`, `guided1024`, `random256`,
  `random1024`; all share one binary and identical CaDiCaL 3.0.1.
- **2 shuffled repeats** for each method and input. Total: 20 × 8 × 2
  = **320 timed trials**, executed in 10 parallel shards (two original CNFs
  each), with independent per-instance timeouts. Order shuffled before
  running and cannot be adjusted based on result.
- **One 60-second limit PER method** including CNF reading and solver
  initialization, not per whole eight-method block. The original native
  C++ method verifies returned SAT witnesses against all clauses. Cross-mode
  conflicting SAT and UNSAT results abort the run. Formal standalone
  UNSAT proof checking is not included.
- Full raw per-method data retained. All timeout and error cases are
  PAR-2 penalized; no optimized-method outlier is selectively excluded.
- Casewise PAR-2 uses the **median over two repeats for each instance**,
  then sums all case costs. Independent bootstrapping over instances
  gives exploratory uncertainty intervals.

This is an independently run **local benchmark of official source
instances**, NOT the official SAT Competition ranking, winner or proof
of generally superior SAT performance. In particular, results from the
previous CaDiCaL 1.x-anchored benchmark are not directly comparable
to this version's CaDiCaL 3.0.1 baseline.

**GitHub Actions:** https://github.com/Frane12/AndroidGameTest/actions/runs/41206285619

**Authoritative official GBD index:** https://github.com/satcompetition/2026/blob/main/downloads/track_main_2026.uri

## Control interpretation

- `majority`: signs added to CaDiCaL before solve without probe.
- `split_plain256` and `split_plain1024`: stop and restart after
  256 or 1024 conflicts without phase hints; separate the intrinsic
  overhead of restarting from the effect of NeuroFlow's guidance.
- `guided256` and `guided1024`: NeuroFlow's variable/sign hints for
  a 256/1024-conflict probing phase, then remove forced polarity and
  resume the SAME CaDiCaL solver retaining learned clauses.
- `random256` and `random1024`: same variable eligibility as guided,
  with random signs as negative controls.

Only declare success if a treatment improves *same-backend* PAR-2 and
solved-case coverage, ideally with a confidence interval excluding
no-effect. Particular instances with large gains are interesting
diagnostics, not a general SAT breakthrough.
