# MATH5 proof I/O: binary DRAT by default

The existing writer emits every learned clause as decimal text. It already buffers output and only flushes on completion; there is no per-clause flush. This experiment changes serialization only: standard binary DRAT additions (`a`, variable-length encoded literals, zero terminator). Every proof-clause emission and final empty clause are retained. The format is accepted by the existing pinned drat-trim. No arbitrary proof-clause skipping or deduplication is introduced.

The current GENERAL100 run and main are unchanged. The canonical `build/drnas-math5` and `build/drnas-math5-proofio` now default to binary DRAT with ordinary `--proof FILE`. No extra flag is needed. `--proof-text` explicitly selects text for diagnostic comparisons; `--proof-binary` remains an accepted compatibility flag. `research/math5/build.py` is the canonical build entry point. GENERAL100 preparation on this branch rebuilds the candidate, verifies its default binary proof and freezes new hashes before measuring. Historical commit reruns intentionally retain their historical format. The archived audit below measured the preceding opt-in commit 9be261e397b1f2373d9695ccfc21fb99b3b0faa1. Both audit arms used the same executable, with identical MATH5 settings and 750 ms math budget. The default change passed all 129 correctness executions again, with BINARY deliberately omitting any format flag, and passed the new preparation guard. Original MATH5 is also compared in controls.

## Validation

43 controls, 129 executions: 63 verified SAT models and 66 independently DRAT-verified UNSAT proofs. All 43 control proof sequences match exactly across original MATH5, candidate text, and candidate binary. Tests cover signed and multi-byte literals; a forged empty-clause proof on SAT is rejected. On four solved real formulas, independently converting the entire text trace to binary yields the identical SHA-256 of the binary trace. This includes all 206,281 learned clauses and 22,654,068 literals of FRB #82. These real formulas are SAT, so those intermediate traces are compared for equivalence, not claimed as UNSAT proofs.

## Local paired diagnostic

Seven previously seen original SAT2024 formulas; three timing repetitions, one pinned logical CPU, sequential arms in alternating order. This small local diagnostic is not a new blind or complete GENERAL100 performance result. Parsing/checking are included in E2E time. #2, #12, #26 use a 3 s total cap; others use 10 s. No new solved sources: both variants solve the same four sources and timeout on the remaining three.

| Source ID | Text MB | Binary MB | Fewer bytes | Text median E2E s | Binary median E2E s | Accepted per arm |
|---|---:|---:|---:|---:|---:|---:|
| 11 | 1.273 | 0.523 | 58.92% | 0.4853 | 0.4966 | 3/3 |
| 62 | 0.607 | 0.288 | 52.55% | 0.3860 | 0.3911 | 3/3 |
| 64 | 0.090 | 0.045 | 50.24% | 0.1054 | 0.1101 | 3/3 |
| 82 | 88.105 | 44.324 | 49.69% | 7.0741 | 5.9067 | 3/3 |
| 2 | 23.743 | 10.258 | 56.80% | 3.0021 | 3.0018 | 0/3 |
| 12 | 37.694 | 19.178 | 49.12% | 3.0018 | 3.0018 | 0/3 |
| 26 | 48.239 | 23.430 | 51.43% | 3.0032 | 3.0028 | 0/3 |

FRB #82 median E2E falls from 7.0741 s to 5.9067 s (16.50% lower). Smaller solved cases show no timing benefit in this sample (binary is slightly slower); do not claim a universal speedup. Timeout proof sizes reflect work generated within the same 3 s cap, not identical completed traces. For source #26, both variants still time out.

## Reproduce

Restore GENERAL100 inputs from run 43697540723 and the pinned drat-trim executable. Run from the repository root:

```sh
python3 research/math5/build.py
python3 research/math5_proofio/check.py selftest
python3 research/math5_proofio/check.py audit --sources /absolute/path/to/math5_general_inputs
python3 research/math5_proofio/compare.py
```

The audit refuses to overwrite its existing scratch results directory. `audit.json` preserves measurements, commands, input identities, binary/checker hashes, compiler, and real trace equivalence checks. Complete verified proof scratch remains in the local audit directory; only incomplete timeout proof scratch is removed by the existing measurement harness. No additional Actions benchmark was launched.
