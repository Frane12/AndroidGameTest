# DRNAS — NEW UNSEEN GRAPH CNF pilot, SAT Competition 2025 Main

Research date 2026-11-16. This is a **source-level prospective,
preselected graph-family holdout** following development work on
SAT Competition 2026 Reeves graph-coloring CNFs.

Branch: experiment/drnas-graph-unseen-2025-holdout1-20261116
No modifications to main or frozen reference solver binaries.

## Prespecified originals — NOT our generated puzzles

Exactly ten distinct GBD identifiers, chosen from the official
[Global Benchmark Database SAT Competition 2025 Main](https://benchmark-database.de/?context=cnf&track=main_2025)
by *source family, submission provenance, and GBD identifier only*,
without executing DRNAS or Kissat, CaDiCaL or CMS.
All ten original hash IDs were committed in
\`research/graph_unseen25/prespec.json\` **before any solver trial**.

The source families and metadata:

| ID | GBD family | GBD author | Original filename |
| --- | --- | --- | --- |
| 0 | clique-coloring | anders | clqcl_100_6_5.normalised.cnf.xz |
| 1 | clique-coloring | anders | clqcl_30_7_6.normalised.cnf.xz |
| 2 | clique-coloring | anders | clqcl_50_6_5.normalised.cnf.xz |
| 3 | clique-coloring | anders | clqcl_30_11_10.normalised.cnf.xz |
| 4 | clique-coloring | anders | clqcl_40_6_5.normalised.cnf.xz |
| 5 | clique-coloring | anders | clqcl_30_9_8.normalised.cnf.xz |
| 6 | coloring | oertel | cliquecoloring_n26_k7_c6.cnf.xz |
| 7 | coloring | oertel | cliquecolouring_n15_k7_c6.sanitized.cnf.xz |
| 8 | coloring | oertel | cliquecoloring_n14_k7_c6.cnf.xz |
| 9 | coloring-clique | yldirimoglu | cliquecoloring_n32_k5_c4.cnf.xz |

The six \`clique-coloring\` originals were submitted in 2025 and
have GBD \`submissions_2025\` provenance. The other four are from older
submissions that are present in the 2025 Main track. The exact
GBD hashes AND GBD isohashes are pinned in \`prespec.json\`.
An ID5 GBD metadata typo was corrected against the public catalog
**before any solver evaluation**; the filename and intended selected
instance never changed.

### What "unseen" honestly means here

* All candidate normalized GBD hashes AND isohashes must be absent
  from the previously frozen 67 original SAT2026 source manifest.
* Selection and comparison matrix are committed before downloading
  inputs or testing any solvers. Download success or parser budget
  cannot guide replacing an instance; if ANY of the ten is unavailable
  or exceeds the preset bounded source limits, freeze fails closed.
* New GBD family labels versus the 2026 Reeves \`graph-coloring\` family,
  and six specifically new 2025 submissions, provide an informative
  out-of-distribution check.
* We **cannot guarantee** a formula was never run in every earlier
  DRNAS experiment branch or by other researchers. SAT Competition
  2025 Main is already public, not secret competition holdout.
* Ten sources across only three catalog families is a pilot, not a
  statistically powered generalization/world-ranking result.

### Freeze-before-solve mechanism

\`research/graph_unseen25/freeze.py\` downloads the unchanged
benchmark instance via
\`https://benchmark-database.de/file/<GBD_HASH>?context=cnf\`,
safely decompresses XZ, verifies strictly valid original DIMACS
clause/variable bounds, computes original uncompressed CNF SHA256 and
compressed archive SHA256, and saves all ten immutable input bytes in
\`inputs/\`. It compares all GBD hashes *and* isohashes against the
old 67-source frozen manifest. Only once all ten are SHA-frozen does
\`benchmark.py prepare\` store the exact frozen experiment protocol.

No SAT or graph recognition is run in the source-freeze stage.

### Exact paired test, E2E verified

* 10 original SAT2025 CNFs x 2 repeats x 6 arms = 120 independent,
  sequential trials, allocated to 5 shards (2 CNFs/shard).
* One logical CPU/core per solver process and verifier. Run arms
  serially within each source/repeat pair on each runner.
* Each total E2E attempt has 8 seconds; unreached/unsupported/
  proof-unverified/timeout status is PAR2=16s.
* Arms: GRAPH_ONLY, GRAPH_PLUS_MATH5,
  X59_MATH5_VERIPB, Kissat, CaDiCaL, CryptoMiniSat.
* Source-only graph preflight and standard VeriPB 3.0 checker are
  included in the E2E time. On a graph-guard UNKNOWN,
  GRAPH_PLUS_MATH5 safely falls back to the exact unchanged native
  X59+MATH5 with the **remaining** time, not in parallel.
* SAT requires model verification directly on the unchanged
  source. UNSAT requires source-bound external VeriPB, DRAT or FRAT.
  Structural JSON without independent **standard** proof
  is NOT accepted in the strict track.
* Any false SAT model, external proof rejection, contradictory
  certified results, source hash mismatch or missing/duplicate
  trial rejects the final benchmark.
* Report both strict and source-inclusive PAR2, source-by-source
  proof-kind attributions, family-level bootstrap interval (caution:
  only 3 catalog families), every unknown/timeout.

Benchmark workflow:
\`.github/workflows/drnas-graph-unseen25.yml\`.
Final audit: \`results/graph_unseen25/final.json\`, produced only
when all 120 source/arm/repeat slots and verifiers complete.

### Promotion

Do not modify main. A 10-source pilot cannot prove general
superiority. If results pass, next use a larger source-family
disjoint holdout frozen before modifying guards, then full
multi-seed proof-verified PAR2 against current references.
