# DRNAS RIT4 — link CaDiCaL EQUIV2 to GF(2)/SCC/XOR4 by original SHA

2026-11-09. One diagnostic, no new CDCL work and no edits to frozen baseline.

## Why

EQUIV1/EQUIV2 use 24 X20 original source SHA, while prior RIT3 tested
24 different X22 SHA: **zero SHA overlap**. Hence previous structural
results must NOT be joined with performance by year, GBD similarity, or
short name. To evaluate structural signals correctly, scan the exact X20
original SHA and join to completed audited EQUIV2.

## Frozen provenance

- Source CNFs and `mre_x20/manifest.json` from run 42607281345,
  artifact `equiv2-frozen-source-and-tested-SCC`. These are repeated X20
  sources, not blind holdout.
- Trial JSON and accepted PAR2 reference from independent successful
  recovery audit run 42608986438 artifact
  `DRNAS-EQUIV2-384-AUDITED-RECOVERED`.
- 24 original SHA, each 2 repetitions x 8 already-completed solver arms.
- Recheck source SHA before/after diagnostics. Validate all 384 trial
  SHA/seed-rep/arm tuples and independently recompute each arm's published
  total PAR2, accepted solved and witnesses. No solver launched.

## Structural-only metrics and bounds

Reuse the RIT3 proof-safe extraction, without altering it:
exact complete 8-clause XOR4 half-cubes; XOR2/3, binary implications,
SCC, shared variables, rank gain, algebraic joint-only rows and bounded
original-CNF RUP checks. Per case at most 8.4s (hard 11s), 4096 total
rows, 12000 pair combinations, 16 RUP candidates. Incomplete is
explicitly INCOMPLETE, never a real zero.

Report per-SHA paired PAR2 for EQUIV2 CaDiCaL 1.7.3, CaDiCaL 3.0.1
default/no-decompose/SCC4, native and Kissat. Differences are descriptive,
not a causal attribution to SCC alone; --no-decompose changes a whole
preprocessing phase. Select best and worst differences for inspection,
without training a selector or leaking cases into prospective holdout.

No new E2E/SAT/UNSAT measurements; UNSAT acceptance is only historical
two-backend source agreement and is NOT LRAT-certified. Original SHA and
all frozen solver data are unchanged. Output: compact CSV, JSON, summary.
