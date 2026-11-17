# DRNAS XORLIN-CDCL1: one process XOR-LIN1 source-only UNSAT + intrinsic CDCL fallback

**Status:** Experimental integration and retrospective benchmark.  
**Branch:** \`experiment/drnas-xorlin-cdcl1-oneprocess-20261117\`.  
**Date:** 2026-11-17. No changes to \`main\`, prior frozen binaries,
the certified GF(2) proof methods, or original CNFs.

## Architecture and the precise scope of "single process"

This first integration is **one native C++ executable**, not a portfolio
and not a launcher of two solver processes. Its C++ compilation unit
includes the **unaltered** intrinsic DRNAS X59 CDCL code
\`src/drnas_x59.cpp\` (main is renamed via C preprocessor for internal
linkage). If the mathematical gate returns UNKNOWN, the C++ application
calls the **existing CDCL run function in-process**, adjusting its time
budget by elapsed gate time. No \`fork\`, \`exec\`, \`popen\`, \`system\`
or parallel solver subprocess exists inside this executable.

To prevent changes in the already externally certified GF(2)
proof generation, the gate **embeds CPython in the same process** and
calls frozen \`research/xorlin1/extract.py:derive\` and
\`research/xorlin1/emit_veripb.py:compile_source\`.
Both are source SHA pinned against the previous successful run
[44053818490](https://github.com/Frane12/AndroidGameTest/actions/runs/44053818490).
The *mathematical analysis is therefore still implemented in Python*;
the solver is a C++ host with a native C++ CDCL fallback. This is not
yet a complete pure-C++ reimplementation of XORLIN1. We must report
its interpreter startup and proof compiler overhead.

The solver accepts \`--gate on|off\`, \`--gate-ms N\`,
\`--mode core\`, \`--time SECONDS\`, \`--proof FILE\`,
\`--repo-root PATH\`. The default gate soft budget is 700 ms,
and the gate skips original sources over 500 KB.
The total 8s cap always includes the gate and remaining CDCL.
Even when the gate finishes early, the **external standard checker**
is run **only after** the solver process exits and counts against
the *same* 8s E2E cap in the benchmark.

Proof route is explicit and unambiguous in solver stdout:
- \`c XORLIN_CDCL1_ROUTE GATE_VERIPB\`: emit a complete source-backed
  VeriPB RED/RUP/CP proof directly in the same solver process. This
  is accepted only when external VeriPB independently verifies the
  ORIGINAL unchanged CNF.
- \`c XORLIN_CDCL1_ROUTE CDCL_DRAT\`: no contradictory GF(2) subset
  or gate OFF, so run the unchanged X59 native C++ CDCL engine in
  the same PID. SAT requires independently verified complete model;
  UNSAT requires external original-CNF DRAT-trim proof check.
- UNKNOWN and proof/resource limits are **not** scored as UNSAT.
  All invalid SAT models, incorrect standard proofs, inconsistent
  proof kinds, missing original source SHA or contradictory outcomes
  are critical, blocking the result.

## Why this experiment is retrospective

The original 12 mixed GBD sources and their
byte-identical SHA-256 frozen manifests come from the already completed
prospective XORLIN1 V2 run
[44059940286](https://github.com/Frane12/AndroidGameTest/actions/runs/44059940286).
The integration and fixed routing budgets are being developed
*after* examining the performance on those originals.
The new ON/OFF comparison is therefore **retrospective engineering
and regression evidence**, not a fresh blind or unseen holdout.
A subsequent new source-frozen evaluation is necessary before
claiming generalization of the integrated solver.

## Evaluation

\`research/xorlin_cdcl1/benchmark.py\` runs:
12 original CNFs ×2 repeats ×5 arms = **120 strict paired trials**
at 8 seconds including independent proof/model check, PAR2=16s
for timeouts and uncertified answers. All arms run serially on
the same **single logical CPU affinity** inside a shard.
Arms:
- HYBRID_ON — same compiled binary with bounded mathematical gate
- HYBRID_OFF — identical binary with gate disabled, native X59 CDCL
- Kissat — frozen original source and reference solver
- CaDiCaL — frozen original source and reference solver
- CryptoMiniSat — frozen original source and reference solver.

The frozen GF(2) standalone self-test includes 24 externally
accepted contradictory-source VeriPB proofs, 48 independently
known SAT controls with zero false UNSAT, degree-four source
incidence and incorrect-source-hash rejection. A separate
one-process smoke test validates: GF(2) UNSAT to external VeriPB;
same UNSAT with gate OFF to native CDCL+DRAT; SAT full model
on gate ON and OFF; non-XOR SAT; non-XOR UNSAT with DRAT.

Per case, we record full E2E time, source SHA, proof kind,
external checker result, and ON vs OFF verified solved-to-unsolved
regressions. The aggregate fails if any missing/duplicated
attempts, source drift, unverified SAT/UNSAT or critical event.

**No automatic promotion to main.** If ON loses solved cases from
OFF or incurs unacceptable overhead on SAT/non-XOR formulas,
reduce gate budget/condition only on a *new* experimental
training branch and rerun frozen evaluations, never retroactively
claim this version was a blind success.
