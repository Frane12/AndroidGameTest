# DRNAS NP Lab — NeuroFlow v0.6 (multifeature, train-only)

Scientific objective: test whether **a cost-aware structural feature vector** predicts the net benefit of running exact renamable-Horn analysis before generic SAT solving, more effectively than v0.5's single Horn-defect threshold.

## Features (17)

Number of variables, clause density and mean length; shares of unit, binary, ternary and long clauses; positive literal share; majority-renamed Horn defect; minority sign share and average variable polarity imbalance; pure-variable share; coefficient of variation of occurrence degrees; top-decile degree concentration; connected-component fraction; largest-component fraction; and quartet-encoded XOR density. All are computed from the unsolved CNF; **no use of SAT vs UNSAT label or external solver output when selecting**. These indicators are not proofs that a formula is Horn, XOR or solvable in polynomial time.

## Frozen, train/test protocol

- Training: 160 previously sampled SATLIB original source formulas + 72 independent constructed controls. All training formulas are solved under both baseline and forced Horn probe and timed twice.
- Testing: 160 *different* original SATLIB formulas + 72 fresh constructed controls. Original SHA256 hashes are checked to be disjoint from training and prior SATLIB benchmark/NeuroFlow v0.4/v0.5 selections. Fixed selection seeds and upstream archive SHA256 hashes are recorded.
- Candidate net gain is `T_original - T_probe - T_features`; failed probes include their own fallback cost. Model predicts gain from 17 features using weighted kNN. k, loss margin, and minimum positive-neighbor fraction are selected only by leave-one-out on training formulas. Model remains **frozen** during test.
- Each held-out problem receives matched 3-repeat A/B/C/D comparison: baseline, forced probe, published frozen v0.5 policy, new v0.6. Vary execution order; count every feature/prediction/failed probe into runtime. CryptoMiniSat independently checks SAT/UNSAT labels for the original SATLIB test inputs; CMS solver speed is not the subject of this evaluation.
- All SAT assignments are validated against unmodified clauses, statuses checked against SATLIB category and constructed logic. Any incorrect outcome triggers a failed GitHub workflow; no data cherry-picking or substitution.

## Interpreting results

Interpret **per-instance paired gain** and positive fractions, not just ratios of medians from different distributions. A tiny speedup near clock granularity is not robust evidence. Novel computational-complexity claims are not supported. Current model does not use a neural network, GPU drivers or private NeuroFlow code.

The method may help on low-defect renamable-Horn formulas, while a C++ CDCL solver like CryptoMiniSat remains a much stronger generic SAT solver. If net speedup is absent or negative, report it and retain safe fallback.