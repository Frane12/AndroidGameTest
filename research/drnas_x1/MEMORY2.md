# DRNAS X1 MEMORY2 — Future Potential Learning (experimental)

Branch: experiment/drnas-x1-memory2-future-20261113

## What was implemented

Native C++20 opt-in module research/drnas_x1/x1_memory2.hpp.
It learns **statistical decision-polarity preferences** from delayed feedback
measured during CDCL search. It **does not** learn arbitrary proofs, discover
new theorems, or change the logical correctness of the SAT solver.

At the start of a bounded decision block, MEMORY2 records:

- Original formula's rename-invariant (coarse) distributional signature;
- Structural context (clause density, binary-clause content, selected variable's
  initial degree and binary incidence, recent conflict pressure and previous
  transition outcome); signed literal incidences and previous four actions;
- Before-snapshot: decisions, conflicts, propagations, learned low-LBD clauses,
  trail size, CDCL depth and elapsed wall time;
- Proposed action: saved-phase polarity or inverted saved-phase polarity;
- Prediction: estimated future-surrogate utility of each action.

At the end of the block, MEMORY2 records the corresponding after-snapshot and
immediate signal. It then holds the episode in a bounded queue, and records
future feedback once **16, 64 and 256 additional CDCL decisions have occurred
AFTER the action block**. If a solve finishes earlier, the horizon is
**censored**, NOT counted as observed training evidence. All file output is
bounded and the per-decision hot path uses a constant-time action lookup.

The policy is a small shrinkage-smoothed contextual bandit: 64 contexts,
two actions, three future horizons. Learned rewards are heuristic proxies
for future implications and low-LBD learning **per unit of cost**, not
probabilities that the formula is SAT or formal causal effects.

## Source-code trust boundary

No learned score may add a clause, assert UNSAT, bypass CDCL conflict analysis,
skip an original-CNF SAT witness check, or forge a proof. The only control
surface is a CDCL **branch decision polarity**. CORE, FACTOR and AUTO without
memory flags retain their original behavior. MEMORY1 and MEMORY2 controls
cannot be used simultaneously.

The solver emits a **staged** policy candidate. The benchmark only promotes
that file after independent checking of the SAT witness or UNSAT DRUP proof.
Do not trust a solver-generated UNSAT label as a training outcome.

## How to build and inspect a trace

    mkdir -p build
    g++ -std=c++20 -O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror \
      research/drnas_x1/x1.cpp -o build/drnas-x1
    ./build/drnas-x1 --mode core --seconds 3 --proof /tmp/answer.proof \
      --memory2 --memory2-interval 8 --memory2-log /tmp/memory2.jsonl \
      --memory2-save /tmp/UNTRUSTED-candidate.txt example.cnf

To read a previously **verified** model without changing it:

    ./build/drnas-x1 --mode core --seconds 3 --proof /tmp/answer.proof \
      --memory2-load /path/to/verified-model.txt --memory2-frozen \
      --memory2-log /tmp/holdout-memory2.jsonl example.cnf

Use --memory2-shadow with --memory2-frozen for a non-intervening, instrumented
control: it logs the same types of events while taking CORE's phase decisions.

## Benchmarks

    python3 -S research/drnas_x1/test.py build/drnas-x1 --cases 500
    python3 -S research/drnas_x1/memory2_bench.py \
      --binary build/drnas-x1 --out /tmp/memory2-compare \
      --train 42 --holdout 30 --repeats 3 --cap 2.0

Paired controls on the same source and seed:

1. Native X1 CORE (no memory overhead)
2. X1 MEMORY1 frozen
3. X1 MEMORY2 shadow (instrumentation overhead, no changed decisions)
4. X1 MEMORY2 frozen (training-derived policy, no holdout learning)
5. X1 MEMORY2 online (within-instance learning, no holdout state saved)

All reported speedups use independently verified **end-to-end PAR2**, including
independent proof checking. Unverified answers get 2 x time cap. The CPU/check
environment, source SHA hashes, memory artifacts and a bounded selection of
future-horizon trace records are retained in CI outputs.

The synthetic pilot is **SHA-distinct**, not strictly family-disjoint, globally
blind or official SAT Competition proof of performance. It does not constitute
a controlled same-internal-state counterfactual: paired independent replays
start with the same source and seed, but their search states diverge once
actions differ. We cannot infer causality from a single episode's reward.

## Planned next step

Collect more structurally varied original CNFs under a frozen disjoint split,
train on multiple full search episodes, compare against reference solvers
(Kissat/CaDiCaL) and ablate the 16/64/256 feedback independently. Study
matched branch-state probes only after implementing correct trail/heap/watch
snapshot restoration and proof-safe continuations. Prefer evidence of
improved end-to-end verified PAR2 to more elaborate "AI" terminology.
