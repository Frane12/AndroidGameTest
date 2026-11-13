# DRNAS Native X4.0 — State Transition Memory, observational baseline

**Status:** First of five planned X4 phases. X4.0 is an independent, native C++20 solver based on the X3 CDCL **core**, without calling Kissat, CaDiCaL, CryptoMiniSat, Python, or any external SAT engine during solving. This version deliberately **does not use a learned policy**: the observer is not connected to the branch selector.

## Why first measure actual transitions?

- **Proof/certainty:** A correctly checked SAT witness gives a final answer. A derived clause is logically entailed but not necessarily a runtime speedup; a native UNSAT declaration is not an independent DRAT/LRAT certificate.
- **Structure:** Number of currently unsatisfied original clauses with three or more unassigned literals in a fixed 64-clause sample. This is a local structural indicator, **not** a distance to the answer.
- **Observed step:** Given a real chosen literal, record pre-BCP state, post-BCP state, new propagated assignments, BCP conflict and processing time. This does not determine if an alternative choice would have been better.
- **Delayed outcome:** If the solve finishes, retrospectively annotate each recorded step with the time remaining *under the same policy*. Unknown/censored runs get `null`. This is a training target for later validation, **not causal reward**.

X4.0 provides two modes using exactly the same CDCL branching policy:

- `--mode core` — uninstrumented solver core for performance control.
- `--mode trace` — same core, passive sampling and optionally a bounded JSONL trace. Sample first 16 decisions, later powers-of-two and each 4096th decision. In-memory trace limited to last 256 samples; monitor `trace_evicted` and `trace_samples_total`. No source name, benchmark label, known outcome, training set or oracle result is ever read by the solver.

## Build and run

```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x4.cpp -o build/drnas-x4
build/drnas-x4 example.cnf --mode core --time 5 --stats
build/drnas-x4 example.cnf --mode trace --time 5 --stats --transitions x4_transitions.jsonl
python3 tests/test_x4.py --cases 2800
python3 research/drnas_x4_bench.py --smoke --synthetic-count 96 --smoke-cap 0.35
```

DIMACS exit: `SAT=10`, `UNSAT=20`, `UNKNOWN=0`, `ERROR=1`. SAT output carries a full assignment to be checked independently on **original CNF**; the native solver checks internally too. The observer writes `X4_STATS` to stderr and an optional versioned `meta` header plus `transition` JSONL records. Original CNF source paths are not included in trace rows. The benchmark captures per-input SHA in its separate manifest.

The trace is retrospective: a recorded step that precedes a successful SAT solution is *not* proved necessary, helpful or optimal. The internal UNSAT output has an explicit `UNSAT_INTERNAL_ONLY` label; on official sources, without an independently checked DRAT/LRAT proof, UNSAT receives PAR2 timeout penalty. Synthetic UNSAT construction checks are not general proof certificates.

## Benchmark / correct claims

- Small truth-table differential tests compare `core` and `trace` on identical CNFs; SAT witnesses, solver statuses, decisions, conflicts, learned-clause count and propagations must match exactly (without timeouts).
- 96 deterministic synthetic CNFs, same cap for X3_CORE, X3_ADAPTIVE, X4_CORE, X4_TRACE; compare verified PAR2, solves and observer overhead.
- 12 **historically seen** SAT2024 original CNFs, same 5s cap on one logical CPU; compare also pinned Kissat/CaDiCaL/CryptoMiniSat in *benchmark-only* processes. This is an exploratory replay, **not a blind holdout**.
- Extract `trace_samples_total`, `trace_evicted`, and total JSONL size to ensure observability is bounded. Never claim X4.0 improves solving until an independently evaluated policy actually does.

## Next phases, separately gated

- **X4.1 Formal signal taxonomy:** decision-level proofs, structural simplification, and uncertain forecasting recorded separately; audit benchmark and unverified UNSAT.
- **X4.2 Offline cost model:** train only on completed and properly censored transitions from training families; estimate full future runtime conditional on context; hold out entire CNF source families and use calibrated prediction intervals, no label leakage.
- **X4.3 Shadow-policy trials:** compare alternative branch decisions at matched states on *separate cloned executions*, including probe cost; only promote a model to the online driver if held-out solved/PAR2 improves beyond measurement noise and regressions are bounded.
- **X4.4 Audited validation:** independent SAT witnesses and UNSAT proof checker, fresh official/industrial families, multiple runs, paired CPU affinity and PAR2 reporting.

**Ground truth:** No general cheap, exact distance-to-SAT solution exists; X4 does not pretend to provide one. The plan learns policy-conditional expected finishing work, not metaphysical proximity.
