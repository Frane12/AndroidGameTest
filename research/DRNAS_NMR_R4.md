# DRNAS New Horizon NMR R4 — calibrated, bounded exploration

## What changed from R3

R3 proved that low-overhead abstention can remove most controller overhead (66/80 solved, PAR2 283.573 s versus 283.561 s clean). But it did not observe beneficial neural activation and consequently learned to abstain on **all 80** benchmark repetitions. The next requirement is controlled exploration that allows the system to discover useful actions without paying for a second solver on every formula.

R4 introduces three profiles built from the *same pinned CaDiCaL source*:
- **Default:** incumbent warm CDCL state, started first.
- **SAT expert:** separate CaDiCaL instance lazily configured for SAT.
- **UNSAT expert:** separate CaDiCaL instance lazily configured for UNSAT.

These are competing search configurations, not different logical theories. All use identical original CNFs. Every complete result is independently compared to known labels where available; SAT models are always checked against the unmodified source.

## Intelligent rest versus permitted exploration

- **REST:** start only the default CDCL solver. No neural scan/extra instances for trivial small inputs or when trained evidence is absent.
- **OBSERVE:** when one of the bounded actions is allocated, probe the default solver in two 256/512-conflict windows, preserving learned clauses.
- **WAKE:** the C++ clause-learner callback measures only O(1) telemetry and may request early return from the bounded solve after observing a sufficiently large change across 64 offered-clause samples. It never makes neural decisions or injects clauses. The controller evaluates only after CaDiCaL has reached a safe return boundary.
- **ACTIVATE:** create the SAT or UNSAT expert lazily when the assigned bounded exploration arm or prequalified cost-aware contextual gate allows it. Measure activation overhead.
- **CONTINUE:** retain the incumbent unless the candidate solves early or its observed short-clause yield per second exceeds incumbent yield by 30% in the controlled pilot. The retained solver continues **in the same process** with its own learned clauses. Short clause yield is a heuristic, not proof of optimality.

## Persistent learning from paired outcomes

SQLite starts from **R3's persistent model** and stores per-context, per-action records: `bucket`, expert, paired PAR2 benefit, activation overhead and observations. Source context buckets use only structural evidence: complete XOR3 groups, coupled XOR–CNF boundary, binary dominance and Horn dominance. No instance ID, filename or expected result enters policy prediction.

The existing 10–8–1 neural network is also updated with labels derived from training-only paired *end-to-end* outcomes (rather than the R2 short-clause proxy). The R4 `r4_safe` choice currently uses **conservative contextual utility statistics**; the neural network is retained and updated for subsequent calibration experiments but is not yet an independently validated calibrated action predictor.

If no useful training result exists, `r4_safe` abstains. It does not hallucinate a positive expectation. When evidence exists, activation additionally requires four relevant samples, at least two meaningful wins, mean net gain > 20 ms and a conservative Wilson-bound threshold.

## Frozen experimental design

- Reuse identical SHA-pinned R2/R3 source pool: 34 previously used training instances; 40 source-disjoint evaluation instances.
- **Not a blind scientific holdout:** those evaluation instances and generator families were already tested by R2 and R3.
- A fixed random sequence *prepared before execution* selects exactly **10 of 80** held-out repeated case slots for possible bounded exploration. Each slot assigns SAT or UNSAT profile. This random sequence is based on a shuffled slot index; source SHA is for identity verification, not an action feature.
- Six methods on all same-source, same-cap pairs (40 instances × 2 repeats × 6 arms = **480 attempts**):
  1. `clean`: pure pinned CaDiCaL;
  2. `r3_gate`: original R3 safe-abstention policy;
  3. `r4_safe`: trained contextual action gate;
  4. `r4_explore`: ten preregistered opportunities for random exploration; actual activation depends on prior solver completion and remaining budget;
  5. `forced_sat`: probe alternative SAT profile;
  6. `forced_unsat`: probe alternative UNSAT profile.
- Every action is charged full wall time, including source scan, Python, SQLite, dual solver creation, and probes.
- Judge solved count, PAR2, matched wins/losses, actual activation, callback wakeups, and model persistence. Use no model writes on test cases and verify checkpoint SHA before and after each shard.

## What would count as progress?

A **demonstrable useful action** means a context where measured net gain occurs repeatedly on untouched follow-on instances despite full exploration overhead and independent replication. One fast synthetic example is not a general SAT breakthrough.

Native CaDiCaL UNSAT outcomes are not independently LRAT certified here. The model cannot alter source clauses or declare SAT/UNSAT. A repetitive telemetry event is not a mathematical proof of periodic CNF structure.

Workflow: `.github/workflows/drnas-nmr-r4.yml`. Experiment branch: `experiment/drnas-nmr-r4-calibrated-explore-20261107`.
