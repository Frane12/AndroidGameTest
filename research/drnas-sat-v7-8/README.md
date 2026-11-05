# DRNAS SAT v7.8: preserve v7.6 performance on official SAT Competition 2026 input

**Live run**: https://github.com/Frane12/AndroidGameTest/actions/runs/41212492468

## Verified original regression

Exact SAT Competition 2026 GBD instance:
`4ae685a11b5cecca76dc3d463481ce92`
Original downloaded CNF SHA256:
`16b09f959320357facb6345950ba5e6528299fc488c07e99f084446148755158`

The completed frozen main comparison ([run 41208564932](https://github.com/Frane12/AndroidGameTest/actions/runs/41208564932),
shard 4, from unchanged CaDiCaL 3.0.1 and DRNAS v7.7 code) recorded:

| Mode | Repeat 0 | Repeat 1 | Final status |
|---|---:|---:|---|
| v7.6 `adaptive_guided` | **1.7448 s** | **1.7284 s** | SAT |
| v7.7 `quality_guided` | 20.5516 s | 20.7032 s | SAT |
| v7.7 `quality_plain` | 43.9096 s | 44.1615 s | SAT |
| v7.7 `quality_random` | 15.8488 s | TIMEOUT (60 s) | SAT or timeout |
| CaDiCaL `plain` | TIMEOUT | TIMEOUT | No answer in 60 s |
| Kissat 4.0.4 | TIMEOUT | TIMEOUT | No answer in 60 s |

This means a roughly 11.9-fold **local per-instance** speed ratio of
v7.6 over v7.7, **not** a general claim about all SAT benchmarks. The
same 20 official instances are previously examined and not a clean blind
holdout. No UNSAT certificate is required for the selected SAT case;
the native code checks each returned SAT assignment.

## Original files remain frozen

- `research/drnas-sat-v7-6/v76_single.cpp` original Git **blob**
  `a254356a45b70f02f33b9506f1122dad33916ca7`.
- `research/drnas-sat-v7-7/v77_single.cpp` original Git **blob**
  `1bbb7fa035e62d5179de9243f672aed9bb9cbaca`.

Both original functions are included and executed without modification
in `v78_causal_probe.cpp` through
`run76(f, "adaptive_guided", seed)` and
`solve77(f, "quality_guided", seed)`.
The benchmark logs source SHA256 and original CaDiCaL Git revision for
auditability.

## Hypotheses isolated with predeclared experiments

1. **Different gate**: v7.6 extends after the first 256 conflicts when
   `max(0, redundant_256 - redundant_pre) >= max(48,ceil(active_pre/4))`
   and `active_256 > 0`. The optional extension runs for a maximum of
   768 more conflicts, then phases are removed. One *same* solver
   preserves its learned clauses.
2. **Different measurement**: v7.7 installs a
   `CaDiCaL::Learner` observer which captures the sizes of clauses
   offered for external export. This is not an LBD statistic, nor
   necessarily the full internal learned clause set.
3. **Different gate**: v7.7 instead extends only if it observed
   `>=32` export offers, `>=10` at length `<=5`, and at least 20%
   length `<=5`.
4. **Change to search trajectory**: the observer itself or the
   decision to keep polarity hints 768 conflicts longer might alter
   the resulting search path much more than the negligible C++ observer
   bookkeeping overhead.

The frozen `orig_v76` / `orig_v77` trials establish that the original
regression reproduces with same code, flags, input hash and seeds. The
six *experimental controls* isolate the two switches:

| Diagnostic mode | Same gate as | Learner callback |
|---|---|---|
| `old_gate_with_observer` | v7.6 | ON |
| `new_gate_with_observer` | v7.7 | ON |
| `force_extend_with_observer` | forced 768 | ON |
| `force_stop_with_observer` | forced stop at 256 | ON |
| `force_extend_no_observer` | forced 768 | OFF |
| `force_stop_no_observer` | forced stop at 256 | OFF |

Every control uses the **same unchanged CaDiCaL 3.0.1, same untouched
helper `add_phase_hints`, same per-repeat seed, same original CNF
SHA256** and no rebuild or learned-clause loss between stages.
All output contains the 256-conflict learning statistics, original
length-5 learner offers when enabled, extension choices, per-stage times,
SAT validity and total elapsed time.

The exact original seed from the v7.7 comparative experiment is
`(7707000 + 527 * repeat + int(GBD_ID[:8],16)) % 2**32`.
We rerun the first two original seeds and one extra repetition on the
known regression instance. An easy official CNF
`0c9da400944b002f90fd385d4fdab385` is a **separate negative
control** to establish whether a change is specific to the selected
hard problem; control results are *not pooled* with the winning case.

The diagnosis **must not** assert which change caused the difference
until the A/B contrasts confirm it. In particular a good result for
`force_extend` does not establish that clause shortness is
informative. Three repeats on a selected case are not a statistical
population estimate.

## Exit criteria and preservation rule

- Require original v7.6 to reproduce SAT for both benchmark seeds.
- Require all diagnostic SAT results to pass the original
  `check_sat_model` validation.
- Preserve the untouched v7.6 source / original public behavior
  throughout the investigation, and publish C++ probe changes only
  in the separate research branch.
- If altering the learner callback changes behavior, measure that
  separately from gate policy; do not infer a cause from one timing.
- Future v7.8 selector should be gated behind an opt-in flag, run on
  independent holdout cases, and automatically fall back to v7.6 if
  no validated improvement is shown. **No global claim of a general
  12x improvement**.

The actual measured results and all raw control rows live in the CI
artifacts; this protocol intentionally does not contain a fabricated
mechanism verdict.
