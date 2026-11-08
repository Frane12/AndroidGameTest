# DRNAS MRE2 — proof-certified CRR with bounded BCP impact gate

## Experimental hypothesis

MRE1 found mathematically valid CNF lemmas but did not improve development-set
PAR-2. MRE2 tests whether selecting only proven lemmas that have a measurable
effect on bounded CNF unit-propagation probes is more economical than
importing all derived lemmas.

This is NOT an in-CDCL, live-trail reduction engine. Bounded pre-solve
single-assumption probes are only a predictor of actual search impact; positive
probe score does not establish faster end-to-end solution.

## Soundness boundary

1. The original SHA-locked CNF is always retained.
2. MRE1 recognizes complete source parity blocks using exhaustive local
   truth-table checks and replays GF(2)/resolution derivations from original
   clauses before any derived lemma can be used.
3. MRE2 only subselects the already proven MRE1 derived clauses; it does
   not create new unproved lemmas.
4. The native CryptoMiniSat 5.11.15 bridge checks SAT witnesses against
   full CNF; Python separately checks original SHA-locked CNF.
5. UNSAT conclusions are NOT independently LRAT-certified in this experiment.
6. Fail closed if any witness is invalid or a verdict differs from frozen label.

## Gate

BCPProbe implements deterministic CNF unit propagation.

For a proven binary lemma (a OR b), assume not-a and propagate baseline CNF,
then additionally force b, counting new units/conflicts; repeat with not-b
implying a. Accept if the combined score is at least 2. For unit lemmas, import
only if root UP does not already establish them. Each accepted lemma enters the
probe baseline before later candidates are evaluated.

Limits: at most 20 selected lemmas, 96 candidates, 0.45s gate time per trial;
abstain above 35,000 clauses. All preprocessing and gate time counts against
the common 30s wall cap.

The gate demonstrates novel bounded-UP implications, NOT measured
propagations on an actual CMS CDCL trail. An online callback is NOT built.

## Causal comparison

Five matched arms (same source SHA, deterministic seed, native library/adapter,
30s wall cap), ALL with OTF Gauss disabled:

| Arm | Source XOR | MRE1 derive | MRE2 gate | Imported lemmas |
|---|---|---|---|---|
| cms_native | no | no | no | none |
| xor_no_otf | yes | no | no | none |
| mre1_all_no_otf | yes | yes | no | all |
| mre2_shadow_no_otf | yes | yes | yes | none |
| mre2_active_no_otf | yes | yes | yes | gate-selected |

32 developmental SHA-locked sources × 2 reps × 5 arms = 320 paired trials
across eight shards, full-wall PAR-2, SAT witness verification mandatory.
The set reuses known R195/MRE1 formulas, and is NOT BLIND.

UNSAT claims are not independently LRAT-proof-checked. Future truly unused
official SAT holdout and repeated seeds are required for generalization.

## Promotion criteria

Prioritize correctness. Promote only if full audit passes and MRE2 Active
demonstrates stable PAR-2 improvement relative to same-config XOR-only and
MRE1-all baselines with total preprocessing costs included, without decreases
in solved count. Choosing zero lemmas is a valid safe abstention.

Next experiment: genuine trail-level CMS hook that measures whether newly
derived clauses lead to native in-CDCL propagation/conflict or saved decisions.
