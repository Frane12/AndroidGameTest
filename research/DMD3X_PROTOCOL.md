# DRNAS DMD3X — full-source structural ANF with native root-BCP gate
Date: 2026-11-09. Experimental branch only. No main/frozen changes.

## Hypothesis
DMD2's Python controller often exhausts its soft time budget before scanning
the first local ANF bag; it also scans only 36 groups from selected clauses.
DMD3X uses one native process per formula to parse once and select candidate
local bags throughout the original CNF, guided by *source-only* unit,
binary implication and potential gate topology. The source-only priority is
heuristic, not a proof that a family is AND/XOR.

An independent whole-original-CNF Boolean unit-propagation comparison
determines whether proved clauses cause genuinely additional root units or
a newly detected root contradiction. This is a stronger diagnostic than
DMD2's first-1200-clause view, but it does NOT prove reduced CDCL conflicts
or less total SAT search.

## Implemented operators and safety
- Reuse exact DMD1 bounded degree-2 GF(2) ANF nullspace algebra as compiled
  source, but with a source-wide spatially diversified seed selector.
- Mine up to 64 connected bags/attempt, each of at most eight variables.
  Search 512 source-selected seed clauses, 8 source regions, and variable
  occurrence neighborhoods, not just the first 1,200 clauses.
- Extract short locally implied units, equivalences, and ANF-derived CNF
  lemmas. Every appended lemma records its **original clause IDs** and
  is independently replayed by exhaustive truth table enumeration of the
  exact original source bag. Original source clauses remain unchanged.
- Execute a full-original-CNF root Boolean unit propagation pass before
  and after candidate lemmas, within a separate 200ms soft probe cap.
  The *gate* arm outputs lemmas only if there is a newly forced root unit
  or newly discovered root conflict. The *all* arm appends every verified
  lemma. A *shadow* arm runs the same gate and passes the original CNF
  unchanged to the solver. Thus the role of proof validity is separate
  from the choice whether to activate a proof.
- Real elapsed time includes parsing, full BCP, ANF work, proof replay,
  solver and I/O; 20/60ms algebra budget is checked after parsing and
  source feature indexing but entire overhead still counts to E2E.
- Every SAT result checked against the original input CNF. UNSAT backend
  results lack independent LRAT verification and MUST be labeled so.
- CPU policy: one logical CPU pinned to every child process; no concurrent
  solver portfolio for a single trial. The original source SHA is frozen
  from the previously tested EQUIV7 set.

## Comparison
24 reused original official competition CNF SHA plus four tiny
synthetic proof controls, two repeats, seven arms, six-second end-to-end
cap, four shards, **392 E2E measurements**:
1. Plain pinned Kissat on original
2. DMD1 15ms active (frozen comparison)
3. DMD2 20ms procedural active (frozen comparison)
4. DMD3X native 20ms global BCP gate active
5. DMD3X native 60ms global BCP gate shadow
6. DMD3X native 60ms global BCP gate active
7. DMD3X native 60ms all proved clauses active

All preprocessing, including independent lemma replay, counts toward
E2E. PAR2 timeout penalty is 12s for each 6s trial.

Report per shard and aggregate: solved, verified SAT, backend-only
UNSAT, cumulative PAR2, prep overhead, number of proof-checked
candidate and activated lemmas, root BCP novelty, causes for empty
output, regressions and speedup vs same pinned Kissat.

## A priori limitations
- Source selection uses structural heuristics that may miss important
  clauses, and root BCP novelty is not necessarily a useful predictor
  of later CDCL performance.
- Extra clauses can change Kissat search order; only randomized paired
  comparisons with a shadow, repeated on held-out original SHA, can
  support claims of net benefit.
- An ANF fact already entailed by original CNF can still be nontrivial
  under branch-level assignment even if it produces no root unit.
- Not a blind set. No claims of broad SAT solver superiority and no
  automatic promotion to main.
