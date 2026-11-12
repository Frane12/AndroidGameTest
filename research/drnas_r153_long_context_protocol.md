# R153/R160: real60 main comparison and conditional hard180

This follows the completed 5-second pilot (run 43171956308). The user requested longer limits for SAT competition formulas. The exact same twelve source hashes, six arms, two repetitions (seeds 17/29), and generation-4 frozen memory are retained. No new training or heuristic changes are introduced.

The main comparison gives every solver **60 seconds** per attempt. After a shard completes its main comparison, a formula enters the **180-second** follow-up only if NO arm reported SAT or UNSAT in either 60-second repetition. An unverified generic UNSAT claim is reported separately but excludes that source from this specifically 'unsolved by all' cohort. The follow-up restarts every arm on the original source with the same seeds; it does not resume a process or sum 60+180 into one solve time.

The former 120-second input guard is increased to 300 seconds in the outer C++ executable, the embedded native entry point and the Python memory wrapper. The R153 exact-stage allowance, CDCL algorithm, online controller, context mapping and SQL schema remain unchanged. Both native binaries are rebuilt to apply the budget guard. Frozen underlying LTM8/LTM9 artifacts are preserved.

Three shards contain four sources each. Each shard runs all six arms sequentially on ONE pinned logical CPU on its own runner, and keeps its 60s and 180s stages on that same runner. The three independent runners may execute concurrently. This uses up to three CPUs across the study, never multiple CPUs for an individual solver. CPU details are retained; comparisons are paired within each source/runner. CMS version and hash must match across runners.

Maximum main duration per shard is 4 x 6 x 2 x 60 = 48 minutes. If all four sources remain unsolved by every arm, its hard follow-up can take another 144 minutes. Jobs allow 240 minutes including setup. Early solves reduce this; the 180s cohort can be empty. Sources and binaries are prepared once and shared.

Per-trial timeout PAR2 is **120s** in the main stage and **360s** in the hard stage. Report each stage and its shards separately; never add the conditional-cohort PAR2 to the full-cohort leaderboard. SAT models and GF(2)/PHP certificates are independently checked against original CNFs. Generic UNSAT stays unverified. Timeouts are not exact speed ratios.

SQL statistics are frozen and their digest is checked before and after every stage and across all runners. The new workflow runs on a separate experiment branch and does not alter the completed short pilot. No automatic promotion or claim of general superiority.

Validation: 60/180/300-second budgets accepted by both native executables and Python wrapper on a known SAT source; 301s rejected; the existing 285 correctness-profile checks and context-memory tests pass. Selection tests reject incomplete or duplicate paired rows. A local three-shard integration test validates separate reports and an empty hard cohort without waiting through artificial long timeouts.
