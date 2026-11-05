# DRNAS R12 — frozen structural + early-dynamics in-process decision test

Date: 2026-11-02. Branch: `experiment/drnas-r12-structure-dynamics-holdout-20261102`.

## Scientific question

Can a **pre-registered** conjunction of static CNF structure and early solver
dynamics predict when the same native Kissat restartint=25 intervention at
conflict 2048 helps, avoiding the major regressions observed in R11?

Do **not** interpret R11 per-formula >2x peaks as a world record or evidence
of a universal law. The R11 120-formula benchmark found zero generally
successful forced restart policy, and R10's learned structural gate did not
validate. R12 is a new prospective falsification experiment.

## Source of rule (development only)

Rule was chosen using **60 R11 development** Random-3SAT formulas, not the
60 R11 reserved-test formulas. Fixed before any R12 CNF results. Frozen
as `experiments/drnas_v16/r12_frozen_structure_early_rule.json` and
backed by the R11 development feature table Git blob
`a1191f9a23f6dd8310ad461e29bc3b9d5daff43f`.
The exploratory rule would have selected 22/60 R11 development formulas,
with roughly +7.9% sum-of-PAR2 improvement *only within that selected
development group*. This is in-sample and susceptible to optimization bias.

### Fixed input features

* Structural: coefficient of variation (population standard deviation over
  mean) of the **variable occurrence degrees in the input CNF**, computed
  before solving. Requires `degree_cv >= 0.265`.
* Early dynamics: at 512 observed conflicts in the **same running Kissat**,
  propagation/conflict `0 < p < 43` and fast/slow learned-clause glue ratio
  `g < 0.95`. R12 implementation matches R11 counters and source.
* Combined hybrid gate: `structural AND early`. If true, schedule
  restart interval 25 at conflict 2048. Otherwise abstain (monitor).
* All policy choices are made from the formula and early trace; no
  post-solve oracle and **no process restart**.

### Nine real comparison arms

1. `monitor` — patched, instrumented same Kissat, never intervene (primary
   causal reference)
2. `r11_2048_25` — intervene on every eligible long search, no gate
3. `r11_2048_50` — same intervention but interval 50
4. `r12_early` — only the frozen early p/g rule
5. `r12_structure` — only frozen degree CV rule
6. `r12_hybrid` — combined frozen early+static decision
7. `r12_inverse` — early rule AND inverse static decision (negative control)
8. `original_kissat` — same upstream SHA, different instrumentation
9. `stable_v1531` — unchanged baseline V15.3.1 (separate architecture)

The five gate and forced modes plus monitor all use the **same compiled
experimental Kissat** and on-the-fly adjustment; the reference programs
must NOT be interpreted as same-binary causal controls.

### New test protocol

* 120 prospective generated 3-CNF formulas, 200/220/240 variables and
  4.23 clauses per variable; 60 new development and 60 new reserved test.
* Each formula receives 9 policies x 3 repeated timed runs in reproducibly
  shuffled order: **3240 total attempts**.
* Frozen generator seeds `411200000 + 10000*n +
  (test?1000:0) + part*10 + j`. No selection by outcome.
* Verify canonical CNF SHA256 against a **1,534-hash historical registry**
  (previous cumulative snapshots and R11) and check all 120 unique hashes.
  This establishes non-overlap with *our registry*, not guaranteed novelty
  relative to all possible formulas or external public collections.
* One GitHub-hosted Linux runner per shard (10 formulas), all paired policies
  restricted to a single chosen CPU core per shard; different shards can
  have different host CPU hardware and must NOT be compared by raw speed.
* Timeout 12 seconds per attempt, PAR-2 timeout value 24 seconds.
  Parse SAT/UNSAT status; check every SAT assignment against the CNF and
  reject contradictory solver outputs. Direct Kissat UNSAT results do not
  provide independently checked UNSAT proof certificates.
* Preserve seed, repository commit, formula/source/manifest/binary hashes,
  CPU affinity and runner, raw traces, timings, status, PAR2, decision and
  actual intervention. Require 3240 complete attempts for the final report.
* Reject prefix counter mismatches between monitor and experimental modes
  before earliest intervention, by conflict 384.
* Quantify real gate activations, false interventions, abstentions,
  regression >2x, acceleration >2x and worst-case outliers. Confidence
  intervals from **formula-block bootstrap stratified by n=200/220/240**
  (never treat 3 repeated timings as independent instances).
* Plot early propagations and input degree CV against signed log2 speedup,
  separately for prospective development and reserved test folds.

## Decision criterion

**Primary endpoint** is the frozen `r12_hybrid` total PAR-2 gain vs monitor
on the new reserved 60-formula R12 test fold. It is considered evidence for
limited domain usefulness only if gain >0, formula-block 95% bootstrap CI
excludes zero, and no severe correctness problems. Also disclose >2x
regressions and compare against the one-feature ablations, forced modes,
original Kissat and V15.3.1. The experiment tests this *one* frozen
candidate; reviewing other rules and thresholds on R12 creates new
exploration, never confirms the same holdout.

Any stronger conclusion or external-domain transfer requires an independent
external/official experiment with certificates and frozen rules. No
claim of P=NP, universal laws, or world ranking follows from this benchmark.

The original V15.3.1 solver source and frozen upstream Kissat SHA remain unchanged.
