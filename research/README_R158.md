# DRNAS R158: Fractal–Entropy–Dynamics (FED)

## Scope

Implemented: deterministic graph-cover approximation; Shannon entropy of predecision propagation/glue/restarts; normalized finite-difference dynamics; repeated-trajectory variability; four predeclared ablation models A/B/C/D; five-fold formula-level cross-fitting; held-out testing; SHA/source/seed/runner/protocol audit; formula-grouped bootstrap; paired PAR-2 tables; two SVG scatterplots; fail-closed abstention.

**A**: fixed R17b evidence/no new features. **B**: early entropy/dynamics. **C**: graph geometry (modularity, growth, approximate box-cover). **D**: B+C. Linear ridge alpha=10; no hyperparameter optimization on test folds. All 160 source formulas from earlier R17 synthetic 3-SAT only, with 80 development / 80 test. One formula, not one attempt, is the statistical unit. Source: GitHub Actions run 42094261835, aggregate artifact 13447042971, commit `dc1a94520e90c75bb121203a273215a3c7b55308`.

**Safety:** R158 is OFFLINE evidence; zero new SAT solves and zero live restart changes. No claim of independent UNSAT certification, official competition status, new world record, proven fractality, calibrated chaos or Lyapunov exponents. A feature with insufficient scale support reports `graph_box_valid=0`. Early trace features use **only conflicts <=1024**. Runtime of extracting features is measured but not included in already-collected PAR-2. The safe deployable policy remains `MONITOR_ABSTAIN`, independent of estimated improvement.

**Provenance:** `r158_experiment.py` pins SHA-256 of the five R17 aggregate files and verifies each raw shard's `measurements.csv`, `traces.jsonl`, `manifest.json`, original CNF SHA, source commit, runner and seed against existing aggregate. It refuses incomplete shards, duplicate `(formula,rep,policy)` records, missing modes, altered folds and mismatched input. It also tests model invariance to deliberate replacement of every test label.

### Reproduce locally

Place the 16 downloaded R17 shard archives extracted under `raw/r17-{category}` with each shard's `manifest.json`, `measurements.csv`, `traces.jsonl` and original `.cnf` files. Extract the R17 final aggregate artifact under `aggregate` with `results.json`, `formula_features.csv`, `paired.csv`, `native_decisions.csv`.

```
python3 src/r158_experiment.py --aggregate aggregate --shards raw --out output
python3 -m unittest discover -s src -p test_r158.py -v
```

### Next independent study, not included in this run

Collect 200–400 original external CNFs prospectively with hashes recorded before R158 model exposure. Deduplicate against the complete historical registry (not merely R7–R17). Pre-register family/folds and frozen model; run same-runner paired native solves versus Kissat and CaDiCaL, with feature computation charged to time. Verify SAT witnesses and independent UNSAT certificates or mark UNSAT unverified. Compare PAR-2 with bootstrap resampling by **formula**, not attempt. Do not call reused community3 or historical official-catalog files independent official test data.

Frozen V15.3.1 and historical analytics SQLite are not modified.