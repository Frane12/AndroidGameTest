# LTM3 decision-path audit and experimental repair

Base: `cbb85ebdc19f833ea7c27fc0207ea89eeb777c7f` (audit-fix branch).
Stable solver sources are unchanged. The native experiment generates a separate
executable from the pinned ATLAS15 source.

## Findings and repairs

1. The existing workflow restored `mi-ltm3-v2-chain-only-*` but saved
   `mi-ltm3-train-only-*`. Consecutive runs could not restore the memory saved
   by this workflow. Save and restore prefixes now agree. The new experiment
   uses a separate namespace and separate databases for chain and native policy.
2. A chain consequence overwrote the structural `feature_key` local variable.
   This corrupted trial feature/matched reporting, not training insertion (which
   used the case key). The variables are now separate, with a regression test.
3. `known_patterns` is used only in offline diagnostics. Runtime routing uses
   a coarse structural opportunity key. Recognition alone never changed CDCL.
4. The trained gate had zero positive classes: XOR preparation cost exceeded
   savings on these small formulas. Abstention was correct. Empty policies now
   skip feature extraction entirely rather than paying a useless source scan.
5. Native process failures were silently converted to UNKNOWN. They now fail
   the benchmark; actual wall timeouts still receive UNKNOWN and PAR2 penalties.

## Direct decision experiment

`LTM_NATIVE` enables a bounded two-sided short-clause incidence heuristic in
the actual `pick_branch_variable()` call. It ranks at most 16 unassigned heap
entries, considers only entries within 80% of the current top activity, and
intervenes at most once every four decisions during the first 64 decisions.
VSIDS activity remains the main score. This is a fixed candidate heuristic;
the training-selected choice is whether to enable it for a structural class.

The native action adds no clauses, performs no model-based assignments and
does not bypass propagation, conflict analysis or backtracking. Counters record
candidate checks and actual departures from the current heap choice. A rolling
hash records every signed decision in all arms for paired trace comparison.
This hash is diagnostic, not a mathematical certificate.

`LTM_NATIVE_GATE` receives only a policy frozen from paired training outcomes.
It may choose the native action or BASE. Training must show at least eight
distinct formulas, 70% wins, no solved regression, and mean/median PAR2 savings
of at least 1.5 ms. These thresholds were not lowered to manufacture activation.
The native and chain databases are intentionally separate because they describe
different actions. Holdout does not update either policy.

## Local validation

19 existing LTM1 tests and 21 LTM3 tests pass. The latter include 80 independently
brute-forced small SAT/UNSAT CNFs, source/provenance checks, actual native gate
routing, unchanged disabled-control counts, real decision divergence, bounded
intervention counts, and rejection of native crashes as benchmark timeouts.

Each benchmark used one logical CPU, 192 training plus 192 fixed holdout CNFs,
six families, two timing repetitions, and a 3 s E2E cap. The control/native
heuristics are deterministic: the repetitions are not distinct search seeds.
This is a repeated nonblind generated holdout, not SAT Competition coverage.
SAT models are checked against the original CNF. UNSAT is independently checked
from complete original-source XOR encodings and GF(2) contradiction, not LRAT.
No Kissat/CMS comparison was run in this focused repair experiment.

Local native holdout (384 trials per arm):

| Arm | Solved | PAR2 seconds | Conflicts | Decisions | Overrides |
| --- | ---: | ---: | ---: | ---: | ---: |
| BASE | 384 | 1.531783 | 4260 | 8936 | 0 |
| LTM_NATIVE forced diagnostic | 384 | 1.563555 | 4208 | 8988 | 404 |
| LTM_NATIVE_GATE learned | 384 | 1.545538 | 4260 | 8936 | 0 |

The forced candidate changed 210/384 decision traces (105/192 distinct CNFs).
It reduced total conflicts by 1.22%, increased decisions by 0.58%, and was
2.07% slower E2E (BASE/candidate PAR2 = 0.980x). No solved regressions occurred.
Training selected zero positive classes; therefore this is verified causal
integration, **not evidence of useful learned intervention**. Do not promote
the forced candidate to the stable default on these results.

In separate before/after runs on the same sources, empty chain-gate overhead
relative to its paired BASE fell from 0.141060 s to 0.021847 s in total.
Millisecond-scale E2E timing includes process startup and is noisy; the structural
fact is that the unnecessary source scan is gone. The chain arm's matched-class
count was corrected from 142 to 376, with unchanged conflicts and decisions.
Detailed aggregate metrics by family are in `decision_fix_local_results.json`.

## LTM5 cross-check

The inspected LTM5 branch at `8fb081f8f1a6451ee3bd44a208e347c71003bffe`
contains reversible XOR graph restriction, source provenance, rollback and
transition signatures. Its successful run `43087620154` audited 384 CNFs,
1,155 synthetic events and 15 transition types, with `live_CDCL=false` and
`PAR2=null`. `audit.py` assigns fixed synthetic values; it does not consume the
native trail or train measured intervention utility. No LTM5 synthetic event
was imported into this experiment's useful-strategy memory. A future integration
needs real enqueue/backtrack events and paired causal outcome measurements.

## Reproduction

The workflow `.github/workflows/drnas-ltm3-decision-fix.yml` builds both binaries,
runs the proof/routing tests, then runs the corrected XOR gate and direct native
benchmarks sequentially. It saves only training databases and exports complete
trial JSON/logs as artifacts. Source generation is anchor-checked and fails if
the pinned solver structure drifts. No benchmark output alone changes a policy
threshold or promotes the experimental heuristic.
