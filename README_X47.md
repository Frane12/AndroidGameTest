# DRNAS X4.7: bounded two-polarity probes and measured continuation work

X4.7 continues X4.5a on an isolated experimental branch. It adds read-only
unit-propagation probes of both polarities, and compares a ridge ensemble with
32 boosted depth-two regression trees. Only polarity at decision 4 may change.

## Isolation and correctness

Each probe copies the current assignment and scans the clause database without
changing clauses, watches, reasons, saved phases, heap, or solver counters.
Each polarity gets at most 8,192 inspected literals. Conflict is distinguished
from budget exhaustion. A one-sided proved failed literal is handled by an
explicit shared rule in FIXED and learned policies, and reported separately.
It is not evidence of learning. SHAM always keeps the baseline decision.

Tests compare all applicable policies with an independent truth-table oracle,
check failed-literal soundness at the first decision, verify unchanged CORE
and SHAM search paths, compare Python/native tree inference, reject malformed
models, and check deterministic work limits.

## Frozen protocol

- 768 fresh formulas from 16 generated regimes, larger than X4.5a.
- 384 train / 144 validation / 240 holdout, disjoint families within the run.
- Generator types were previously researched; this is fresh-formula evidence,
  not a claim of globally blind industrial or unseen-to-researcher families.
- Pair labels: actual remaining propagations to independently verified SAT
  after the baseline versus reversed decision, from an identical prefix.
- Collection uses exactly 100,000 propagation-queue operations as the search
  budget, with no solver wall limit. An emergency process timeout fails the
  experiment instead of silently changing the training set.
- Work-censored pairs are excluded from regression labels. Validation charges
  unresolved attempts 200,000 operations, and chooses thresholds and the primary
  model using work, not noisy runtime. The no-learned-intervention option remains.
- Both models freeze before any holdout outcomes. The primary model is chosen
  on validation only. Holdout does not update any model or threshold.
- CORE / SHAM / STATIC / FIXED / RIDGE / TREE run serially on one logical CPU,
  randomized order, three repeats, 0.8 s E2E cap. All costs count in runtime.
- Primary criterion: lower 95% paired formula-bootstrap bound exceeds 10%
  PAR2 improvement against CORE. Repeats are clustered by original formula.
  Other comparisons are exploratory and not multiplicity-adjusted. Only five
  holdout regimes support the exploratory family-level analysis.

CORE does no feature inference; STATIC uses only passive clause features;
FIXED chooses using probe-unit gain plus the failed-literal rule. SHAM pays
the primary learned model's costs but keeps CORE's decision. Comparing the
learned policy with FIXED and SHAM separates probe and model effects.

The ridge score uses ensemble mean minus SD; the tree score sums its leaves.
Neither score is a calibrated probability. Probe features describe immediate
unit propagation, not mathematical distance to SAT. The target measures the
remainder under the baseline continuation, not repeated learned interventions.
All performance sources are generated SAT with checked witnesses; UNSAT is
covered only by the separate exhaustive correctness suite. No competitor or
industrial superiority is claimed.

## Reproduce

```bash
python3 -m pip install numpy==2.3.5
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x41.cpp -o build/drnas-x41
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x47.cpp -o build/drnas-x47
OPENBLAS_NUM_THREADS=1 python3 tests/test_x47.py --cases 400
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -u research/drnas_x47.py --out x47_results
```

Artifacts retain protocol, formula manifest, matched pairs, frozen models,
every timed trial, and the final report. Train-label digests make cross-host
determinism auditable. Repeated execution is replication of this protocol,
not an additional independent holdout.
