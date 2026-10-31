# DRNAS NP v0.8 — Native C++ NeuroFlow + embedded CaDiCaL

This experimental release removes the Python controller from the timed SAT path.

## Key design

**One compiled C++ executable**, `drnas_nf08`. Uses `<cadical.hpp>` and
the `libcadical-dev` **in-process CaDiCaL library** (Ubuntu 24.04 package
1.7.4). There is no `subprocess.run(cadical)` and no Python DIMACS parse in
the solver.

Both baseline and adaptive modes parse the **same source DIMACS in the same
C++ parser**, feed the same clauses to the **same CaDiCaL::Solver** C++ class
for normal CDCL solving, and check SAT models against the original clauses.
Adaptive adds cheap counts during that parse, before deciding whether the
Horn proof machinery is justified.

The following exact alternatives are used:

- `base`: parse once, add clauses to `CaDiCaL::Solver`, solve and verify.
- `neuro`: parse once and measure signed-literal counts. Apply fixed v0.6.2
  thresholds, test majority-flip Horn defect only on screened candidates;
  if exact Horn, solve with linear-time Horn forward chaining; otherwise
  attempt a **bounded exact 2-SAT renamable-Horn test** (at most 200k
  literal pairs and 12ms); if it fails, use the same CaDiCaL backend.
- `force`: always attempt exact Horn recognition before fallback. This is
  a *diagnostic* control, not a recommended general-purpose setting.

All Horn witnesses are converted to original polarity and independently
checked against the unmodified CNF. The 2-SAT implications represent
constraints preventing two literals in the same clause from both becoming
positive under variable renaming. The 2-SAT procedure returns a valid
assignment only after checking that all transformed clauses really are Horn.

**This is in-process integration with CaDiCaL's public C++ API**, NOT yet a
patch to CaDiCaL's upstream internal source tree. Future work could insert
the screen into CaDiCaL's built-in DIMACS parser, but that requires careful
upstream/ABI design and is not claimed here.

## Reproducibility

```bash
sudo apt install g++ libcadical-dev cryptominisat
cd DRNAS_NP_Crypto_Benchmark
g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
    native_v08/drnas_nf08.cpp -lcadical -lz -pthread -o native_v08/drnas_nf08

./native_v08/drnas_nf08 --input path/to/sample.cnf --mode base
./native_v08/drnas_nf08 --input path/to/sample.cnf --mode neuro
./native_v08/drnas_nf08 --input path/to/sample.cnf --mode force
```

Machine-readable stdout contains `status`, `route`, `parse_ms`,
`gate_ms`, `probe_ms`, `solver_ms`, `total_ms`,
`witness_valid`. Stderr is reserved for errors. Real time includes
file parsing and native CDCL setup/solving. Process startup is measured
separately by Python benchmark harness, which only orchestrates
subprocesses but **is not part of the SAT timed path**.

The CI run verifies 280 exhaustive small CNFs × 3 solver modes, 30
independently generated renamable-Horn SAT examples, and then
runs 96 paired benchmarks with 3 repetitions for each mode.
Status checks use independent CryptoMiniSat; cases that timeout and
reference unknowns are included in coverage counts and not mislabeled
as wins. The 60 externally authored CNFs were used in previous studies:
they are **a regression benchmark, not a new blind holdout**.
36 newly seeded synthetic controls are separately reported.

### Interpretation rule

Demonstrate an *end-to-end* gain on previously unseen, real external CNFs
against the same library, not only on our own renamable-Horn controls.
Never infer a P vs NP breakthrough or general SAT speedup from synthetic
results. The frozen routing policy remains fixed before benchmark.

### Follow-up design

For a true long-term Android native module, compile this C++ solver with
an Android NDK ARM64 toolchain and separately validate the CaDiCaL
ARM64 build and licenses. This research build currently targets
Linux x86_64 GitHub Actions.
