# DRNAS SAT — Ultimate R1 research record (2026-11-07)

## Sources and evidence (not a record claim)

- **R153 GF(2)** frozen pure-XOR/unit recovery: proof replay from original CNF and original SAT witnesses. Original R153 confirmation used 25 source-pinned formulas and repeated comparisons; strong specialized XOR performance but not broad mixed-CNF evidence. Source benchmark artifact: Actions run 42128549081.
- **R160** original R153 binary was kept bit-identical while a frozen R135-style structural selector chose Kissat/CaDiCaL at fallback. Trial run 42139118528 completed five shards but audit rejected different *cross-shard CPU models*; R160 and R153 were approximately tied (26/50 each). Distinguish CPU-paired comparisons from aggregate runner effects. Other R160 portfolio run 42135803972 was valid but did not improve reference Kissat.
- **R194** dual-live two profile candidates, 128-conflict pilots, keep learned clauses of surviving solver, total overhead measured. Independent seed/order replay on **one previously known** real source showed 6/24 solved vs 0/24 default. Corrected, replayed audit: Actions run 42307109683. This is NOT source-level transfer proof.
- **R159/R162/R172**: GF(2) bookkeeping and more conclusions can decrease conflicts or callback overhead without improving solved count or PAR-2. Preprocessing (e.g. dozens of ms) can erase gains on easy/non-XOR problems. Avoid always-on Gaussian passes.
- **R193/R195**: Dual-keep's wins on some real formulas coexist with substantial hard-formula regressions. Split256 small global improvement in R195 with seed-sensitive outcomes; never presume interruption = gain.
- **R196/R197**: restart/rephase/stabilization state affects CDCL trajectory; R197 development results show higher solved count under split256, but eight new-to-R195/R196 formulas × three seeds gave **0/24 vs 0/24**. Not a proven general acceleration.

## Ultimate R1 precommitted integration

The exact R153 certified binary is not edited. On a certified full parity SAT or source-implied GF(2) UNSAT, it returns a checked result. Otherwise it execs a source-only selector. **R160 control** uses the original byte-pinned R160 dispatch rule. **Ultimate R1** keeps this rule but, on eligible *large* low-binary/low-Horn prefix cases, runs the R194 dual-live default-retained strategy in-process. The original DIMACS is never rewritten; no candidate selection uses case ID, SHA, expected label, or observed test outcomes. Dual fallback gate:

- Prefix parses with at least 128 complete clauses.
- At least 1,000 declared clauses and 4,096 scanned bytes.
- R160 rule: binary fraction below 0.20, Horn fraction below 0.50.
- Otherwise choose exactly the R160 frozen CaDiCaL/Kissat fallback.

These thresholds are research **hypotheses**, not trained or independently validated boundaries.

## Experimental protocol

- 25 historical R153/R195 overlapping originals (counted **once**), 12 official 2026 R195 originals, eight R197 originals new-to-R195.
- 45 unique original SHA-frozen CNFs, two randomized mode-order repeats, seven methods = 630 trials.
- Every source/rep arm runs sequentially on the same shard CPU; runner CPU models may differ between shards and are recorded.
- Same source/cap per pair; R194 CaDiCaL 2.1 default and dual share seeds 11/23. Other frozen executables retain their internal default seed policies.
- Reference Kissat 4.0.4 and CaDiCaL 3.0.1, plus CaDiCaL 2.1 to isolate revision differences from R194.
- End-to-end wall time including source scanning, GF(2), selector and dual pilots; timeout penalty PAR-2 = 2× cap.
- All SAT witnesses verified against original source; R153 GF(2) contradictions independently replayed from original clauses. Other native UNSAT solutions **do not have independent LRAT**. Absent LRAT is not proof of incorrectness but limits external certification.
- This source set is **not globally blind**. It is prospective only for the newly composed Ultimate R1 program; earlier experiments saw these cases.

## Acceptance / rejection rules

Primary: paired *solved count* and total *PAR-2*, separated by historical, R195 official 2026 and R197 official 2026 cohorts. Require no unacceptable regressions and nontrivial advantage on new-source groups before promoting. Check route distribution and actual dual activations; a simple no-op / always-abstain path is not a positive neural or dual result. A fast solve on one reused case is diagnostic, not world-record evidence.

## Follow-up hypotheses after R1

1. **R153 scan budget:** use a provably safe source-only prefilter to avoid full GF(2) scans on clearly non-XOR originals; test false negatives separately.
2. **R160 structural threshold:** calibrate cutoffs on *training* originals only and freeze before a new, SHA-disjoint test; test adverse case families.
3. **R194 dual profit gate:** learn net reward from pilot work *including* the losing candidate's time; prune when activation overhead exceeds expected utility.
4. **R197 split256 causal control:** add only after a prospective paired source+seed success; do not combine multiple unproven perturbations into R1.
5. **UNSAT certification:** add DRAT/LRAT proof generation and independent check for CDCL UNSAT, not just source-implied GF(2) contradictions.
6. **Runtime and fairness:** compare equal version/native options, report bin hashes and single-shard paired CPU; avoid across-shard raw microsecond comparisons.
7. **Hard mixed CNFs:** optimize for at least one genuinely additional solved unseen mixed case, not merely reduced conflict counters.

No merge to main, no automatic PR merge, no record claim.
