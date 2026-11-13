# DRNAS X4.5 — which branch from the SAME solver state shortens verified search?
13 November 2026. Research branch: experiment/drnas-x45-matched-branch-cost-20261113

Workflow (green): https://github.com/Frane12/AndroidGameTest/actions/runs/43356515002
Artifact: drnas-x45-matched-branch-verification

## Experimental design

The native X4.1 C++ solver has a bounded, opt-in, proof-safe
--branch-at K flag and --flip-branch flag. They leave the deterministic
CDCL search unchanged up to the Kth decision. At that point, the solver
selects its usual variable but can negate the literal polarity. We run
both variants as separate processes from the same original CNF, identical
prior decisions and algorithm, with the same logical CPU.

The two checkpoint states are accepted as a matched pair ONLY if a hashed
digest is identical. The digest includes the complete trail, decision
limits, saved phases, variable activities, all original/learned clauses and
dead flags, current decision variable and prefix counters. The selected
literals must be exact opposites. This is a deterministic matched-prefix
counterfactual; it does NOT snapshot and fork one live memory image.

168 fresh SHA-distinct synthetic CNFs across seven families; attempt K =
1,2,4,8, three repetitions, normal/negative polarities. Some formulas
terminate before K; these are excluded from matched comparisons, not
called negative results. There were 1461 matched pairs and 555 pairs
where K was not reached. Every paired SAT outcome was independently
checked against ORIGINAL CNF; only tiny n=12 UNSAT cohorts were counted
and independently exhaustively checked. All 1461 pairs have both valid
answers. Original 168 CNFs, not 1461 correlated pairs, are the
independent statistical units.

Measures: verified end-to-end elapsed PAR2, native continuation conflicts,
native continuation decisions, and solver continuation elapsed seconds.
The measured costs are often only milliseconds, so process scheduling
noise limits precision of elapsed time. Deterministic conflict and
decision counts are more robust as evidence of search work.

## Overall matched-pair results

| Metric | Normal polarity | Opposite polarity |
|---|---:|---:|
| Continuation conflicts, pooled | 77,619 | 87,603 |
| Continuation decisions, pooled | 96,726 | 107,076 |
| Verified end-to-end PAR2 total | 4.048106 s | 4.118265 s |

Opposite polarity wins the comparison on **number of decisions** in 585
pairs, the usual phase in 456, and 420 tie. However, very costly
regressions outweigh the many small savings: opposite polarity consumes
12.86% MORE pooled conflicts and 10.70% MORE pooled decisions, and
1.73% MORE verified PAR2.

95% original-formula-cluster bootstrap for relative PAR2 *improvement
from flipping* approximately [-7.87%, +3.00%]. A universal time
advantage is NOT established, even though individual interventions
produce large deterministic changes in search trajectory.

| K | Matched pairs | Reverse-sign wins decisions | Normal-sign wins decisions | Reverse-sign relative verified PAR2 |
|---|---:|---:|---:|---:|
| 1 | 504 | 231 | 138 | 1.37% slower |
| 2 | 402 | 156 | 117 | 3.95% slower |
| 4 | 312 | 114 | 105 | 2.55% slower |
| 8 | 243 | 84 | 96 | 2.10% faster, exploratory |

K=8 is CONDITIONAL ON reaching the 8th decision, i.e. only 81
distinct sources. This subgroup is not randomized across the same source
distribution as K=1 and must not be promoted as a universal policy.

## Per-family results

| Family | Pairs | Opposite-sign PAR2 change vs usual |
|---|---:|---:|
| planted3 | 288 | 0.28% slower |
| planted4 | 288 | 7.20% slower |
| xor_mixed | 216 | 0.01% faster (measurement noise) |
| three_color_planted | 186 | 0.53% faster |
| community_planted | 288 | 0.52% faster |
| unsat_php | 117 | 1.25% faster |
| unsat_k4 | 78 | 0.07% faster (no meaningful signal) |

Caveat: family differences are in-sample exploratory results on the
synthetic cohort. The strongest disadvantage was hard 4-SAT; a few
costly trajectories dominated pooled conflicts.

## Two contrasting, independently verified counterfactuals

- planted4 source id 300017, at K=8: same pre-state digest
  8ec17503f57236c1; baseline decision literal -38, alternative +38.
  To complete verified SAT, baseline used 1468 conflicts/1687
  decisions; alternative 351 conflicts/398 decisions. This is a
  4.18x reduction in conflicts, measured identically on three
  repetitions. Continuation solver time about 8.8ms -> 2.0ms.
- planted4 source id 300018, at K=2: same pre-state digest
  8b9a1033a9b22e12; baseline -13, alternative +13.
  Baseline needed 923 conflicts/1088 decisions; alternative
  2630 conflicts/2948 decisions, i.e. about 2.85x MORE conflicts
  with the opposite branch. Continuation time about 4.9ms -> 17ms.

This shows WHY simplistic labels "flip is good" or "fewer decisions
is always better" fail.

## Hypothetical oracle upper bound, NOT an available algorithm

If a magical, cost-free judge chose the better of the two *completed*
continuations per matched pair, then conflicts would fall from
77,619 to 56,442 (27.28% fewer) and decisions from 96,726 to
72,144 (25.41% fewer). With wall time as the hindsight selection
criterion, PAR2 would fall 4.0481 -> 3.8988 seconds (3.69%
apparent gain; biased upward by picking the minimum of two noisy runs).

This is a NON-IMPLEMENTABLE hindsight upper bound: an online solver
cannot know which entire branch is faster without paying to inspect it.
Fully running both alternatives would cost ~2.13x the baseline
conflict work even before extra control overhead. The next experiment
must examine *short bounded probes* that can predict the winner with
far less than the cost they save, and evaluate decisions on NEW CNFs
using actual total end-to-end costs.

## What we now know, and what we do NOT

Proven in this small diagnostic: changing ONLY the Kth decision polarity
from a state with matching prefix can materially change deterministic
CDCL search work, sometimes strongly for better and sometimes strongly
for worse. This is a controlled algorithmic counterfactual, not proof
that a learned policy has found the right action.

NOT established:
- general speedup on new official or industrial SAT Competition instances;
- a cheap predictor of which polarity will be better;
- cost-beneficial active lookahead or online learning;
- any relationship to a generalized exact distance-to-SAT or P versus NP.

Main research direction: learn to predict *expensive tail-risk from
a decision*, and abstain when uncertain, using short, independently
audited continuations and family-disjoint untouched test sets.
