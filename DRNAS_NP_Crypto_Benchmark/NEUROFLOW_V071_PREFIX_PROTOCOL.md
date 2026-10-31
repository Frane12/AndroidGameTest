# DRNAS NP v0.7.1 — Bounded CNF prefix filter before real CaDiCaL

## Status and scope
**Experimental, same CaDiCaL binary as v0.7.** Tests:
https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-np-v071-prefix.yml

Problem found in measured v0.7: on 60 existing independently published
CNFs, NeuroFlow did not recognize any Horn structure and generally slowed
down plain CaDiCaL. Existing v0.7 parses the entire DIMACS to compute
structural features even when it subsequently rejects the formula.

v0.7.1 adds a bounded **prefix rejector**, not an extra SAT solver:
1. If policy is disabled or caller supplies n < 30, call plain CaDiCaL
   immediately, reading no prefix.
2. Otherwise read at most 32KiB of the original DIMACS, examining at most
   160 complete clauses. Count sign frequencies and unit clauses.
3. If sample includes a unit clause, or if sample covers >=65% of variables
   and has very high minority-polarity density (>0.335), consider this
   unsuitable for the **frozen** v0.6.2 Horn policy: call CaDiCaL directly.
4. If insufficient or ambiguous input, fall open to the existing FULL
   verified v0.7 renamable-Horn check, not a false inference about SAT.
5. If promising, run the unchanged v0.7 analysis. A successful early
   prefix check never itself licenses a Horn shortcut. Only a proved
   renamable-Horn transform permits the exact Horn algorithm. Otherwise
   the same original CNF is handed to identical CaDiCaL.

The prefix thresholds were fixed *before* the benchmark; no training on
external answers. This is a routing heuristic: it can miss potentially
beneficial Horn cases, although it can NEVER cause an incorrect SAT/UNSAT
response because every bypass uses the exact CDCL backend.

## Evaluation

- 60 source-pinned previously published third-party CNFs, repeated from
  the v0.7 study for an A/B regression (NOT presented as a fresh,
  never-seen set).
- 36 new separately labelled synthetic controls.
- 3 repeats, rotating order, for four variants: plain CaDiCaL; old
  v0.7; prefix v0.7.1; always-run Horn.
- CryptoMiniSat independently checks satisfiability if it finishes.
- Full wall time includes prefix scans, full parse if performed, exact
  Horn probe, subprocess startup and witness validation.
- Matching solved pairs only for median speed, with explicit completion
  rates and timeout counts; do not pool control speedup as evidence for
  generic SAT.
- Required regression: at least eight of twelve previously unseen
  positive constructed Horn controls must still be recognized.
- Exhaustive small-CNF equivalence test checks SAT/UNSAT and satisfying
  witnesses in all routes, and the existing old mathematical regression
  suite is rerun.

## Explicit limitations

A prefix sampled heuristic is not a mathematical proof of not-being-Horn.
It can only skip an optional acceleration, never change the answer. Its
cost is nonzero, and the benchmark may show that it is still slower
than calling CaDiCaL alone. For substantial general-purpose speedups,
upstream in-process integration into a modern CDCL solver would be
needed; one extra Python read/process is potentially too costly for
millisecond-scale SAT formulas.
