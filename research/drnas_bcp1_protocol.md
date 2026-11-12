# BCP1: native propagation on the known real-instance gaps

Frozen parent: f5e7ea76f0b0ea6dedc0db30ba1befceba47400b.
Hypothesis: avoid clause memory loads when a cached clause literal is true;
then test whether a complete circular scan reduces repeated work on long clauses.
This is a propagation implementation experiment, not a new learning claim.

BASE is the exact unmodified R153/native composite. BLOCKER activates its existing
conditional blocker cache. CIRCULAR adds a per-clause scan cursor to BLOCKER.
Both also guard no-op compaction before moving live clause vectors. Stress testing
exposed this latent boundary bug; ordinary reduction already calls compaction only
when tombstones exist, so it is not evidence of a prior benchmark mis-solve.
Both retain R153 exact algebra, the same 50 ms gate, native learning profile FAST,
KEEP50, selective GF2, seeds, and empty cross-formula memory. Frozen binaries and
source hashes must remain unchanged. Candidate code never calls a reference solver.

12 original SAT2024 CNFs are pinned by filename and SHA256 before the run:
REAL24 IDs 1/7/20/21 are known gaps; 0/3/6/9/12/15/18/23 are fixed spread controls.
These are retrospective and potentially seen. They are not an unbiased leaderboard
or unseen holdout. Include 8 separately labeled synthetic algebra/PHP/3SAT controls.
6 arms: BASE, BLOCKER, CIRCULAR, Kissat 4.0.4, CaDiCaL 3.0.1, packaged CryptoMiniSat
(record exact package version and binary SHA). One logical CPU, serial randomized
arm order, 3 paired seeds, 8s real / 2s synthetic full-process cap: 360 trials.

External wall limit includes launch, parsing, reduction and output. Validation runs
afterward with its time recorded separately. Original SAT models and source-derived
GF2/PHP UNSAT certificates are independently checked. Other UNSAT remains explicitly
unverified; report both PAR2 columns. UNKNOWN/timeout/unverified in strict score = 2*cap.
Stop on bad models, contradictory claims or process errors. Save compact validated
outputs, manifests, telemetry, per-source/per-shard totals and comparisons to BASE.

Correctness: existing native brute-force suite; 640 additional mixed formulas per
variant against exhaustive truth tables; real production deletion/compaction with
locked reasons; UBSan; existing 285 composite/profile checks per variant, original
GF2/PHP proofs, forged-proof rejection and outer-deadline check.

No automatic promotion. A candidate must subsequently show >=30% lower verified
PAR2 than the best reference on a frozen, independent family-disjoint holdout, while
preserving verified coverage and the R153 algebraic controls. Treat repeated trials
as within-source measurements, not additional independent formulas.
