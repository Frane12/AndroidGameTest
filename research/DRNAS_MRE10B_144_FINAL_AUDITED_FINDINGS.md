# DRNAS MRE10b — final SHA-frozen 144/144 external source validation

Date: 2026-11-08
Branch: experiment/drnas-mre10b-new2023-2025-20261108
Run (all jobs **success**): https://github.com/Frane12/AndroidGameTest/actions/runs/42511332725
Protocol: research/DRNAS_MRE10B_144_NEW_SOURCES_PROTOCOL.md

## Experimental integrity

Exactly **12** new-to-tracked-history official 2023–25 Main Track original
SHA-locked formulas; **4 each** from 2023, 2024, 2025.
Preselected BEFORE DRNAS benchmark by GBD official minisat1m=yes
and independent CaDiCaL 0.07–10s status/time; source size and deterministic
SHA order. Nine official SAT and three UNSAT. All 12 original byte SHAs
verified; unmodified pinned MRE10 native C++ + CMS binary reused from
successful prior run 42509505558; independent Python-vs-C++ exact original
CNF transformation parity 12/12 for clean/rename/joint.

Four arms × 3 frozen SHA-derived seed reps × 12 sources = **144 actual
end-to-end attempts**, 15s full cap each, PAR2 timeout=30s.
Native SAT models checked against the unmodified exact original CNF;
UNSAT agreement with independent CaDiCaL reference, **NO independent LRAT**.
All 6 source-paired shard jobs and independent 144-attempt audit GREEN.

Selection is NOT an exhaustive global fresh blind holdout. It is a
precommitted, tracked-prior-disjoint, external-solver-difficulty-conditioned
cohort; the historical GBD registry is incomplete.

## Final all-source PAR2 results

| Mode | Solved | SAT | UNSAT | Timeouts | PAR2 total seconds | × vs original CMS |
|---|---:|---:|---:|---:|---:|---:|
| N_ext original CMS | 26/36 | 23 | 3 | 10 | **415.178377** | **1.000000×** |
| cpp_native unchanged C++ wrapper | 26/36 | 23 | 3 | 10 | 415.657497 | 0.998847× |
| cpp_clean duplicate/tautology removal only | 26/36 | 23 | 3 | 10 | 426.287736 | 0.973939× |
| cpp_joint certified equivalence + cleanup | 24/36 | 21 | 3 | 12 | 470.811893 | 0.881835× |

C++ Joint increased PAR2 by **55.633516 seconds** (+13.40% more PAR2
seconds versus original CMS), and finished TWO FEWER paired SAT attempts.
No new solved timeouts; both are paired regressions. Clean-only has one
paired new solve and one paired regression (net same 26/36), while its
total PAR2 is **11.109359 seconds worse**.

Original previous MRE10 development cohort: C++ Joint 168.473602s vs
original CMS 211.756782s (1.256914×); that overall advantage does
**NOT** transfer to this external independently preselected cohort.

## Individual source regression explanations

Most important 2024 original:
`be6411f4784a3c879886dda807cdc607` (SAT)
across 3 paired seed reps:

| Mode | solved | PAR2 |
|---|---:|---:|
| Native CMS | 2/3 | 40.805667 |
| C++ native wrapper | 2/3 | 40.825? (from per-trial rounding) |
| C++ clean only | **3/3** | **21.931896** |
| C++ joint | **1/3** | **67.059342** |

On the one solved C++ Joint seed, its original-CNF certification
eliminated **229 variables** and removed **731 clauses**. It timed
out in the other two seeds. The clean-only mode removed **118 clauses**
and solved all three. The relative difference in solve robustness,
not just a few milliseconds of preprocessing, is a genuine recorded
regression under this protocol. However actual gate telemetry is
missing on timed-out child processes, so the exact mechanism of each
timeout is not independently established.

Another 2023 SAT original:
`909f704d5f4127c1197a086705468624`
Native CMS 1/3, PAR2=68.774214; Clean and Joint 0/3,
PAR2=90 each. For the CMS-solved seed 1, native was 8.774214 s
and Clean/Joint timed out at 15s. The run did NOT record an applied
certified reduction on this source; do NOT attribute this regression
to algebraic equivalence rewriting without stronger traces/repeats.

2025 original `0e1d562093d5f4fc9013cf4a14a03f70`:
all modes 3/3 SAT solved. Clean removes **4,356 clauses** in each
repetition yet PAR2 worsens from 14.991909 to 22.710125 s;
Joint has no additional equivalences, essentially identical to Clean
at 22.749832 s. Thus removing more syntactically redundant clauses
is not a universally reliable speed proxy: propagation/indexing/search
order can change.

2024 original `7f7109dce621ef361a72b3e8cee9a962`
UNSAT; Clean removes 510 clauses per seed but has no meaningful
PAR2 win over CMS (2.506356 vs 2.447464).

## Decision

**Do not promote C++ Joint or Clean unconditionally.**
The prior 1.2569× advantage was development-cohort-dependent.
On independent external-source-selected 2023–25 original formulas,
C++ Joint has two observed solved→timeout regressions.

A follow-up, if desired, is to reproduce the paired regressions
at 30–60 second caps on isolated identical CPU runners with 5–10
frozen seeds; inspect branch decisions, clause visits and actual
proven equivalence activation before designing a cheap select/abstain
gate. Any selector should be trained and then evaluated on an
unseen SHA-disjoint cohort, not optimized on these 12 sources.
