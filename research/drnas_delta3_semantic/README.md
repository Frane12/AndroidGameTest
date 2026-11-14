# DRNAS Delta3 semantic application: discovery-first, not speed

Goal: independently demonstrate a meaningful application of the REAL SAT2024
hardware-miter source ID30 nonlinear-separator witness.

Original source SHA-256:
ead2a1c2fb44d173d3a24bab1212f07adf571f4fc7563392d434e0f58386939b

The exact joined local relation under x771=0 and x772=0 permits just
(x1,x3,x777)=(0,0,0) or (1,1,1). The join of the separate affine hulls
permits four configurations, so the exact nonlinear join removes one
additional bit compared with the pair of linear approximations.

## Proof-carrying conditional equivalences

These five clauses are present in the ORIGINAL CNF:
  A = [ 1,-3,771]
  B = [-1,-3,777]
  C = [-1, 3,772]
  D = [ 1,-777]
  E = [ 3,-777]

One-step resolution yields two absent-from-source, globally sound clauses:
  resolve(B,C,pivot=-3) = [-1,772,777]
  resolve(A,B,pivot= 1) = [-3,771,777]

The independent script checks each resolvent RUP against all 11331 clauses
of the SHA-frozen original source, not only the two parent clauses.

Combined with original reverse-implication clauses D and E, they prove:
  x772=0 implies x1=x777
  x771=0 implies x3=x777
  both guards imply x1=x3=x777

These are GUARDED equalities, not an unconditional XOR replacement.

## A concrete use

Within this conditioned local component we can represent three variables
with a single equivalence-class representative, reducing eight unconstrained
local combinations to two feasible configurations. The script verifies the
exact local truth table, validates a concrete affine countermodel, and
demonstrates rollback-safe union-find aliasing across decision levels.
Any future integration into CDCL must preserve clause reasons and undo
aliases whenever their guard is undone.

No speed benchmarking, solver promotion, or claim of new mathematical
theorems is part of this experiment. Resolution, equivalence reasoning,
and relational joining are known methods. A genuine novel contribution
would require proving additional applicability beyond existing CDCL/BCP,
binary-implication graph, and local-consistency techniques on unseen sources.

Run the isolated workflow on this experimental branch; it downloads the
frozen real CNF from the previous DELTA3 successful preflight, executes
semantic_use.py, and uploads an independently reproducible JSON certificate.
