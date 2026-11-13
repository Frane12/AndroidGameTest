# DRNAS REAL-SPEED v1 — six-hour development audit

Status: experimental, **no production promotion**. The recurring job is a
verified development screening benchmark, **not a repeatedly reused blind
holdout**. Only a separately approved, newly collected and unexposed holdout
can support a final generalization claim.

## Each cycle (fixed defaults)

1. **preflight**: frozen reference SHA checks, native candidate compilation,
   protocol unit tests, exact binary freeze artifact;
2. **material**: collect up to 160 fresh, complete original application SAT CNFs
   from the REAL2 historical sources and split by permanently assigned family.
   Merge cumulative REAL2 + REAL-SPEED registry and prevent cross-run reuse.
   Any newly reserved holdout sources are **sealed but never executed**;
3. **paired**: development-only train + validation original CNFs, cap 5 seconds
   solver time per trial, separate proof-check cap 10 seconds, 2 repetitions,
   8 shards, strictly one logical CPU per solver and serial runs within shard;
4. **report**: verify all expected source/arm/repetition rows, credit only
   independently verified SAT witness / UNSAT certificate, compute verified
   solver PAR2 and 95% family-clustered bootstrap; compare CORE, X5_NO_MIN,
   fixed X5, X52_LBD, Kissat, CaDiCaL and CryptoMiniSat;
5. **persist**: append run-scoped manifests, compressed trial records,
   hash and benchmark reports to the separate data branch, never main.

All outputs have structured \`SPEED_*\` events in logs and artifacts.

Data branch:
\`experiment/drnas-real-speed-v1-data-20261113\`

Code branch:
\`experiment/drnas-real-speed-v1-sixhour-20261113\`

### Metric contract

\`PAR2_s = solve_s\` for an answer independently VERIFIED under the
5-second solver limit; otherwise \`PAR2_s = 10.0\` seconds.
Verification is separate and limited to 10 seconds, mandatory for solved
credit. \`verified_e2e_s\` and \`check_s\` are separately recorded;
do not compare this metric as if it were the older REAL2 end-to-end PAR2.

Results are research diagnostics. A positive development screen does NOT
deploy a policy, open the holdout or establish a blind improvement.

### Statistical and safety constraints

- Family clusters are resampled; solver attempts or repetitions are not
  considered independent original CNFs.
- No holdout CNF bytes are uploaded to the development benchmark runners.
- Dataset selection does not inspect outcomes.
- Frozen SHA is rechecked on each runner.
- No training based on previous holdout.
- No automatic promotion or branch merges.
- Maximum 8 parallel shards; each shard serializes solver invocations.
- A failed prerequisite aborts the dependent phases and preserves failing logs.

### Still required for the full REAL-SPEED research protocol

A separate one-time blind workflow with a newly unexposed, family-disjoint
200-CNF set, predetermined 30-second cap, stronger replication gate,
multi-comparison correction, and an explicit authorization for each opening.
The current six-hour loop must never fake that evidence.

### Launch / recurrence

The experiment workflow listens to pushes updating
\`research/real_speed_v1/trigger.json\` on the **code** branch only.
It does not run a GitHub \`schedule\` event (GitHub scheduled workflows only
run from the default branch, which is intentionally protected).
A ChatGPT scheduled automation can advance the trigger on the code branch after
checking for an in-progress workflow; it must not change solver/main.
