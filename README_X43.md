# DRNAS X4.3 — 3,000 original generated SAT CNFs, two sequential cycles

Status: Research experiment. It measures repeated-input adaptation and a *source-only learned router*. It does not claim a solved SAT theory, a causal metric of progress, or generalization to SAT Competition 2024 formulas.

## Protocol

- Deterministically generate **3,000 distinct SAT CNFs** from the **same ten generator families** used by X4.2, but with a **new frozen seed namespace**. These are *generated, planted SAT*, **not 3,000 independent official SAT2024 instances**. Verify every source SHA and every reported SAT witness on its original CNF.
- Freeze all 3,000 SHA and the 1,800/600/600 family-disjoint train/validation/holdout split before any solve. Per source cap = 3.0 seconds, UNKNOWN penalized as 6.0 s in verified PAR2. Use one logical CPU per runner, 12 shards × 250 sources.
- **Cycle 1 (first full pass):** X4.1 native CORE, X3 native ADAPTIVE, and the passive X4.1 TRACE observer execute on the exact same input CNF. Paired times and bounded state transitions are recorded. Both strategies are independently written DRNAS C++ solvers; neither invokes Kissat, CMS or CaDiCaL.
- **Freeze learning:** Fit a ridge-regression router predicting the *signed difference in actual verified PAR2* between our two DRNAS strategies, from cheap numerical source-only features. Fit on 1,800 TRAIN formulas. Select one fixed threshold/constant fallback using only 600 VALIDATION formulas. All 600 held-out families stay out of model fitting and hyperparameter selection.
- **Cycle 2 (second full pass):** after the model has been frozen and all 3,000 cycle-1 sources have finished, run X4.1 CORE, X3 ADAPTIVE, globally learned router, and a clearly labelled same-SHA memory comparator on the **same 3,000 original CNFs**. Rotate execution order across formulas to mitigate CPU/cache effects. The learned arm reads only numerical features computed from the original CNF, not SHA, family, filename or a first-pass per-formula lookup; source scan + model evaluation is charged to learned end-to-end time. The memory comparator **does** deliberately reuse an exact-SHA best-arm lookup from cycle 1, demonstrating memorization on repeated inputs, *not unseen generalization*.
- **Final:** audit that every SHA appears once per pass and matches exactly; report solved, PAR2, real E2E, regressed/faster pairs, per-family counts, controller selection, censored runs and trace size. Compare learned against same-cycle baseline controls, and separately compare cycle-1 versus cycle-2 core to quantify ordinary repeat/cache/runner effects.

No branch decision inside X4.1 is directly modified yet. The learned controller is an **outer DRNAS native strategy chooser**, not an in-solver model of the distance to SAT. That distinction is essential. Observed step-level trace features are retained as diagnostics and for a later *decision-level* X4.4 design. Retrospective future-time labels are not causal rewards.

## Local use

```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x41.cpp -o build/drnas-x41
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x3.cpp -o build/drnas-x3
python3 tests/test_x43_two_cycle.py
python3 research/drnas_x43_two_cycle.py freeze
# In GitHub Actions, 12 independent cycle1 shards each process 250 sources,
# then all cycle1 artifacts are aggregated and the model is frozen,
# then 12 cycle2 shards rerun EXACT SAME sources, then final audit.
```

Run URL is provided after CI starts. No new APKs, no external SAT fallback, no large proof/log uploads. The benchmark evaluates the two-cycle learning experiment; it is **not** an independent competition benchmark. Large UNSAT proofs are not needed here because all generated instances have independently planted satisfying assignments; any solver UNSAT report is treated as a correctness failure.