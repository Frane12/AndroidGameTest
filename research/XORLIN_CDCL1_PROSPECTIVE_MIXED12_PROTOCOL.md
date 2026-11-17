# DRNAS XORLIN-CDCL1 V2 — resource-revised original GBD mixed12 prospective evaluation

**2026-11-17.** This is a separate experimental branch, not main.
V1 selection was locked at commit `bc2fac2beccfb333f147c1b6d605234c2dcdbdc8`
before any original source downloads or solver outcomes.

## Transparent V2 pre-solver resource amendment

Original V1 runs
[44070338062](https://github.com/Frane12/AndroidGameTest/actions/runs/44070338062)
and [44070631698](https://github.com/Frane12/AndroidGameTest/actions/runs/44070631698)
failed **before any solver trial**: first from an audit-only Python import
collision, then a pre-solver source size check when ID3 decompressed
above the fixed 50 MB limit. ID4 also had compressed source size
metadata suggesting a large decompressed input. V1 remains a recorded
unsuccessful preflight, not a completed holdout.

A **new, separately committed V2 source list**
`de3cf2b8e46c5d4620d4240932ff6c69273fd0dd` retains ten
original identifiers and changes only IDs 3 and 4 before any
solver performance measurements. They are different source originals
from public GBD metadata. The V2 run is performance-blind to these
selected originals, not fully blind to source resource metadata.
Original algorithm, reference binaries, 8s cap, one-CPU condition
and 20/50 MB file limits remain unchanged.

## Purpose

Test the previously certified **one native executable, one PID,
single logical CPU** with an in-process embedded CPython XORLIN1
GF(2) standard-proof gate and the unchanged intrinsic C++ X59
CDCL fallback, compared feature OFF and ON and to frozen
Kissat/CaDiCaL/CryptoMiniSat on *unseen instances*.

**Not** a new mathematical C++ port: the XORLIN1 proof generator
remains the SHA-locked embedded Python code. This is prospective
at **source-instance level only**; selection uses public GBD metadata.
It is not family-independent, globally secret, or a proof of
general SAT superiority.

## Candidate/reference freeze from prior successful run

Immutable source/binary/proof archive is copied from original completed
GitHub run
[44065020804](https://github.com/Frane12/AndroidGameTest/actions/runs/44065020804).
Its subsequent audit-only repair
[44068859741](https://github.com/Frane12/AndroidGameTest/actions/runs/44068859741)
independently rechecked 8 standard VeriPB and 2 DRAT UNSAT proofs
and reported 120/120 original paired attempts, 0 critical.

The same **already-tested** C++ executable binary has SHA-256:
\`2046aee7f7cb1eb3dfc44b2e7a7b5a9f69b482230f106a4aaea93ab968f60646\`.
Its C++ source is SHA:
\`19d55c9e39fd876e70a7617bd6ec12d4b2bdafb1dc23f3c1f45573e817c36a56\`.
Embedded \`extract.py\`, \`emit_veripb.py\`, independent
\`check_math5.py\`, standard checkers and all baseline binary
SHA-256s are compared to the prior certified protocol. No
algorithmic parameters or source code from prior solver tests
may change. Gate budget 700ms, max 500KB source for mathematical
scout, 8s total E2E (including verifier), no parallel solver.

## Frozen original GBD source sample — source-identity disjoint

**12 source originals from 10 catalog families**, six catalog SAT
and six catalog UNSAT. The exact 32-character GBD IDs, isohash,
isohash2 and selected filenames were committed before the
test, with two shuffled repeats per source:

| ID | Catalog family | Catalog label | GBD filename |
|---:|---|---|---|
| 0 | hamiltonian | SAT | x9-04045.sat.sanitized.cnf.xz |
| 1 | uniform-random | UNSAT | unif-c1275-v300-s428434218.cnf.xz |
| 2 | agile | SAT | bench_3169.smt2.cnf.xz |
| 3 | subsumptiontest | UNSAT | DivU_545_9.cnf.sanitized.cnf.xz |
| 4 | subgraph-isomorphism | UNSAT | SGI_30_80_29_60_7-dir.shuffled-as.sat03-217.cnf.xz |
| 5 | bitvector | SAT | g2-newton.8.3.i.smt2-cvc4.cnf.xz |
| 6 | bitvector | UNSAT | bvslt_13916.cnf.xz |
| 7 | station-repacking | SAT | 43-116107.cnf.xz |
| 8 | uniform-random | SAT | unif-k5-r21.3-v120-c2556-S1963731659-060.cnf.xz |
| 9 | diagnosis | UNSAT | dated-5-13-u.cnf.xz |
| 10 | random-graph-xorsat | SAT | mod2c-rand3bip-sat-230-1.shuffled-as.sat05-2503.cnf.xz |
| 11 | miter | UNSAT | 6s16.cnf.xz |

Database source: <https://benchmark-database.de/?context=cnf>

Catalog labels and \`minisat1m\` columns guided the **metadata-only
sampling** but are **not independently accepted proof labels**.
Solver inputs are raw original CNF contents only. SAT only counts
after complete original-CNF model checking. UNSAT only counts after
an independently accepted original-CNF DRAT/FRAT or standard VeriPB
certificate. No false answer is tolerated.

Before any solver trial, the source freezer must compare GBD
IDs, both GBD isohashes and actual decompressed SHA-256
to **all 119 prior frozen originals** from six manifests
(67+10+10+10+12+12). Selection is invalid if any overlap exists.
All 12 original CNFs are bounded (20MB archive / 50MB
decompressed) and SHA-frozen before trials. If any source
unavailable or resource-ineligible: **abort the whole test**,
record failure; don't silently replace instances.

## Strict evaluation and gate

Five serial arms per paired trial:
\`HYBRID_ON\`, \`HYBRID_OFF\`, \`Kissat\`, \`CaDiCaL\`,
\`CryptoMiniSat\`. Same tested binary ON and OFF.

12 originals × 2 repeats × 5 arms = **120 attempts**, four
shards, three sources/shard, all arms serial inside a shard.
Cap 8 seconds for source SHA, integrated math/C++ solver,
post-solver independent model/proof verification, all overhead;
timeout/unverified = PAR2 penalty **16s**. Keep strict proof
kinds distinct and count false UNSAT as critical.

Preflight reruns the prior 24 GF2 standard UNSAT/48 known-SAT
controls and frozen algorithm SHA checks, *before downloading
the newly selected CNFs*.

Freeze then export:
- \`research/xorlin_cdcl1_prospective_mixed12/inputs/manifest.json\`:
  each exact original SHA-256, bytes, clause count and reference
  hashes; purely source-bound before performance.
- \`results/xorlin_cdcl1_prospective_mixed12/protocol.json\`:
  exact algorithm, reference and proof verifier SHA fingerprints.
- Per-shard SHA-bound JSONL, accepted VeriPB/DRAT proof artifacts;
  all missing/duplicate attempts and invalid SAT/UNSAT are
  fatal, including contradictory models/proofs.
- \`results/xorlin_cdcl1_prospective_mixed12/final.json\`:
  strict verified coverage, strict PAR2 and ON/OFF
  solved-to-unsolved regressions for all 120 attempts.

This is **not** a new implementation of GF(2) math, a general
complexity result, or a reason to promote anything to main without
further mixed-source regression and proof audit.
