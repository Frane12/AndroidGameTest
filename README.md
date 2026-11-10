# DRNAS SAT / ORION
### Experimental SAT solving · Verified XOR / GF(2) reasoning · CDCL integration · Mathematical reductions

**Research by Frane Drnas (Croatia)** · [Research status (10 Nov 2026)](research/DRNAS_SAT_STATUS.md) · [Public research dossier](research/DRNAS_ORION_2026-11-06_PUBLIC_REVIEW.md) · [ORION evidence release](https://github.com/Frane12/AndroidGameTest/releases/tag/drnas-orion-review-v0.1-20261106)

**The research question:** can we *prove* useful structure in an original CNF formula and exploit it cheaply enough to avoid some CDCL search—without making ordinary, non-XOR SAT instances worse?

This repository is a **public research and reproducibility hub** for DRNAS SAT experiments (alongside older Android porting work). SAT implementation and benchmark sources currently live primarily on **pinned experimental branches**, linked below. Results are exploratory, **not peer-reviewed**; Gaussian elimination and XOR-aware SAT solving are established prior art.

## Experimental results — start here

| Reproducible run | What was measured | Result and scope |
| --- | --- | --- |
| **[R194 — 456 benchmark trials](https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737)** | 38 original cases × 6 modes × 2 repeats; matched CryptoMiniSat/Kissat comparisons in four CI shards | **1.16× PAR-2 improvement** for CMS + R28 route vs plain CMS; **1.40× PAR-2** for Kissat + R28 route vs plain Kissat. Family-dependent; **not** a universal speedup. |
| **[R32q — certified XOR example](https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807)** | One original SHA-verified SAT Competition 2026 CNF; two repeats; R28 exact-GF(2) path vs clean Kissat | **0.004184 s** median with original SAT witness checked; Kissat timed out at **60 s** twice. Therefore **>14,340×** is a *timeout-censored lower bound on one known XOR case*, not a completed-run ratio. |
| **[R189 — selective GF(2) study](https://github.com/Frane12/AndroidGameTest/actions/runs/42228208905)** | 38 cases / 456 attempts; clean reference vs source-certified selective gate | Aggregate PAR-2 **1514.506 → 1085.118 s** (1.396×) on this study cohort. Broader blind validation remains open. |

**For raw JSON, logs, source hashes, original CNFs, CPU/cap details, solved counts, negative controls and limitations:** **[Open the research status & reproducibility index →](research/DRNAS_SAT_STATUS.md)**.

[Download R194 final audit artifact](https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737/artifacts/13579769872) · [Download R32q original results artifact](https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807/artifacts/13239399691) · [View all Actions](https://github.com/Frane12/AndroidGameTest/actions)

## Research directions

- **Source-certified GF(2) / XOR:** detect parity equations and derive mathematically justified implications; activate only when cost-effective.
- **GF(2) ↔ CDCL:** study live propagation, trail monitoring, clause reasons and conflict feedback; distinguish real search impact from passive diagnostics.
- **MRE / CRR:** proof-preserving cross-representation reductions between CNF, XOR, Boolean implications, graph structure and ANF.
- **Native standalone SAT solver:** under active development; no claim that portfolio or existing-backend results prove standalone superiority.

### Source and audit entry points

- **[R194 exact source commit](https://github.com/Frane12/AndroidGameTest/tree/8229dc79bbb55577e1f0850ea3153a6740d18d38)** — benchmark runner, workflows and frozen source/binary manifests.
- **[R32q exact source commit](https://github.com/Frane12/AndroidGameTest/tree/95b2b06f16efc68827ed34de9cbc1bda7b6a0a37)** — original-CNF certified-XOR experiment.
- **[Public ORION review dossier](research/DRNAS_ORION_2026-11-06_PUBLIC_REVIEW.md)** — supporting R115, R153, R186 and R189 evidence, plus limitations.
- **[Technical issues & reviewer feedback](https://github.com/Frane12/AndroidGameTest/issues)** — report reproductions, discrepancies and negative results.

## Validation commitments

We report **original-CNF SAT witness verification**, independent UNSAT certificates **only where actually checked**, outcomes and timeouts, PAR-2 in seconds, per-family regressions, and exact GitHub run/commit provenance. A timed-out reference solver establishes **only a lower-bound** comparison. Multi-shard CI throughput and multi-core portfolios must never be conflated with single-core solver performance.

**Outstanding work:** genuinely unseen mixed-family holdouts; independent proof verification; measuring whether GF(2) actually changes CDCL propagation; low-overhead selective gates; and a separately benchmarked complete native DRNAS solver. See the [live research status](research/DRNAS_SAT_STATUS.md).

---

<details>
<summary>Other projects in this repository — Android native ports</summary>

Earlier Android experiments are preserved, including the pre-alpha **Stellarium 26.3 ARM64 native port** (Qt 6.8.3 / OpenGL ES), which is unrelated to DRNAS SAT benchmarking.

- [Stellarium source / build instructions](https://github.com/Frane12/AndroidGameTest/tree/experiment/stellarium-native-android-26-3/stellarium)
- [Stellarium Android CI](https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-stellarium-android-arm64.yml)
- [APK pre-releases](https://github.com/Frane12/AndroidGameTest/releases) — experimental; APK availability varies and Actions artifacts may expire.

The port is not an official release of the Stellarium project; upstream licenses and notices apply.

</details>
