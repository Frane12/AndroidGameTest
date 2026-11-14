# DRNAS FUSION1B — paired PAR2 proof-first benchmark, 2026-11-14

**GitHub Action:** https://github.com/Frane12/AndroidGameTest/actions/runs/43606753178  
**Branch:** experiment/drnas-fusion1b-par2-20261114  
**Artifact:** fusion1b-par2-verified-final  
**Outcome:** entire workflow completed successfully; do NOT promote a faster
solver claim to main.

## Frozen protocol

40 original SHA-distinct sources (16 original SAT Competition 2024, 12
hard synthetic 3SAT/XOR/PHP and 12 graph 3-coloring), SHA-disjoint from
the earlier 24-source FUSION1B build test. Retrospective cohorts:
not an untouched random real-world holdout. Exactly 2 repeats per source
and 5 serial modes = **400 attempts**.

One pinned logical CPU per solver. Time cap 6 seconds end-to-end per
solver process. **PAR2 = verified solver E2E wall-time** when the original
SAT model or original-CNF independent UNSAT DRAT is valid and wall<=6s,
otherwise 2*6=12 seconds. The *cost of independent proof verification* is
kept separate; solver startup and parsing ARE included.

Five frozen comparison arms:
- CORE_B: same FUSION1B compiled binary with modules completely OFF;
- SHADOW_B: same compiled binary with pre-gate observing only;
- FUSION1A: older cold-module gated policy;
- FUSION1B: selective graph/XOR structural pre-gate, cold modules;
- SIGNAL8_FULL: earlier source-blind proof-gated algebra without cold pre-gate.

## Original-source verified results

| Arm | Verified / 80 | Timeout/unknown / 80 | Aggregate wall PAR2 (s) | Module wakeups | DELTAX proof clauses |
|---|---:|---:|---:|---:|---:|
| CORE_B | 58 | 22 | **270.995418** | 0 | 0 |
| SHADOW_B | 58 | 22 | **270.954070** | 0 | 0 |
| FUSION1A | 58 | 22 | **271.095189** | 208 | 2 |
| FUSION1B | 58 | 22 | **271.084849** | 64 | 2 |
| SIGNAL8_FULL | 58 | 22 | **271.170424** | N/A | 2 |

Every arm: SAT 28 verified, UNSAT 30 independent-DRAT certified,
UNKNOWN 22. No incorrect SAT/UNSAT was credited.

**FUSION1B vs CORE_B:** PAR2 **0.089431 s higher** (0.033% worse)
across the 80 attempts. CORE/FUSION1B PAR2 ratio **0.999670**.
**FUSION1B vs FUSION1A:** 0.010340 s smaller PAR2 (only 0.0038%
better); practically equal at this precision. **FUSION1B vs SIGNAL8_FULL:**
0.085575 s smaller PAR2 (0.0316% better). There is NO verified
meaningful overall speed advantage.

The 22 common timeouts contribute **264 seconds** to each arm, about
97.4% of total PAR2. Synthetic graph and hard cases were all solved;
the 22 timeouts came entirely from the SAT2024 real cohort (10/32
original-real trials solved in each arm). Consequently the aggregate
PAR2 is poorly sensitive to millisecond improvements on easy CNFs.

## Activation benefit without proved wall-time benefit

FUSION1B reduced expensive module wakeups from **208 to 64** compared
with FUSION1A, a **69.2% reduction**, while retaining the same 2 source-
proved DELTAX clauses and the same number of solved instances.
FUSION1B also halved matched clone checks from 4 to 2.

By category, FUSION1B vs CORE_B PAR2:
- Original 2024: 270.620677 vs 270.561852 s (FUSION1B slower);
- Synthetic graphs: 0.179809 vs 0.146710 s (slower);
- Hard synthetic: 0.284363 vs 0.286855 s (slightly faster).

No DELTAX clauses were injected for the original SAT2024 subset;
FUSION1B nevertheless authorized six module windows there.
All 2 native DELTAX clauses that were injected came from synthetic
graph cases.

## Statistical and design caveats

Two repeats and timing differences of milliseconds on CI runners do not
support a reliable statistical ranking. The report includes a
source-cluster bootstrap across the 40 independent source SHA groups,
but this bootstrap **does not capture run-to-run CPU scheduler or
machine noise** and should not be treated as a meaningful universal
speedup or slowdown test.

This experiment showed correctness, safe module gating, strict
baseline parity when modules are OFF, and fewer activations. It did
**not** demonstrate statistically significant or practical wall-PAR2
improvement over standard native CDCL.

## Suggested next action

Maintain CORE as the benchmark reference. For FUSION2 require:
1. O(1) or cheap structural gate that vetoes unnecessary GRAPH/XOR
   starts on real formula families, and a strict measured per-formula
   module budget as a fraction of current solve time;
2. Before tuning, distinguish low-cost source structural features from
   actually useful proof-carrying clauses; do not ask cloned CDCL to
   do work unless cheap benefit predictors pass;
3. Newly sealed source-family holdout, >=3 repeats, matched CPU, and
   independent proof checks. Require improved solved counts/PAR2
   and no family-level regressions to consider promotion.

main and every frozen reference binary remain unchanged.
