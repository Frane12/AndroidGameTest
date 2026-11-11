# DRNAS MI-LTM4 — Relational Reasoning Trajectories (experimental)

**Scope:** first usable implementation of cross-formula memory for complete
*paths of algebraic inference*, rather than storing formula-specific clauses.
The current adapter observes **source-certified XOR/GF(2)** operations. It
does **not** yet capture the native CDCL trail, BCP implication graph,
resolution proof, or restart behavior.

## What is actually implemented

- For each original CNF, detect only complete source-certified 2/3-XOR rows.
- Perform bounded GF(2) closure, independently audit every resulting endpoint.
- Represent 2–4-source derivations as a small directed dependency graph:
  certified source rows -> ordered GF(2) combinations -> unit/binary/conflict.
- Canonicalize the source hypergraph under variable renaming and row
  permutation, including changes in intermediate widths. Identical keys are
  *structural matches*, never logical entailment between different problems.
- Store each motif once per original formula SHA in training-only SQLite.
- Optionally associate motifs with real paired native BASE/MI_CHAIN PAR2,
  counted per distinct training formula; no unmeasured motif can become positive.
- Require 8 distinct audited paired formulas, >=70% wins, mean and median
  PAR2 saving >=1.5ms, and no solved-count regression before recommending CHAIN.
- Freeze the memory before SHA-disjoint holdout; never learn from holdout.
- Keep a safety default of BASE for unrecognized, unproven or negative motifs.

## Reproduce

Unit tests:

    python3 -m unittest discover -s mi_ltm4 -p 'test_*.py' -v

Light offline smoke (requires only Python standard library):

    python3 mi_ltm4/diagnose.py --smoke --generation 1

Full 384-original-CNF structure-transfer diagnostic:

    python3 mi_ltm4/diagnose.py --generation 1

Native BASE/MI_CHAIN E2E control, after building the pinned ATLAS15 binary
following the workflow commands:

    python3 mi_ltm4/diagnose.py --smoke --paired --generation 1

CI: [LTM4 workflow](../.github/workflows/drnas-mi-ltm4.yml).

## Interpretation restrictions

- Pure structure diagnostic does NOT establish a performance improvement.
- Native controls compare **ungated** BASE and MI_CHAIN; the offline
  trajectory-extraction cost is excluded from those E2E figures. Therefore
  neither their PAR2 difference nor the inferred route is an LTM4 online win.
- Association of a motif with a faster solver path is not causal attribution:
  other motifs and formula features co-occur.
- Reusing the same held-out CNFs across CI generations is not a fresh blind
  test after the first run.
- No source variable IDs, imported clauses, SAT witnesses or UNSAT verdicts
  are transferred from one formula to another.
- An UNSAT outcome in the algebraic trajectory is only an audited GF(2)
  consequence of source-certified rows, not an LRAT proof of a native CDCL run.

## Next experiment (not implemented yet)

Instrument native CDCL to emit *bounded causal events*, not giant traces:
BCP, decision, learned-clause origin, conflict, restart, proof provenance.
Match cross-method outcome patterns (e.g. reduction -> new unit -> conflict),
then perform a truly prospective, on-line-gated BASE vs LTM4 paired benchmark,
including matching and intervention costs in E2E and PAR2. The stable solver
must remain unchanged until blind improvement is established.
