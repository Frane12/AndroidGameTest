# DRNAS SAT — constructive category atlas (native C++)

Research stage: experimental. Source: Frane12/AndroidGameTest.
Development branches: sat-unified-xorblind1 and sat-xorhard2 (2026-11-15).
Main, prior frozen references and APK workflows are untouched.

## Contract

Input: original DIMACS CNF F, monotonic CPU-cost budget, one logical CPU.
Output: either a **complete** assignment a with independent check F(a)=TRUE,
or UNKNOWN and fall back to the same native X59 CDCL core. A structural
constructor NEVER returns UNSAT. Its experimental heuristic may be wrong
about expected runtime but not about satisfiability: only a FULL original
source model can produce SAT. Any UNSAT result must come from a separate
sound native CDCL path and independently checked DRAT/LRAT as required
by scientific benchmarks.

This is not a proof that arbitrary SAT can be decided in polynomial time.
Even a perfect classifier of known structural categories can encounter
unrecognized, mixed or NP-hard residuals.

## Implemented categories

| Source structure | Algorithm | Exact SAT certificate | Limit |
| --- | --- | --- | --- |
| Horn | forward chaining, least-model closure | full source assignment | not general non-Horn |
| Renamable Horn | 2-SAT on sign flips + Horn closure | full source assignment | pairwise memory guard |
| 2-SAT | implication SCC | full source assignment | clauses of width <=2 |
| Pure polarity | satisfy each variable's unique observed polarity | full assignment | fails if mixed polarities |
| Unit/pure reduction | bounded root unit BCP and pure peeling | full reconstructed assignment | must pass original validation |
| Matching / at-least-one and mutex | conservative component matching | chosen positives + all-other-false, fully checked | disjoint ALO input; UNKNOWN otherwise |
| GF(2)/XOR | complete signed CNF XOR pattern recognition, Gaussian elimination | full candidate; original clauses checked | source patterns of width 2..6, size guards |
| Independent components | variable graph DSU and exact sub-solvers | component union; original checked | fails on unsupported component |
| Small residuals | complete assignment search for <=14 variables | full assignment | exponential, hard cap |
| General CNF | original X59 CDCL | verified SAT model or independently checked UNSAT proof | bounded execution can return UNKNOWN |

The source AST and SAT-model validator are shared; the modes are sound only
as SAT-certificate producers. Source-derived arithmetic parity and matching
are known prior art. Novelty of the particular cost-based orchestration is
an experiment, not an established theorem.

## Three layers in one process

1. Cheap source classification and guard. Eligible implementations share one
   wall-time budget. No separate solver process, concurrent portfolio, or
   thread.
2. Structured constructive SAT modules. Complete source model must pass
   byte-for-byte original CNF independent checking. If no model: abstain.
3. Unmodified native CDCL fall-through with clause learning, restarts,
   and standard UNSAT evidence.

Integration:
  src/drnas_sat_construct.hpp
  src/drnas_sat_construct.cpp
  src/drnas_x59.cpp

Native options:
  --sat-construct-ms 0     default OFF
  --sat-construct-ms 25    guarded original-CNF construction
  --sat-construct-ms 100   comparison with looser limit

Each module may help a narrow family yet regress other families from overhead.
A global speedup claim requires verified paired PAR2 improvements on
source-independent retrospective and prospective mixed sets.

## Results and frozen protocols

- Structural soundness controls: 257 original native/unified2 cases passed,
  no observed incorrect SAT. Width5/6 added 80 more source-model-checked
  cases, no observed incorrect SAT.
- XORBLIND1 source freeze:
  https://github.com/Frane12/AndroidGameTest/actions/runs/43707163289
  SHA256 manifest:
  41e1ede703a2fd1a6401b51d2d82407973a224046d94bf7ae2806c0bfec5287d
  100 newly generated source-distinct SAT cases, 5 syntactic cohorts.
- XORBLIND1 evaluation:
  https://github.com/Frane12/AndroidGameTest/actions/runs/43707869814
  1200 verified SAT-only paired attempts; X59+UNIFIED2 aggregate PAR2
  0.781564 s vs X59 OFF 0.824110 s, 5.16% lower, not a confident 10% win.
  The gain was concentrated in pure XOR4; other cohorts regressed.
- XORHARD2 source freeze:
  https://github.com/Frane12/AndroidGameTest/actions/runs/43708271049
  SHA256 manifest:
  0d9121da9d63312bd24e24e4cf2754bc0cf6ea6de50ba21b2597324a1d4f8514
  60 new constructed SAT sources with widths 3..6 and controlled partial
  and mixed structures, selected before solver timing.
  All source manifests are immutable in the archived Actions artifact.

Caveat: both XORBLIND1 and XORHARD2 are **prospectively generated synthetic
unseen instances**, not previously unseen original competition inputs.
Performance on these cohorts does not establish SAT Competition leadership.
A subsequent blind original-source study with completely held-out source SHAs
and strong XOR-aware reference CryptoMiniSat is necessary.

## Next practical direction

Classify structural density cheaply, estimate expected gain versus overhead,
turn on XOR, matching, Horn or component analysis only with a positive
expected-net-benefit margin, then fallback to CDCL without lost correctness.
Benchmarks must report by structural family, not only pooled average:
solver CPU, checker time, SAT witness, independent UNSAT proof when relevant,
timeout and memory limits, per-source PAR2 wins/losses and bootstrap uncertainty.
