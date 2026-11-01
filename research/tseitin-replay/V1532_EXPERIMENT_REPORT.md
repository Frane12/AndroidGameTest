# DRNAS SAT V15.3.2 prefix-gate experiment — 2026-11-01

## Decision: DO NOT replace V15.3.1 No-Hang

This experimental branch derives directly from `experiment/drnas-v153-base-nohang-v1531-20261101`, which itself preserves the V15.3 Unified core. V15.3.2 adds a bounded 128-clause / 64-KiB prefix scan before full DIMACS parse and sends formulas judged nonstructural directly to the same pinned Kissat. Every SAT/UNSAT answer still originates in the unchanged V15.3 structural proof routes or Kissat; prefix classification is never a proof.

Two successful GitHub Actions runs on Ubuntu 24.04, pinned Kissat commit `8af8e56f174b778aef3aa45af9f739b2a5f492c2`:

- External 72 + structural audit: https://github.com/Frane12/AndroidGameTest/actions/runs/41280480050
- External long DIMACS and independent controls: https://github.com/Frane12/AndroidGameTest/actions/runs/41280510026

### Sums of per-case median wall times (seconds)

| Benchmark | Cases | Repeats | V15.3.1 | V15.3.2 | Kissat | V15.3.2 change vs V15.3.1 |
|---|---:|---:|---:|---:|---:|---:|
| Fresh SATLIB H: uf33-48, uuf33-48, flat33-48, AIM100/AIM200  | 72 | 5 | 0.438780 | 0.441414 | 0.335492 | 0.60% slower |
| Structural development (14 families) | 168 | 5 | 0.217697 | 0.225417 | 0.234209 | 3.55% slower |
| Constructed mixed XOR and unit | 96 | 3 | 0.130834 | 0.137820 | 0.136685 | 5.34% slower |
| Third-party controls | 16 | 3 | 0.208810 | 0.205234 | 0.186807 | 1.71% faster |
| Original DIMACS hole6..hole10 Hall UNSAT | 5 | 3 | 0.007044 | 0.007453 | 1.676277 | 5.81% slower |
| Adversarial anti-hang stress | 8 | 3 | 0.040430 | 0.037241 | 0.018275 | 7.89% faster |

All test cases were solved correctly; SAT witnesses checked against original CNF and structural UNSAT certificates independently replayed. There were no observed timeouts on these suites. This does not establish absence of hangs generally.

**SATLIB H is a newly frozen set relative to prior F/G subsets**, but not an official SAT Competition blind test. The 72-case run confirmed 72/72 correct for all solvers, five repetitions; the V15.3.2 prefix shortcut fired only **60/360** V15.3.2 calls. Its overhead outweighed the savings.

The original DIMACS five-formula Hall sub-class still runs around **225x faster than pinned Kissat** on this particular suite, not general SAT.

### Interpretation and next step

A second prefix parse is often redundant and adds latency to every structural case. Therefore **retain V15.3.1 as stable default** and do not merge V15.3.2. Prefer a truly single-pass fused parser+structural signature or pinned **in-process Kissat C API** fallback that does not repeatedly launch a solver, with exact proof/model checks. Test on fresh official SAT Competition inputs and a new, pre-frozen, untouched holdout before claiming out-of-sample acceleration.
