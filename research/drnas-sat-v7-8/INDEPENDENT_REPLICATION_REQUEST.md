# DRNAS SAT / NeuroFlow — request for independent replication
**Status:** Preliminary research note, 31 October 2026. **Not a world-record claim, competition submission, or general solver ranking.**

## Claim and exact instance
On one **previously examined and selected** original SAT Competition 2026 SAT instance (GBD ID `4ae685a11b5cecca76dc3d463481ce92`; SHA256 of normalized original DIMACS `16b09f959320357facb6345950ba5e6528299fc488c07e99f084446148755158`), the experimental DRNAS v8.0 CaDiCaL-based wrapper solved in ~1.24 s versus ~6.34 s for the original submitted `gopalan_kissat-evolve-b2[main-ai]` source, i.e. **~5.13x faster on this one selected instance on the same GitHub Actions runner**. Both produced SAT solutions checked against the original formula.

This is **not an official SAT Competition score**. The official published score for that 2026 competitor and instance is 13.22 s on competition hardware; combining that 13.22 s with our GitHub time would be an **invalid cross-hardware speed ratio**.

### Same-run controlled observations
Pinned CPU affinity, Ubuntu 24.04 GitHub Actions, 20-second per-solver wall cap, original source archive for competitor, two sequential repeats; wall-clock includes each process and solver invocation, but **input file parsing occurs outside the timed native DRNAS solver function**, and the competitor's launch script has its own startup/input path. This difference and GH CPU variability mean the comparison is **suggestive, not fully standardized**.

| Solver | Repeat 1 | Repeat 2 | Outcome |
|---|---:|---:|---|
| DRNAS v8.0 hybrid (CaDiCaL 3.0.1) | 1.2326 s | 1.2401 s | SAT |
| DRNAS v7.6 (CaDiCaL 3.0.1) | 1.2619 s | 1.2330 s | SAT |
| Original `kissat-evolve-b2` | 6.3372 s | 6.3373 s | SAT |
| Original `Kissat-MAB-DA` | 8.7132 s | 8.8018 s | SAT |
| Plain CaDiCaL 3.0.1 | Timeout 20 s | Timeout 20 s | UNKNOWN |

**Negative control:** On original 2026 instance `43d40ced32b5be08814ef24f97379654`, submitted `satsuma-iter+kissat` reported UNSAT in 0.0164 s and 0.0081 s (matching the published official label), while DRNAS v8.0 and v7.6 both timed out at 20 s. Independent UNSAT proof checking was **not** performed by this workflow. This counterexample prohibits any broad superiority claim.

## Method (frozen source, no solution leakage)
- Core: unchanged upstream CaDiCaL **rel-3.0.1**, Git commit `c60730422e758ef1cebe7aeddf2dda31c996bf04`. No changes to its internals.
- Formula-derived phase preferences only: count positive/negative occurrences of each variable. If total occurrences >=6 and the polarity difference >=15% (and nonzero), pass majority polarity to the documented CaDiCaL `phase()` API. No instance name, official answer, or model is used in the algorithm.
- Continue the **same CaDiCaL solver object** with a 256-conflict probe. A v7.6 durable gate checks new redundant clauses >= max(48, ceil(active_pre/4)) and `active_256 > 0`; if accepted, maintain hints for an extra conflict-limited 768-conflict solve, then `unphase()` and continue without resetting learned clauses.
- v8.0 retains that gate and adds an export-offer-shortness override using public `Learner` callback. Export-offer length is **not LBD**. Current evidence has **not shown that this override generally improves performance**.
- v8.2 late-hint activation was **worse** on this selected win case (~43.6 s), so it is not presented as an improved solver.

### Reproducibility
1. Matched20 completed GitHub Actions run, including build, native SAT validation, pinned original competitor archive, two reps, original CNF hash, CPU affinity and raw logs: https://github.com/Frane12/AndroidGameTest/actions/runs/41221508017
2. Benchmark script: https://github.com/Frane12/AndroidGameTest/blob/experiment/drnas-sat-official-best-matched-20261031/research/drnas-sat-v7-8/matched20_best.py
3. Benchmark workflow: https://github.com/Frane12/AndroidGameTest/blob/experiment/drnas-sat-official-best-matched-20261031/.github/workflows/drnas-sat-matched20-best.yml
4. v8.0 implementation and original v7.6: https://github.com/Frane12/AndroidGameTest/blob/experiment/drnas-sat-official-best-matched-20261031/research/drnas-sat-v7-8/v80_hybrid_probe.cpp and https://github.com/Frane12/AndroidGameTest/blob/experiment/drnas-sat-official-best-matched-20261031/research/drnas-sat-v7-6/v76_single.cpp
5. Official SAT Competition 2026 instance-wise scores: https://github.com/satcompetition/2026/blob/main/downloads/scores.csv

## Limits and replication request
The example was **selected after exploratory testing**. Two measurements per solver are inadequate for general performance inference. Competitor and DRNAS startup paths differ; CPU isolation and frequency were not benchmarked to official competition standards. Official competition participation deadlines have passed. **No claim of SAT complexity breakthrough, P=NP, general SAT solver superiority or world record is made.**

We request (a) independent replication of the original CNF on identical hardware with harmonized command/startup timing; (b) feedback on whether phase/polarity heuristics here are novel or known; and (c) suggestions for a sound broader evaluation.

A **72 previously unrun official 2026 CNF** retrospective study has been frozen *before evaluating the selected IDs*, with paired repeats, 12 jobs, explicit missing-data handling and PAR-2, stratified using **public official outcome and original CaDiCaL runtime** (so **not blind and not representative**). Pending run: https://github.com/Frane12/AndroidGameTest/actions/runs/41222491055

### Attribution and AI disclosure
DRNAS is a research extension / external API wrapper of the CaDiCaL project, **not a standalone SAT solver developed independently of CaDiCaL**. The DRNAS experimental design, code and evaluation were developed with substantive AI assistance under independent project direction. Exact human-versus-AI line accounting has **not yet been audited**; it must be quantified if formally submitted under SAT Competition documentation rules. Credit and citation to CaDiCaL and original competitor authors must be retained.
