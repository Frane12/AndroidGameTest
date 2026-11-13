# DRNAS X5.2 — controlled original-CNF learned-clause retention ablation

Research-only experiment; no edits to main, no APK changes and no automatic model promotion.

## Frozen solver controls

- `CORE`: pinned DRNAS X4.1 native frozen-proof binary from X5 run 43368689724.
- `X5_NO_MIN`: pinned X5 binary with `--x5-no-minimize`.
- `X5`: same pinned X5 binary with default X5 clause minimization and reduction.
- `Kissat`, `CaDiCaL`: pinned independent references from the same earlier run.
- All original control binaries are byte-checked by their pinned reference SHA-256 manifest.

The candidate `src/drnas_x52.cpp` is a copy of X5 with a **new, isolated**
`--x52-policy` switch. Policy 0 delegates unmodified to the original X5 reduction routine.
The nonzero policies retain the standard SAT inference rules and enforce the
original locked-reason and short-clause safeguards.

## Pre-registered retention policies

| Candidate | Prioritization | Deletion cadence | Deletion quota |
| --- | --- | --- | --- |
| X52_LBD | Protect LBD<=2, age<700 conflicts | Every 1,400 conflicts | Worst 1/3 of eligible |
| X52_RECENT | Protect LBD<=3, age<2,500 and LBD<=6 if age<12,000 | Every 2,000 conflicts | Worst 1/5 of eligible |
| X52_PRESSURE | Protect LBD<=2, age<1,000; skip below dynamic live-clause threshold | Every 1,000 conflicts | Worst 1/3 when above threshold |

The pressure threshold is `clamp(original_clause_count / 4, 1500, 12000)`.
Eligible learned clauses are ranked by worse LBD, lower activity, longer size,
then deterministic clause index. Original clauses, binary/short clauses and
currently locked reasons are never discarded. Clause garbage collection remaps
live references. Memory/CPU accounting and proof checks are inside evaluation.

## Dataset and anti-leakage constraints

SAT Competition 2024 main-track **original bytes**, not new synthetics.
The independent preparation job uses deterministic family round robin,
compressed-entry bounds, decompressed DIMACS sanity bounds, SHA-256 dedup
and records the archive paths. It never reads solver outcomes, SAT labels,
training files, or earlier runtime measurements. A family can contribute more
than one distinct SHA. This is a retrospective, not a globally blind sample.
No model training or adaptive threshold tuning is permitted during this run.

Primary campaign: up to 100 original SHA-distinct CNFs, 2 paired repetitions,
8 fixed solvers, 5-second cap, 10 shards, one logical CPU per solver. Optional
30-second diagnostic uses the same frozen policy and sources; it must not be
presented as a fresh independent holdout. The source SHA and run manifest
are uploaded as artifacts.

The archived benchmark row includes solver binary identity and original SHA,
status, witness/proof verification, end-to-end time, PAR2, conflicts, decisions,
memory and reduction telemetry.

## Correctness and decision rule

- SAT: verify the returned assignment on the original formula.
- UNSAT: accept only after an independent DRAT proof check within the cap.
  An unverified UNSAT or timeout receives PAR2=2*cap, never solved credit.
- Incorrect SAT or invalid completed UNSAT must fail closed.
- A candidate qualifies only for a **new independent replication** if, on the
  fixed original-source set, it improves verified PAR2 by >=10% compared
  against **each** native CORE, X5 and X5_NO_MIN control, with a positive
  source-cluster bootstrap 95% lower bound, no verified-solved regression
  and zero correctness failures. Repeated trials are not independent sources.
- No candidate is promoted from this experiment into production.

Caveats: CPU host variance across shards, reference unsat checking overhead,
single-source-family heterogeneity, and retrospective SAT2024 selection mean
that further original-family held-out replications are mandatory before making
an industrial speed or generalizable learning claim.

Code: `research/drnas_x52_prepare.py`, `research/drnas_x52_bench.py`,
`research/drnas_x52_report.py`, `tests/test_x52.py`, workflow
`.github/workflows/drnas-x52-original100.yml`.
