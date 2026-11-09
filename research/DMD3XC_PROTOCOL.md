# DRNAS DMD3X-C — Conditional Progress Gate (source-only experimental)
Frozen protocol: 2026-11-09. Branch:
\`experiment/drnas-dmd3xc-conditional-progress-20261109\`.

## Primary hypothesis
A locally exhaustive-proof-certified ANF lemma can be useful under a
*branch assignment* despite producing no new unit at root. DMD3X root-UP
gate rejected every lemma on the 24 original CNFs (but not four controls);
DMD3X-all accelerated SHA 5e7c2b214b6a but regressed on SHA
7dc278b4ced0. The separately controlled DMD4test real CaDiCaL trail
study suggests some ANF lemmas alter CDCL work but does not identify
individual causal lemmas or establish broader unseen generalization.

DMD3X-C is designed as a cheap CONDITIONAL BCP novelty selector over
already-certified DMD3X ANF lemmas. No solver-internal live CDCL trail
is observed in this experiment; decision assignments here are
**deterministic controlled clause-derived assumptions**. It is not
valid to report its conditional opportunities as saved solver conflicts.

## Procedure
1. Run unchanged native DMD3X (full-source geometry, 60ms algebra budget,
   max64 groups, `all` mode) and obtain <=24 locally implied clauses.
2. Independently exhaustively replay each candidate using only the exact
   original source-clause IDs; validate augmented CNF is exactly original
   followed by the certified candidates.
3. In a second native C++ process, parse the exact original CNF and
   candidate-augmented CNF, require strict original prefix match.
4. For candidate \`l1 or ... or lk\` with k<=3, for each target \`li\`,
   run watched-literal BCP on the entire ORIGINAL CNF under assumptions
   \`¬lj\` for all j!=i. If the original alone neither contradicts the
   assumptions nor forces \`li\`, adding the candidate would create
   a provably valid **conditional unit implication**. Count directions.
   This is *a utility heuristic*, NOT a proof itself; proof is in step 2.
5. Select at most 8 or at most 16 candidates with positive conditional
   novelty using deterministic ranking plus overlap penalty for
   repeatedly selected variable supports.
6. Recheck selected subset as exact appended original-source lemmas
   with independent exhaustive replay. Deliver either original CNF or
   exact original + selected lemmas to unchanged pinned Kissat.
7. Cond16 shadow runs the identical candidate discovery/filter and
   then supplies the ORIGINAL CNF, so active benefits vs matched shadow
   separate filtering overhead from CDCL algorithm changes.
   Any conditional filter parsing/budget timeout fails closed: no
   selected lemma, original CNF passed unchanged.

## Pre-registered E2E benchmark
24 previously reused EQUIV7 official original source SHA + 4 tiny
synthetic control CNFs, two repeats, seven arms, single logical CPU per
child process, same pinned Kissat 4.0.4, 6-second E2E cap including
all preprocessing and independent exhaustive replay.
Exactly **392 paired trials** in four shards:
- unchanged Kissat original
- unchanged DMD1 15ms active
- unchanged DMD3X full-source root BCP gate, 60ms
- unchanged DMD3X all, 60ms
- DMD3X-C conditional 8 active
- DMD3X-C conditional 16 shadow
- DMD3X-C conditional 16 active

Report PAR2 sum, solved, verified SAT original models, backend UNSAT
**without independent LRAT**, paired gains/regressions, candidate counts,
positive conditional directions, activation counts, time spent probing,
and matching candidate/selection signatures in active/shadow arms.

## Scientific constraints
- Candidate generation is source-only but *selection* is controlled BCP
  of the original, **not** actual CaDiCaL/Kissat CDCL trajectory.
- No proof of net performance absent a paired E2E advantage with shadow.
- Conditional novelty can be an unhelpful implication and does not
  establish lower worst-case complexity or general solver superiority.
- The 24 original competition sources and four controls are REUSED,
  NOT blind holdouts; no automatic production promotion.
- Source provenance/inference checks verify selected lemmas locally,
  not a full independent UNSAT LRAT proof of backend verdicts.
- All measured times include Python/C++ process launch and parsing.
