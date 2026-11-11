# DRNAS ATLAS40 — three independent native CDCL clause decision trees

Date: 2026-11-11. All 3 experiment branches use the frozen ATLAS39 native
reference, a fixed deletion quota of 75%, and a separate C++ tree mode=3
while leaving the A39_PROTECT mode=2 untouched.

## Source + status
- Conservative: [paired 208 trial run](https://github.com/Frane12/AndroidGameTest/actions/runs/43036590461); [successful independent immutable audit](https://github.com/Frane12/AndroidGameTest/actions/runs/43037579999).
- Balanced: [paired 208 trial run](https://github.com/Frane12/AndroidGameTest/actions/runs/43036599741); [successful independent immutable audit](https://github.com/Frane12/AndroidGameTest/actions/runs/43037495783).
- Pressure: [paired 208 trial run](https://github.com/Frane12/AndroidGameTest/actions/runs/43036613150); [successful independent immutable audit](https://github.com/Frane12/AndroidGameTest/actions/runs/43037592766).

All six benchmark shards of **each branch succeeded**. The original
audit step in each run failed due to a stale assertion that the
*distinct* new tree mode was 2 rather than 3. Recovery audits reused
the stored results without rerunning solvers, verified 26 distinct
canonical SATLIB SHA, 208 trials each, paired seeds, original SAT
witnesses, and marked UNSAT **unverified by independent LRAT**.

## Aggregate reported PAR2 seconds (lower is better)
Each branch includes its own A36_75, A39_PROTECT, and pinned Kissat
controls, matched within that branch. Do NOT compare raw wall times
across independent GitHub runners without considering host contention.

| Policy | A36_75 | A39_PROTECT | New tree | Kissat | Verified SAT (new) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Conservative | 251.907375 | 261.388324 | 266.258542 | 40.174405 | 32/52 |
| Balanced | 243.726630 | 269.572785 | 265.924587 | 42.053588 | 31/52 |
| Pressure | 250.328456 | 263.436540 | 253.226316 | 39.499244 | 32/52 |

Strict verified PAR2 (SAT independently checked; all uncertified
UNSAT penalized) for new policies: conservative 505.696097;
balanced 512.728033; pressure 501.655684 seconds.
Matched A36 controls: 490.695560, 489.159080, 486.839387,
respectively. All three new trees **regress** on strict verified PAR2.

Changed deletion-candidate selections in the new policy:
conservative 136705; balanced 195092; pressure 226917.
Thus new tree is really active, not a dispatch-only placebo.

## Within-branch reported PAR2 by source cohort

| Branch | Cohort | A36_75 | New tree | New minus A36 |
| --- | --- | ---: | ---: | ---: |
| Conservative | regression | 77.87239 | 81.01960 | +3.14721 |
| Conservative | extension | 64.65461 | 80.74826 | +16.09365 |
| Conservative | hard | 109.38038 | 104.49068 | -4.88970 |
| Balanced | regression | 63.81752 | 59.61730 | -4.20022 |
| Balanced | extension | 69.89539 | 95.53104 | +25.63565 |
| Balanced | hard | 110.01373 | 110.77623 | +0.76250 |
| Pressure | regression | 75.17708 | 73.97959 | -1.19749 |
| Pressure | extension | 68.64683 | 79.63049 | +10.98366 |
| Pressure | hard | 106.50455 | 99.61624 | -6.88831 |

## Interpretation
- **No new policy beats fixed A36_75 on aggregate or on strict
  verified PAR2**. None should be promoted to the stable DRNAS solver.
- Conservative and pressure can help some harder cases, but that
  benefit is outweighed by consistent **extension regressions**.
- Pressure gets an additional *reported*, **uncertified** UNSAT result
  (13 vs 12) and one fewer timeout, while still regressing on strictly
  verified PAR2.
- Balanced on one hard shard cut conflicts from 140955 to 65047, a
  real local algorithmic signal; it did not survive aggregation across
  the full 26 SHA.
- The fixed A36 baseline logged 914980 conflicts in all three runs,
  while actual E2E varied considerably between runs. This is an
  indicator of scheduler or host effects; do not over-interpret tiny
  timing gains.
- Further conditional trees should not be tuned on these *already
  examined* SHA and then advertised as prospective blind results.

## Next experiment
Prefer targeted clause-level counterfactual replay:
1. Keep A36_75 as reference and pre-register two or three small
   proposed new utility features, rather than changing all thresholds.
2. Log each changed candidate's age, LBD, reason-use count, score,
   and clause hash at deletion (bounded sample; no proof log bloat).
3. Freeze the policy and evaluate on source-disjoint original
   SAT/UNSAT CNF with 3+ seeds and one logical CPU.
4. Only promote if verified solved and verified PAR2 improve without
   cost/memory regressions.
