# MATH5 BLIND30 — prospective evaluation

Frozen solver: `8614545baee7e9c6f2c0427406405be13c2ff712`. The solver and its structural checkers are unchanged. This branch only adds selection, measurement and reporting.

The precommitted `prespec.json` is authoritative. The selector uses only public catalog metadata, file availability/size/syntax, and exclusion identities. It never imports or runs a solver and never reads prior runtimes. It first tries to select eight SAT and eight UNSAT catalog controls, then fills to 30, with at most three sources per family. Catalog labels do not certify answers. A fixed hash order and a pinned Main-track URI list determine candidates; no replacement is allowed after evaluation starts.

Exclusions include the original 24, MATH4 unseen15, MAXPAR2 27, 670 earlier recorded source hashes, and all source hashes in the pinned global memory snapshot. Equal GBD IDs, known isohashes and raw SHA-256 are excluded. All exclusions and input-only failures are retained. This is prospective and source-disjoint relative to that recorded history; it is not a claim that every historical branch was audited or that all families are unseen. At least 12 eligible sources and four catalog SAT controls are required; the actual denominator is always reported.

Five arms: MATH5, MATH4, MATH5 executable with its math module OFF, frozen Kissat and frozen CaDiCaL. Three repetitions, 10 seconds total per solver-plus-checker attempt, one logical CPU, sequential paired arms on each runner, six independent shards. SAT models, DRAT proofs and structural proofs use separate checker processes. Primary PAR2 accepts any verified model/proof within the total cap; strict MODEL/DRAT PAR2 penalizes structural-only UNSAT. Timeouts, failed verification, resource limits and errors cost 20 seconds. Complete result-matrix validation prevents dropping bad runs. Repetitions are not counted as independent sources.

The declared target is at least 10% lower aggregate primary PAR2 than the better of the two reference solvers, with no invalid answers/proofs. Paired bootstrap resamples source formulas, not repetitions. Module time and overhead relative to OFF on jointly solved non-structural cases are also retained. There is no automatic promotion or update to any learned policy.

Workflow stages: known-control self-test; outcome-free input freeze; binary/checker/input hash freeze; paired evaluation; complete-matrix aggregation. Full source, manifests, logs, certificates and compressed verified DRAT proofs are retained as Actions artifacts. Incomplete proof scratch is removed after recording its size and failure status.

Local entry points (run from repository root after preparing the pinned reference binaries and memory snapshot):

```sh
python3 research/math5/build.py
python3 research/math5_blind/selftest.py
python3 research/math5_blind/freeze.py
python3 research/math5_blind/benchmark.py prepare
python3 research/math5_blind/benchmark.py shard --index 0
# Run indices 1–5 on separate runners, then collect all six shard directories.
python3 research/math5_blind/benchmark.py report
```
