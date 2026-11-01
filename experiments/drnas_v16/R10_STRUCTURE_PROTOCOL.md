# DRNAS R10 — structural experience-to-action test (preregistered, 2026-11-01)

## Aim and scientific status
R7 (GitHub run 41346915939) contains two exceptional generated Random-3SAT
instances: rnd3_82.cnf (27.68x) and rnd3_110.cnf (27.10x) under forced restart
at conflict 2048 compared with in-process Kissat monitor, over three paired
attempts. Cases rnd3_42, 52, 26 are 7.87x, 6.44x, 5.18x. These are
**retrospective discoveries**, not proof of generality. Other 3-SAT cases
regress severely. Extreme performance is not the same as a SAT
Competition record or a mathematical breakthrough.

The prospective **structural hypothesis** is: selecting the restart switch
using CNF-only degree heterogeneity is beneficial on *previously untested*
Random-3SAT instances near clause/variable ratio 4.23. Specifically:

* Input: n=200/220/240 and m=round(4.23*n), randomly generated 3-CNF.
* Frozen features: degree coefficient of variation
  CV = stddev(variable occurrence count)/mean(variable occurrence count),
  and Gini coefficient on variable occurrence count.
* **Frozen selective rule:** if CV >= 0.285 AND Gini >= 0.158, route to
  DRNAS_V177_MODE=switch2048 (restart interval 25); otherwise use
  DRNAS_V177_MODE=r5_monitor. This occurs **before** solving any CNF.
* Four other paired policies: patched Kissat passive monitor, forced switch
  on all cases, pinned original Kissat, and unchanged stable DRNAS V15.3.1.
* All patched Kissat modes use identical source, executable and
  preprocessing. The V15.3.1 and original Kissat are reference
  implementations, **not** causal controls for the in-process policy.

## Provenance and controls
The thresholds were chosen after inspecting R7 development data, hence R7 is
NOT a blinded proof. The old R7 exploratory structural split had 36/120 cases
selected (14 >3% gains, 8 >3% regressions), vs 84 unselected
(26 >3% gains, 25 >3% regressions). These are weak, mixed indicators.

R10 uses deterministic seed stream 221100000+n*10000+i with distinct
development and **reserved test** seeds; **no outcome-based prescreening**.
We freeze all formulas, gate, source and historical SHA-256 registry before
benchmarking. The registry contains 1,226 formula identities from earlier
cumulative SQLite and historical generator snapshot; it may not include every
public formula in existence. New formulas are therefore "prospectively
generated and non-overlapping with the frozen registry," NOT an official
blind competition benchmark.

120 formulas total: 40 per n, half in development and half in reserved test.
Each formula receives 5 policy comparisons x 3 interleaved, reproducibly
shuffled repeated measurements, on the same runner; 1,800 total attempts
(12 shards x 150). Cap 12s; PAR-2 timeout penalty 24s. Every category uses
its own runner; compare paired policies **within** each shard, never assume
between-runner hardware equality. Preserve raw CSV, trace JSONL, manifest,
source revision, Git commit, runner, seed, formula and binary hashes.

## Prespecified analysis / falsification
1. Validate full 1,800-attempt matrix, matching source/formula SHA, runner,
   and status across modes; reject invalid SAT witnesses.
2. Compare 3-repeat *formula-level* PAR-2 and runner-matched group PAR-2;
   report policy activation, >3% winners/losers and severe regressions.
3. Report entire development and reserved-test sets separately. Analyze
   structure CV / Gini vs signed log2 speedup; include scatter plots.
4. Form uncertainty intervals by **resampling formulas within n strata**,
   retaining all repeats together; do not treat 3 attempts as 3 independent CNFs.
5. Evidence for limited conditional usefulness would require enough eligible
   independent test formulas (>=15), positive total test gain, a 95% formula-level
   bootstrap CI excluding zero, no serious unacceptable correctness regressions,
   and an independent repeat on a distinct problem family. If these fail, report
   negative or inconclusive result — NOT a discovered universal law.
6. Larger/selective gains must be confirmed against regressions and
   measurement noise. R7/R8/R9 old outcomes can inform the **hypothesis**
   but cannot be reused as proof of R10 validation.

## Documentation gate
Only if a validation criterion is actually met, write an empirical findings
document naming its domain and limitations, hashes, runner, seed, correctness,
PAR-2, confidence intervals, and negative controls. Do not promote a
universal theorem or world record from generated formulas.

The stable V15.3.1 C++ code and Kissat baseline SHA are immutable.
