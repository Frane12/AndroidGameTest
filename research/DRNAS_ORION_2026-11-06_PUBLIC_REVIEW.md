# DRNAS–ORION Ω: independent-review dossier and benchmark evidence

**Author:** Frane Drnas (Croatia)  
**Manuscript date:** 2026-11-06  
**Status:** Public research proposal and evidence index. **Not peer-reviewed; no claim of universal SAT superiority or established novelty.**  
**Research repository:** [Frane12/AndroidGameTest](https://github.com/Frane12/AndroidGameTest)

## Research question

Can a proof-carrying, low-overhead and selectively activated interaction between source-certified GF(2) (parity/XOR) reasoning and conflict-driven clause learning (CDCL) help on *heterogeneous* SAT instances, without producing unacceptable overhead on conventional CNF benchmarks?

The proposed DRNAS–ORION design is a **hypothesis and experimental plan**, not a result already demonstrated by its name. Gaussian elimination and XOR-aware SAT solving are prior art. Key questions concern correctness of exported reasons, source certification, utility-based selection, incremental updates, and the total cost of communication and proof checking.

## Directly linked experimental evidence

| Experiment / branch snapshot | Scope and original log evidence | Observation | Limits |
| --- | --- | --- | --- |
| [R115 repeat, run 41898809612](https://github.com/Frane12/AndroidGameTest/actions/runs/41898809612) ([source commit](https://github.com/Frane12/AndroidGameTest/tree/6aaba92e9df33d44fac65c46b61364a83e163354)) | One external benchmark-database CNF (250 variables, 1,000 clauses), five repetitions. Artifact: `R115-historical-14k-repeat-raw` (ID 13356024585). | R28 SAT: **0.002465–0.003064 s**. Kissat 4.0.4 and CaDiCaL 3.0.1: **60 s timeouts in each repeat**. Lower-bound speedup ~19,582× to ~24,341×, **not** exact speedup. | One specialized formula, exposed historical case; no generalization or independent SAT witness audit established by this log alone. |
| [R153 repeat, run 42128549081](https://github.com/Frane12/AndroidGameTest/actions/runs/42128549081) ([source commit](https://github.com/Frane12/AndroidGameTest/tree/ea3575a512a3f93bc60bf74d0014b18b0a5440af)) | 25 original CNFs, five solver modes, three repetitions; 375 attempts. Artifacts: `DRNAS-R153-REPEAT-25-5SOLVER-3X20S-AUDIT` (ID 13464465612), and `r153repeat-original25-frozen-source-and-binaries` (ID 13461223630). | R153 solved 39/75 attempts versus Kissat and CaDiCaL 0/75 within 20 s cap; strongest effect on certified complete XOR and XOR+units. | Development/repeat selection, not unseen blind validation; all mixed-residual and non-XOR controls timed out in this test. PAR-2, not uncensored geometric mean speedup. |
| [R186 selective gate, run 42217191848](https://github.com/Frane12/AndroidGameTest/actions/runs/42217191848) | 129 test formulas / 774 attempts. Artifact: `DRNAS-R186-CHEAP-SELECTOR-774-PAIRED-FINAL` (ID 13502475162). | Selective mode aggregate PAR-2 **259.322 s** vs clean **412.500 s** (~1.591×). | External mixed-encoding subgroup: both modes time out; benefit concentrated in already recognized XOR-related cases. |
| **[R189 source-certified useful-information test, run 42228208905](https://github.com/Frane12/AndroidGameTest/actions/runs/42228208905)** ([exact source commit](https://github.com/Frane12/AndroidGameTest/tree/7728bc0d9b7caa29e6547319953f79035b26d747)) | **Primary experiment related to ORION proposal**. 38 formulas, 6 tested modes, 76 attempts per mode = 456 total. Artifacts: `DRNAS-R189-SOURCE-CERTIFIED-USEFUL-INFORMATION-FINAL` (ID 13507242165), `r189-exact-source38-pinned-native` (ID 13506767125), plus individual shard artifacts. | Clean reference aggregate PAR-2 **1514.506 s** (26/76 solves); source-certified selective gate **1085.118 s** (40/76 solves), **1.396× PAR-2 ratio**. | This is **not** a 1,000× aggregate gain. Proof/feedback causality, independent UNSAT certificates, and unseen generalization require further research. |

**Provenance:** Raw audit lines include `R115_SOURCE`, `R115_RESULT`, `R153_REPEAT_FINAL`, `R186_FINAL`, and `R189_FINAL`. The Run pages above are the primary evidence. GitHub Actions artifacts have a retention limit; copies should be preserved in a permanent Release and mirrored in an archival repository.

### External formula in R115

- Benchmark database ID: `75429ff7acb5acb597abe01aa745c2a6`.
- Decoded CNF SHA-256: `243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83`.
- CNF: 250 variables / 1,000 clauses.
- Order of solver calls alternated across repeats, with 60 s wall-time limit for each.
- A timeout is *censored*, meaning `60 / DRNAS_time` yields a **lower bound** on speedup; the reference's true time is unknown.

## Platform, hardware, and comparators

Experiments executed on GitHub Actions Linux runners, reported as `ubuntu-24.04` in sampled audit jobs. The R155 eight-shard audit reported different underlying CPU model strings: AMD EPYC 7763, AMD EPYC 9V74, AMD EPYC 9V45 and Intel Xeon Platinum 8370C. These are **host CPU identification strings**, not a guarantee that the runner received an entire physical socket. Different GitHub-hosted runners may use different hosts; paired comparisons within a shard are preferable to cross-run absolute times. Exact CPU allocation, clock policy, RAM limits, compiler flags and binary SHAs must be reported for a fully reproducible performance claim; no unrecorded specification is assumed here.

Reference solvers used in the linked studies include Kissat, CaDiCaL, CryptoMiniSat and other modes where specified in each job's log and frozen artifact. Scores include run elapsed time or PAR-2 as labeled; they must not be conflated.

## Proposed ORION protocol (not yet a validated algorithmic discovery)

1. Extract *source-certified* parity relations from the unmodified original CNF while preserving a verifiable entailment witness.
2. Maintain a sparse incremental GF(2) subsystem with assumptions and CDCL assignment feedback.
3. Generate only certified short reasons or conflicts with explicit input dependencies.
4. Estimate expected utility from live solver signals (e.g. conflict/propagation reduction) against measured preprocessing, export, injection and verification cost.
5. Enable the interaction only when a frozen low-cost selector predicts a positive net benefit, otherwise fall back to the original CDCL solver.
6. Validate every SAT witness against the **original** CNF and every UNSAT assertion using independently checked proof evidence where available; absent such evidence, explicitly flag the claim.

The experiment should compare clean CDCL, static GF(2) routing, shadow-only detection, proof-carrying feedback, and the full selector on frozen, unseen and formula-SHA-disjoint datasets, with identical resource limits, paired seeds, per-family reporting, PAR-2 and uncensored speedups, bootstrap confidence intervals, independent witness/proof audits and negative controls.

## Manuscript package (prepared, awaiting permanent GitHub upload)

The following files are authored research documents, **not yet embedded in this GitHub repository**. The original PDF files should be added to a dedicated GitHub Release together with the final audit bundle:

- `DRNAS_ORION_Frane_Drnas_Research_Manuscript_2026-11-06.pdf` (18-page full manuscript; SHA-256 `2221b17961406159a133553b58315598a1233b2ddda9225edceb82a844ee3f2f`).
- `DRNAS_ORION_Independent_Review_Brief_Frane_Drnas.pdf` (one-page English review brief; SHA-256 `a4cd3ba0e5bb9fe6663f593220376d40a87266aa73a75f50f181b65f0e5fd9aa`).
- Combined reviewer ZIP: `DRNAS_ORION_Frane_Drnas_Review_Package.zip` (SHA-256 `401e496882641303f262b6953dcc5214cec37a4a334df4c6d6708e6fd3e6322f`).

Scientific framing and document preparation received AI assistance. This dossier does not claim independent peer review or a completed new SAT benchmark record. Please cite the exact GitHub commit and run IDs when evaluating the evidence.

## Request to reviewers

Independent assessments are invited on (i) source-certified correctness and proof requirements, (ii) whether selective GF(2)-CDCL feedback contains a technically distinct contribution over existing XOR-aware SAT solvers, and (iii) the design and outcome of a genuinely blind, multi-family evaluation. **Negative findings and failure to generalize are part of the research evidence.**
