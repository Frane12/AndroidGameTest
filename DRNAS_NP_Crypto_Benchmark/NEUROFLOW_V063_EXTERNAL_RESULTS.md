# DRNAS NeuroFlow v0.6.3 — independently authored external corpora, measured results

**Date:** 2026-10-31. **Run SUCCESS:**
https://github.com/Frane12/AndroidGameTest/actions/runs/41193998983

Raw artifact:
https://github.com/Frane12/AndroidGameTest/actions/runs/41193998983/artifacts/13039724315

## Source provenance

Zero-shot (no external retuning) with v0.6.2 frozen policy from training
on earlier SATLIB and manufactured Horn controls.

Selected before solving and pinned to exact GitHub upstream commits:
- Tractables/cnfs: LGSynth89 logic circuits 12, ISCAS85 hardware 8,
  ISCAS89 hardware 12, feature-model software constraints 12.
- Byt-wyze-technology/sat-instances-library: 16 *third-party synthetic*
  SAT benchmarks (not industrial). Two independent publishing entities,
  five distinct families.

Source URL, original SHA256, canonical DIMACS SHA256, upstream commit
and descriptions are in manifest.csv. All 60 original CNF files
successfully fetched and parsed.

## Independent correctness

CryptoMiniSat resolved 57/60 within 7s: **49 SAT, 8 UNSAT**, and timed out
on 3 hard Byt-Wyze formulas. DRNAS baseline solved 42/57 cases with known
reference results within **0.75 seconds per method** and returned LIMIT for
the other 15. All cases solved by DRNAS were SAT (12 LGSynth89,
12 ISCAS89, 12 FeatureModels, 6 ISCAS85); no incorrect SAT/UNSAT
or invalid SAT model observed. On the 16 Byt-Wyze formulas, Python DPLL
timed out on all 16, while CryptoMiniSat determined 13 with the longer
7s cap. The remaining 2 ISCAS85 problems (c499.isc.cnf and
c1908.isc.cnf) also timed out in DRNAS; CryptoMiniSat solved them.

Independent verification used *identical canonical CNF* for DRNAS and
CryptoMiniSat; CMS process timing is not compared as an in-process speed
baseline.

## Per-source in-process matched performance

Three repetitions per formula, rotating order. Four algorithms:
original DRNAS, frozen adaptive NeuroFlow v0.6.2, forced Horn attempt,
legacy v0.6 (17-feature computation even when disabled).

| Source | selected | CMS known | DRNAS solved | Baseline median ms | NeuroFlow median ms | mean paired gain ms | recognized |
|---|---:|---:|---:|---:|---:|---:|---:|
| LGSynth89 | 12 | 12 | 12 | 5.1906 | 5.2401 | -0.6723 | 0 |
| ISCAS85 | 8 | 8 | 6 | 40.2167 | 42.6299 | -1.1882 | 0 |
| ISCAS89 | 12 | 12 | 12 | 9.1658 | 9.3564 | +0.2156 | 0 |
| FeatureModels | 12 | 12 | 12 | 25.8406 | 24.8114 | -0.1726 | 0 |
| Byt-Wyze | 16 | 13 | 0 | n/a | n/a | n/a | 0 |
| ALL | 60 | 57 | 42 | 19.3590 | 19.5427 | -0.3496 | 0 |

Across 42 independently verified completed case pairs and 3 repeats:
126 comparable samples, 46/126 adaptive wins. Paired median gain
**-0.0672ms**, paired mean gain **-0.3496ms** (negative = slowdown).

The previous target-specific 2.47x Horn speedup did NOT generalize.
The v0.6.2 first-stage selector rejected 57/60 external CNFs and
skipped the remaining 3 at the size gate; no external Horn target
was recognized or accelerated. Force-Horn median 23.6275ms on solved
cases; more expensive than baseline.

## Scientific conclusion / follow-up

- There is no evidence of generic SAT speedup from v0.6.2 on these
  independently existing sources. All benefits on custom renamable
  Horn-SAT controls remain domain-specific.
- General SAT performance is overwhelmingly limited by the
  transparent Python DPLL fallback: 18/60 formulas not solved in
  its 0.75s budget (including three that reference CMS did not solve
  in 7s). No wrong satisfiability claims were observed.
- Next controlled architecture: retain NeuroFlow only for proof-carrying
  preprocessing where a mathematically sound transform is identified
  cheaply; delegate unspecialized CNF to a genuine CDCL backend
  (e.g. CaDiCaL or CryptoMiniSat). Benchmark the SAME backend
  with and without that preprocessing, accounting for detection
  and transformation overhead and complete SAT-model reconstruction.
- Do not claim superiority to CryptoMiniSat from Python in-process
  timing or extrapolate a P vs NP result.

## Biases

The sample is limited by source file size before solving and by
the Python 0.75s cap. FeatureModels SAT interpretation does not
evaluate model counts. Byt-Wyze is synthetic even though independently
authored. CMS timeout/reference failure examples remain visible.
No holdout hyperparameters were retuned.
