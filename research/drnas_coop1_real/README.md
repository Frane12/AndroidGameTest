# COOP1: original application XOR diagnostic

This tests the unchanged COOP1 build on original SAT Competition 2024 CNFs. It does not train a persistent model, alter the frozen solver, relax correctness checks, or promote a new default.

## Application and scope

- Simon: reduced-round cipher encodings with AND/XOR gates, selected by source filename for rounds 16 through 21. They are real application encodings, but deliberately simplified benchmarks, not full-strength cryptanalysis or production traces.
- Four frozen large controls: two Ascon hashes, MD5 and AES-related straight-line-program synthesis. All exceed the existing COOP1 size limits. They show fallback behavior, not active cooperation performance.
- This is a development diagnostic. Some inputs were already used by the project; none are claimed as blind holdout.
- Official archive: https://zenodo.org/records/15095752 . Benchmark descriptions: https://satcompetition.github.io/2024/ .

## Frozen selection and protocol

All original archive members matching `simon-r(16..21)-*.sanitized.cnf.xz` are selected without looking at solver outcomes. Raw decompressed CNF bytes are preserved and SHA256 recorded before any benchmark solving. Four controls have additional prior SHA256 checks. A structural audit counts complete explicit width-2/3/4 parity encodings; it is not a complete XOR detector and is never supplied to a solver.

Active Simon cohort: 5-second solver wall cap, 3 repetitions. Large inactive controls: 1-second cap, 1 repetition; report separately and never pool their PAR2 with the active cohort. Native same-binary COOP_OFF vs COOP_ALGEBRA is the primary ablation. Frozen X5_NO_MIN, Kissat, CaDiCaL and CryptoMiniSat are controls. All modes retain ordinary CDCL clause learning. Processes are fresh, serialized and pinned to one allowed logical CPU. CryptoMiniSat also receives `--threads=1`. Within each paired case/repetition, arm execution order is deterministically shuffled.

All configurations emit proofs. A checked SAT and nontrivial UNSAT preflight validates each solver's invocation and proof format before the real test. Every reported SAT is independently checked against the original clauses, and every reported UNSAT must pass drat-trim (DRAT) or FRAT-rs elaboration and LRAT checking (FRAT from newer CryptoMiniSat versions). Solver errors and invalid models/proofs fail the run. Checker timeout counts as unverified, never solved. No inference of UNSAT from timeout.

PAR2 is the sum of solver end-to-end times (startup, input, solving and proof emission), with 2×cap for unknown, unverified or over-cap outcomes. Independent checking time is retained separately. Hashes, commands, raw output, proofs, original CNFs, RSS, CPU time and COOP1 telemetry are retained in the CI artifact. This is a proof-producing comparison, not a no-proof competition configuration.

## Initial local result

The two previously downloaded Simon originals were tested for five repetitions per arm, 30 measured trials total. Every trial produced an independently verified SAT model. Average solver wall times:

| Arm | Verified | Average ms |
|---|---:|---:|
| X5_NO_MIN | 10/10 | 9.429 |
| COOP_OFF | 10/10 | 10.486 |
| COOP_ALGEBRA | 10/10 | 27.033 |

COOP_ALGEBRA took 2.578× the COOP_OFF time on this small local subset. It generated 252 proved clauses across the ten runs, but the baseline already solved these inputs with zero conflicts. Thus the synthetic gain does not transfer to these two easy application instances; analysis/proof work is overhead here. Millisecond timings and two correlated instances do not justify a broad statistical or industrial conclusion. Full local JSON records are in `results/`.

## Reproduce

Build unchanged binaries using `research/drnas_coop1/build.py` and the accompanying workflow. Then:

```sh
python research/drnas_coop1_real/benchmark.py --cap 5 --repeats 3
```

The GitHub workflow `.github/workflows/drnas-coop1-real-xor.yml` installs the archive reader and reference solvers, records versions, then runs the protocol. An already downloaded original input directory with `manifest.json` and `<sha256>.cnf` files can be used with `--local-inputs DIR --native-only`; this is explicitly marked a local subset. An output directory must not already exist.
