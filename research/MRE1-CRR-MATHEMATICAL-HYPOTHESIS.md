# DRNAS MRE1 + CRR — Mathematical Representation Research

## Central hypothesis (2026-11-08)

> Do not merely search the space of candidate solutions faster. Find a
> mathematically equivalent representation in which part of that search is
> unnecessary.

**MRE1** is the bounded, cost-aware reduction orchestrator. **CRR**
(Cross-Representation Reduction) is its proof-carrying mechanism for transferring
facts between CNF, Boolean implications, GF(2), graph structure and eventually
ANF, iterating until the overhead exceeds the value.

This is a scientific hypothesis, not a demonstrated universal speedup and not
a P=NP claim. All new constraints must be logically implied by the original CNF.

## Implemented first experimental slice

- Parse original, SHA-locked CNF without deleting source clauses.
- Extract complete 2..6-variable XOR truth tables already implied by CNF.
- Independent replay of every source parity implication.
- Bounded GF(2) Gauss-Jordan elimination using source XORs and proved units.
- Convert GF(2) short consequences into CNF units, binary clauses or empty
  clause, with explicit XOR-combination provenance.
- Bounded binary-clause resolution; reuse new units in a second GF(2) round.
- Independently replay all lemmas from original CNF / earlier lemmas before
  providing appended CNF to the unmodified CMS 5.11.15 bridge.
- Preserve original CNF, validate SAT witness against original, do not treat
  CMS UNSAT result as independently LRAT-certified.
- Charge CNF parsing, preparation, proof replay and solver runtime to the
  same 30-second cap; abort/fail closed on malformed evidence.
- Compare 4 SHA-paired arms: CMS native; source XOR import; MRE1 shadow
  (all prep, no imported lemmas); MRE1 active (identical prep + lemmas).
- 32 reused R195 development CNFs x 2 repetitions x 4 arms = 256 trials.
  **NOT BLIND**. No worldwide leaderboard or novel performance claims.
- Retain small JSON summary and shard logs. Temporary augmented CNF files
  are removed automatically after each trial.

## Scope limitations

This initial implementation only performs CNF/GF(2)/binary-implication
cross-transfer, not full ANF polynomial factoring, general graph symmetry
breaking, nor a new externally injected *live* CDCL trail callback. CMS's
native Gaussian engine is the only in-CDCL GF(2) mechanism here.

R195's native bridge requires exact mode strings \`cms_native\` and
\`source_xor_import\`. We discovered and fixed that adapter mismatch in
the MRE1 experiment before allowing performance claims.

## Next falsifiable research steps

1. Freeze proof-replayed MRE1 against R195 and a pure CMS baseline, then
   report full-wall-clock and PAR2, solved delta, conflicts, decisions and
   provenance cost per original SHA and by cohort. Do not tune on holdout.
2. Add an implication-graph SCC equivalence detector, with an explicit
   replayable CNF chain proof; measure true new units/binary implications.
3. Introduce bounded ANF decomposition only for locally verified functional
   constraints (AND, XOR, ITE), with bidirectional truth-table verification.
4. Add a source-disjoint 2026/2025 *blind* holdout, pre-registered gate and
   independently verified SAT/UNSAT proof where applicable.
5. Promote to conditional active live-in-CDCL feedback only after a
   source-disjoint net-benefit result. If proof/overhead conditions fail,
   fall back to original CMS with the original input.

## Promotion criteria

- Zero falsely strengthened formulas on exhaustive small-CNF tests.
- SHA and parser provenance retained, proof replay reproducible.
- Full-wall-clock measured including all MRE1/CRR preparation.
- No SAT witness violations and no contradictory non-timeout verdicts.
- Positive paired benefit compared with both source-import and shadow;
  avoid average improvement hiding catastrophic per-formula regressions.
- Withhold world-class speedup claims until independent larger unseen tests.

Research code: \`research/mre1_cross_representation.py\`.
Workflow: \`.github/workflows/drnas-mre1-crr.yml\`.
