# DRNAS New Horizon SAT — R4b targeted benchmark-driven repairs

## What actually failed in R4

R4's full-source Python preprocessor often cost more than the native
CaDiCaL solver needed to solve the same trivial CNF:
- Larger generated Horn and 2SAT cases showed consistent slowdown.
- Source recognition plus full reread doubled parsing costs.
- Pure source-complete XOR/GF(2) remained the strongest repeatable local
  advantage, but additional R4 gate code increased overhead.
- Real SAT originals remained timeouts across all modes.

The result is a **policy performance deficit**, not evidence that the exact
Horn or 2SAT algorithms are logically incorrect.

## R4b implementation

- A **single streaming source pass** performs source-wide candidate
  disqualification or completes a full proof-gated classification. It
  stops at the first source clause proving the selected family impossible.
- Only a **full original CNF** may be classified as source-exact XOR/GF2
  or 2SAT. Partial prefixes never certify a SAT result.
- Previously measured expensive Python Horn path is temporarily disabled.
  Larger 2SAT examples are abstained at the header:
  only 80 <= clauses <= 512, variables <= 192 are considered.
  Source-pure parity is considered only when 8 <= clauses <= 64,
  variables <= 128. These bounds are **heuristics chosen using R3/R4
  development evidence**, not universal timing models or logical rules.
- A complete source-exact XOR3 parity encoding goes directly into the
  R164 GF(2) core with a checked source witness or traced XOR contradiction.
  We reuse certified rows and do not repeat parity motif detection.
- A source-wide 2CNF goes directly to SCC and an original source SAT
  witness check. There is no second DIMACS parse.
- For unknown or unprofitable source structures, the unmodified original
  CNF is passed to the same pinned native CaDiCaL binary.
- **Approximation applies only to predicted economic value**. No clause
  or constraint is removed, guessed, or probabilistically rewritten.

## Audit / limitations

The next GitHub Actions benchmark is an ablation, not a claims package:
- 194 SHA-reused R4 original sources (including previously seen external
  SAT formulas).
- 32 additional deterministic cases: 8 new pure XOR3, 8 small 2SAT,
  8 general planted SAT, and 8 deceptive 2SAT prefixes with a late
  invalidating original clause.
- Four paired arms: clean CaDiCaL, frozen R4, pure-only ablation, R4b.
- Two repetitions; 8 shards: **226 formulas and 1808 trials**.
- Same pinned CaDiCaL native binary SHA and original SHA per matched run;
  all parsing/proof costs charged in elapsed wall time.
- Audit refuses missing arms, contradictory successful SAT/UNSAT results,
  modified CNF sources or inconsistent PAR2 accounting.
- Exact SAT models checked against original CNF; independent native
  UNSAT LRAT/FRAT certificates **not supplied**.
- Data is **not an independent blind industrial holdout**: R4 was
  inspected to design policy thresholds, and new formulas use known
  generator families. Avoid general SAT speedup claims from this pilot.
- Sub-millisecond results need hardware-stable replication.

## Relevant files

- research/new_horizon_r4b.py
- research/new_horizon_r4b_benchmark.py
- .github/workflows/drnas-new-horizon-sat-r4b.yml

The SHA-frozen original R4 source and CaDiCaL binary are imported from
R4 GitHub Actions run 42325396082, preserving the previous experimental
branch and avoiding changes to the frozen R4 reference.
