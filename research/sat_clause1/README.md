# SAT-CLAUSE1: from UNSAT structure to SAT phase guidance (experimental)

This is an ablation pilot, not a new SAT theorem, an official SAT Competition
result, or a promotion decision. It probes whether information extracted cheaply
from unresolved original CNF clauses can change a native CDCL decision sign
and decrease verified SAT end-to-end time.

- OFF: native X59 reference, original branch policy.
- CLAUSE_SCORE: original-clause residual-width weighted polarity score
  (a known Jeroslow-Wang-like idea, not claimed novel).
- CLAUSE_PROBE: CLAUSE_SCORE plus, on a small original, two bounded
  in-process BCP assumptions. Only actual contradictory assumptions affect sign.
- All options retain the same conflict analysis, propagation, learning and
  complete SAT model verifier. The new heuristic cannot assert UNSAT or SAT.
- Gate: first 16 decisions, only decisions 1,5,9,13; <=1,200 variables
  and <=15,000 source clauses; 2 ms scanning cut-off and a 5% accumulated
  wall-budget guard. Probe pair only at decision 1 on <=800 variables,
  <=8,000 clauses, and under 1 ms prior scoring.
- No solver portfolio, no external solver, one logical CPU.
- Independent model verification checks every original clause.
  A wrong model or UNSAT on a known-SAT source fails the experiment.
- Compact per-family summary; complete JSON artifacts saved separately.

The benchmark creates 48 constructed SAT formulas from four families:
planted 3-CNF, graph 3-coloring, consistent parity/XOR, and resource
assignment. Two paired timing repetitions per source/arm, 288 trials.
Each trial has 1 second including solver execution, startup and independent
model checking. Timeout/non-verified costs 2 s PAR-2. These are development
formulas, not prospective or competition performance.

Important interpretation: "which sign immediately contradicts CNF" and
"which sign leads fastest to SAT" are different quantities. Local clause
satisfaction does not imply global progress. A speedup is demonstrated only
with verified models, per-case costs and matched timing. For a robust claim,
repeat on frozen original SHA-disjoint SAT Competition inputs with matched
Kissat/CaDiCaL/CryptoMiniSat and significant per-family PAR-2 improvements.

Reproduce:
  g++ -O3 -std=c++20 -DNDEBUG src/drnas_x59.cpp -o build/drnas-sat-clause1
  python3 research/sat_clause1/benchmark.py

The default branch, frozen references, and historical experiments are untouched.
