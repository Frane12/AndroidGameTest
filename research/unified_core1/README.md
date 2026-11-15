# UNIFIED CORE1 — experimental integration candidate

One native X59 CDCL process and one logical CPU in the harness. No portfolio or
clone probes. Main is unchanged. Default shared analysis budget: 100 ms.

Build: `python3 research/unified_core1/build.py`.
Run: `build/drnas-unified-core1 input.cnf --time 8 --proof proof.drat`.
Research structural lane: additionally `--certificate fresh.json`.
A certificate path must be new and distinct from input/proof. Structural results
are custom JSON, independently checked with `research/unified_core1/check.py`;
they are NOT DRAT/LRAT. Without that path custom UNSAT early returns are disabled.
The CDCL proof defaults to binary DRAT. `--proof-text` is diagnostic only.

Modules: SAT constructors including GF(2), robust ARG3 (not V3), MATH5 EO/XOR,
and HALL3 clause-Hall/BDD capacity. Bit mask `--unified-mask`: 1 SAT constructors,
2 MATH5, 4 HALL/BDD, 8 ARG3; default 15. `--unified-off` supplies same-core baseline.
Shared source copy and wall budget; internal extractor indices remain separate
in this initial integration. SAT construction gets up to 25 ms, ARG3 15 ms,
MATH5 35 ms, HALL/BDD the remainder. Source copy is included. Source hashing is
included in full E2E time, outside the guard budget. Existing size gates remain.
No dynamic learnt-clause injection. Every constructed SAT model is scanned
against the source clauses. Custom UNSAT never writes a fake empty DRAT clause.
The existing restricted PCMAX VeriPB exporter is included as an optional separate
proof-export utility, not automatically invoked or counted as standard proof here.
CF7 deletion-policy changes, QUOTA, learned routing and ARG3-V3 are not enabled.
Their combined performance is not established.

## Validation and regression

`python3 research/unified_core1/test.py`: 315 three-mode executions with exhaustive
small truth-table oracles, source model checks, structural proof checks, corrupt
certificate rejection, binary DRAT checking when build/drat-trim exists, then
isolated BDD and ARG3 tests. CI restores the frozen independent DRAT checker.

Workflow: original67 retrospective regression, 6 arms, 2 repetitions, 8 seconds
including verification; 804 trials, ten paired shards, at most four concurrent
runners. Each runner pins solver/checker sequentially to one logical CPU. Arms:
UNIFIED_OFF, UNIFIED_STRICT, UNIFIED_FULL, Kissat, CaDiCaL, CryptoMiniSat.
Both custom-inclusive and standard-only PAR2 are reported. Frozen original
sources/reference binaries come from run 43712040086; they are not changed.
This is NOT a new blind holdout. Compact console summaries; full rows in artifacts.

## Promotion gate

No automatic main update. A green workflow only means the experiment completed.
Before promotion: zero invalid answers/proofs; complete reproducible evidence;
new source/family-separated frozen holdout; at least 10% verified PAR2 gain over
the best fixed reference with source/family clustered confidence excluding zero;
review all solved-to-unsolved and severe regressions; demonstrate preserved known
module wins; state exactly which proof standard qualifies. A custom-only win is
not sufficient to advertise competition-standard superiority. Preserve the prior
main commit and frozen references before any explicit promotion operation.
