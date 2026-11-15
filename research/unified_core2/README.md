# DRNAS UNIFIED CORE2: development experiment

CORE2 is a deliberately narrow A/B candidate based on CORE1. Its only solver
behavior change is the default shared guard budget: 50 ms instead of 100 ms.
The existing `--unified-ms` option still overrides the default. Module order,
per-module caps, checks, source size guards, proof semantics, binary DRAT default,
and the single native CDCL process are retained. A smaller shared budget can miss
proofs or models that CORE1 finds; this is a hypothesis, not a proven speedup.

Build with `python3 research/unified_core2/build.py`, then run
`python3 research/unified_core2/test.py`. The test suite checks SAT models,
structural certificates, independent DRAT validation when available, corruption
controls, and isolated BDD and ARG3. The frozen CORE1 binary is not overwritten.

The new workflow reuses the 67 previously examined original CNFs and the exact
frozen CORE1, Kissat, CaDiCaL, CryptoMiniSat and checker binaries from run
43717935841. CORE2 is built afresh, so compiler and build environment differences
from the frozen CORE1 binary are a potential confound; both hashes are recorded.
Five arms run in shuffled paired order, twice per source, with 8 s including
verification, one logical CPU per trial, and compact live progress. The 670 trial
rows, protocol, hashes and aggregates are retained. Structural and standard-only
scores are separate. Temporary individual proofs are checked and hashed but are
not retained in this workflow.

This is development and regression evidence, not a new blind holdout; the same
sources informed the choice of budget. Report solved-to-unsolved regressions and
compare against CORE1 as well as each reference. A green workflow only means it
completed. No automatic promotion or changes to main are authorized. Promotion
requires the previously specified independent source/family-separated holdout,
proof validation, zero invalid answers, review of regressions and at least 10%
verified PAR2 improvement against the best reference under the stated standard.
