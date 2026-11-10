# DRNAS SAT / ORION — Technical Architecture

**Author:** Frane Drnas · **Status:** experimental research architecture · **Updated:** 2026-11-10

> This document separates the *proposed architecture* from features actually demonstrated in individual experiment arms. DRNAS SAT is not yet established as an independent, generally competitive, end-to-end native SAT solver. Some reported experiments use Kissat, CaDiCaL or CryptoMiniSat backends.

## Research objective

Can proof-preserving transformations reveal useful structure in an **original CNF** early enough to avoid part of the CDCL search, while keeping extraction and communication overhead below the benefit?

The central principle is **reduce the need for search, not merely search faster**. Gaussian elimination, XOR detection, CDCL, and XOR-aware solvers are established prior art; the specific contribution under investigation is *certified extraction, selective use, communication to live CDCL, and cost-sensitive fallback*.

## Conceptual processing flow

```text
Original DIMACS CNF + source SHA-256
        |
        v
Input integrity / source-preserving validation
        |
        v
Cheap structural screening
  - units / Boolean implications
  - parity / GF(2) / XOR candidates
  - graph or SCC equivalences
        |
        v
Soundness gate: only source-entailed deductions
        |
        +--> No useful, cheap deduction --> clean CDCL reference path
        |
        +--> Certified and useful structure
                  |
                  v
           GF(2) / reduction engine
           - linear relations and conflicts
           - proof/checkable dependencies
                  |
                  v
           Selective delivery to live CDCL
           - propagations and conflict reasons
           - account for extraction + verification cost
                  |
                  v
            CDCL search / fallback
        |
        v
Original-formula verification
  SAT: independently check assignment on original CNF
  UNSAT: independently check original-CNF proof where available
  otherwise: UNSAT proof status NOT independently verified
        |
        v
Per-trial audit JSON + matched benchmark summary
```

**Important:** this is a research roadmap, **not** a claim that every current binary implements the whole diagram. Static routing, GF(2) standalone reductions, shadow-mode observations, bounded-CDCL diagnostics and live native feedback must be audited as **different experiment types**.

## Main research components

| Component | Purpose | What requires further validation |
| --- | --- | --- |
| **R28 / exact parity route** | Solve or simplify detectable, mathematically justified GF(2) structure; fall back when needed | Which original formulas allow complete proof-safe extraction; overhead on non-XOR CNFs |
| **Selective gate / router** | Decide whether to activate the additional path or use ordinary CDCL | Out-of-sample calibration; regressions; cost of screening |
| **GF(2) ↔ CDCL** | Feed useful implications or conflicts from parity reasoning into the active CDCL trail | Independent derivation checking, valid clause reasons and measured causal CDCL benefit |
| **MRE / CRR** | Explore cross-representation reductions using CNF, XOR/GF(2), Boolean rules, SCC/graphs and ANF | End-to-end correctness, source entailment and concrete search reduction |
| **Native standalone DRNAS solver** | Long-term fully independent SAT/UNSAT engine | Completion, original-formula witness/proof checking, blind head-to-head benchmarking |

Not all components are production-ready or integrated. A benchmark using an existing backend is labeled as **backend-assisted**, not a standalone native DRNAS result.

## What the experiments presently establish

- **[R32q](https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807):** a **known XOR-structured** official-source original CNF. The R28 path solved SAT twice (0.004179 and 0.004189 s) and the original SAT witness was checked; clean Kissat timed out at 60 s in both comparisons. **>14,340× is a timeout-censored lower bound on that single instance**, not a general speedup.
- **[R194](https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737):** 38 original cases × 6 solver modes × 2 repeats = 456 measured trials, four CI shards. On that cohort, the source-matched R28 route improved **aggregate PAR-2** by **1.16×** over plain CryptoMiniSat and **1.40×** over plain Kissat. Results differ by formula family and are not blind universal superiority.
- **[R189](https://github.com/Frane12/AndroidGameTest/actions/runs/42228208905):** selective source-certified routing shows a promising cohort-level PAR-2 effect, but causality on the *live CDCL trail* remains an open question.

[Complete benchmark tables and caveats](../research/DRNAS_SAT_STATUS.md) · [Public research dossier](../research/DRNAS_ORION_2026-11-06_PUBLIC_REVIEW.md)

## Engineering and scientific priorities

1. Measure **new implications, usable reasons, verified conflicts, overhead and net end-to-end speedup** separately. Observing XOR structure is not the same as helping CDCL.
2. Keep one logical CPU per solver in the main comparisons; disclose all caps, host variation, wall/CPU time and binary/source hashes.
3. Test prospective, SHA-disjoint, unseen formulas across parity-rich, mixed and non-XOR families with explicit negative controls.
4. Independently validate original-CNF SAT witnesses and **original-CNF UNSAT proof artifacts**. A backend UNSAT status without an independently checked certificate must not be presented as a verified proof.
5. Preserve unmodified source formulas and frozen selection rules; publish both improvements and regressions.

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for an independent-audit checklist and the linked raw evidence. All experiments remain **research-stage, not peer-reviewed**.
