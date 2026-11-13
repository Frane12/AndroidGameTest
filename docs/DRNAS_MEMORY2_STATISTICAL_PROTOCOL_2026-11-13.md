# DRNAS X1 MEMORY2 — Statistical validity protocol (13 Nov 2026)

## Why three repeats of 30 formulas are not 90 independent samples

Each original CNF is the sampling/paired comparison unit. Different seeds or
repetitions measure run-to-run stability; they do not multiply the number of
distinct mathematical problems. Different CNFs from one synthetic generator
share a structural source, so a second uncertainty interval clusters by
generator family.

## Pilot: 240 training / 360 holdout / 3 repetitions

- Exactly six training generator families and six disjoint heldout families.
- 360 distinct holdout CNF SHA-256 inputs, 1,080 paired runs per arm.
- Arms: native CORE, instrument-only SHADOW, frozen MEMORY2, MEMORY2 online.
- Independent SAT witness or UNSAT DRUP check for every credited answer.
- End-to-end verified PAR2 (time including independent validation); unverified
  solutions receive 2 x cap. Freeze the model file before holdout.
- Explicitly synthetic; do **not** call it globally blind/real-world proof.

Pilot result: MEMORY2 frozen −4.7018% relative PAR2 reduction (i.e.,
slower); formula-cluster bootstrap 95% interval [−8.8472%, −0.9219%].
MEMORY2 online +1.84% relative PAR2 reduction; formula-cluster bootstrap
95% interval [−4.8296%, +9.8446%], exploratory one-sided paired sign-flip
p = 0.3898. Thus **no supported performance gain**.

A rough variance-based calculation projected about 1,807 distinct instances
to have 80% power for a *hypothetical 5% effect* in the online comparison.
This estimate is distribution-dependent and should not be described as a
guarantee of significance.

## Confirmation: fixed before checking new outcomes

- New separate branch: experiment/drnas-x1-memory2-confirm2400-20261113
- Training: same 240 family-disjoint sources, policy trained only from
  independently certified results.
- Holdout: 2,400 **fresh**, SHA-unique sources from new generator indices
  10,000–10,399 for each of the six holdout families, not the 360 pilot
  sources at indices 0–59. CI independently asserts no pilot SHA overlap.
- Exactly three seeds and four arms: 28,800 paired holdout trials.
- One logical CPU, rotated arm order, identical source and seed for each
  comparison, and a fixed proof-on budget of 0.5 seconds per solver.
- Primary comparison registered before the confirmation run:
  MEMORY2 ONLINE vs X1 CORE. Frozen MEMORY2 and SHADOW are secondary.
- Null hypothesis: no improvement; practical target: at least **5% lower**
  verified PAR2 at a fixed mix of the six heldout synthetic families.
- One primary positive claim only if (i) >=200 distinct CNFs and >=6
  families; (ii) no decrease in verified solved count; (iii) formula-level
  paired bootstrap 95% lower bound >+5%; and (iv) generator-family cluster
  bootstrap 95% lower bound >+5%.
- Report one-sided paired sign-flip p-value as **exploratory** because
  random-sign exchangeability may fail. It is not a substitute for the
  predeclared uncertainty gate.
- Publish all outcomes, even if a regression or a null result.

The family bootstrap draws only six family clusters and cannot justify a
universal generalization claim. A further ***official original-CNF***
benchmark, grouped by genuine competition source family and never used for
learning/tuning, is necessary before claiming a robust solver improvement
outside these synthetic source distributions.

A larger sample reduces uncertainty. It does not force a positive result,
prove a new complexity theorem, or ensure learned structural understanding.
