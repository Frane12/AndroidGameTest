# DRNAS X5.7 — Scheduling SAT CHB vs VSIDS/LRB on new original instances

This is a **new-to-REAL36 source verification run**, not a claim that
the sources have never been used in SAT research. The original SAT2024
archive and similar templates have already appeared in other research.

## Hypothesis

The completed X5.7 Decision Trace experiment recorded that CHB made
103 fewer branching decisions than VSIDS on one *worker scheduling SAT*
instance (original REAL36 source ID 12). On the complete REAL36 mixed
application set, however, CHB and LRB had **worse overall verified
PAR2**, and solved no additional formulas.

The present experiment tests whether the scheduling observation
generalizes to *different original SAT2024 source bytes* selected
independently of solver outcomes, using exactly the previously frozen
CHB, LRB and VSIDS policy binary.

## Sources and leakage safeguards

Official SAT Competition 2024 Main archive:
https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1

The source selection excludes **all 36 previously evaluated REAL36
original filenames and SHA256 hashes**. The input names are
selected by deterministic archive filename patterns and compressed
file-size strata, BEFORE any solver is run. It does not select cases
by CHB gains, runtime, past SAT status, LBD or any subsequent output.

GitHub preflight run ID: 43434020900.

Official catalogue diagnostics:

- 215 otherwise eligible official archive ZIP entries in the chosen
  metadata size interval.
- 5 eligible Break scheduling-family names, 11 eligible
  pcmax-scheduling names and 1 eligible worker name.
- 73 distinct filename-template groups available for controls.
- The frozen evaluation selection includes **12 scheduling-labelled
  originals**: 5 Break, 6 pcmax-scheduling, 1 worker, plus
  **8 nonscheduling controls** from distinct filename groups.

The category is based on source-name patterns; this is a practical
scheduling-related group, not a semantic theorem that every formula
is the same scheduling optimization task. The "medium" source size
stratification is also a proxy, NOT runtime-based difficulty screening.

The selected 20 original CNFs are saved unmodified as raw DIMACS.
Every source has its original archive entry name, original SHA256,
variable and clause counts, byte length and path in
\`x57_sched_unseen/manifest.json\`, and a separately frozen binary
SHA manifest in \`x57_sched_unseen/protocol.json\`.

## Frozen solvers

The SAT solver binary \`build/drnas-x57\` is copied verbatim from
successful verified previous X57 run 43418696306 and called with only
one policy flag difference:

- \`--x57-branch vsids\`
- \`--x57-branch chb\`
- \`--x57-branch lrb\`

Kissat and CaDiCaL also use pinned binary versions from the earlier
REAL36 native binary artifact.

**No heuristic is trained or updated between formulas.**
There is no automatic policy tuning or promotion.

## Benchmark protocol

- 20 original sources, each repeated twice; five solver arms;
  **200 expected solve trials**.
- Each solver is executed serially, pinned to **one logical CPU**.
  Source/arm order is deterministic but rotated by source/rep.
- Cap: **15s solver E2E**; timeout/unverified gets PAR2 30s.
- DRNAS proof generation and OS process overhead are paid inside the
  E2E clock. Independent DRAT verification time is accounted
  separately; only verified UNSAT earns a solve.
- Every SAT model is checked against the untouched original CNF.
- Proof file cap 512 MiB; proof-size censoring is not a false UNSAT.
- All arm/source hashes are revalidated in every shard.
- Independent sample units are **source CNF hashes**, not repeats.

The final report gives overall verified PAR2 and solve counts,
separate scheduling-related and controls, individual name-group and
per-formula comparisons, source-clustered 95% bootstrap intervals,
CPU and memory telemetry, and the distinction between proved SAT,
proved UNSAT, timeouts and unverified answers.

For the scheduling claim to be credible, CHB needs repeatable gains
across *multiple independent original formulas* rather than winning
only the prior worker source ID 12. No result on this reused archival
collection by itself establishes broad statistical superiority:
validation on a distinct unexposed source-family holdout would still
be required.

## Status and links

- GitHub Actions:
  https://github.com/Frane12/AndroidGameTest/actions/runs/43434020900
- Branch:
  \`experiment/drnas-x57-scheduling-unseen-20261113\`
- Selector, SHA freeze, comparisons:
  \`research/drnas_x57_sched_unseen.py\`
- Offline source-selection unit tests:
  \`tests/test_x57_sched_selection.py\`
- Five-arm benchmark:
  \`.github/workflows/drnas-x57-scheduling-unseen.yml\`

\`main\` has not been modified, and this workflow does not modify
production solvers, publish an APK, or merge a winner automatically.
