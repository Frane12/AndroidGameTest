# R28 + DRNAS native learning — experimental historical replay

Base: `f03a0c4c7081aaa96151f0f514137cd994d6758a` (LTM13 HARD600).
The stable baseline is frozen LTM8 FAST; this experiment does not promote LTM13 or replace main.

## Composition

One native process first tries exact source-CNF GF(2) elimination. Its R28 core is extended by R153 complete parity-block detection and original unit clauses. An unsuccessful prepass returns to the original CNF and the DRNAS native CDCL engine. No CMS, Kissat or CaDiCaL runs inside the candidate.

The prepass has a cooperative budget of min(50ms, 10% of total cap); a process-wide hard wall deadline also bounds every stage, including parsing. The existing source limits remain: 12 MiB, 3000 variables, 150000 clauses. Larger or mixed unresolved inputs go to native search.

Native FAST uses LTM8 online policy learning. DIRECT separately tests LTM13 64-conflict UCB windows and low-reward fallback. Both retain the LTM9 independently checkable PHP certificate and LTM7 gate that disables unproductive live XOR checks after 1024 checks. A new conservative deletion setting limits the quota to 50 instead of the baseline 75, preserving existing locked and low-LBD protections. This quota and the combination are hypotheses, not previously demonstrated improvements. CLI `--keep75`, `--no-selective`, `--gf2-ms 0`, and `--profile fixed0` support follow-up ablations.

Learning memory is empty for each benchmark process. Online adaptation may occur within each formula, but this replay makes no claim of learning across formulas or blind generalization. Reward based on LBD/work is a surrogate, not measured speedup. FAST may not reach enough conflicts to learn on easy algebraic cases.

Vendored sources are unchanged:
- R28: `experiments/drnas_v16/r28_exact_gf2.cpp` at `6aaba92e9df33d44fac65c46b61364a83e163354`.
- R153: `research/r153_exact_units_gf2.cpp` at `b14abe967589f0dc9941fa76d553c320480101a5`.

Build transformations operate on independent copies, asserting every edit anchor and checking frozen binary hashes remain unchanged. `pins.json` records produced source and binary SHA256.

## Paired experiment

All arms run sequentially on the same single logical CPU. No parallel portfolio. References: frozen Kissat 4.0.4, CaDiCaL 3.0.1, recorded CryptoMiniSat package and binary hash, plus unchanged R28+CMS. Pure R28/R153 arms abstain when algebra cannot solve and are specialist controls, not general-purpose competitors.

Two repetitions with deterministic shuffled arm order and seeds 17/29 for configurable solvers. Historical R28+CMS uses its original default backend seed. Each subprocess receives the same external wall deadline, including launch and parsing. Independent verification is outside solving time, separately recorded as `verify_s`.

Stages are reported separately:
- Original frozen 25-CNF R153/R160 cohort plus SHA-deduplicated R115 historical source: 3s screening.
- Eight generated XOR, PHP and planted 3-SAT controls: 3s.
- Exact historical R32q/R115 source SHA `243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83`: 60s.
- Up to two Lights-Out sources selected by metadata and SHA before measuring: 20s.

This is a retrospective extreme-case replay, not an unseen benchmark or evidence for a globally best solver. R190/R194 parallel architectures are not merged into this single-core native executable. Their relevant exact-algebra-before-backend principle is represented by the R28+CMS reference.

## Verification and scoring

Every accepted SAT assignment satisfies every original clause. Every accepted GF(2) UNSAT certificate is checked against complete original parity encodings and original units, then reduced independently to 0=1. PHP certificates check original positive rows and original binary exclusions. Generic UNSAT without a certificate remains `UNSAT_UNVERIFIED` for every arm. No expected answer or generator label can certify a solve.

Reported PAR2 accepts a solver's SAT/UNSAT claim; verified PAR2 accepts only independently checked answers. Unsolved or unverified costs twice the cap. Publish both: a verified score difference due to missing proofs must not be described as a search-speed improvement. Timeout speed ratios are lower bounds, never exact factors. Counts are attempts and distinct sources separately. Stages with differing caps are never combined into one leaderboard.

Invalid models/proofs, incompatible SAT/UNSAT claims, crashes and missing frozen sources fail the run. Summary checkpoints and JSONL are saved after every source. Large generic search proofs are not enabled. One serial shard is identified as shard 0.

No promotion from this replay alone. A future disjoint general holdout must demonstrate at least 30% lower PAR2 (candidate/reference <=0.70) against the strongest reference, with verification coverage and solved-count regressions assessed separately.
