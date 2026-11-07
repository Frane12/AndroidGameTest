# DRNAS New Horizon SAT — R1

Research goal: do not assume "mixed SAT" is a natural well-defined class. Recognize provable source structures cheaply, reconstruct equivalent relations at runtime, and route to the narrowest sound method with conservative CDCL fallback for UNKNOWN.

## Architecture

research/new_horizon_sat.py: canonical XOR3 truth-table index, mapping each sorted variable triple to sign masks. Four complete forbidden assignment masks imply an exact 3-variable parity equation. Scanning is limited to 2048 clauses, with analysis-walltime gate. Incomplete motifs are not declared proven.

research/new_horizon_benchmark.py: freeze and SHA verification, controlled synthetic generators, 4 matched arms, source-witness checking, and independent result audit.

Decision chain:
1. Scan first 2048 original CNF clauses, compute canonical motif pointer invariant under variable renaming.
2. For small source-complete parity instances, independently confirm source equivalence and use existing R164 GF(2) certified method.
3. For certified XOR3 blocks connected to residual CNF, if cost and source-size permit, reconstruct source-complete XOR3 rows using R182. Add only GF(2)-proven implied units to original CNF, otherwise abstain.
4. Use clean CaDiCaL 2.1 on the original CNF whenever no useful safe evidence exists. No guessed clauses or false heterogeneous labels.
5. Charge full analysis and preprocessing time to the selected method.

## Frozen benchmark

- 12 previously used real original CNFs from existing R187 archive (not blind).
- 32 newly seeded synthetic examples from previously known R186 generator families.
- 10 pure XOR3 SAT/UNSAT controlled examples.
- 20 XOR3+residual controlled examples across 0/25/50/75/100 percent generated cross-boundary clauses; 4 per level.
- 74 formulas, 2 repetitions, 4 arms = 592 paired runs.
- Modes: clean; shadow (scan+clean, isolates overhead); forced (expensive source GF2 processing); new_horizon (cost-gated).
- Caps: 3s generated, 10s reused real originals.
- Same CaDiCaL pinned source SHA 31f9aae44947c673dc6190c9beb399acb9ffec6a and binary for all modes.
- Primary metrics: solved count, PAR2, preprocessing overhead, derived units, source hash, model correctness, algebraic UNSAT evidence.

## Limits

The controlled mixing percentage is a construction parameter, NOT a universal formula class or objective measure of mixing.

Native CDCL UNSAT has no independently replayed LRAT proof here. Pure/GF2 algebraic contradictions are replayed from source clauses, but not LRAT either. SAT answers are checked against original source CNFs. Previously used real CNFs and known synthetic generator families do not constitute a blind external holdout. Do not make claims of general SAT speedup or polynomial complexity from this pilot.

Workflow: .github/workflows/drnas-new-horizon-sat.yml
Benchmark source baseline R187 GitHub Actions run 42221503842.

Next steps: expand the transformation index to certified implication-chain motifs, and test adaptive response-aware control against static source fingerprints, with holdout and full time accounting.
