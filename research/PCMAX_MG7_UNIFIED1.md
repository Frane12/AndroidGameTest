# DRNAS PCMAX + MG7 Unified 1 — evidence-first experimental target

**Branch only:** experiment/drnas-pcmax-mg7-unified1-20261116. No changes to \`main\`. No background solver, portfolio, extra CPU, subprocess or Python inside the native solver.

This is the **first real single-process union of two currently certified components**, not a complete PCMAX algorithm:

1. Bounded native PCMAX BDD capacity extraction (structural weighted UNSAT certificate).
2. Native CDCL fallback with opt-in residual SCC analysis and DRAT RUP additions.

A third proposed component — generalized integer packing/parity global-conflict proof search — **is NOT yet integrated or independently certified** and must not be claimed as implemented.

## Build

\`\`\`sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target drnas-pcmax drnas-mg7-scc drnas-pcmax-mg7-unified -j2
\`\`\`

Requires OpenSSL::Crypto for the unified target.

## Run

\`\`\`sh
./build/drnas-pcmax-mg7-unified original.cnf \
  --mode core --time 5 --stats \
  --pcmax-capacity --pcmax-budget-ms 1000 \
  --pcmax-certificate original.capacity.json \
  --residual-scc --proof original.drat
\`\`\`

**The two outputs are not interchangeable.** The solver prints an explicit certificate kind.

* If \`c PCMAX_UNIFIED_PROOF_KIND CAPACITY_JSON_NEEDS_VERIPB\` appears with \`s UNSATISFIABLE\`, the \`*.capacity.json\` is authoritative only after the independent structural checker re-reads the original CNF and an independently generated PBP is accepted by VeriPB 3.0.2. An empty \`*.drat\` is expected on this branch of execution and is **not** a DRAT proof.
* If \`c PCMAX_UNIFIED_PROOF_KIND DRAT_PROOF\` appears, the BDD gate did not return a structural proof and the solver performed ordinary native CDCL with bounded MG7 SCC. On UNSAT, only a complete DRAT proof accepted by drat-trim is counted.
* On SAT, verify the returned full model against every clause of the unchanged original DIMACS.
* On UNKNOWN, retain UNKNOWN regardless of intermediate hints and incomplete proof files.

Existing standalone \`drnas-pcmax\` and \`drnas-mg7-scc\` retain their prior behavior. The combined proof mode is compiled only with \`DRNAS_PC_GUARD_COMBINED\` in the new target, and is not switched on automatically.

## Soundness and limitations

The native capacity guard already checks the source-bound BDD premise and weighted capacity before writing its immutable structural JSON. The MG7 residual SCC re-extracts residual binary/unit source clauses under the current CDCL trail, then writes witness-guarded RUP clauses that an external DRAT checker must independently accept. A consistent 2-CNF subformula never implies that a mixed CNF is satisfiable.

Neither method is complete for all PCMAX instances or all CNF encodings. No guarantee is made about performance, overhead or the novelty of the mathematical inequalities.

Benchmark harness: \`python3 -u research/pcmax_mg7_unified1.py\` checks the combined and independent BDD/SCC arms serially with one logical CPU each on frozen original PCMAX cases plus synthetic controls. This is a **retrospective family-targeted pilot, not blind PAR2**.

Promotion conditions: accepted external proof on every claimed UNSAT, valid models on SAT, no false answers, preserved deterministic frozen references, verification-inclusive PAR2 on a prospective source-disjoint holdout and low or no regression. Do not merge into \`main\` automatically.
