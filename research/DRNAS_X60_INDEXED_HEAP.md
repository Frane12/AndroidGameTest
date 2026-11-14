# DRNAS X6.0 — indexed VSIDS heap, isolated core upgrade

Experimental development only. No changes to main or frozen X5, no promotion,
no claims about blind holdouts. Based on the existing \`src/drnas_x59.cpp\`.

## What changes
- An opt-in, copy-safe indexed max-heap with **one entry per unassigned variable**
  replaces the lazy heap's duplicate/stale VSIDS entries.
- Operations: insertion or score update O(log n), assignment removal O(log n),
  backtrack reinsert O(log n), rare global activity rescale O(n) heapify.
- Exact ordering from frozen \`Entry::operator<\`: activity + base descending,
  variable index ascending for equal scores.
- \`--x60-indexed-heap\` toggles the ONLY difference in the same executable.
- \`--x60-heap-audit\` checks every free variable and heap ordering for safety;
  enable only in tiny correctness tests, not speed benchmark.
- OFF and ON both run with \`--x59-stamp-glue\`, so LBD optimization is controlled
  and 1-UIP, clauses, watched literals, restarts, proof emission, SAT checking
  are unchanged. Speculative Solver copies own independent heaps.

## Evidence requirements
- Preflight: 30,000 randomized heap operations, score/tie-order comparison,
  then synthetic SAT witnesses and independently checked DRAT UNSAT proofs.
  On completed OFF/ON pairs, identical conflicts/decisions/propagations/learnt.
- Real A/B: 36 previously used SAT Competition 2024 originals, 7 families,
  two repeats, 5-second cap, X60 OFF, X60 ON, frozen X5, Kissat, CaDiCaL.
  All 360 paired attempts on one logical CPU per solver, shuffled arm order.
  Verify SAT witness against original CNF and UNSAT with independent drat-trim.
- Report end-to-end verified PAR2 and family-cluster bootstrap CI95.
  Timeouts count 2x cap; unverified UNSAT never credited.
- This is retrospective; new family-disjoint blind data is required before
  promotion. A successful workflow is **not** itself evidence of a speedup.

## Links
- Branch: experiment/drnas-x60-indexed-vsids-20261114
- Core: src/drnas_x60.cpp
- Heap: src/drnas_x60_indexed_heap.hpp
- Tests: tests/test_x60_indexed_heap.cpp, tests/test_x60_indexed_heap.py
- Benchmark: research/drnas_x60_indexed_heap_real36.py
- Workflow: .github/workflows/drnas-x60-indexed-heap.yml
