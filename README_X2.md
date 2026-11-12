# DRNAS NATIVE X2 — Structural Backdoor + Implication Distance

Independent C++20 SAT solver. The X2 **solver executable contains no Kissat,
CaDiCaL, CryptoMiniSat, Python, cloud service, or external SAT engine**.
Reference solvers are called only by separate Python benchmark scripts.

## Two ideas that must not be confused

**Pattern** is a property of the residual CNF: e.g. the number of currently
unresolved clauses with at least three unassigned literals. This is a cheap,
structural *indicator*, not a proof of proximity to the solution.

**Step toward a simpler problem** is the *change* caused by one temporary
assignment and bounded Boolean propagation. X2 probes candidate literals,
measures how many sampled long clauses become satisfied or short enough for
2-SAT, then rolls back the probe. The probing budget is time-limited.

## Modes

- `--mode core`: X2's native CDCL engine (1-UIP, learned clauses, restarts,
  VSIDS-like activity, watched long clauses, direct binary implication edges).
- `--mode backdoor`: `core` plus exact detection of residual 2-SAT up to decision
  depth 12; Kosaraju SCC solves SAT leaves, or an entailed decision nogood is
  learned for UNSAT leaves. Not a guarantee that a short backdoor exists.
- `--mode x2` (default): `backdoor` plus bounded structural-distance lookahead
  (3 candidates, both polarities, limited BCP, cost-based gating).

**Important X1 correction:** A speculative polarity that causes a contradiction
must be *avoided*, rather than preferred. Both-polarity contradictions are not
assumed to be a proof without further CDCL resolution.

### Correctness of backdoor learning

Let `D1 ... Dk` be all currently selected decision literals. Every other trail
assignment follows from them by sound unit propagation. If the residual CNF is
UNSAT under these decisions, the original CNF logically entails the clause
`(!D1 OR ... OR !Dk)`. X2 backtracks one decision and adds this asserting clause.
This is sound even when the residual was simplified by earlier implications.

For SAT SCC leaves, X2 constructs a complete assignment and checks it against
its original stored clauses; the external benchmark checks the **original CNF**
again. X2's general UNSAT results are **not** independently certified on large
CNFs, because DRAT/LRAT proof generation/checking is not implemented yet.

## Compile and run

```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic src/drnas_x2.cpp -o build/drnas-x2
build/drnas-x2 example.cnf --mode core --time 5 --stats
build/drnas-x2 example.cnf --mode backdoor --time 5 --stats
build/drnas-x2 example.cnf --mode x2 --time 5 --stats
```

DIMACS output: `s SATISFIABLE` and a full `v ... 0` witness, or `s UNSATISFIABLE`
or `s UNKNOWN`. Exit codes: SAT=10, UNSAT=20, UNKNOWN=0, error=1.
Telemetry is a JSON record `X2_STATS` on stderr. The process wall time, *including
DIMACS load/verification*, is measured by the benchmark script and counted in PAR2.

## Reproducibility and reporting

```bash
# Requires X1 executable to compare against prior baseline.
g++ -std=c++20 -O3 src/drnas_x1.cpp -o build/drnas-x1
python3 tests/test_x2.py --cases 2500
python3 research/drnas_x2_bench.py --smoke --synthetic-count 64 --smoke-cap 0.35
# Requires third-party references and public SAT2024 range-reader only for benchmark:
python3 research/drnas_x2_bench.py --official --official-cap 5
```

- Tiny correctness oracle: 2,836 different CNFs * 3 modes = 8,508 attempts at
  default seed; full exhaustive truth table for each source.
- Synthetic benchmark: deterministic, source-SHA-distinct, many families;
  mathematical construction checks are **not** substitutes for DRAT/LRAT.
- Retrospective official benchmark: same original 12 SAT2024 CNFs as X1,
  SHA manifest, equal caps, all results include input and wrapper overhead,
  original-CNF SAT witness verification, unverified UNSAT penalized.
  **Not globally blind. No claims of statistical significance from one repeat.**
- X1 and reference binaries may be used by the *benchmark*, but are not part
  of the X2 solver or its executable/decision loop.

Next: benchmark more diverse unseen families, isolate any regressions by clause
width/degree, reduce unnecessary 2-SAT rescans, add checked UNSAT proof trace,
then selectively integrate parity/XOR/GF(2) where benefit is provable.