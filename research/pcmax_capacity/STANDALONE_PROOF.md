# DRNAS standalone standard UNSAT proofs (experimental)

This is an opt-in standalone proof pipeline for DRNAS SAT. It never invokes
Kissat, CaDiCaL, CryptoMiniSat, or another third-party SAT backend to FIND a
proof. The DRNAS C++ source-clause/Hall structure analyzer and Python
mixed-math detector run first. A DRNAS-owned Python proof emitter then generates
DRUP (a subset of DRAT) and DIRECT LRAT hints by bounded source-core DPLL
and reverse unit propagation (RUP). Every proof is checked against the
unaltered original CNF by independent drat-trim, upstream lrat-check,
and a separate strict RUP/LRAT hint verifier.

**Not yet a fully self-contained C++ CDCL binary.** Orchestration and LRAT
emission currently run in Python. The native C++ module supplies a Hall/BDD
structural certificate. Standard checkers are external only for validation,
not proof search.

## One-command usage

After building drnas-pcmax and obtaining drat-trim and lrat-check:

~~~bash
python3 research/pcmax_capacity/drnas_prove.py input.cnf \
  --binary build/drnas-pcmax \
  --drat-trim build/drat-trim \
  --lrat-check build/lrat-check \
  --out results/input-auto-proof \
  --native-budget-ms 1100 \
  --proof-budget-s 3.0
~~~

Result directory:
- result.json: original source SHA, method, proof status, and limits
- proof.drat and proof.lrat: published ONLY after full original-CNF
  verification by three checkers, direct LRAT generated without converter
- discovery/certificate.json: independent structural proof if present
- standalone/producer.json: generator diagnostics even on UNKNOWN

Three possible statuses:
- UNSAT_STANDARD_VERIFIED: full original-CNF standard DRAT/LRAT accepted
- UNSAT_STRUCTURAL_ONLY: mathematical proof checked but standard proof missing
- UNKNOWN: no independent UNSAT certificate; does not mean SAT

Timeouts and size limits never imply UNSAT.

## Reproduction and scope

- [One-command smoke benchmark](https://github.com/Frane12/AndroidGameTest/actions/runs/43704138210):
  four standard-proven UNSAT examples (XOR, 2-SAT, Hall and Hall3/BDD),
  one SAT control, no outside SAT backend.
- [Frozen standalone 153-case audit](https://github.com/Frane12/AndroidGameTest/actions/runs/43703735851):
  61 standard LRAT/DRAT proofs of 105 synthetic UNSAT formulas, of which
  43 were freshly LRAT-hinted from existing DRUP traces and 18 were
  generated from scratch by our own bounded proof search.
- 39 total SAT controls across the two cohorts: zero false UNSAT.
- Eight original PCMAX UNSAT instances structurally proved, zero
  independently standard DRAT/LRAT proved by this standalone emitter.

The proof emitter uses RUP only, not new RAT extension variables.
Large Hall/pigeonhole instances may have very long resolution proofs,
so this prototype currently returns a conservative non-standard result
in those cases. No general solver superiority is claimed.

All original-source hashes, logs and proof files are archived in Actions.
