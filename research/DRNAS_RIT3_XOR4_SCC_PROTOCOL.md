# DRNAS RIT3 — exact XOR4 × SCC structural screen

2026-11-09; experimental branch `experiment/drnas-rit3-xor4-rank-screen-20261109`.
Only **one** 24-original-SHA screening experiment. Zero CDCL/Kissat/CaDiCaL
invocations, no SAT/UNSAT scoring, no edits to original sources or stable main.

## Hypothesis preregistered before results

RIT2 observed 4 overlapping formulas but SCC never raised the rank above GF(2):
24 RUP lemmas tested/accepted, zero distinctly mixed-derived RUP.
Possible missed source motifs are exact 4-variable XOR forbidden half-cubes.
A four-variable XOR is source-certified only when **all 8 different**
clauses of the same four-variable support and forbidden parity appear
on the original SHA-matched CNF. Partial patterns never become equations.
Both parity half-cubes are recorded independently if present.

Compare with the same already-seen original X22 corpus (24 SHA,
`x22-frozen-originals-and-cpp`, run 42591977333; 11.52 MB).
This is retrospective discovery only, **not a blind official holdout**.

## Precommitted gates and metrics

- Two shards of 12 distinct sources, each source once; 9 s per formula
  (8.4 s alarm, hard child timeout 10 s).
- Max 4096 source relations (including XOR4), 12000 row-pairs, 512-bit
  intermediate width, 16 original-CNF RUP checks.
- Preserve SHA before/after. If limit/timeout, record INCOMPLETE,
  not "no improvement".
- GF(2)2/3 row count, independently certified GF(2)4 row count,
  total source GF(2) rank, SCC rank, joint rank.
- `rank_gain_from_xor4 = rank(XOR2/3/4) - rank(XOR2/3)`.
- `rank_gain_from_scc = rank(XOR2/3/4+SCC) - rank(XOR2/3/4)`.
- Short implied algebraic candidates, genuinely joint-only algebraic
  consequences (not in either individual span), separate original-source
  RUP checks, and count of jointly novel RUP clauses.
- Selection tier A: complete original SHA with mixed-only accepted RUP
  or mixed-only algebraic relation; tier B: joint rank gain even if no
  short clause; separately list XOR4-rich formulas.
- Do not claim independently certified UNSAT without LRAT.
- Do not equate RUP failure with invalid GF(2) algebraic consequence;
  also do not append any non-RUP clause to a solver on this track.

## Outputs

Small two-shard JSON, final full JSON, CSV and summary JSON only.
Keep original CNFs and baselines outside output artifact.
If all novel counts zero: report zero, do **not** launch expensive CDCL.
