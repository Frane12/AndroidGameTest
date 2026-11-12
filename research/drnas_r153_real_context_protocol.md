# Frozen R153/R160 context memory on original SAT2024 CNFs

This is the first real-source transfer test of the SQL memory experiment. It reuses binaries and generation-4 memory from successful run 43170837571, commit `99bdc04656033d472bcbb63d0620fe017dcd2f0c`; no recompilation or new training is performed. The R153 exact GF(2) kernel remains first, followed by the native DIRECT engine with R160-informed context features.

Select 12 of the 24 original SAT2024 sources in the frozen MATH14 manifest from run 43161813420. Sort by compressed size and source filename and take indices 0,2,...,22. Do not consult solver outcomes. Download those exact named entries from the official archive and enforce the recorded decompressed SHA256. Every selected source has a distinct normalized name family. The dataset was used earlier: this is a transfer/replay audit, NOT a globally unseen or blind benchmark.

Arms: frozen NATIVE_DIRECT, CONTEXT_COLD (same new controller with empty priors), CONTEXT_MEMORY (saved priors), Kissat 4.0.4, CaDiCaL 3.0.1, and the recorded Ubuntu CryptoMiniSat package. Two repetitions, seeds 17/29, 5s wall cap, shuffled arm order, one pinned logical CPU, one process at a time, CMS one thread. Total 144 attempts; logical reporting shards contain four formulas each, executed serially on the same runner.

The cold-versus-memory comparison isolates transferred knowledge. The frozen-native comparison also includes the new controller's phase handling. Report the number of attempts that actually loaded nonzero prior weight: synthetic training may not cover the structural contexts of real formulas. No claim of a memory benefit is justified when no priors load.

Memory statistics remain frozen throughout evaluation and are checked by digest before and after. The evaluation registry is local to this run; neither the database nor new evaluation telemetry is published as training memory. Original-CNF SHA and split checks must pass. Source files are not modified. Sources assigned to training in the inherited database are rejected.

SAT requires an independently validated original-CNF witness. UNSAT is independently accepted only with source GF(2) or PHP certificates. Generic UNSAT from any arm is reported separately and penalized in verified PAR2. Publish both reported and verified PAR2; proof-coverage differences are not search-speed improvements. Invalid models, certificates or contradictory answers fail the run.

Report total seconds, solved attempts, both PAR2 totals, per-shard tables, memory preparation overhead, prior coverage, regressions and measured speed ratios. Ratios against timeouts are lower bounds. Memory preparation counts against native wall budgets; independent verification is separately timed. No large generic proofs or original source archives are uploaded.

No automatic promotion: the user's target is at least 30% lower PAR2 than the strongest reference, with solved counts and proof coverage considered. This small previously used dataset cannot establish global generalization even if the target is met.
