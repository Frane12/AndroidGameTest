# DRNAS SAT — research status and reproducibility index

**Author:** Frane Drnas · **Updated:** 2026-11-10 · **Research stage:** experimental, not peer-reviewed.

> This is a point-in-time research index, not a SAT competition ranking. All performance numbers below refer to the exact linked experiments. They do **not** establish universal or previously unknown algorithmic superiority over established SAT solvers.

## Scientific goal

**DRNAS SAT / ORION** studies when source-certified XOR/GF(2) deductions, selective routing, and proof-compatible information exchange can reduce the cost of solving the **original** CNF. Related research threads include:

- **GF(2) / XOR recognition and Gaussian elimination:** identify provable parity structure; route only when predicted benefit exceeds overhead.
- **CDCL integration:** explore incremental propagation and sound CNF reasons backed by derivations from the input; evaluate on the live solver trail.
- **Mathematical Reduction Engine (MRE) / Cross-Representation Reduction (CRR):** explore sound transformations among CNF, parity, Boolean implications, graphs and ANF.
- **Native standalone SAT engine:** an ongoing engineering direction; current portfolio/route results must not be represented as standalone-solver performance.

Known methods such as Gaussian elimination and XOR-aware CDCL are prior art. Novelty and broader scientific value remain to be established by technical review and blind, multi-family tests.

## Reproducible benchmark evidence

### R194 — cross-backend, source-matched comparison

[GitHub Actions run](https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737) · [Final audit artifact](https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737/artifacts/13579769872) · [Exact source snapshot](https://github.com/Frane12/AndroidGameTest/tree/8229dc79bbb55577e1f0850ea3153a6740d18d38)

- **38 original source cases; 6 modes × 2 repetitions = 456 trials**, executed in four independent CI shards.
- Runs record SAT/UNSAT/timeout outcomes, original-source checks, PAR-2, input and binary pins, and per-shard results.
- *Four parallel shards* refers to CI execution, **not** a four-core speedup claim. Compare paired solver-mode results within the experiment.

| Solver mode | Solved / 76 | Aggregate PAR-2 (s) | PAR-2 ratio vs same-backend plain |
| --- | ---: | ---: | ---: |
| CryptoMiniSat plain | 52 | 758.878 | 1.00× |
| CryptoMiniSat + R28 route | 52 | 655.967 | **1.16×** |
| CryptoMiniSat + GF(2) hybrid | 52 | 674.599 | **1.12×** |
| Kissat plain | 26 | 1209.259 | 1.00× |
| Kissat + R28 route | 40 | 864.852 | **1.40×** |
| Kissat + GF(2) hybrid | 40 | 867.566 | **1.39×** |

Ratios are **plain PAR-2 / tested PAR-2** (lower is better), **not** geometric-mean uncensored speedups. These are cohort-level gains for this study, with case selection and family dependence. The four-way hybrid was not uniformly better than the simpler R28 route.

### R32q — known official-source XOR case (strong specialized example)

[GitHub Actions run](https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807) · [Results + live log](https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807/artifacts/13239399691) · [Exact source snapshot](https://github.com/Frane12/AndroidGameTest/tree/95b2b06f16efc68827ed34de9cbc1bda7b6a0a37)

- Original SAT Competition 2026 benchmark database ID: `75429ff7acb5acb597abe01aa745c2a6`.
- Original DIMACS SHA-256: `243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83`; 250 variables / 1,000 clauses.
- R28 exact GF(2) pathway: **SAT in 0.004179 s and 0.004189 s**; original-source model verified both times.
- Clean Kissat: **TIMEOUT at 60 s in both trials**. Median R28 time **0.004184 s**.
- Hence **>14,340×** is a **censored lower bound** on this *one* known parity-structured case, not an exact measured speedup and not a general SAT benchmark record.
- Measured aggregate PAR-2: R28 **0.008368 s** versus Kissat **240 s** (timeout penalty, not real solving time).

### Other published research evidence

The [ORION research dossier](DRNAS_ORION_2026-11-06_PUBLIC_REVIEW.md) links original 2026-run evidence and caveats, including:

- [R115 historical repeat](https://github.com/Frane12/AndroidGameTest/actions/runs/41898809612): five repetitions of a known parity-related benchmark, with reference timeouts; specialized and *not blind*.
- [R153 repeat](https://github.com/Frane12/AndroidGameTest/actions/runs/42128549081): 25 formulas, five modes, three repetitions; family-dependent results.
- [R186 selector test](https://github.com/Frane12/AndroidGameTest/actions/runs/42217191848): aggregate PAR-2 gain concentrated in XOR-related cases.
- [R189 source-certified test](https://github.com/Frane12/AndroidGameTest/actions/runs/42228208905): 38 cases / 456 attempts; selective gate aggregate PAR-2 1085.118 s vs 1514.506 s clean (**1.396×**), with incomplete causal and blind generalization evidence.

A publicly indexed [ORION research evidence pre-release](https://github.com/Frane12/AndroidGameTest/releases/tag/drnas-orion-review-v0.1-20261106) provides the publication entry point. Public evidence is not the same as independent peer review.

## How to reproduce and audit

1. Select a linked GitHub Actions run above; download its **Artifacts** (GitHub sign-in may be required, and artifacts can expire).
2. Check pinned workflow / source commit; use the original SHA-verified CNF manifest and frozen source/binaries where published.
3. Read raw per-trial JSON and logs, not just a summary table. Verify backend status, SAT model checks on **the original CNF**, and independent UNSAT proof certification where claimed.
4. Compare the same source cases under matched hardware / CPU limits / caps. Report both **solved count** and **PAR-2 seconds**, as well as wins, losses, regressions and timeouts.
5. Keep *standalone native SAT/UNSAT*, *portfolio/routing*, *shadow diagnostics*, and *bounded-CDCL telemetry* **strictly separate**. Do not silently treat timeout-derived lower bounds as exact speedup ratios.

## Current limitations and next verification targets

- **Generalization:** prospective SHA-disjoint, truly unseen, heterogeneous SAT/UNSAT holdouts; include non-XOR and near-XOR negative controls.
- **Causality:** measure whether live GF(2) reasoning produces useful new CDCL implications, conflicts or checkable reasons **after** its overhead.
- **Correctness:** SAT witnesses checked against original CNF; independently checked UNSAT proof artifacts when claiming certified original UNSAT.
- **Engineering:** reduce duplicate transforms, unnecessary clause injection, memory and log/proof artifact size; keep one logical CPU per compared solver for the main benchmark table.
- **Native engine:** demonstrate complete independent SAT/UNSAT capability before claiming results achieved through existing solver backends as standalone DRNAS wins.

## Reviewer contact and citations

Open a [GitHub issue](https://github.com/Frane12/AndroidGameTest/issues) with the exact source SHA, workflow run ID, artifact name, CPU/cap, and full observed verdict. Critical replication results and negative findings are welcome.

**Citation convention:** Frane Drnas, *DRNAS SAT / ORION*, experiment [R194](https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737) or [R32q](https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807), GitHub Actions artifact and exact pinned source commit, accessed with date.
