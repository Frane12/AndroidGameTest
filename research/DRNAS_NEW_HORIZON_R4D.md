# DRNAS New Horizon SAT R4d — 384-byte suffix veto

## Why R4d
The complete R4c audit (run 42327577985, 1152 paired runs)
showed that a single sparse-density threshold **overfit**:
R4c removed overhead on misleading source prefixes, but lost valuable
source-exact sparse 2-SAT acceleration. Frozen R4b remained faster
overall. Thus a density threshold alone was rejected.

## Proposed improvement
Before an optional 2-SAT source-complete parse, inspect **only the last
384 bytes of original DIMACS**. A source token sequence with a complete
clause bounded by explicit 0 terminators containing >2 distinct signed
literals permits immediate *abstention*, because the raw original source
is not source-wide 2CNF.

- This is a **negative-cost observation**, NOT a proof of SAT or UNSAT.
- A suffix without such a clause does NOT certify 2-SAT.
- If no suffix veto, R4d still streams and fully checks every original
  clause before SCC; if positive, original SAT witness is checked.
- If the suffix preview is ambiguous or malformed, no positive inference
  is made. Full-source gate or unmodified CaDiCaL is used.
- A misleading clause buried in the middle and not in the 384-byte
  window can still cause wasted scanning. That limitation is tested.
- Pure source-exact XOR3/GF(2) is unchanged and certified. Sparse valid
  2-SAT is still considered; no density threshold excluding it.
- Native CDCL UNSAT results lack independent LRAT/FRAT verification.

## Controlled test
Identical SHA-frozen R4c 72 formulas reused verbatim plus 8 deterministic
middle-clause misleading examples. Four repetitions, five same-source
methods: clean, XOR-only, frozen R4b, frozen R4c, proposed R4d.
Total: **80 formulas, 1600 SHA-paired trials**.

The same CaDiCaL 2.1 executable SHA as the prior four New Horizon runs.
All screening, source checking and fallback solver time is counted.
Final audit refuses source SHA drift, missing arms, inconsistent PAR2,
or any opposing successful SAT/UNSAT.

This experiment is **NOT blind external industrial SAT**; families were
already seen. A source-suffix veto can add small overhead even where
the solver would have succeeded quickly. Favor evidence, not merely
theoretical linear-time characterization. Do not merge until audit.

## Source
- research/new_horizon_r4d.py
- research/new_horizon_r4d_benchmark.py
- .github/workflows/drnas-new-horizon-r4d-tail.yml
- Frozen R4c source manifest SHA:
  c8931d34ef876bd2ebabdda965492801142596412d0dee7b7e84f6d317e598f3
