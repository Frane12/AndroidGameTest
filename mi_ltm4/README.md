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


## LTM4.1 native trace pilot (added)

Implementation: live_cdcl.py, live_store.py, live_bench.py, tests in
test_live_cdcl.py and test_live_store.py. Workflow: drnas-mi-ltm41.yml.

- Build two variants of the same native DRNAS ATLAS15 CDCL source: ordinary
  control and -DDRNAS_MICRO_TRACE passively instrumented diagnostic.
- Capture bounded, actual native decision, assignment, conflict and learned
  clause events. REDUCE2_NODE and REDUCE2_EDGE provide real native reason
  dependencies for the original small-n sampling window.
- Form observational episodes spanning the decision, BCP, conflict and 1-UIP
  learning boundary. These reflect actual native CDCL steps, but temporal
  adjacency alone is NOT causality.
- Compute a bounded directed WL-style reason-graph fingerprint, preserving
  node type, width, and incoming/outgoing dependencies but not clause IDs.
  The fingerprint may collide and is NOT an isomorphism certificate.
- Store TRAINING ONLY native motifs and co-occurring original-source-certified
  XOR trajectories; freeze before evaluating SHA-disjoint holdout formulas.
  Across GitHub runs, training CNFs change with the run generation.
- The native motif policy ALWAYS returns BASE. We never inject any carried
  learned clause, unverified XOR relation or SAT/UNSAT outcome.
- Source SAT models are verified against original CNF; source UNSAT relies on
  independent source GF(2) contradiction checks, NOT general LRAT.

Reproduce, after the native builds in the workflow:

    python3 -m unittest discover -s mi_ltm4 -p 'test_*.py' -v
    python3 mi_ltm4/live_bench.py --generation 1

The default pilot selects one training and one frozen holdout formula per
six synthetic families (12 original CNFs). Each native binary gets 2s,
one logical CPU. Use --full for 48 original formulas.

IMPORTANT EVALUATION RESTRICTIONS:
- Passive instrumentation adds stderr overhead. Its runtime is not a measure
  of LTM speedup.
- Offline XOR scanning time is outside the native E2E measurement.
- Co-occurrence within a formula is NOT evidence of a causal link.
- Native reason-graph traversal is restricted to n<=50, selected conflicts;
  event output is capped at 10,000 native micro events.
- An online CDCL intervention based on matched cross-representation patterns
  and a prospective full-cost PAR2 benchmark remain NOT implemented.
