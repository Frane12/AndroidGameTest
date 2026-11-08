# DRNAS MRE4 P3 — MRE-Q1 Certified Search-Space Reduction
2026-11-08 — experimental source branch `experiment/drnas-mre4-p3-certified-quotient-20261108`

## Central principle from research
**Do not merely accelerate the exploration of the same Boolean search space.**
Instead seek a certificate allowing the solver to eliminate an independent
coordinate. Keep the earlier exact R28 GF(2) safe exit.

## Empirical research inherited, not silently promoted
- R28/MRE4 P1: full-CNF checked fast SAT exits; preserve source and cost guard.
- MRE4 P2: 20 replay-certified active CRR clauses caused 68 genuine native
  watched binary propagations, but active ran 0.116 seconds slower than
  same-preparation shadow. So more propagations != less work.
- MRE5: full native solver CPU and binary watcher accounting, measured
  instrumentation cost; trace OFF for P3 timing.
- MRE6b: proof-certified equality quotient without imported source XORs
  reduced native CPU on **one reused** SAT2026 formula over four seeds.
  Quotient WITH XOR showed a negative interaction there. This is a hypothesis,
  **not** an unseen-source validation. No MRE6 policy automatically deployed.
- CRR1B3: duplicate/non-cross relevant clauses often fail to improve PAR2;
  avoid expensive filtering when there is no certified equivalence.

## Actual algorithm
For positive equivalence a=b proven by two original clauses
`(-a OR b)` and `(a OR -b)`, OR by independently replayed MRE1 clause
proofs, construct a quotient with b replaced by a in CNF. For GF(2)
constraints, replace b by a and cancel repeated parity terms. Store source
proof origin. Preserve original variable coordinate for SAT witness lifting.

No logical direction is guessed. No "similar variables" heuristic may
authorize quotient. Verification always reconstructs a full original-CNF
SAT model and rejects any mismatch. UNSAT remains without independent LRAT.

## Paired stage P3 development test
40 source SHA: 32 reused development cases (8 reused 2026 official, 16 prior
synthetic, 8 prior mixed synthetic) and **8 new synthetic equivalence controls**
generated from fixed seeds. These last cases are **not real official holdout**.

6 arms, 2 repetitions, 30 s timeout, 8 shards = **480 measurements**:
- clean CMS
- unmodified R28 safe
- source-certified XOR import
- certified quotient prep, shadow (no rewrite)
- certified quotient without importing source XORs
- certified quotient plus source XOR import (interaction test)

Same pinned CryptoMiniSat 5.11.15 binary and seed within each source pair;
OTF Gauss OFF and tracing OFF; SAT model always checked on original CNF.
All prep included in PAR2. Strict budget (max 0.40 s) and score guard
(replaced occurrences >=4 and reduced CNF clauses >=1) reject costly
or ineffective quotient attempts.

## Interpretation and promotion policy
- An active quotient with one erased variable is mathematical coordinate
  reduction, *not* automatically one fewer actual native CDCL decision:
  compare the native `decisions` and `conflicts` against shadow.
- If P3 doesn't beat its same-prep shadow across diverse real sources,
  do NOT activate it by default.
- Even with a development win, freeze all code and policy before a
  source-disjoint blind SAT2026 benchmark.
- Never claim independent UNSAT validation until a verified LRAT/FRAT
  pipeline is present. Never label new synthetic controls "official".

Links to primary evidence:
- MRE4 P2 run: https://github.com/Frane12/AndroidGameTest/actions/runs/42490307382
- MRE6b factorial audit: https://github.com/Frane12/AndroidGameTest/actions/runs/42492372821
