# X21: prospective competition-style mini benchmark

Frozen before new timings, 2026-11-09. This is a shortlist of five distinct
candidate families, not a statistically established global top five. Repeated
CMS/Kissat races in X12/X14/X15/X16 are represented once by the pinned X16 race.
The latest Select2 is included as a challenger despite losing to Kissat.

| Candidate | Historical paired evidence | Caveat |
|---|---|---|
| X15 gate | 15/32, PAR2 732.979569 vs Kissat 952.481683; 1.29947x | 8 development + 8 then-new sources; holdout-only advantage 6.1661% |
| X16 race2 (X14/X15 parallel family) | 15/32, 458.480893 vs 590.681286; 1.28834x | 2 CPUs, historical replay |
| X16A balanced50 | ratio-80 job: 14/32, 491.227702 vs 586.275392; 1.193x | best historical repetition; winner-selection risk; rerun prospectively |
| front100 (X11/X13 family) | X11 41/64, 779.099289 vs 890.343644; 1.14279x | development replay, benefits concentrated in a few sources |
| X18 Select2, confirmed through X19/X19B | X19B 9/16, 195.001785 vs Kissat 160.443474; 0.82278x | latest challenger, NOT a proven improvement; 2 CPUs |

SQL source: analytics branch commit 6d15409, database SHA256
`e0d0df933c17dde44237647cb40cf843b41afe7b27943fa3d4b60782f2420173`.
Queried research_final_runs_20261109 and research_final_scores_20261109;
18 final benchmarks and 136 aggregate scores. X19/X19B read directly from
successful Actions (42581795977 / 42582976460). X20 failed before measurement.
No historical PAR2 values are pooled across cohorts or caps.

## New protocol

- 24 original CNFs from official main_2021..main_2025 indexes, quotas 4/4/4/6/6.
- Deterministic salted order, no solver/timing selection, no minisat-easy filter.
- Fixed tractability stratum: <=20 MiB decompressed, <=100000 variables,
  <=500000 clauses; up to 160 candidate fetches per year. Fetch/geometry rejects
  logged; fail closed if quota cannot be filled. Not representative of unlimited
  size competition inputs.
- Exclude every 32/64 hex identifier found in the frozen SQL text cells,
  branch research/experiments, and restored X6/X18/X19/X19B manifests. This is
  registry-disjoint, not an exhaustive claim about all historical GitHub branches.
- Five candidates + CMS native, Kissat, CaDiCaL references + X21 delayed portfolio.
- 24 x 9 x 2 = 432 E2E attempts, eight shards, 54 attempts per shard, cap 30 s.
- One fixed policy for the entire holdout; no tuning from partial results.
- Same source and seed within each pair, shuffled arm order, maximum two logical
  CPUs; solos and timeshare use one. All children pinned before exec.
- Report actual elapsed, parent/child CPU, wall PAR2 and allocated-CPU PAR2;
  one-vCPU and two-vCPU methods must be identified when comparing results.
- Startup, transformations, feature selection, witness replay and cleanup are
  included in E2E; timeout or unconfirmed UNSAT costs 60 s wall PAR2.
- SAT witness replay on original; UNSAT requires agreement from at least two
  independent baseline backends. This is NOT an LRAT-validated competition.
- No bounded-CDCL diagnostics contribute to scores. No large proof artifacts.
- Original binaries and code/source hashes frozen; no stable-main changes.

## Experiment: X21 delayed portfolio

Kissat starts immediately; native CMS starts on a second CPU after 250 ms only
if no answer is available. Kissat state is retained. Hypothesis: preserve race
coverage while reducing CPU/process cost on easy Kissat solves. The delay is
preregistered, not claimed optimal. The unchanged immediate race is the paired
ablation; actual CPU cost is essential to judging the result.

Validation before launch: Python compilation, workflow YAML parsing, all nine
arms on known SAT and UNSAT originals, and delayed second-process launch/cleanup.
