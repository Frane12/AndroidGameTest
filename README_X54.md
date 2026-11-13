# DRNAS X5.4 — watched-literal scan cursor / X5.3 proof-size audit

This is an **isolated research branch**. No change to `main`, no APK, and no solver promotion.

## Findings from the complete X5.3 REAL36 investigation

Original run: https://github.com/Frane12/AndroidGameTest/actions/runs/43399730112

The last report failed because 26 complete paired executions on 3 original
SAT2024 CNFs hit `RLIMIT_FSIZE=128 MiB`: subprocess return code 153
(SIGXFSZ forwarded by /usr/bin/time), and each proof file had precisely
134,217,728 bytes. This is **proof I/O resource censoring**, not a demonstrated
wrong SAT or UNSAT answer. All such attempts remain unaccepted with PAR2=16s.

A separate immutable-evidence salvage report was generated in workflow
`prior_x53_evidence`; **no original trial was changed in place**.

| Solver | Verified /72 | PAR2 (s) | Proof-cap attempts |
|---|---:|---:|---:|
| CaDiCaL | 26 | 743.708674 | 4 |
| Kissat | 26 | 746.161883 | 0 |
| X5.2 BASE | 24 | 770.983827 | 6 |
| X5.3 BASE | 24 | 771.179828 | 6 |
| X5.3 GLUE | 24 | 770.212679 | 6 |
| X5.3 UTILITY | 24 | 770.287490 | 4 |

X5.3 GLUE vs X5.3 BASE total ΔPAR2 = -0.967149 seconds;
source-cluster bootstrap95: [-3.002609, +0.069245] seconds (not
statistically established). UTILITY's interval also overlaps zero.

### X5.3 telemetry audit

Cumulative observed counters are **not direct elapsed times** and timed-out
trials have censored snapshots. The following figures compare similarly
instrumented X5.3 policies on the same frozen formulas:

| Counter | BASE | GLUE | UTILITY |
|---|---:|---:|---:|
| Watched entries inspected | 4,989,507,053 | 5,539,247,130 | 7,080,323,879 |
| Long-clause literals inspected | 8,273,674,309 | 6,594,455,435 | 12,215,074,349 |
| Blocker hits | 2,529,556,680 | 2,955,964,618 | 4,181,675,715 |

UTILITY scans ~42% more watch entries and ~48% more long-clause literals
than BASE in the censored telemetry, despite preserving more clauses.
This is consistent with extra BCP work being an important tradeoff.
It does **not** prove that the chosen change will improve runtime.

The former X53 `deleted_used`/ `live_used` metric was misleading: the
mandatory initial asserting enqueue of every learned clause counted as
"use". X5.4 adds `x54_true_reuse`, `x54_deleted_never_reused`,
and `x54_deleted_reused` which **exclude the initial asserting enqueue**.
Those count subsequent reason/analysis/conflict appearances, not causal
runtime savings.

## X5.4 controlled BCP change

A learned clause's nonwatched literals used to be searched in the fixed
order `2..N-1` on every watched-list visit. The new option
`--x54-rotate-watches` saves a small per-clause scan cursor and searches
cyclically through **all** nonwatched literals before concluding a unit
propagation or conflict.

In a circular scan, reaching end of the literal array wraps to literal 2.
No literal is skipped and watcher invariants, proof output, learned-clause
deletion policy, restart policy, and 1-UIP analysis remain unchanged.

Frozen comparison:

- `X53_BASE`: unchanged original X5.3 binary.
- `X54_CONTROL`: new X5.4 binary with rotation **off** and additional
  correctness/utility counters.
- `X54_ROTATE`: same X5.4 binary with rotation **on**.
- Kissat and CaDiCaL frozen references.

All variants run on identical original REAL36 SHA-frozen CNFs
(36 sources × 2 repeats = 72 attempts per arm), an 8s solver wall budget,
512 MiB proof-size budget and source-paired comparisons. Independent SAT
witness and UNSAT DRAT certification are required. If the new proof cap is
hit, the result is explicitly `PROOF_SIZE_LIMIT` (unaccepted, PAR2=16s),
never a false solver correctness failure.

The preliminary smoke test ran 90 small formulas with a brute-force oracle
(55 SAT + 35 UNSAT), 270 executions and 105 independent DRAT checks.
The X54 control reproduced the X53 search counters; rotation was activated
255 times. These tests validate basic correctness and exercise the branch,
but do not certify arbitrary input behavior.

**Promotion rule:** no promotion until a separate, truly new family-held-out
original SAT benchmark demonstrates verified PAR2 benefit with acceptable
memory/proof overhead and no wrong SAT/UNSAT.

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/43402461614
