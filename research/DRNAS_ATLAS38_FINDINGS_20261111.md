# DRNAS ATLAS38 — Paired single-reduction causal study: findings

2026-11-11. Source: [successful immutable audit-only recovery run](https://github.com/Frane12/AndroidGameTest/actions/runs/43030773839), auditing completed benchmark data from [run 43030019163](https://github.com/Frane12/AndroidGameTest/actions/runs/43030019163). The latter displayed workflow **failure** only because the initial audit could not locate the uploaded JSON in its artifact path; **both benchmark shards finished successfully**, and the independent audit-only recovery on the same artifacts succeeded. Do not describe the original workflow as fully green.

## Audit integrity
- 3 original SATLIB SHA, disjoint; 60 benchmark trials.
- 24 paired 75% vs 100% **one-reduction** interventions over 4 targets and 2 seeds.
- 15 matched, observed pre-deletion state fingerprints.
- 9 targets not reached before solving or no usable intervention marker.
- Among 15 matched interventions, 7 favor 75% on reported PAR2, 7 favor 100%, 1 approximately neutral (within 0.01 seconds).
- Sum of matched reported PAR2 changes (100 minus 75): **+48.203222 s**.
- SAT original witnesses checked; UNSAT has no independent LRAT certificate.
- Deterministic replay of the original CNF, same seed and fixed-75 prefix; not a bitwise in-memory fork. Fingerprint includes conflicts, decisions, propagations, watch visits, live clause count, trail and deletion count. It does not prove identity of all internal variable activities.
- Each intervention changes the *quota to delete* in a single reduction, not 100% of all learned clauses.

## Source-level results

### UF250-1065 source index 10 (SHA 86fcdd447ce72530...)
- 3 matched interventions, 5 targets not reached.
- Seed 1, reduction 5: 75% solves SAT; 100% times out at cap=12s.
- Seed 1, reduction 15: 75% solves SAT; 100% times out at cap=12s.
- Seed 2, reduction 5: virtually equal; further targets not reached.
- Both divergent timeout cases matched their measured pre-reduction fingerprints.
- Sum of matched reported PAR2 delta: **+42.9399 s**.

### UF250-1065 source index 11 (SHA aa0c7b9083f68d47...)
- 6 matched interventions, 2 targets not reached.
- 5/6 favor 75%, 1/6 favors 100%.
- Seed 1, target 5: 100% times out while 75% verifies SAT.
- Seed 2, target 5: 100% adds **52,113 conflicts**, +5.307s.
- Seed 1, target 15: 100% adds **30,752 conflicts**, +3.224s.
- Seed 1, target 30: 100% adds **23,695 conflicts**, +2.483s.
- Seed 2, target 30: 100% adds **43,178 conflicts**, +4.457s.
- Seed 2, target 15: 100% *reduces* 12,177 conflicts, ~0.994s faster.
- Sum of matched reported PAR2 delta: **+33.517s**.

### UUF250-1065 source index 11 (SHA 7962095bba05ff82...)
- 6 matched interventions, 2 targets not reached (reduction 45).
- 4/6 reported PAR2 results favor 100%, 2/6 favor 75%.
- Reduction 5 (both seeds): 100% reduces conflicts by 2,958 / 3,769.
- Target 15 seed 1 increases conflicts by 52; target 15 seed 2 decreases by 2,875.
- Target 30 seed 1 decreases conflicts by 758 yet may be slightly slower in wall time.
- Sum of matched reported PAR2 delta: **-0.8144s**.
- Both solver verdicts are UNSAT **unverified by independent LRAT**, so do not interpret as certified UNSAT victories.

## Interpretation

These data support a narrowly causal conclusion: deliberately increasing
the deletion quota at a selected reduction, after an identically observed
deterministic prefix, can change the subsequent CDCL search trajectory
enough to cause a verified SAT solution to become a timeout. This is
different from merely correlating high BCP pressure with late solving.

However, the experiment **does not show** that specific deleted clauses
were subsequently relearned. That mechanism requires canonical learned
clause fingerprints and per-clause reason-use telemetry or an in-memory
fork. It also does not establish a reliable SAT-vs-UNSAT router: early
watch-visits/propagation ratios overlap heavily across sources, so a
high-BCP gate cannot distinguish this effect.

## Recommended next experiment

Keep A36_75 as the conservative reference. Add a conditional 100% arm
that requires measured clause reason-use *and* evidence that prior
deletion actually reduced subsequent cost; use frozen thresholds and
validate on prospective SHA-disjoint original SAT/UNSAT data. Instrument
consecutive reductions, reason activity and independent proof checking.

Avoid retrofitting a rule based on these three already inspected SHA and
then claiming it generalizes on them.
