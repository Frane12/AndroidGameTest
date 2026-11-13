# DRNAS X4.6 — completed counterfactual-cost pilot and learned-policy holdout
13 November 2026

## Provenance

X4.6 short-probe native reference branch:
experiment/drnas-x46-short-probes-20261113

X4.6 cost-learning branch (the actual frozen learned model):
experiment/drnas-x46-counterfactual-learned-20261113

First costed-probe reference CI (success):
https://github.com/Frane12/AndroidGameTest/actions/runs/43358698040

Cost-learning train/freeze/holdout CI (success):
https://github.com/Frane12/AndroidGameTest/actions/runs/43360009130

All work was on research branches, not main. Native X4.1's base
CDCL is unchanged when short probes are not enabled.

## What is implemented, not just suggested

An opt-in native X4.6 controller forks two deep-copied internal C++
solver states immediately BEFORE decision K. Those copies have the same
selected variable, trail, activity, watches, phase-saving, learned clauses
and restart/reduction schedule. They force opposite polarities and search
under bounded 8/32/128 additional conflicts, and bounded decisions/wall time.

The copies cannot add clauses, assert UNSAT, or manipulate the original
solver. Their measured time, including cloning, is charged to actual
end-to-end solver runtime. The only available native intervention is the
polarity of ONE chosen decision K. Shadow mode probes but does not
intervene. Full-trajectory matched-prefix hashes are compared for every
controlled arm to guard against accidental pre-action divergence.

The supervised X46COST1 logistic cost model uses 12 features computed
from the two short-probe conflict, decision, propagation, preliminary
internally verified SAT signals, and K. Targets come from TWO separate
and independently checked COMPLETED continuations of the same original
CNF and prefix, labelled by fewer future conflicts. Such targets are
available only in training/evaluation and never reach the live solver.

The model has a strict text file format with frozen per-feature means,
scales, coefficients, probability threshold and bias. Bad models or
missing inputs are rejected, never silently accepted. A model is loaded
only when explicitly passed with --x46-model.

## Reference 112-formula nonlearned experiment

112 independent new synthetic original CNFs x 4 checkpoints x 3 repeats;
990 matched and fully verified pairs across six arms. The rest ended
before their proposed checkpoint and are not part of the matched comparison.

| Strategy | Future CDCL conflicts | Verified end-to-end PAR2 |
| --- | ---: | ---: |
| CORE | 55,950 | 3.649867 s |
| Fixed short-probe 8 | 53,694 | 3.730346 s |
| Fixed short-probe 32 | 52,206 | 3.775901 s |
| Fixed short-probe 128 | 46,626 | 3.835691 s |

The 128-conflict probes reduce future conflicts by 16.66%, but
the extra probing makes end-to-end PAR2 5.09% WORSE. The 128-conflict
short-probe rule correctly identified the cheaper completed polarity in
621/738 evaluable non-tie paired continuations (84.15%), but no
real-world official SAT performance improvement follows.

## Actually learned counterfactual cost policy

Training: 84 distinct original synthetic CNFs at generator index 600000+;
source-level 63 train / 21 validation, selected threshold 0.60 from
validation, frozen file SHA256
234cb83b155bc5fe5ff5ec0337945480f4c09082f37fcfaacda6a1b7995cb4c4.

Separate smoke sources used index 620000+. Final new holdout used indices
700000+ and had ZERO original-source SHA overlap with train: 112 distinct
CNFs, 7 source families, 3 repeats, checkpoints 1/2/4/8, 972 matched
pairs. Seven arms, all 972 per arm independently verified. Of those,
846 pairs have SAT witnesses checked against ORIGINAL CNF, and 126
UNSAT outcomes are tiny original CNFs with independent exhaustive
enumeration (not fabricated general proof certificates).

| Holdout strategy | Future conflicts | End-to-end verified PAR2 |
| --- | ---: | ---: |
| CORE | 32,193 | 2.808357 s |
| X46 fixed 8 | 30,282 | 2.911093 s |
| X46 learned 8 | 30,678 | 2.949399 s |
| X46 fixed 32 | 29,235 | 2.943606 s |
| X46 fixed 128 | 26,406 | 2.986861 s |
| SHADOW fixed 8 | 32,193 | 2.916291 s |

The learned selector correctly ranked the cheaper future-conflict
continuation on 561/669 non-tie comparisons (83.86%), vs 504/669
(75.34%) for the fixed short 8-conflict rule. Improvement is +8.52
percentage points on these paired observations. A source-clustered
posthoc bootstrap of this *accuracy difference*, counting original
formulas as the units, gave approximately +1.36 to +15.72 percentage
points at 95% confidence. Individual decision pairs are correlated.

BUT the improved classification was NOT rewarded by lower total conflict
cost: it changed polarity in 330 matched pairs rather than 162, and
consumed 30,678 future conflicts vs the fixed controller's 30,282.
A single formula generated 1,995 MORE continuation conflicts for the
learned policy than the fixed 8-conflict rule, disproportionately
damaging the aggregate.

Compared to no probe, learned X46 did reduce conflicts by 4.71%, but
verified end-to-end PAR2 was 5.02% WORSE (2.9494 vs 2.8084 seconds).
The formula-clustered 95% interval for relative time improvement over
CORE was [-6.24%, -3.94%]. Relative to fixed X46-8, its PAR2 was
approximately 1.32% worse; a posthoc source-bootstrap interval for
relative improvement was approximately [-2.46%, -0.38%].
The solution count stayed identical and fully checked.

## Interpretation, limitations and next gate

We succeeded technically at:
1. making short, proof-safe, side-effect-free matched-state continuations;
2. measuring their overhead and completed future search work;
3. training a small cost predictor on prior, source-disjoint verified
   counterfactuals and loading it into the native C++ decision branch;
4. freezing the model before a fresh-source test and quantifying
   real end-to-end speed rather than just prediction accuracy.

We did NOT achieve a faster SAT solver. Detecting which branch wins
by conflict count is not sufficient when wrong high-cost flips dominate,
or when the probe itself is too expensive.

These were controlled synthetic CNFs from the SAME seven generator
families, not unseen families from SAT Competition. The native
intervention covers polarity at only ONE checkpoint, not the complete
adaptive search policy. Better transfer and industrial/general UNSAT
certificate verification remain open.

Next optimization should be PRE-DECLARED cost-sensitive selective
intervention: model the upper tail of regret, require sufficient
predicted expected CONFLICT savings to justify the measured probe cost,
and abstain otherwise. Assess on another fully untouched family/source
split. Ordinary CORE remains the performance-safe baseline. No
unconditional X4.6 deployment is justified.
