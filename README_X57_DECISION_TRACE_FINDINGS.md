# X5.7 Decision Trace — frozen SAT10 retrospective findings

**Verified GitHub run:** https://github.com/Frane12/AndroidGameTest/actions/runs/43430526013

**Outcome:** complete and successful. 10 original SAT2024 CNFs × 2 repeats
× 9 arms = 180 independently witness-checked SAT attempts. Five
five-of-five paired shards, every trace-on/off/frozen matched search has
identical decisions, conflicts, propagations and learned-clause counts.

## What we measured

The 10 instances previously solved by every baseline SAT arm consist
of **9 SIMON cryptography formulas and 1 scheduling formula**.
This is **not** a broad SAT difficulty sample; it reuses SAT outcomes
from run 43418696306, with the manifest/SHA frozen first.

| Policy | SAT solves, all traced /20 | Frozen untraced PAR2 (s) | Decisions (all SAT runs) | Conflicts | Propagations |
|---|---:|---:|---:|---:|---:|
| VSIDS | 20 | 0.250827 | 3746 | 482 | 80508 |
| CHB | 20 | 0.243355 | 3540 | 478 | 79138 |
| LRB | 20 | 0.242623 | 5452 | 508 | 81636 |

All policies correctly solve the instances. The small differences in
wall time are **not evidence of statistical superiority** because
tiny SIMON solve times are dominated by measurement jitter and one
application source determines almost all branching differences.

There are exactly 60 independent JSONL trace files (20 SAT runs for
each of VSIDS, CHB, LRB), with a total of:
- VSIDS: 3746 decision records
- CHB: 3540 decision records
- LRB: 5452 decision records

The trace-enabled variants cost extra wall time, partly due to JSONL
serialization, and MUST NOT be compared to uninstrumented speeds
without on/off controls. The paired total overhead vs same-source
trace-off is approximately:
- VSIDS: +0.008441 seconds (source-cluster CI includes zero)
- CHB: +0.041150 seconds (source-cluster interval [0.001651,0.079216])
- LRB: +0.015963 seconds (source-cluster CI includes zero)

## Only materially informative application: scheduling SAT, source_id 12

Both repeats produce the same search counters and chosen-literal
sequence for each fixed policy:

| Policy | Real decision count, rep0 | Immediate first-BCP conflicts, rep0 | Immediate conflict learned LBD (median) |
|---|---:|---:|---:|
| VSIDS | 1585 | 109 | 29 |
| CHB | 1482 | 108 | 36.5 |
| LRB | 2438 | 107 | 39 |

The first **531 chosen literals are identical** between the three
policies on scheduling SAT. At decision 532:

- VSIDS chooses literal \`+382\` (first-BCP conflict).
- CHB chooses literal \`-405\` (first BCP does not conflict).
- LRB chooses literal \`+382\` (first-BCP conflict).
- VSIDS and LRB diverge at decision 533.

CHB reaches a verified SAT solution using **103 fewer decisions**
than VSIDS (6.5% fewer) and LRB uses **853 more decisions** than VSIDS
(53.8% more). These counts support an *observed* efficiency gain for CHB
on **this one scheduling source**. The immediate conflict LBD
distributions do **not** show CHB learning uniformly lower-LBD clauses,
which makes a simplistic "lower LBD always causes fewer decisions"
narrative incorrect.

The immediate BCP conflict count is a strict subset of all conflicts:
conflicts may also arise in later propagation cycles. The LBD median
is computed only from sampled decisions whose **first** BCP directly
produced a learned clause.

## Limits, safety and implications

The step-by-step path comparison is **not a counterfactual**: the two
policies end up in different solver states after the first divergence.
A better SAT path for CHB on this formula does not prove that the
\`-405\` decision *caused* a speedup or would be better in the VSIDS
state.

These results suggest testing CHB on **new original scheduling-like
SAT sources with independent source-family holdout**, while keeping
VSIDS as the frozen default. Do not promote CHB globally because
the full REAL36 benchmark made it slightly **worse** on overall PAR2.

To build a genuine decision-selector improvement, predeclare features
and a decision-level evaluation, use the existing trace data only for
training/diagnostics, then freeze the policy and validate with
independent unexposed SAT formulas.

The main branch is untouched, and no new online learning/routing
policy was activated by this diagnostic experiment.
