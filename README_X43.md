# DRNAS X4.3 — before-action statistical direction learning

Branch: experiment/drnas-x43-before-action-predictor-20261113

## Research hypothesis

Given only features available before a real CDCL branch action, can a
low-cost model predict whether it increases, decreases, or leaves unchanged
the fraction of satisfying completions under the current partial assignment?
Does supervised prediction improve over a constant predictor on NEW,
structurally different CNFs?

This asks about predictive association, not causal effect. Native SAT solver
branching, propagation and verification remain unchanged. No learned
prediction is used to make CDCL decisions or declare SAT/UNSAT.

## Three actual, cumulative learning cycles

- TRAIN: planted3, planted_2sat, community3, planted_xor.
  Three cycles, 24 new original CNFs per family per cycle:
  96 new sources/cycle, 288 cumulative training sources.
- VALIDATION: sparse4 (24 separate sources), evaluated after every training
  cycle, never used to train a model or change hyperparameters.
- HOLDOUT: sparse3 + xor_ring, 32 new original CNFs each (64 sources), scored
  only once after the policy is frozen.
- UNSAT CONTROL: php_unsat and graph_k4_unsat, eight originals each, truth
  from exhaustive enumeration. No "toward" training label on UNSAT.
- Total 392 SHA-unique original CNFs x three representation cycles = 1,176
  native diagnostic runs. Replays are not independent source problems.
- All sources generated from previously unused formula index ranges >= 30000.
  Previous replay SHA values are explicitly excluded.

## Exact diagnostic, available only in tiny n

Independently enumerate M(F), the set of satisfying complete assignments,
for n <= 18. On any partial trail s:

    p(s) = |{m in M(F): m agrees with s}| / 2^(n - |s|)

Increase in this probability is classified as toward; decrease as away;
equality as flat. An inconsistent current branch is not a whole-formula
UNSAT proof. The exact oracle is too expensive for general large SAT inputs.

The before-action feature vector uses only the current decision, initial
clause/variable-incidence statistics, the pre-decision CDCL snapshot, and
already observed previous transitions. It never uses the same action's
after-state, exact oracle probability, formula SAT status, family tag or
future runtime to make a prediction.

## Metrics and controls

Model: three-class ridge softmax with fixed 90 epochs and TRAIN-only
feature scaling. Each original formula has equal total training weight
regardless of its number of decisions or representation replay trials.

Each cycle: report family-disjoint validation log loss, class accuracy,
non-flat toward/away accuracy and formula-cluster bootstrap CI for
improvement over a constant training-frequency baseline.

Final test: freeze model, evaluate the holdout families ONLY ONCE,
report individual per-family losses, confusion table and formula-clustered
95% interval for log-loss improvement. No positive claim unless its lower
bound is strictly > 0. Also report against always-toward nonflat baseline.

An observed prediction gain would still not show that an ACTIVE policy
would speed up SAT. That would require a later paired proof-safe experiment
with the cost of feature extraction included.

SAT witnesses are checked independently against original CNFs. UNSAT controls
use exhaustive small-n enumeration. No independent UNSAT proof on large real
instances is implied.

## Reproduce

    mkdir -p build
    g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x41.cpp -o build/drnas-x41
    python3 -u research/drnas_x43_preaction_bench.py --binary build/drnas-x41 --out x43_preaction --train-per-family-per-cycle 24 --valid-per-family 24 --test-per-family 32 --unsat-per-family 8 --cap 1.5

GitHub workflow: .github/workflows/drnas-x43-preaction.yml
