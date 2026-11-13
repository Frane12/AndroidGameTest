# DRNAS Native X4.5 — repeated same-state counterfactual ranking

**Status:** controlled experimental pipeline, NOT proof of improved SAT solving. X4.5 is a standalone C++20 CDCL solver based on X4.4. Kissat/CaDiCaL/CMS are not linked or invoked. The only changed behavior is a **read-only observational analysis** at an explicitly requested checkpoint. This is **not yet a model-driven branching policy**.

## What X4.4 taught us
On 300 generated SAT CNFs, many matched-state opposite-polarity interventions had different future time, but a 10-feature ridge model showed essentially no runtime improvement on held-out families. Single measurements could be noisy, and structural features were weak.

## X4.5 approach
- **10 legacy features**: context (assignment fraction, level, conflicts, learnt, residual structure, literal sign balance and source size).
- **18 new local features** measured BEFORE intervention: positive/negative residual clause occurrences (short/3/long), binary implication fanout, and **bounded read-only unit propagation** for both candidate polarities: implied literals, conflicts, inspected clauses and incomplete-probe flags. Features never include source filename, SHA, outcome, post-intervention information or learned model feedback. Clause-occurrence index is built once; probe works on an independent copy of the assignment, without modifying watched literals, CDCL trail, phase, statistics, or learned clauses.
- Each of up to **five states per formula** is deterministically replayed. **Three runs of each sign** in alternating order, all **six prestate fingerprints/features** checked equal; every run continues normal CDCL with backtracking and a whole-formula SAT witness independently checked on the original CNF.
- 300 new generated, planted-SAT CNFs with frozen SHA and family-disjoint split: **180 training, 60 validation, 60 holdout**. These are *not* industrial or official competition sources; some generator patterns are known from earlier experiments.
- Time cap: **2.5 s per executable**. Incomplete runs are censored and do not get invented completion-time labels. The benchmark records the number of censored observations.
- **Reliable comparison:** only fully completed 3x2 pairs enter supervised regression. A strong signal requires a median gap of at least 4 ms, at least 15% relative difference, at least twice the within-polarity MAD, and the same winner in at least two of three repetition pairs.
- **Ranking, not absolute SAT distance:** train regularized ridge ranking on relative median time (positive versus negative), grouped by original CNF to reduce correlated checkpoints. Fit only TRAIN; select regularization and among legacy10/local18/combined28 only on VALIDATION; evaluate HOLDOUT once, with SHA-clustered bootstrap CI.
- **Cost accounting:** the local features are measured and their duration included in both post-decision continuation time and process wall clock. A separate conservative comparison deducts the estimated feature overhead from the default policy (which could skip probing); this is an estimate, not a measured independent no-probe control. CPU collection cost is **not** amortized by a single solve.
- **No online deployment:** learning remains offline/shadow. The objective is to determine if new local predecision information is predictive enough for further controlled experiments.

## Compile and test

```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x44.cpp -o build/drnas-x44
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x45.cpp -o build/drnas-x45
python3 tests/test_x45.py
python3 research/drnas_x45_counterfactual.py freeze
# GitHub Actions: 10 independent shards, then offline validation-first aggregate
```

Output is standard DIMACS: `SAT=10`, `UNSAT=20`, `UNKNOWN=0`, `ERROR=1`, with `X45_STATS` and optional `X45_CHECKPOINT` JSON in stderr. A SAT assignment is independently checked by the Python benchmark on the *original* CNF. No independent UNSAT proof certificate is produced. In the planted SAT test, any UNSAT is a correctness error.

**Interpretation caveat:** repeated prefix matching is deterministic replay, not a serialized snapshot cloned in memory; same-state identity is grounded in fingerprints, feature vectors and identical software/environment. Strong-sign labels and oracle time advantage are retrospective; neither establishes any universal exact distance to SAT nor the gains of deployed decision-level reinforcement learning.
