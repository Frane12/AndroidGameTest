# DRNAS ATLAS41 — Exact candidate utility: preregistered native experiment
Date: 2026-11-11. Independent experimental branch, no main changes.

## Testable hypothesis
ATLAS40's three trees all failed aggregate reported and strictly verified PAR2
against the conservative A36_75 reference. To avoid another global quota
guess, ATLAS41 changes **only candidate score**, and only for recently
reused low-LBD learned clauses that are already eligible for deletion.
Quota always remains the **same 75%**.

Native modes:
- **A36_75** frozen fixed-deletion reference
- **A39_PROTECT** frozen original A39 heuristic; mode 2
- **A41_GUARD** mode 3: LBD <= 11; learned-clause age <= 5000
  conflicts; last reason-use within 1500 conflicts; >=3
  observed minimization-reason touches; score discount 350
- **A41_DECAY** mode 4: LBD <= 17; age <= 2500 conflicts; last
  reason-use within 800 conflicts; >=4 touches; same discount
- **KISSAT** source-pinned external reference

C7's original locked, low-LBD, short-clause gates remain unchanged.
Both new modes share the original A39 learning telemetry, including
clause-slot compaction migration and cause-independent checks.
Important: reason-use touch = a *valid minimization reason*; it
does not track all BCP implication events or exact future usefulness.

## Exact-candidate audit
When a candidate actually receives score protection, native code records
the clause slot ID and FNV64 fingerprint of the literal list, length,
LBD, conflict age, recent-touch age, touch count and before/after score.
Output is bounded to the first 12 candidates per run to prevent
large logs. Aggregates count all protected candidates and the exact
symmetric difference in selected deletion candidate identities,
not just their score change.

The fingerprint is useful as a local identifying trace, but is
NOT a cryptographic guarantee of unique clauses, proof of identical
subsequent clauses, or a true counterfactual replay. To establish that
a clause was actually relearned, store learned-clause hashes over time
and compare against prior deletion hashes.

## Benchmark
26 original canonical SATLIB SHA across regression, extension and hard,
2 seeds each, 5 arms, 260 total one-logical-CPU paired trials;
10s cap regression and 12s extension/hard.
SAT requires original-CNF witness verification; reported UNSAT without
independent LRAT remains unverified. Report per-cohort and overall PAR2
(reported and strict verified), E2E, conflicts, watch visits, metadata
bytes, exact candidate selection changes, timeout and regression count.

These SHA have been used for development; no global-blind claim.
No option can be promoted to stable based only on these data.
Strong candidates must be frozen then tested on prospectively selected
SHA-disjoint sources with independent LRAT on UNSAT when practical.

## Links
Branch: https://github.com/Frane12/AndroidGameTest/tree/experiment/drnas-atlas41-exact-utility-20261111
Workflow: .github/workflows/drnas-atlas41-exact-utility.yml
