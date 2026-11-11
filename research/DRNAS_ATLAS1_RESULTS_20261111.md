# DRNAS ATLAS1 — Completed prospective benchmark (2026-11-11)

**Run:** https://github.com/Frane12/AndroidGameTest/actions/runs/42932742956
**Branch:** `experiment/drnas-atlas1-boolean-library-20261111`
**Status:** all 4 shards successful. A preceding run was correctly rejected as
a harness error: timed-out processes did not emit ATLAS1 telemetry. The harness
was fixed to score UNKNOWN = PAR2 60 s, rather than assert telemetry.

## Fixed comparison

Four SHA-locked original SATLIB satisfiable random-3SAT CNFs selected solely by
SHA256(family|basename) rank 14; three paired repeated trials per solver and
one logical CPU per solver. 30 s cap, SAT witnesses checked on original CNFs,
timeouts scored 60 s, no independent UNSAT LRAT tested. All E2E elapsed
times include process startup, source scan, and native CDCL.

| Original cohort (one CNF each) | DRNAS A PAR2 / solved | ATLAS1 PAR2 / solved | Kissat PAR2 / solved | CaDiCaL PAR2 / solved |
|---|---|---|---|---|
| uf100-430 | 0.019188 s, 3/3 | 0.019262 s, 3/3 | 0.054303 s, 3/3 | 0.015811 s, 3/3 |
| uf150-645 | 0.091569 s, 3/3 | 0.092429 s, 3/3 | 0.163196 s, 3/3 | 0.067453 s, 3/3 |
| uf200-860 | 0.077637 s, 3/3 | 0.079121 s, 3/3 | 0.115610 s, 3/3 | 0.194220 s, 3/3 |
| uf250-1065 | 117.988419 s, 2/3 | 118.535156 s, 2/3 | 0.151603 s, 3/3 | 2.252063 s, 3/3 |
| **TOTAL** | **118.176813 s, 11/12** | **118.725968 s, 11/12** | **0.484712 s, 12/12** | **2.529547 s, 12/12** |

ATLAS1 routes: **0 commits, 4 sleeps**. No profitable 2–4-input
modules were detected within the bounded local scan on these four
unstructured SATLIB random-3SAT inputs. No verified speedup, and total
PAR2 is slightly worse than A. The much larger PAR2 of both native
variants primarily reflects two SAT times near 30 s and one timeout
on the 250-variable source, not a fault in the atlas rewrite rules.

## Soundness controls

Generator:
* k=2: 16 functions -> 4 NPN classes
* k=3: 256 functions -> 14 NPN classes
* k=4: 65,536 functions -> 222 NPN classes

Native exhaustive C++ verification passed **65,808 / 65,808** truth
tables, including polarity and permutation reconstruction. Synthetic
original-model-verified controls:
* binary resolution: 2 clauses -> 1, save 3 literals (commit);
* four-literal resolution: 2 clauses -> 1, save 5 literals (commit);
* absorption: 2 clauses -> 1, save 2 literals (commit);
* unrelated clauses: abstain (sleep).
All pass, independently of benchmark performance.

## Interpretation / next gate

* A library of mathematically valid small rewrites has been implemented and
  exhaustively checked. No claim of a universally faster solver is supported.
* Random-3SAT is a poor opportunity distribution for frequent small **repeated
  structural blocks**. Future structured cohorts (complete gate encodings,
  parity, cardinality, circuit verification) should be frozen independently
  before testing and compared with the same original-model verification.
* The first release commits only one best module per input and scans a
  maximum of 1,400 original clauses; a source-structural density prefilter
  would reduce the no-op overhead. More reductions or a batch approach must
  be tested prospectively against an unchanged A baseline.
* For the heavy uf250 formula, DRNAS A trials were SAT 29.600765 s,
  SAT 28.387654 s, UNKNOWN 30 s; ATLAS1 SAT 29.067761 s, SAT 29.467395 s,
  UNKNOWN 30 s. Thus no meaningful change in solved count.

Keep ATLAS1 experimental until a structured, original-source benchmark
shows a reproducible benefit in end-to-end PAR2 without proof regressions.
