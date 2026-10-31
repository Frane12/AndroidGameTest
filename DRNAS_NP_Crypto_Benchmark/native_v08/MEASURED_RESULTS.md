# DRNAS NP v0.8 — native C++/libCaDiCaL measured results

**Build:** SUCCESS, `DRNAS NP v0.8 native C++ CaDiCaL` Actions run
https://github.com/Frane12/AndroidGameTest/actions/runs/41198696694

**Raw artifact (incl. compiled Linux native executable, exact original source fingerprints):**
https://github.com/Frane12/AndroidGameTest/actions/runs/41198696694/artifacts/13041812126

## What actually changed

The previous Python controller and `subprocess.run(cadical)` loop have been
removed from the **timed solver implementation**. Both native variants run
the **same C++ binary** using the **same single-pass DIMACS parser**, and
call the **same in-process libCaDiCaL API**. The NeuroFlow variant only adds
signed-literal counts during parsing, frozen v0.6.2 gating, and bounded exact
Horn renaming, backed by 2-SAT or a direct Horn equivalence check. If no
Horn is certified, the original CNF is passed unchanged to CaDiCaL.

We do **NOT** claim an upstream modification to CaDiCaL's private parser
or backend algorithms, and this is NOT an Android APK. It is currently a
native Linux x86_64 research executable linked with Ubuntu 24.04 CaDiCaL
1.7.4 (`libcadical-dev`). Potential Android NDK ARM64 port is future work.

## Quality verification

- C++ compile SUCCESS with `-std=c++17 -O2 -Wall -Wextra -pedantic`.
- 280 random small CNF formulas × 3 solver strategies =
  **840 correctness checks** against exhaustive truth tables.
- Independently generated 30 renamable-Horn SAT formula checks:
  **30/30 recognized** under forced recognition.
- All SAT models verified against original CNF.
- External SAT/UNSAT statuses checked against CryptoMiniSat when
  reference completed. No wrong completed results observed.
- All 60 source-pinned existing external CNFs were fetched successfully.
- Three timed repetitions per solver and CNF.
- 56/60 external cases finished under the native 2000 ms limit in both
  variants; other four remain UNKNOWN. CryptoMiniSat references solved
  57/60, with three reference timeouts.

## Measured results (milliseconds)

Each number is the MEDIAN of paired completed in-process wall timings,
including C++ parse, features, Horn proof and libCaDiCaL setup/solve.

| Source | Cases | Baseline median | Native NeuroFlow median | Mean paired gain | Horn accepted |
|---|---:|---:|---:|---:|---:|
| 60 external files, 56 solved | 60 | 1.01038 | 1.00286 | **-0.14565** | 0 |
| Constructed SAT Horn | 12 | 0.24798 | **0.19620** | +0.04453 | **12/12** |
| Constructed UNSAT Horn | 12 | 0.22169 | 0.22173 | -0.00194 | 0 |
| Constructed near Horn | 12 | 0.30285 | 0.31052 | -0.00714 | 0 |
| All 96 (92 solved) | 96 | 0.46178 | 0.45576 | -0.08403 | 12 |

**Interpretation:**
- On the 12 deliberately Horn-like SAT controls, the native selector
  was faster on 33 of 36 run pairs. Median ratio ~1.26×, and all 12
  cases had a positive *per-case median* gain.
- On real external formulas, 88 of 168 completed pairs are faster with
  NeuroFlow, and the median paired gain is only +0.00172 ms. The
  **mean paired gain is negative (-0.14565ms)** and strongly affected
  by harder third-party SAT cases; this does NOT justify a general
  improvement claim.
- For rejected external formulas, `gate_ms` was on the order of
  microseconds (median ~0.0003 ms); much of the old Python extra scan
  overhead has been eliminated architecturally. Native parsing and
  solver work remain the primary costs.
- In 60 external cases, zero Horn transforms were recognized, so the
  system still lacks a real-world target domain for this optimization.
- Comparing this run's native 1 ms median with old Python 8 ms median
  **would not be a valid controlled speedup factor** because runs,
  environments and instrumentation differ. The valid within-run
  comparison is against the same native binary with the feature switch
  off.

### Per-case exploratory inference

Across 56 completed external formulas, after aggregating the three
repetitions to a median for each formula:
- case-level median gain +0.00082 ms;
- case-level mean gain -0.24140 ms;
- exploratory case-bootstrap 95% intervals: mean [-0.711,+0.026] ms,
  median [-0.0044,+0.0095] ms, each includes zero.
This is supplementary exploratory uncertainty analysis; the experiment
was not designed for strong statistical power.

## Next engineering direction

Keep native v0.8 as a baseline. If pursuing further, introduce **native
phase/polarity hints or proof-preserving preprocessing directly at the
libCaDiCaL C++ API boundary**, testing each against exactly the same
baseline and tracking SAT correctness and full time costs.
Avoid additional Python feature scans or new classifiers until a
real external problem family demonstrates predictive benefit.
