# DRNAS NP v0.9 — native decision-phase hints for CaDiCaL

**Experiment status:** C++ compile and exhaustive correctness regression passed; main
paired timing workflow: https://github.com/Frane12/AndroidGameTest/actions/runs/41199540301

## What actually changed

This is an in-process C++ experiment with Ubuntu 24.04 `libcadical-dev`.
The original v0.8 single-parse DIMACS / exact Horn recognition / CDCL fallback
is preserved. The new ingredient is the documented public
`CaDiCaL::Solver::phase(int lit)` API, which biases a **decision polarity**
inside CaDiCaL. It is **not an assumption**, **not a unit clause**, **not a
proof of satisfiability**, and it does not alter the CNF.

All candidates receive exactly the same original DIMACS and are solved
using the same `CaDiCaL::Solver` class. Timings include the full native
parser, feature counting, `phase()` calls, actual solver work and SAT
witness verification. The controlled experiment compares these frozen
strategies (not trained on the benchmark):

- `base`: plain CaDiCaL without phase hints;
- `phase-majority`: phase all used variables toward their majority
  sign in the original CNF;
- `phase-minority`: phase all used variables toward their minority sign;
- `phase-selective`: phase only used variables with at least eight
  occurrences and an absolute signed imbalance >=60%, toward their
  majority sign;
- `neuro`: existing frozen v0.8 exact Horn recognition, CaDiCaL fallback;
- `neuro-phase`: identical Horn recognition, but apply selective hints on
  any CaDiCaL fallback.

`force` remains implemented for correctness diagnostics only.

For every solver result, every SAT assignment is checked against the
*original* formula. An independent CryptoMiniSat reference establishes
the expected SAT/UNSAT status where it finishes. Unsolved/time-limited
formulas remain in the report's completion counts; timing means and
medians use only matched completed, reference-confirmed solves.

## Protocol and limitations

- Reproducible GitHub Actions job, native g++ with `-O2`, same
  `libcadical` binary for every arm; 240 tiny exhaustive CNFs × 7
  native modes = 1680 tested status/model combinations, plus explicit
  contradictory formulas.
- 60 previously published and previously tested third-party CNFs from
  Tractables/cnfs and Byt-Wyze SAT library; this is a **regression/test
  corpus**, not a new untouched holdout.
- 36 new, separately labelled constructed Horn and near-Horn examples,
  never pooled as proof of general-purpose performance.
- Three order-rotated repeats per case and mode; phase count and
  phase-initialization time recorded separately.
- Phase-selection thresholds are **fixed before testing**; the different
  phase variants constitute a hypothesis comparison. Selecting the
  best post-hoc winner and claiming unseen generalization would be
  invalid. A winning strategy would require an independent later holdout.
- Small tasks may be dominated by parsing and solver initialization
  noise; look at paired distributions and consistency per source
  family, not just differences of pooled medians.

## Native build

```sh
sudo apt install g++ libcadical-dev cryptominisat
cd DRNAS_NP_Crypto_Benchmark
g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  native_v09/drnas_nf09.cpp -lcadical -lz -pthread -o native_v09/drnas_nf09

./native_v09/drnas_nf09 --input sample.cnf --mode base
./native_v09/drnas_nf09 --input sample.cnf --mode phase-selective
./native_v09/drnas_nf09 --input sample.cnf --mode neuro-phase
```

This is a Linux native C++ build, not yet an Android ARM64 APK.
