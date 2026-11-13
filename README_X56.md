# DRNAS X5.6 — original binary implication CSR and frozen E2E evaluation

**Status:** experimental branch only. No edits to \`main\`, no APK.
Prototype is a controlled performance experiment; not a promoted solver.

## Hypothesis

X5.5c and the earlier X5.4 experiments showed many billions of BCP
operations. Changing the *order* of long-clause watch scans cut their
operation count but did not establish a significant verified PAR2 gain.
X5.6 targets a different source of memory traffic: vectors of binary
implications for the *immutable original CNF*.

## Isolated algorithm change

A solver flag \`--x56-binary-csr\` builds a **compressed sparse row**
representation of directed original binary implications during
\`finishParsing()\`:

1. Freeze the original adjacency before any CDCL-learned clause is added.
2. Preserve each original implication pair \`(implied, clause_reason_id)\`
   and the exact traversal order within each signed literal.
3. Construct \`uint32_t offsets[2 * nvars + 1]\` and one contiguous
   \`std::vector<std::pair<int,int>>\` for the original edges.
4. Release original dynamic per-literal buffer allocations.
5. Continue storing newly learned binary implications in the original
   **dynamic** adjacency lists, which are traversed after static edges.

During garbage collection, original clause IDs are stable because
original clauses are inserted first and are never deleted. Learned
binary reason pointers are still remapped by the existing collector.

The option is **disabled by default**. It activates only when variable
count is between 1 and 250,000 and at least 512 directed original binary
edges exist. This bounds startup overhead on huge sparse formulas and
avoids creating a CSR for tiny problems.

This is a storage layout optimization, **not a SAT/UNSAT inference**,
and does not change CDCL variable selection, clause learning, restart
policy or the proof format. Static reason IDs and literal lists are
preserved.

## Correctness gates

\`tests/test_x56_binary_csr.py\` runs a small exact SAT/UNSAT brute-force
oracle and six binary-dense test sources. SAT assignments are independently
checked, and every UNSAT result requires a verified DRAT certificate.
A three-way comparison tests:

* untouched X5.5b binary built using identical compiler flags,
* instrumented X5.6 with CSR disabled,
* instrumented X5.6 with CSR enabled.

All solved test cases must agree on decisions, conflicts, propagations,
learned clauses, and reductions. The tests assert the CSR branch was
actually activated, that directed binary edge counts are correct, and
that the original clause reason identifiers remain stable.

**Initial CI passed:** 210 executions, 153 independently verified
UNSAT proofs, 1,279 CSR-directed edge visits. This validates core
invariants on the test inputs, not competitive performance.

## Paired official original SAT2024 benchmark

36 previously frozen, original SAT2024 application CNFs from the REAL36
archive; two repeats each; five arms:

\`X55B_FROZEN\`, \`X56_OFF\`, \`X56_CSR\`, Kissat, and CaDiCaL.

Total **360 paired executions**, 10-second solve cap, PAR2=20s on
unsolved/unverified attempts, one logical CPU per solver invocation.
SHA256 of original source and every binary is frozen before trials.
Actual CSR activation (and number of original directed binary edges)
is reported per source. A new CSR source path never implies that it was
activated for a source where the guard rejects it.

SAT witnesses are checked against the original CNF. UNSAT is credited
only with independently checked DRAT. Checker time is reported separately
from the solver E2E; proof-writing cost is paid in the solver E2E.

Report includes: verified solved count, PAR2, process user+system CPU,
maxRSS, proof limitations, activation rate, original static edge
visitation, a source-clustered bootstrap confidence interval, and
exact paired differences.

**Important:** this is a retrospective reuse of known original CNFs,
not a new blind holdout. A proof of broad improvement requires an
additional family-held-out evaluation on newly selected originals.

## Artifacts and workflow

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/43410343295

Branch: \`experiment/drnas-x56-binary-csr-20261113\`.
Comparison code: \`research/drnas_x56_csr_real36.py\`.
Benchmark workflow: \`.github/workflows/drnas-x56-binary-csr.yml\`.

The CI preserves results in per-shard ZIPs with paired \`trials.jsonl\`
and a separately verified final summary.

No automatic promotion or merge is performed.
