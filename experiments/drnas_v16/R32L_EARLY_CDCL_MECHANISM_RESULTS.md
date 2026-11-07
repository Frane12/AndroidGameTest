# R32l — early CDCL telemetry isolates XOR-root-unit mechanism

**Completed audited run:** https://github.com/Frane12/AndroidGameTest/actions/runs/41647823014  
**Full data (1,920 serial executions):** https://github.com/Frane12/AndroidGameTest/actions/runs/41647823014/artifacts/13234214381  
**Date:** 2026-11-03. All six GitHub Actions jobs succeeded; `R32L_AUDIT_PASS`.

## Protocol and policy safety

Exactly one pinned native Kissat process per trial. No inter-solver communication,
parallel portfolio, watchdog process or restart-policy intervention.
Native root-unit ablations are subsets of the same original-CNF-certified
GF(2) consequences: first4, first8, last4, all available (up to 12).
Original unmodified Kissat and native OFF are the controls.
We added *read-only* native early-CDCL trace points: solver entry before
preprocessing; search entry; first conflict before/after analysis; decisions
1/4/16/64; conflicts 1/4/16/64; final statistics. Every early trace
final counter was checked against the original native final log.

62 SHA-distinct original CNFs: 2 **previously examined** R32e causal
diagnostics, and 60 newly seeded **synthetic** generator sources
(42 base +18 coupled stress). Ten repetitions of known diagnostics,
five of unseen synthetic formulas, six matched policies = 1,920 attempts.
No timeout, all solver verdicts agree with source labels. SAT witness
validated against original CNF, UNSAT by generator known label only, no
LRAT certificate. 8s cap; data does not establish generic competition
performance, P=NP, or a world record.

## Main results: new 60 synthetic formulas only

| Single-solver policy | Sum wall time for 300 attempts | Change vs native OFF |
|---|---:|---:|
| Clean original Kissat | 5.632722 s | -0.24% vs native OFF |
| Native OFF | 5.646419 s | baseline |
| First4 certified units | 5.572936 s | -1.3014% |
| First8 certified units | 5.417331 s | -4.0572% |
| **All certified units** | **4.951287 s** | **-12.3110%** |
| Last4 certified units | 5.642616 s | -0.0674% |

Case-resampled 95% bootstrap interval for all-units vs native OFF on the
60 fresh *synthetic source medians* was **[-22.304%, -4.268%]**. These
intervals characterize this specific synthetic generator distribution,
not independent real-world formulas or repeated runner hardware.

Only **19 of 60** sources improved on *summed five-run wall time*;
**41 of 60** were slower. The six largest time-saving sources contributed
**91.7% of net time saved** across the entire new synthetic cohort.
Therefore the aggregate 12.31% is strongly concentrated rather than an
across-the-board performance gain. Do not call it universal acceleration.

The conflict totals of the 300 matched native trials only changed
**88,440 → 88,090** (-0.4%); native decision totals changed
**126,340 → 124,910** (-1.1%). This disparity indicates timing
benefits are NOT mainly explained by fewer CDCL conflicts in aggregate.

## Key mechanistic observation: the intervention changes work BEFORE CDCL

Of the **60 new source CNFs**, native OFF entered CDCL search for
**21**, whereas full GF2 root units entered it for **19**.
The full-unit intervention made the CDCL phase completely unnecessary
for **two** new coupled-stress sources:

- `r32l_stress_consistent_hidden_332.cnf`
- `r32l_stress_consistent_hidden_333.cnf`

Equivalently, 105/300 native OFF trials entered search versus 95/300
all-unit trials (five repetitions each); 195 versus 205 solved without
entering CDCL. No source became more reliant on search under full
intervention in this sample.

Crucially, for several of the *largest speedups*, **neither OFF nor full
ever entered search**. For instance, five-run case medians:

| New synthetic formula | OFF median | GF2-full median | OFF entered search? | Full entered search? |
|---|---:|---:|---|---|
| `r32l_stress_consistent_visible_331.cnf` | 35.885 ms | **4.777 ms** | no | no |
| `r32l_stress_consistent_mixed_333.cnf` | 28.385 ms | **4.431 ms** | no | no |
| `r32l_fresh_consistent_hidden_303.cnf` | 26.836 ms | **3.770 ms** | no | no |

Thus, the primary hypothesis is that the additional certified units
alter the **early SAT shortcut or Kissat's preprocessing work**, rather
than improving the CDCL decision policy itself. This inference is strong
about *where* to investigate, but the specific phase (early lucky,
preprocess, late lucky) is **not yet isolated**. Do not attribute those
times specifically to preprocessing without the next phase-resolved trace.

## The two known R32e inversion cases

On previously seen `r32e_stress_consistent_visible_51.cnf`:

- native OFF: 21 conflicts, 85 decisions, 3,990 propagations, search entered;
- full original-certified GF2: 56 conflicts, 129 decisions,
  5,125 propagations, search entered;
- the first conflict occurs after **14 decisions** in BOTH modes,
  with **146** literals on the internal trail in BOTH modes.
  The after-analysis trail differs by one literal (43 vs 44), and
  subsequent learning/search paths diverge. It is a *late trajectory
  effect*, not an earlier first-conflict event.

On previously seen `r32e_stress_consistent_mixed_53.cnf`:

- native OFF: 27 conflicts, 90 decisions, 3,827 propagations,
  first conflict after **9 decisions**, entering CDCL;
- full: **0 conflicts, 0 decisions**, never enters CDCL;
- first4 and first8: also no CDCL; last4: **46 conflicts,
  115 decisions**, entering CDCL.

Hence certified XOR clause selection can cause two distinct mechanisms:
(i) end the solve during earlier preprocessing/lucky phases, or
(ii) leave first conflict essentially identical but change the later
learning trajectory. A single coarse feature selector cannot assume
these mechanisms are the same.

## Next falsifiable intervention — still SINGLE SOLVER ONLY

Instrument Kissat's native `kissat_search` calls separately:
`luckyearly`, `preprocess`, `luckylate`, and entry into CDCL.
Capture phase-local CPU/wall timestamps and deltas in propagations,
assigned trail length, and final status. Add an optional **read-only**
original-CNF implication-graph proxy and test whether it predicts
which early phase wins. Apply to **new hard external SAT/Crypto CNFs** and
compare fair same-host controls. Keep code changes minimal and derive
all solver correctness claims from independently checked original CNF
witnesses/proofs. No watchdogs, parallel SAT solvers or process portfolios.
