# X5 GAP14: diagnose the BEST100 coverage gaps

This experiment diagnoses the completed BEST100 run [43404243647](https://github.com/Frane12/AndroidGameTest/actions/runs/43404243647). It uses all fourteen original CNFs for which at least one frozen solver produced an independently verified answer inside that run's five-second shared budget. Nine are cases where both native variants failed; five are native controls, including FRB, ITC, Break and Simon instances.

The selection is outcome-dependent and retrospective. These fourteen originals are diagnostic data, not unseen validation, training material, or evidence of generalization. `selection.json` records the original bytes, original source IDs, SHA-256 identities, previously verified truth values, native/control groups, and the exact parent report SHA. The frozen X5_NO_MIN reference remains the primary baseline. No solver policy or learned model is promoted by this workflow.

## Competitive measurements

The unchanged BEST100 harness executes frozen X5_NO_MIN, X5, Kissat, CaDiCaL, and CryptoMiniSat. Both 5-second and 15-second limits include solving and independent verification. Two repetitions per cap give 280 complete paired trials. Each source and all its solver/cap combinations stay on one runner and one logical CPU; only independent source groups run in parallel.

SAT assignments are checked against the original CNF. Accepted UNSAT requires independent DRAT or FRAT checking inside the common deadline. Unaccepted attempts score twice the limit. The reference binary artifact is from run 43368689724; the original CNF bytes are from run 43396550073. Exact hashes and the CryptoMiniSat runtime version are checked on every runner. Timing comparisons must use the shared-budget measurements from this section.

## Diagnostic profiles

A separate `drnas-x5-profile` clone preserves the frozen X5 search algorithm. Its optional POSIX CPU sampler classifies exclusive phases such as propagation, conflict analysis, minimization, clause reduction, proof output, variable selection, and remaining work. The reported CPU phase allocation is a statistical estimate from sample shares; sample counts and observed process CPU accompany it. Nested minimization is separate from exclusive analysis. No per-literal clock readings are extrapolated into CPU time.

The nominal timer interval is 1 ms, but the effective delivery frequency depends on the runner kernel and is reported from actual samples and CPU time. Normalizing the phase shares makes their sum bounded by total CPU by construction; this does not independently establish sampling accuracy. A phase with zero observed samples may still have consumed CPU. Instrumented watch counters and signal delivery have overhead, so phase estimates must be interpreted alongside same-binary profiler ON/OFF throughput and elapsed-time controls.

Each source receives six additional 15-second diagnostic executions: minimization on/off, with the profiler on/off and proofs enabled, plus both minimization settings with profiling enabled and proof output disabled. These 84 executions are separate from the competitive PAR2 table. Same-binary profiler controls expose measurement overhead through completed work and CPU usage. Proof-disabled executions expose proof-output cost; they do not produce independently certified UNSAT results.

Native profiles have a 15.25-second external guard so the native 15-second limit can emit final telemetry. This extra shutdown allowance is diagnostic only. Any subsequent proof audit is also diagnostic and cannot turn a competitive timeout into an accepted solution. Progress snapshots and interrupted executions are explicitly partial. The diagnostic proof-file cap is 512 MiB; exhausting it is resource censoring, not evidence of a wrong logical answer.

## Correctness and evidence

Before real measurements, the workflow checks profile-off/on search parity against the frozen source, verifies SAT truth and witnesses, and independently checks UNSAT proofs. The report requires all fourteen source identities, all four shards, all 280 competitive rows, and all 84 profile configurations. Unknown comparison arms, duplicate or missing pairs, contradictory answers, source drift, and mixed binary identities fail closed. Low-sample and incomplete profiles retain raw evidence but do not support precise phase percentages.

Artifacts retain the protocol, paired rows, diagnostic rows, stdout/stderr snapshots and checker logs, per-source summaries, and the profiling self-test. The intended outcome is an evidence-based choice of the next narrowly scoped optimization, followed by separate validation on unseen formulas.
