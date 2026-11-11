# DRNAS ATLAS3 — opportunity-cost gating for an exact Boolean atlas

**Isolated experimental branch:** `experiment/drnas-atlas3-cost-gate-20261111`. This changes neither stable main nor the frozen ATLAS2 and earlier ARL reference source files.

## Question

Is a cheap source-structural fingerprint sufficient to **avoid opening the full
2–4-variable NPN Boolean atlas** when repeated local Boolean structure is
unlikely to justify its cost? ATLAS2 applies exact, assignment-preserving
reductions to up to 32 disjoint modules; ATLAS3 adds one **read-only,
time-bounded gate** before the identical deep ATLAS2 procedure.

## Implementation

* Scan up to 384 original clauses of length 2–4 only, one pass, and stop at
  a 180 µs screening budget. Use hashed UNSIGNED variable-support
  signatures and binary/3–4-literal subset memberships, independent of
  variable naming, order and literal sign.
* `score = 3 * repeated_support + 2 * binary_nested_in_longer_support`.
  `ATLAS3` invokes ATLAS2 only when `score >= 12`; `ATLAS3_STRICT`
  uses `score >= 32`. These thresholds are **unvalidated heuristics**,
  NOT statistically learned estimates of runtime savings.
* Otherwise return the ORIGINAL CNF unchanged with `decision=sleep`
  and run the original native DRNAS CDCL.
* Even when the gate passes, ATLAS2 must derive an exact 2–4-variable truth
  table for each candidate, reconstruct the permutation/polarity mapped
  NPN formula, and verify ALL local assignments before changing a clause.
  An approximate hash collision can only waste probe time; it cannot make
  an unsound simplification.
* No restart modifications, no parallel portfolio, no clause deletions
  except independently verified locally equivalent substitutions.
* Native `--atlas-selftest` checks all 65,808 Boolean functions with
  2–4 inputs; `research/drnas_atlas3_smoke.py` checks many independent
  positive blocks, a single low-opportunity block, and an unrelated
  negative control. SAT models are checked against original clauses.
  UNSAT lacks independent LRAT proof.

## Benchmark contract

One logical CPU per arm, full end-to-end subprocess wall time inclusive
of preprocessing and process startup. PIN source SHA where available,
original SAT witness verified, UNKNOWN receives PAR2=2*cap; independent
UNSAT proof not claimed.

| Cohort | Purpose | GitHub Actions |
|---|---|---|
| 8 prior ATLAS2 generated AND/OR, XOR, exactly-one and ITE fixtures | Repeatable **regression pilot**, NOT an unseen holdout | [ATLAS3 pilot](https://github.com/Frane12/AndroidGameTest/actions/runs/42936762739) |
| 8 previously untested original public feature-model CNFs, pinned immutable Git blob SHA | **Prospective, independent real structured SAT** | [ATLAS3 features](https://github.com/Frane12/AndroidGameTest/actions/runs/42936821768) |
| 8 new SATLIB `uf100/150/200/250` source-only SHA ranks 16 and 17 | **Prospective negative-opportunity test**, SAT with original-model checks | [ATLAS3 random](https://github.com/Frane12/AndroidGameTest/actions/runs/42937235798) |

## Results (two completed cohorts)

### Previously studied controlled generated structured formulas
Six arms, 8 formulas x 3 repeats = 144 measurements, all verified SAT.

| Arm | Verified SAT | PAR2 seconds |
|---|---:|---:|
| Native A | 24/24 | **0.098975** |
| Kissat | 24/24 | 0.101312 |
| ATLAS3_STRICT | 24/24 | 0.106833 |
| Frozen ATLAS2 | 24/24 | 0.108316 |
| ATLAS3 | 24/24 | 0.109376 |
| CaDiCaL | 24/24 | 0.112648 |

All ATLAS3 variants invoked the deep atlas on all 8 formulas, with
5–16 µs initial gate cost. The baseline is fastest. This is an
expected severe confound of very easy formulas whose runtimes are only
milliseconds, not evidence for algorithmic performance improvement.

### Previously untested real software feature models
Eight SHA-pinned external feature-model CNFs (from
`Tractables/cnfs/feature-models`), 3 rep x 6 arms, 144 measurements;
all original SAT models verified, 24/24 per arm.

| Arm | Verified SAT | PAR2 seconds |
|---|---:|---:|
| Kissat | 24/24 | **0.116387** |
| Native A | 24/24 | 0.123437 |
| Frozen ATLAS2 | 24/24 | 0.136913 |
| ATLAS3 | 24/24 | 0.138058 |
| CaDiCaL | 24/24 | 0.138797 |
| ATLAS3_STRICT | 24/24 | 0.140344 |

All 8 inputs crossed both gates, so ATLAS3 executed identical deep
ATLAS2 simplification: the structural signal is too coarse to estimate
actual downstream CDCL benefit. Per-source accepted modules ranged 1
to 32 and saved literals ranged 2 to 220. High structural score is
**not** evidence of E2E improvement. A screen of 9–19 µs was cheap
but not enough to compensate for the expensive deep NPN pass on these
very easy SAT formulas.

## Conclusions

* The gate is an exact-safety-preserving prefilter, but presently NOT
  validated as cost-benefit prediction.
* It is critical to distinguish **frequent local patterns** from
  **profitable preprocessing**. Block count, saved literal count,
  conflict count, and wall-clock acceleration are different metrics.
* SATLIB ranks 16/17 will test whether the gate can at least
  **avoid the no-op atlas overhead** where clauses have no shared
  small signed-support structure. No result was used to set the
  gate thresholds.
* Future changes should use an independently validated
  expected saving estimate or a very cheap certified direct reduction,
  and remain on a new experiment branch. No performance claim from
  either of the completed two cohorts.
