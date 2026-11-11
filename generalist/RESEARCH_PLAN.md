# DRNAS GENERALIST1 — category-aware general SAT research

Experimental branch: `experiment/drnas-generalist1-category-router-20261111`.

## Goal
Do **not** reduce benchmark difficulty. Keep previous matched SAT2024–2026,
SATLIB and native ATLAS/PCD cohorts and add slightly harder unseen originals.
The router learns *which algorithm is promising for which source family*;
the source family is not a ground-truth difficulty label.

## Twenty source strata
1. certified XOR / affine
2. near-XOR / deliberately broken parity (negative control)
3. pigeonhole
4. graph coloring
5. clique / independent set
6. Hamiltonian / graph search
7. crypto hash
8. crypto stream / block
9. arithmetic / factoring
10. bitvector / multiplier
11. bounded model checking
12. circuit equivalence
13. software verification
14. planning / logistics
15. scheduling / resource allocation
16. random 3SAT (satisfiable)
17. random 3SAT (unsatisfiable)
18. crafted hard SAT
19. crafted hard UNSAT
20. unknown / mixed industrial

Current router uses 10 broad **non-overlapping routing buckets**; above 20 are
benchmark strata. Do not invent certified-XOR labels; require proof-preserving
source analysis. Do not claim routing performance on a stratum with no
original-source verified trials.

## Candidate arms
- DRNAS native frozen baseline (required)
- DRNAS native conservative clause-retention (one variable changed)
- DRNAS native PCD selective (one variable changed)
- DRNAS native ATLAS adaptive decision (one variable changed)
- DRNAS native combined arm only after individual ablation wins
- Kissat / CaDiCaL, and CryptoMiniSat for XOR (references only, not evidence of native superiority)

## Hard test schedule
- Smoke: 2–4 frozen original CNFs per stratum, cap 20 s, correctness first
- Research: 10–20 SHA-disjoint cases per stratum, cap 60 s, three fixed seeds
- Confirmation: additional unseen cases per stratum, cap 90 s, same one-logical-CPU allocation per arm
- Report **per-shard** and global solved, PAR2 seconds, ratio, timeouts,
  wins/losses, E2E runtime, memory, conflicts, decisions, propagations,
  restarts, learned clauses and source fingerprints.
- Preserve original CNF and verify every SAT witness. An UNSAT label only
  counts as independently certified when its original proof was actually checked.
- Do not use held-out cases for strategy selection or per-family thresholds;
  freeze model first. Published results must distinguish *paired validation*
  from truly unseen *family-disjoint external holdout*.
- Keep baseline exact commit and manifests pinned, no silent retries or solver changes.
- Avoid unnecessary proof-log megabytes. Keep hashes, compact JSONL and
  only proof artifacts required for claimed independent certification.

## Router format
One JSON object per solver trial, for example:
```json
{"original_sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","family":"graph-coloring","arm":"drnas_base","status":"SAT","e2e_s":4.2,"cap_s":60.0,"verified":true}
```
All baseline and candidate arms must be run on the same frozen original cases.
Run `python -m unittest discover -s generalist/tests -v` then
`python -m generalist.category_router trials.jsonl --min-paired 8`.

## Honest integration status
GENERALIST1 is **offline category learning only**. It does not yet alter the
native solver, has no measured speedup and does not launch the actual hard
cohort without frozen original-source manifests plus correctly verified
native trial telemetry. Next integration step: export JSONL from
existing pinned ATLAS/PCD runners, validate it, then link the winning
category policy behind a disabled-by-default runtime gate.
