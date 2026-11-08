# DRNAS MRE6i — final audited 80-trial findings, 2026-11-08

Successful GitHub Actions run: https://github.com/Frane12/AndroidGameTest/actions/runs/42509063941
Branch: experiment/drnas-mre6i-prefilter-new2026-20261108
Protocol: research/DRNAS_MRE6I_NEW2026_FROZEN_PROTOCOL.md
Audited: 4/4 paired shards, 80/80 source×seed×mode full-SAT/UNSAT attempts,
35s full wall cap, PAR2 timeout penalty exactly 70 seconds, one identical
pinned native CMS 5.11.15 backend and matching original SHA/native seed.

## All eight-source PAR2 — real solve, not bounded-CDCL telemetry

| Mode | Solved / 16 | PAR2 seconds | End-to-end × vs pure CMS | Preprocessing wall total s |
|---|---:|---:|---:|---:|
| CMS + verified source XOR | 12/16 | **332.860886** | 1.00851× | 0.483429 |
| MRE6h fast signed GF2, no extra XOR | 12/16 | 332.983650 | 1.00814× | 0.725956 |
| MRE6i sampled XOR gate → GF2, no extra XOR | 12/16 | 333.328952 | 1.00709× | 0.699717 |
| MRE6i sampled XOR gate → GF2 + source XOR | 12/16 | 334.216650 | 1.00442× | 0.697955 |
| CMS Native pure original CNF | 12/16 | 335.692460 | 1.00000× | 0.410818 |

No difference in number solved: each mode has 4/16 timeouts.
MRE6i gate/no-XOR is 0.1404% SLOWER than CMS+XOR by total PAR2,
despite a small improvement versus pure CMS. The relative differences
are small on this cohort, so DO NOT interpret as statistically proven
performance ranking.

## Critical cohort split (NEVER merge without labels)

| Mode | Four genuinely NEW official SAT2026 CNFs / 8 attempts PAR2 | 2 reused known anchors / 4 attempts PAR2 | 2 new synthetic XOR controls / 4 attempts PAR2 |
|---|---:|---:|---:|
| CMS Native | 314.960392 | 20.696164 | **0.035904** |
| CMS source XOR | **314.481384** | 18.320524 | 0.058978 |
| MRE6h no XOR | 314.725276 | **18.122243** | 0.136131 |
| MRE6i gate no XOR | 314.975754 | 18.219532 | 0.133666 |
| MRE6i gate with XOR | 315.217054 | 18.866907 | 0.132689 |

NEW official SAT2026: 4/8 solved per mode. Both fresh SAT inputs
solved in both repetitions. Both fresh UNSAT inputs timed out at 35s
for every mode (4 timeouts PER MODE on those two UNSAT originals, or
20 timeout attempts across all five modes). Published external CaDiCaL3 reference
times for UNSAT originals were 113.24s and 642.71s, so the 35s cap is
an explicitly difficult comparison; these timeout cases remain fully
counted in every PAR2 sum, never excluded.

**Zero GF2 equivalence eliminations on all FOUR new official sources.**
Thus MRE6i's 0.015362s PAR2 regression against clean CMS on this
new official cohort does not measure an active mathematical reduction.

## Certifiable mathematical mechanism

The known reused SAT anchor (official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf)
again produced 4 CERTIFIED signed equivalence eliminations on BOTH
seeds, with SAT models independently checked against the source CNF.
Two-run E2E totals:
MRE6i gate no-XOR 10.179411s; CMS native 12.779433s;
CMS+source XOR 10.389691s; MRE6h no-XOR 10.185966s.
This is a reused development calibration source, not blind evidence.

Two new synthetic SAT XOR/CNF controls each produced five independently
verified variable eliminations in BOTH repetitions: 20 total
successful synthetic merges per active mode. But synthetic problems
are so easy that CMS native solved four trials in 0.035904s whereas
MRE6i no-XOR took 0.133666s; the mathematical verification dominates
and is NOT economical on these easy instances.

Across all eight sources, MRE6i activated on exactly the same three
sources (one reused + two synthetic) as MRE6h; no missed activation was
observed here. However its sampled structural gate only examines up
to 6,000 original clauses and CAN MISS a valid XOR block after that
prefix; this is an explicitly acknowledged, safe false-negative gate,
not a mathematically exact absence detector.

## CPU budget / end-to-end findings

On the four fresh official instances, summed preprocessing wall:
MRE6h fast no-XOR 0.211703s; MRE6i gate/no-XOR 0.190426s
(~10% less), but no measured end-to-end PAR2 gain.
On the known active anchor, two-run gate/no-XOR PAR2 10.179411s vs
MRE6h no-XOR 10.185966s: only ~6.6ms, within unreplicated runtime
noise. Gate remains a selective research tool, NOT a production win.

## Proof / scientific boundaries

- Every SHA and native seed paired, all 80 attempts audited.
- SAT witnesses reconstructed for eliminated variables and checked
  against ORIGINAL input; UNSAT statuses crosschecked with verified
  official status; NO independent LRAT UNSAT proofs were produced.
- Two reused anchors and two synthetic controls must not be merged into
  claims of new real-world improvements.
- Historical source registry is incomplete; "new official" means not
  present in tracked excluded cohorts, not exhaustively global unseen.
- No statistically robust/general acceleration established over
  CMS+XOR. Do not promote MRE6i into production.

Next research direction: move precommitted source-disjoint testing to
actual SAT2025/2026 XOR-rich MEDIUM original formulas that can be solved
within cap, using structural labels to ensure both activation-positive
and negative controls WITHOUT inspecting DRNAS runtime. Also investigate
reusing source-XOR extraction proofs to avoid two independent scans,
and selective gating only when expected variable elimination benefit
can repay verification cost.
