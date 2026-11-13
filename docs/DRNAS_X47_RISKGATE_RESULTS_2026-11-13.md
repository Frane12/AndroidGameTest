# DRNAS X4.7 — cost-sensitive abstention and tail-risk control

Date: 13 November 2026
GitHub branch: experiment/drnas-x47-riskgate-20261113

## Intent and implementation

X4.6 learned to classify the cheaper of two verified, matched-state branch
continuations, but even its higher classification accuracy made verified
end-to-end PAR2 WORSE due to cloning/probe overhead and occasional expensive
wrong flips. X4.7 therefore implements explicit action abstention.

Native C++ additions in src/drnas_x41.cpp:
- Optional strict frozen X47GUARD1 on-disk model, accepted with --x47-guard.
- Pre-probe gate based solely on publicly available original CNF variable
  count, clause count, and current designated decision index.
- Post-probe conservative probability floor; expected signed future conflict
  savings estimated from TRAIN-only mean wins and regret magnitudes. Wrong
  polarity's TRAIN 90th-percentile conflict cost enters a tail-risk penalty.
- The X46 short-probe model and X47 risk model are frozen and source-separated
  before an unseen formula's result can be inspected.
- When the formula fails the pre-probe eligibility gate, X4.7 skips both
  probes, does not flip, and (optimized variant) does not deserialize the
  X46 cost model; it still validates the X47 guard itself.
- The parent solver never imports clauses/proofs from cloned continuations.
  No intervention can claim UNSAT or bypass independently checked SAT models.

The guard-fitting script research/drnas_x47_guard_fit.py calibrates an
unambiguous 7-candidate menu on 21 validation originals after learning a
counterfactual logistic model on 63 separate originals. One choice is the
zero-probe fallback. A policy may be selected only when its lower
one-sided conservative source-level bound on *net time saved* is positive.
This is an explicit failure-safe baseline, not an unconditional speedup.

## Training and choice

- 84 distinct generated original training CNFs; 63 original sources for
  X46 logistic learning and 21 original sources for threshold/gate selection.
- TRAIN counterfactual mean win when flip helps ~44.79 conflicts.
- TRAIN 90th-percentile regret when a flip hurts: 30 conflicts.
- No tested nonzero-probe rule crossed the conservative validation criterion.
- The **NO_PROBE** policy was frozen for new holdout: min-variables gate
  makes it ineligible to probe these small source formulas. The serialized
  X47 guard SHA-256 is
  7647bf185d8c75a184cfff3e1f4f500434619bf6b553b0516b8c5a9150c223a7.

This selection means X4.7's inference on these synthetic formulas is NOT
evidence that a nontrivial branch-cost predictor has become profitable.
It is evidence that the controller correctly abstains when confidence and
net expected return are insufficient.

## First held-out cohort: 112 original sources, index 800000+

Successful initial run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43361487332

987 matched checkpoint decision pairs; eight arms each verified against
the original CNF (SAT) or exhausted small UNSAT construction, 112 independent
source formulas. The original X4.7 selected NO_PROBE and logged 987/987
pre-probe skips. Its continuation decisions and conflicts were identical
to CORE, but its end-to-end PAR2 was 3.202744 versus 3.116391 seconds
for CORE (2.77% slower), mostly from fixed setup and model loading.

## Lazy loading, confirmed on a FRESH new holdout

After observing the setup overhead in the first cohort, the code was
updated to validate the X47 guard first and deserialize the X46 logistic
model ONLY if the guard allows this formula to attempt a probe.
This change was NOT tested as a fresh-independent algorithm improvement
until a separate cohort had been generated.

Independent new holdout: index 900000+ (zero source overlap with previous
training and previous holdout); 112 new original source formulas from
seven synthetically generated families. Four designated checkpoints and
three source-correlated repeats; 966 matched pairs, 357 pairs terminating
before the checkpoint. All eight arms independently verified for every
matched comparison. Run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43361824371

| Arm | Continuation conflicts | Total verified PAR2 |
|---|---:|---:|
| CORE | 21,147 | 3.013998 s |
| X46 fixed 8 | 19,986 | 3.141617 s |
| X46 learned 8 | 23,997 | 3.204320 s |
| X46 fixed 32 | 19,830 | 3.169955 s |
| X46 fixed 128 | 17,538 | 3.244589 s |
| X47 risk gate + lazy load | 21,147 | 3.078646 s |

X47 chose NO_PROBE again. It performed **966/966 early aborts**, zero
clones and zero changed branch polarities. Its search work (21,147
conflicts/29,694 decisions) was identical to CORE, but end-to-end time
was 2.14% slower (configuration file deserialization and short-run timing
overhead). Formula-clustered 95% CI for X47 relative PAR2 reduction was
[-2.53%, -1.73%], i.e. regression on these tiny instances. No
improvement was established.

By comparison X46_128 found 17.1% fewer continuation conflicts but was
7.65% slower in verified wall time, reinforcing that paying for probes
can outweigh better decision work.

## Scientific limitations and next experiment

- The 966 matched comparisons are NOT 966 independent formulas.
  Formula-level N is 112. Three reruns and multiple checkpoints remain
  correlated.
- These are small, *synthetic* original CNFs with repeatable source-index
  generation. The two sets are SHA-disjoint, but share the same seven
  generator families. They do not establish transfer to new official
  SAT Competition or industrial families.
- SAT models are independently checked on original input CNFs. UNSAT
  credit is restricted to separately exhausted 12-variable controls;
  general UNSAT DRAT/LRAT certification is not implied.
- The selected NO_PROBE policy needs no predictive intervention and cannot
  be sold as a learned branch speedup; it is conservative fallback.
- Current harness deliberately launches one process per tiny formula;
  fixed model/guard loading is meaningful relative to ~milliseconds
  per instance and would require amortization in a long-lived process.
- To test a *potential* positive return, the next experiment must focus
  on genuinely harder CNFs with meaningful end-to-end search work and
  correctly costed, once-per-process probing, while verifying SAT witnesses
  and independent general UNSAT certificates before making any claims.

Code: research/drnas_x47_guard_fit.py,
research/drnas_x46_probe_bench.py,
src/drnas_x41.cpp,
.github/workflows/drnas-x47-riskgate.yml.

Do not promote this variant to default or claim speedups. Main was not changed.
