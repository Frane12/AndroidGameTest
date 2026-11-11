# DRNAS ATLAS-X S3 — subset-support Boolean relation closure, verified holdout

**Date:** 2026-11-11. **Status:** correctness PASSED; all 8 benchmark shards SUCCESS.

- Source branch: `experiment/drnas-atlasx-structured-s3-subset-20261111`.
- Full Actions run: https://github.com/Frane12/AndroidGameTest/actions/runs/42937920549
- Benchmark commit: `18e93abc7d16bbf9cf9273425f6cb93e5d9ffe23`
- No modifications to stable `main` or S1/S2 frozen experimental branches.

## What changed relative to S2

**Exact subset-support recognition**: build compact truth masks of original
CNF clauses whose variable-support sets lie inside a parent support of
2–4 variables. This picks up ordinary gate definitions consisting of one
ternary and two binary clauses, rather than requiring identical support.
Each local replacement is verified on all 2^k assignments before commit.
Parent modules can now share source clauses through their subset closure;
all L2 pairs with overlapping clause IDs are excluded to prevent incorrect
double counting and duplicate deletion.

L2 still performs optional expansion only with the previous strict source
opportunity gate, and only if it yields a proof-checked literal reduction.
The runtime has a bounded source scan (900 source clauses), max 160 local
modules, 400 L2 pairs, max 6 materializations, and 8s trial cap
(min(5ms, 0.05% of cap) preprocess budget). One logical CPU per arm.

### Correctness

- Generated atlas and native engine compiled.
- Randomized 300 full local truth-equivalence cases: **PASS**; 300/300 cases
  found at least one exact, sound rewrite (non-blind synthetic exercises).
- Exact AND gate with ternary + binary support: recognized.
- Exact cross-support absorption: saved **6 literals** with truth preserved.
- Previous L2 implied-module and lazy-expansion controls: PASS.
- All SAT models for benchmark results verified on ORIGINAL CNF.
- No UNSAT LRAT certification claimed.

## S3 prospective source protocol

Four new source selections relative to frozen S1/S2:
SATLIB planning-logistics SHA-ranked indices 0 and 1, and SATLIB flat200-479
graph-coloring SHA ranks 21 and 37. Original archive SHA256 pinned; each
normalized CNF SHA is logged and included in artifact. These are public
published sources, not wholly novel to prior SAT research; only new to
this S3's held-out selection.

Four separately classified planted controls: redundant-Boolean relation
seeds `0xAD31` and `0xB7D3`, plus standard AND/XOR/ITE gate seeds
`0xC891` and `0xDB92`. These are **synthetic development controls** and
MUST NOT be treated as independent real-world benchmark results.

Five solver arms: native independent DRNAS R3C A, ATLAS1, ATLAS-X S3,
Kissat pinned commit `8af8e56f174b778aef3aa45af9f739b2a5f492c2`,
installed CaDiCaL. Each source x arm with 3 matched repetitions under
8s per trial, one logical CPU, E2E wall-clock time including preprocessing
and process invocation, PAR2 timeout penalty 16s. 8 x 5 x 3 = 120
trials, 24 per solver.

## Results: PAR2 seconds; same as E2E totals because all solved SAT

| Cohort | Arm | Verified solved | PAR2 s |
|---|---|---:|---:|
| External original (4 SHA) | DRNAS A | 12/12 | 0.141741 |
| External original (4 SHA) | ATLAS1 | 12/12 | 0.148800 |
| External original (4 SHA) | **ATLAS-X S3** | **12/12** | **0.150892** |
| External original (4 SHA) | Kissat | 12/12 | 0.342401 |
| External original (4 SHA) | CaDiCaL | 12/12 | 0.113902 |
| Planted controls (4 new seeds) | DRNAS A | 12/12 | 0.049298 |
| Planted controls (4 new seeds) | ATLAS1 | 12/12 | 0.050130 |
| Planted controls (4 new seeds) | **ATLAS-X S3** | **12/12** | **0.050151** |
| Planted controls (4 new seeds) | Kissat | 12/12 | 0.054471 |
| Planted controls (4 new seeds) | CaDiCaL | 12/12 | 0.057555 |

External original S3/A = 1.06456 (~6.46% slower). Planted-control
S3/A = 1.01730 (~1.73% slower). Entire diagnostic cohort S3 = 0.201043s,
A = 0.191039s, but **don't pool cohorts** to make efficacy claims.
All are short millisecond-scale SAT instances; scheduler noise is substantial.

### Efficacy and bottleneck

- External logistics (2 formulas): `L0_no_subset_or_composite` in all
  six ATLAS-X trials. Zero rewrites, as designed.
- External flat200-479 graph-coloring (2 formulas): both inspected
  the 160-module bound on every repeat, total **960 recognized
  subset-support modules** but zero profitable exact rewrites. S3
  preprocessing added ~0.0155s across 12 external attempts; roughly
  0.002–0.0025s per graph-coloring trial.
- Planted redundant controls: S3 accepted 6 source-sound L2
  subsumption rewrites across their 6 total repetitions.
- Planted ordinary gates: S3 accepted **6 L1 NPN rewrites** across
  6 trials; **none** in S2's ordinary-gate cohort. This is the
  requested cross-subset recognizer working.
- On synthetic cohort S3 source-level accepted rewrites: 12/12,
  **96 cumulative literal reductions** (24 per source x3-rep cohort);
  ATLAS1 yielded 72 cumulative saved literals. Important: not unique
  source reductions — repeated benchmark executions count again.
- S3 made **zero** L2 extended CNF materializations in this holdout.
- There is **no evidence of solver speedup** over pure native DRNAS
  on this small external cohort; measured E2E regression.

## Next falsifiable hypothesis

Prototype a **cheap source-only confidence gate** before full
subset-support closure, so a high volume of false-positive structural
modules (graph-coloring) sleeps quickly. For example, hard cap of local
unproductive NPN probes, with a separate shadow mode to quantify
missed profitable rewrites. Validate on fresh original source SHA
holdouts; keep the S3 control and solver comparisons frozen.
Keep independent SAT model verification and distinguish bounded proof
diagnostics from genuine end-to-end results.
