# DRNAS ATLAS41 — exact candidate utility: final audited findings

Date: 2026-11-11. Benchmark run [43038778961](https://github.com/Frane12/AndroidGameTest/actions/runs/43038778961) completed **six successful shards and a successful independent audit**.

## Provenance and controls
26 original SHA, 2 seeds, 5 solver arms, 260 matched trials; 1 logical CPU per solver; regression cap 10s; extension/hard cap 12s. All SAT witness claims verified on the original CNF. Reported UNSAT *not independently LRAT certified*. Benchmark cohorts had been inspected in prior experiments; NOT globally blind.

## Aggregate
| Policy | reported PAR2_s | strict verified PAR2_s | verified SAT/52 | UNSAT unverified/52 | unknown/52 |
|---|---:|---:|---:|---:|---:|
| Kissat | 41.361315 | 450.382377 | 32 | 20 | 0 |
| A36_75 | **247.754529** | **487.074030** | 32 | 12 | 8 |
| A39_PROTECT | 261.738352 | 501.807319 | 32 | 12 | 8 |
| A41_DECAY | 272.653183 | 511.735484 | 31 | 12 | 9 |
| A41_GUARD | 287.955142 | 527.139599 | 31 | 12 | 9 |

A41_DECAY exact changed deletion selections: 24,173. A41_GUARD: 59,816. Both actively changed the native deletion ranking while keeping 75% fixed.
A41 selected candidates using literal fingerprints (FNV64), CID, LBD, clause length, age, since-last-used, reason-use count, before/after score; emitted samples bounded to first 12 per solved run.

## By cohort: reported PAR2_s
| cohort | A36_75 | A39 | DECAY | GUARD | Kissat |
|---|---:|---:|---:|---:|---:|
| regression | 72.293040 | 67.227461 | 68.838937 | 72.370216 | 11.930441 |
| extension | 68.893695 | 86.929986 | 99.127847 | 104.308470 | 10.609943 |
| hard | 106.567794 | 107.580905 | **104.686399** | 111.276456 | 18.820931 |

A41_DECAY shows a small +1.8814-s PAR2 advantage over A36 on the harder 10-source cohort, but loses **30.2342s** on extension and one verified SAT.
A41_GUARD loses a verified SAT on extension and regresses elsewhere.

## Exact inspected regressions
- uf250-1065 index 11, rep=1, original SHA `aa0c7b9083f68d47...`: A36 verified SAT at **3.48149s**, A39 at 2.904909s, A41_GUARD at 11.651901s, A41_DECAY **UNKNOWN at 12s** (reported PAR2=24s).
- uf250-1065 index 10, rep=0, original SHA `86fcdd447ce72530...`: A36 verified SAT 2.567397s, A39 8.388251s, A41_DECAY verified SAT 6.624958s, A41_GUARD UNKNOWN at 12s (reported PAR2=24s).

Note: the current Python benchmark drops stderr/stdout on external timeout. Thus missing clause telemetry on those UNKNOWN runs means **unavailable**, not zero interventions; the native counters on solved cases are reliable. Fix timeout partial-output preservation before drawing case-level intervention conclusions.

## A concrete successful microcase, not a general success
- uf250-1065 hard index 13, rep=1, SHA `c0d936e2d2f2d12f...`: A36 3.051938s, A39 4.300320s, A41_GUARD 2.511628s and A41_DECAY **0.892919s**, all verified SAT. This local 3.42x ratio to A36 is an exploratory effect only.
- Candidate sample in that run (DECAY): local cid 3257, fingerprint 10396294381012298088, clause length 11, LBD 10, age 807 conflicts, since last use 696 conflicts, hits 8, score changed 1011->661. This is one protected candidate sample, **not proof this one clause caused speedup**.

## Scientific conclusion
The exact candidate records confirm that low-LBD / age / recent minimization-reason use heuristics move the deletion ranking, but **neither fixed score policy provides a general improvement** on these tested source families. Do not merge into stable or claim a breakthrough. Keeping A36_75 is empirically justified.
Possible reason: uses in minimization are only a partial proxy for a clause's actual future BCP implication and conflict contribution. We have NOT demonstrated a causal per-clause usefulness mechanism. A promising next direction is to track **actual BCP reason events**, test a bounded target clause counterfactual at a matched reduction state, and avoid using inspected SHA for final confirmation.
