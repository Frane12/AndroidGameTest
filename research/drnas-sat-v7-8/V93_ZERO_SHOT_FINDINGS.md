# DRNAS SAT v9.3 — zero-shot transfer to six previously unused mathematical constraint encodings

Original 540 solver runs: https://github.com/Frane12/AndroidGameTest/actions/runs/41230824168
Successful aggregate of the SAME saved data (no retesting): https://github.com/Frane12/AndroidGameTest/actions/runs/41230964020

## Why this experiment
Does the previously frozen O(input literal occurrences) DRNAS v9.2 early polarity selector transfer, without retraining or family flags, beyond the earlier random-3SAT/random-4SAT/color3/xor3/pigeonhole/planted3 generators?

## Methods and unseen encodings
Thirty new CNFs: 5 sizes each for N queens, planted graph clique, Latin square completion, arithmetic subset sum (with a planted selected-weight witness), exact set cover (with a hidden partition), and circuit equivalence miter (known UNSAT by construction).
Six frozen modes: plain CaDiCaL, original DRNAS v7.6 guided, original DRNAS v7.6 no hints, full-compatible checkpoint probe, sparse polarity hints, and frozen v9.2 structural gate. No threshold was retrained after seeing these classes. Five GitHub Ubuntu 24.04 shards, 3 repeated runs, 3s timeout, PAR2=6s for a timeout. 30 unique CNF hashes, all 540 attempts included.
All six modes linked the same instrumented CaDiCaL 3.0.1 checkout. Source-frozen v7.6 and v7.7 verified by Git object hashes. The original artifact workflow's individual shard summary checks failed because they assumed the CSV's two matched rows were ordered, not because any solver failed; all attempts completed and uploaded. The corrected audit makes the reference row explicit. The final audit PASSED and found no contradictory SAT/UNSAT statuses.

## Complete PAR2 sums of per-case medians (lower is better)
- DRNAS v7.6 without hints (orig_v76_plain): 0.26143 s
- DRNAS v7.6 guided (orig_v76): 0.27546 s
- v9.2 strong sparse hints (v92_sparse): 0.27807 s
- v9.2 structural selector (v92_structural): 0.29144 s
- v9.2 guided compatibility control (v92_full_compat): 0.26745 s
- plain CaDiCaL (ca_plain): 0.32057 s

## CRITICAL validity limitation
These new NP/CSP classes were far too EASY at the sampled sizes. Almost every formula solved in 2 to 30 milliseconds, where process and parsing noise can dominate. The predeclared meaningful-comparison filter (both baselines solve all 3 repeats and each baseline median >=50ms) retained ONLY ONE of the 30 formulas: subset_sum-18.
On that single case: plain CaDiCaL 0.1096s, frozen guided v7.6 0.0706s, frozen no-hints v7.6 0.0693s, frozen structural v9.2 0.0696s. Plain/v9.2 structural 1.58x but structurally this is a very small sample and cannot demonstrate generalization.
Therefore the aggregate ordering is DESCRIPTIVE ONLY, not a reliable generalization result, world record, or SAT Competition comparison. Stronger claims from these <50ms microbenchmarks are unsupported.

## Key observation and next experiment design
- The no-hint frozen v7.6 control had the lowest aggregate, but the v9.2 structural selector did not beat it.
- Claimed new family diversity alone does not suffice: need harder instances and external SAT corpora with representative SAT/UNSAT balance.
- Select benchmark difficulty exclusively by a frozen plain baseline or independent metadata *before* comparing candidate performances, avoid cherry-picking from per-mode timings.
- Require >=50-100ms meaningful hard baseline per instance when feasible, all retries, tail latency and timeouts, independent proof checking of UNSAT, fixed hardware.
- To validate transferred structure: test both classes absent from model development and genuinely external problem distributions rather than only new synthetic formulas, with a predeclared measurable-sample minimum.

Methodological nuance: distinct random/hash permutations of the same mathematical instance are not necessarily independent. A new encoder/generator is closer to out-of-distribution than new seeds, but not a replacement for real independent industrial and SAT Competition cases.

Do not claim P=NP, a world record, or a universal solver advantage from this data.
