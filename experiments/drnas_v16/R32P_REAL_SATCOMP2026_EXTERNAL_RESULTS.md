# DRNAS R32p — first real SAT Competition 2026 external test

**Date:** 2026-11-03  
**Completed run:** https://github.com/Frane12/AndroidGameTest/actions/runs/41656883104  
**FINAL source-audited data, all 48 attempts:** https://github.com/Frane12/AndroidGameTest/actions/runs/41656883104/artifacts/13239359763  
**Frozen originals and manifest:** https://github.com/Frane12/AndroidGameTest/actions/runs/41656883104/artifacts/13240166954  
**Official source list:** https://satcompetition.github.io/2026/downloads/track_main_2026.uri

### Protocol

Original 400-GBD-URI Main 2026 list from SAT Competition. Fourteen
precommitted index/hash pairs were locked before measuring anything.
Eight original compressed official instances were fetched and verified
via exact SHA256 original DIMACS; six were size-excluded (rather than
cherry-picked by solving time). Max compressed 28MiB, max source 56MiB.
**All 14 candidates, 8 successes, 6 rejection reasons are stored** in
the frozen manifest and final report.

Compare a single pinned unmodified Kissat
`8af8e56f174b778aef3aa45af9f739b2a5f492c2` with the same
underlying Kissat instrumentation in passive OFF and R32n GF2-FULL modes.
Two random-ordered paired repeats per source, 60s cap and 120s PAR2
penalty for timeout, 4 separate GitHub Actions runners/shards.
Each individual attempt uses **one solver process**; no watchdog/portfolio
or communication. SAT output checked against *unchanged original CNF*.
UNSAT not independently LRAT proof certified. All six Actions jobs and
source/binary checksum audit PASS.

### Complete R32p results

| Mode | Solved distinct official CNFs | Solved attempts | Timeout attempts | Sum PAR2 seconds | Actual sound GF2 root injections |
|---|---:|---:|---:|---:|---:|
| Clean Kissat | 2/8 | 4/16 | 12/16 | 1527.075492 | 0 |
| Native OFF | 2/8 | 4/16 | 12/16 | 1526.613456 | 0 |
| DRNAS GF2 FULL | 2/8 | 4/16 | 12/16 | 1526.454830 | **0** |

**NO demonstrated solver acceleration.** None of the eight real
competition CNFs caused GF2 to inject one literal, so small observed
time differences are noncausal measurement/instrumentation variation.
Do not calculate a purported DRNAS speedup from these totals.

| Official GBD source | Variables | Clauses | Clean median s | Native OFF median s | DRNAS full median s | GF2 injected |
|---|---:|---:|---:|---:|---:|---:|
| `0e068956...` | 380 | 432291 | TIMEOUT 60 | TIMEOUT 60 | TIMEOUT 60 | 0 |
| `2b7e8634...` | 248213 | 803227 | 19.5472 | 19.4457 | 19.4392 | 0 |
| `75429ff7...` | 250 | 1000 | TIMEOUT 60 | TIMEOUT 60 | TIMEOUT 60 | 0 |
| `860788f9...` | 510 | 19652 | TIMEOUT 60 | TIMEOUT 60 | TIMEOUT 60 | 0 |
| `991aec61...` | 2776 | 9092 | TIMEOUT 60 | TIMEOUT 60 | TIMEOUT 60 | 0 |
| `aa0eadb6...` | 9612 | 210064 | TIMEOUT 60 | TIMEOUT 60 | TIMEOUT 60 | 0 |
| `ba14be20...` | 83188 | 1909831 | 23.9905 | 23.8610 | 23.7882 | 0 |
| `fd1e0ce3...` | 441 | 627443 | TIMEOUT 60 | TIMEOUT 60 | TIMEOUT 60 | 0 |

Tables mark timeouts as `60` elapsed, never confuse them with
the `PAR2=120s` penalty. Sources are real official 2026 original,
not user-generated synthetic cases; the sample is explicitly
limited by predefined size caps and non-exhaustive prior-use checking.
It is **not** a SAT Competition leaderboard or equivalent hardware.

### Important boundary: 250-source-XOR example

`75429ff7acb5acb597abe01aa745c2a6` has exactly 250 variables,
1000 clauses, and native R32n reported 250 algebraically derived
root literals, but the unit-safety gate imposes
`gap.extra <= 12`. The intervention correctly abstained. This is
one genuine official original with extensive XOR structure for which
the mathematical technique is promising but the *current*
engineering constraints make it inert.

As a **separate previously analyzed diagnostic**, the historical
DRNAS R28 complete-XOR Gaussian-elimination solver independently
returned a satisfying 250-variable assignment for this same
official input; all 1000 untouched original source clauses were
checked and passed. That diagnostic was initially executed on
a separate local host, so do not infer same-host acceleration.
A new fixed-source same-host R32q control was launched separately;
it must be labeled diagnostic, not a blind official holdout.

### What should change before another real benchmark

1. Add a rigorous original-source-certified partial-unit selection
   or a bounded native complete-XOR solver that supports hundreds
   of sound consequences, without silently relaxing correctness.
2. Evaluate with **one solver** and original-CNF SAT witness checks
   on prospective *new* external official sources; monitor both
   recognition coverage and cost, not only solver wall time.
3. Compare against established parity-aware competition solvers
   (CryptoMiniSat / modern Kissat) and use same hard timeout/CNFs.
4. No P=NP or breakthrough ranking claim from this restricted benchmark.
