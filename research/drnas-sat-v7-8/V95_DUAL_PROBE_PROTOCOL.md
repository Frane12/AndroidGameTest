# DRNAS SAT v9.5 — separate dual-solver quality probe (preregistered)
Date: 2026-10-31

Benchmark run: https://github.com/Frane12/AndroidGameTest/actions/runs/41236194691

## Implementation
- New branch only; original frozen v7.6, v9.2 and v9.4 source is untouched.
- Two **different** CaDiCaL 3.0.1 solver instances, identical original CNF.
- CaDiCaL plain first, up to 96 conflicts. If it solves, end immediately.
- Otherwise second independent solver receives frozen v9.2 strong majority phases and also runs up to 96 conflicts. If it solves, end immediately.
- If neither solves, compute from true instrumented first-UIP LBD <=2, LBD <=4, retained redundant learned clauses, and conflicts:
  quality = (4*LBD2 + 2*LBD4 + retained) / max(1,conflicts).
- Choose Sparse only with at least 12 sampled conflicts, quality >= 1.20*plain quality and sparse-probe CPU <= 1.50*plain-probe CPU. Otherwise choose plain.
- Continue **the existing chosen CaDiCaL instance** with its native learned clause database. Discard the other solver. No replay.
- Probe time for both branches, formula filling, instrumentation, selector cost, and final solve are all included in external 15-second per-process wall-clock. A time-out counts PAR2=30s.
- OOM protection: if >300000 input vars OR >1200000 clauses, run plain CaDiCaL directly; report gate_reason=v95_large_input_fallback.
- The internal first-UIP quality is a crude proxy, not evidence of actual future usefulness of clauses. This method may cost substantially more than a fixed single solver.

## Test protocol
- 12 official SAT Competition 2026 CNFs, already used in v9.4: six SAT and six UNSAT; sourced by frozen SHA256 manifest from run 41232668762.
- 5 solvers: original plain CaDiCaL, frozen v7.6 guided, frozen v7.6 no-hints, frozen v9.2 Sparse, v9.5 dual probe.
- 2 repeats each = 120 actual paired subprocess runs; 4 single-core runner shards.
- Report solved/24, timeouts, mean PAR2, per-SAT/UNSAT, all cases, probe time, selected solver counts, regressions vs both plain and Sparse.
- Fail closed on missing samples and SAT/UNSAT mismatch against frozen public verified label.
- This is **NOT** an independent generalization test. These 12 CNFs and some outcomes have been seen before. Model thresholds were frozen before v9.5 benchmark but can still reflect previous exploration. Fresh 2026 competition instance cohorts and independent UNSAT proof checking are required for strong claims.

## Publication constraint
Never call this a world record, P=NP result, or generic speed improvement without an independent preregistered large holdout, comparison against official solvers on the same hardware, and proof validation.
