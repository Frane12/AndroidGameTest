# DRNAS SXL: source-proved ANF lemmas and bounded binary lookahead

Experimental branch: `experiment/drnas-sxl-binary-lookahead-20261109`.
Immutable parent: DMD3X `6c8502098f8daadd268f100b6355d0ed54fe55f7`.
No main changes, no automatic solver promotion, no edits to frozen references.

## Hypothesis

A lemma can have no root-level UP novelty but shorten propagation or expose an
implication after a decision. A tiny binary lookahead tree may distinguish such
lemmas from clauses that are merely logically valid. This is a selector study;
the experiment does not claim a new complete SAT algorithm or polynomial SAT.

## Algorithm

Run the unchanged DMD3X C++ generator in `all` mode with a 20 ms mining budget,
64 local bags and at most 24 candidates. Independently replay each original-source
local truth-table proof. Original clauses remain an exact prefix.

SXL considers at most the first eight shortest proved clauses (source order breaks
ties), tests each individually against full original-CNF unit propagation, and
returns at most two original, unconditionally proved clauses. Tree branching uses
lemma support variables ranked by original occurrence degree, with one original
CNF neighbor interleaved after the first support variable. Both variable values
are examined. Depths 0, 1 and 3 give at most 1, 3 and 15 nodes per candidate.
Branches already conflicting under the original CNF are excluded.

Score: `1,000,000 * earlier_conflicts + 10,000 * novel_units + work_bonus`.
The work bonus is capped at 9,999 and requires at least 64 fewer literal
inspections and at least 2% savings across the paired UP probes. Work counts
include inspections of the extra clause. Scores count opportunities across nodes;
they are neither unique deductions nor measurements of CDCL runtime.

The entire native gate, including parsing and indexing, starts an 80 ms soft
deadline. Polling occurs during indexing, propagation and traversal. Parsing and
output cannot promise a hard 80 ms wall bound; the outer full E2E process cap
still applies. If the gate exceeds its soft budget, it abstains completely.
No conditional unit or branch assumption is inserted. No external propagator
or variable-freezing observer is used. The final backend is pinned Kissat 4.0.4.

## Sources and comparisons

Restore artifact `equiv7-sourceonly-48SHA-pinned-binaries` from run 42618653489.
All 48 are reused official EQUIV7 sources, **not globally unseen**. Before SXL
measurements, screen only original Kissat with seed 1000 and a 4 s cap. Retain
reference-completed sources, up to the first 16 by source SHA; require at least
four. This is a reference-selected diagnostic cohort, not a representative
competition ranking. Save the complete screening ledger and freeze.

Six arms: clean original Kissat, all DMD3X lemmas, SXL root, SXL tree depth 1,
SXL tree depth 3, and depth-3 shadow (identical selector cost, original CNF solved).
Three paired seeds 1001/1002/1003; 6 s complete E2E cap; one logical CPU for
harness and all child processes. Arm order shuffled reproducibly per SHA/seed.
Up to 288 trials, four shards, no portfolios or simultaneous solvers in a trial.
All CNF parsing, extraction, independent proof replay, tree and solving are timed.
Repeated source hashing is timed identically for every arm.

## Validation and acceptance

Strict `-Wall -Wextra -Werror` compilation. Compare native UP closures against
an independent slow implementation on 2,160 randomized cases including empty,
duplicate and tautological clauses. Verify complete original and augmented model
sets on 48 small random formulas; replay all local proofs independently; assert
the branch-only novelty example; verify every selected clause is a proved subset.

Check SAT witnesses against the original CNF. UNSAT is explicitly reported as a
backend verdict without independent LRAT certification. Check verdict agreement
across arms. Enforce exact source/arm/seed completeness, original SHA, common
binary hashes, one-CPU affinity and no duplicate trials. Report total and per-shard
PAR2, solved counts, speedup ratios, preprocessing, tree abstentions, best cases
and regressions. A bounded-tree score is never counted as an E2E solve.

An improvement requires full E2E PAR2/solved gains over original Kissat and
against the root/shadow controls, followed by a separately preregistered holdout.
Two winners on one known training source are not transfer evidence.

## Related direction

Heule, Kullmann, Wieringa and Biere, *Cube and Conquer: Guiding CDCL SAT Solvers
by Lookaheads*: https://fmv.jku.at/papers/HeuleKullmannWieringaBiere-HVC11.pdf.
SXL borrows bounded binary lookahead as a diagnostic; it does not solve a cube
partition or use parallel cube-and-conquer.
