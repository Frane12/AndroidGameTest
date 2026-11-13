# DRNAS X5.8 — SAT-only decision trace without DRAT overhead

**Experimental branch only:** \`experiment/drnas-x58-sat-decision-audit-20261113\`.
No merge to main and no production solver promotion. The original
X5.7 CHB/LRB/VSIDS algorithms and their fixed coefficients are
unchanged. Default policy remains VSIDS.

## Why

The completed X5.7 fresh-original scheduling benchmark showed:
VSIDS 4/40 verified solved (PAR2 1100.44s), CHB 2/40 (1140.43s),
LRB 2/40 (1140.73s). Specifically one RBSAT original was solved
by VSIDS while CHB and LRB could not solve it at 15s.

On the worker instance, VSIDS and CHB reached a 512MiB DRAT proof
file limit before their 15s time budget. This makes their
proof-enabled wall times unsuitable for drawing an inference
about their *search speed* relative to LRB.

X5.8 explicitly separates **SAT witness search** from **UNSAT proof
production**. It does not change the chosen variable or learned
clause logic.

## CLI

In a build compiled from \`src/drnas_x58_sat_audit.cpp\`, e.g.:

\`\`\`bash
g++ -std=c++20 -O3 -DNDEBUG -g -fno-omit-frame-pointer \
    src/drnas_x58_sat_audit.cpp -o build/drnas-x58

# Uninstrumented SAT-only search (no proof file, no DRAT I/O)
build/drnas-x58 formula.cnf --mode core --time 25 --stats \
    --x57-branch vsids --x53-policy baseline \
    --x52-proof-deletions --x58-sat-only

# Same search policy with an observational chosen-decision JSONL trace
build/drnas-x58 formula.cnf --mode core --time 25 --stats \
    --x57-branch chb --x53-policy baseline \
    --x52-proof-deletions --x58-sat-only \
    --x57-decision-trace decisions.jsonl

# Normal proof-enabled original X5.7 behavior
build/drnas-x58 formula.cnf --mode core --time 25 --stats \
    --x57-branch lrb --x53-policy baseline \
    --x52-proof-deletions --proof result.drat
\`\`\`

The \`--x58-sat-only\` option requires \`--mode core\` and
**rejects \`--proof\`**, so proof generation cannot accidentally
contaminate the SAT-only timing arm.

A SAT model is internally checked by the solver and **must**
pass an independent, unmodified original-CNF witness validator in
the benchmark. SAT-only may output \`s SATISFIABLE\` and exit 10.

If the solver reaches internal \`UNSAT\` with proof generation disabled,
\`--x58-sat-only\` explicitly **returns UNKNOWN**, exits 0, and emits
\`X58_SAT_ONLY\` in stderr with
\`"UNSAT_without_proof_credited":false\`. This protects against
treating an unproved UNSAT answer as certified.

## Provenance and methodology

From the official SAT2024 original archive pre-frozen in completed
run 43434020900, purposefully select these five previously seen
sources, **not blind validation**:

| Original source ID | Description | Reason |
|---|---|---|
| 1 | \`Break_08_24.xml.cnf.xz\` | Fast verified SAT positive control |
| 3 | \`worker_40_80_40_0.9.cnf.xz\` | Prior 512 MiB DRAT proof limit |
| 12 | \`pcmax-scheduling-m24-24102-255206-SAT.sanitized.cnf.xz\` | Large scheduling source; name suggests SAT, no credit without witness |
| 18 | \`rbsat-v945c61409gyes9-sc2009.cnf.xz\` | Prior VSIDS-only success |
| 19 | \`circuit_48in64out_with_700gates_4in4out_dist128_seed1.sanitized.cnf.xz\` | Previous reference-solver SAT wins |

For each source, two identical formula repetitions are paired
across eleven arms:

\`VSIDS_PROOF\`, \`VSIDS_SAT\`, \`VSIDS_TRACE\`,
\`CHB_PROOF\`, \`CHB_SAT\`, \`CHB_TRACE\`,
\`LRB_PROOF\`, \`LRB_SAT\`, \`LRB_TRACE\`,
\`KISSAT_SAT\`, \`CADICAL_SAT\`.

**110 total attempts**, 25s E2E solver cap, PAR2=50s for
unsolved or unverified answers. One logical CPU at a time per
shard. Five shards can execute concurrently on separate runners.

For **normal proof-enabled** DRNAS, valid UNSAT requires
\`drat-trim\` to certify the proof. The proof file has a 512 MiB
cap. For every SAT-only arm, no proof is generated and UNSAT is
never accepted; valid SAT models must be verified by a separate
Python validator against the original CNF.

\`X57_TRACE_WRITE\` measures trace serialization cost separately.
Trace sampling is bounded (first 4096 decisions, every 512th
afterward, at most 8192 rows). The trace documents the actual
chosen literal, policy-specific score, immediate BCP observations,
and immediate conflict LBD. It does *not* establish a causal
counterfactual. Solved search counters are checked for equality
across proof / SAT / trace variants of the **same policy**.

Use the 11-arm, 5-source scores only for diagnosis and the
within-source, within-policy proof-overhead comparison. This
purposively selected five-source set is not statistical evidence
of broad superiority or a model-promotion gate.

## Tests and artifacts

Workflow:
https://github.com/Frane12/AndroidGameTest/actions/runs/43443186119

The preflight gate succeeded:
- 45 independent small formula sources;
- 540 fixed-policy proof/no-proof/trace executions;
- 60 independent UNSAT DRAT checks;
- SAT-only UNSAT is downgraded to UNKNOWN as intended;
- exact equality of completed search counters across the modes
  in all tested instances.

\`research/drnas_x58_sat_decision_rbsat.py\` freezes original
SHA hashes and binary SHAs before benchmarking, preserves trial
metrics and emits a final \`X58_FINAL\` summary with first
observed decision divergences (not causal proof).

\`main\` remains unchanged, no APK is built, and no heuristic
is auto-promoted.
