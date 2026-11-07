# TD2: reduce GF2 cost while preserving source certification

TD2 replaces the quadratic pivot-pair back-substitution in the R182 Gaussian
routine with substitution through present lower pivot bits. Echelon insertion
and source traces are unchanged. Lower pivot rows are fully reduced before a
higher row uses them. Every contradiction and unit still passes the original
source-trace verifier; every added clause passes the existing R189 derivation
and replay checks. The original clauses must remain an identical prefix.

Preparation has a 0.8 s deadline. An interrupted attempt discards its partial
CNF and proof and returns the original source to the same backend. A separate
variant first gives that backend 25 ms on the original CNF; a completed answer
skips preparation. An expired pilot is killed before preparation, then the
backend restarts. All this time is charged to the same 20 s budget, including
SAT witness verification. Lost pilot search state is an experimental tradeoff.

No formula ID, family, expected answer or historical timing controls routing.
Expected status is used only after solving for correctness checks.

## Development protocol

Use the unchanged 40 SHA-pinned original sources and solver binaries from R199
run 42390697619, commit 7e8d0c2ed7312f93089907a146597d658d4bc2a2. These sources
are now exposed development data. This is **not** a fresh blind holdout and must
not be described as a global SAT competition result.

For both Kissat and CryptoMiniSat compare plain, original R193 preparation,
sparse preparation with the 0.8 s budget, and pilot plus sparse preparation.
Two repetitions, 8 deterministic stratified shards, randomized arm order:
40 × 2 × 8 = 640 attempts. Report solved counts, PAR-2, paired wins/losses,
preparation cost, pilot completions, budget abstentions and source cohorts.
Backend UNSAT answers do not have independent LRAT certificates. Source GF2
contradictions are source-trace replayed. SAT is verified on the original CNF.

## Local validation on 2026-11-07

Seven automated checks passed, including 800 seeded Gaussian comparisons
(400 with guaranteed satisfying assignments), 100 independently exhaustive
six-variable checks, byte-identical augmented CNFs for Simon and multiplier,
interruption during output creation, actual deadline expiry, original-solver
recovery and an incomplete XOR encoding. These checks run again in CI.

The local Kissat smoke test used 3 repetitions on each of the 2 already exposed
sources, 4 variants, 24 SAT results verified on the originals. It includes SAT
verification in the recorded wall time, unlike the older R199 timing boundary.
Do not directly compare these numbers to historical R199 runner times.

| Source | Plain s | Original hybrid s | Sparse budget s | Pilot + sparse s |
|---|---:|---:|---:|---:|
| cryptography-simon | 0.011163 | 0.311115 | 0.064113 | 0.011119 |
| multiplier-circuits | 1.338117 | 1.551368 | 0.938576 | 0.926886 |

These are arithmetic means, local smoke evidence only. Multiplier's pilot
variant was about 1.44× faster than plain Kissat; Simon skipped preparation.
The broader paired run is needed to measure regressions and CMS transfer.
Raw local measurements: `td2/local-kissat-smoke.json`.

Run locally from the repository root after restoring R199 inputs:

```sh
python3 -m unittest discover -s research -p test_td2_bounded_gf2.py -v
python3 research/td2_cost_gate_benchmark.py shard --shard 0
python3 research/td2_cost_gate_benchmark.py audit
```
