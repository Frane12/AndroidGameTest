# DRNAS LEGO-2 — proof-carrying relation LEGO grammar, 5s targeted evaluation

New experimental branch only: experiment/drnas-lego2-positive-real-short5-20261109.
Stable main, X22, X24, and LEGO-1 remain unchanged.

## Why this experiment

LEGO-1 passed proof self-tests but had **zero** learned relation fingerprints
from eight repeated real SAT sources and **zero** added clauses on evaluation.
A test with no training signal cannot tell whether the learning machinery
works. LEGO-2 supplies positive, negative, and real-source controls to
separate structural detection from actual SAT speed.

## Train/eval split (frozen before timing)

Train on eight deterministic synthetic positive relation systems, no
evaluation outcomes. Frozen relation fingerprints store an empirical
**structural reachability proxy** only, never solver time, SAT labels, or
learned assertions. Six disjoint generated positive evaluation sources
use different variable permutations and polarities, clause shuffles,
and noise. Two negative evaluation sources have missing XOR half-cube
clauses and incomplete implication cycles: no fake inferred relation
is permitted. Four original real SHA SAT sources are recycled from the
X22 original-source roster, as a separate real-world diagnostic,
NOT a new blind holdout.

Generated positives contain a deliberately compositional motif:

* parity(x1, x2, x3)=0
* parity(x2, x3, x4)=0
* original CNF binary implication paths proving x4 <=> x5
* another binary implication SCC path proving x5 <=> x8

This yields a relation x1 <=> x8 after multiple compositions,
rather than relying on superficial clause counts or invented "XOR hints".
Every source cube is independently checked on ORIGINAL CNF, both
implication paths are checked on ORIGINAL binary clauses, and
every GF(2) combination is recomputed from its source-leaf IDs.
Only verified short consequences can be appended as redundant clauses.

Polarity permutation is applied consistently to clauses and a planted SAT
witness, which is checked before freezing each generated source.
Generated controls are satisfiable by construction; an UNSAT claim on
them fails the audit. Original real-source UNSAT only counts if the
frozen X22 original Kissat+CaDiCaL agreement says UNSAT; **not LRAT**.

## Small/fast protocol

Four arms: original 2-CPU Kissat+CaDiCaL race, frozen X24 GF(2),
LEGO static grammar, and LEGO ranked by frozen training-only table.
Twelve evaluation CNFs x two repetitions x four arms = **96 paired**
end-to-end measurements split across four parallel shards.
Strict **5 seconds wall** per measurement including preprocessing;
PAR2 10-second penalty for failed/uncertified solve.
Native GF(2) extraction timeout 0.65 s; LEGO preprocessing
soft budget 1.1 s; fail closed on over-budget or invalid proof.
Source SHA, binaries, time, proof counts, number of *new* implied clauses,
unsolved cases, CPU and SAT witness correctness are audited.

## Interpretation

Positive-control proof detection is a **functional** requirement.
No synthetic result should be promoted as real SAT generalization.
Both synthetic and reused real cohorts are reported separately.
Improvement means lower real held-out paired E2E PAR2, not just more
relations or fewer child CPU seconds. A learned table that behaves
identically to static must not be called successful adaptive learning.
No automatic promotion.
