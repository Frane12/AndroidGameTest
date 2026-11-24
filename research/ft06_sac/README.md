# DRNAS SCALE8 — source-only structural FT06 solver (SAC + DRAT)

**Experimental branch; main unchanged.** This extends the PCMAX/ATLAS investigation from Hall/clique covers to raw-CNF domain consistency. It is based on the **published JSPLIB FT06** job-shop benchmark, time-indexed by the previous SCALE7 test. No annotated job-shop input, answer label or CDCL search is used by the new module.

## What we recovered directly from the unchanged source CNF

At deadline 54, 19,690 clauses and 1,560 variables contain **36 disjoint all-positive exactly-one start domains**. The structurally extracted binary conflict graph has **110 cross-domain links**. Exactly 30 links form a strict lower-triangular relation between equally sized domains; these form six precedence chains of six operations. Excluding those 30 chains leaves 80 conflict links, whose connected components are six 6-operation groups (corresponding post-hoc to the six machines). The corresponding 55-deadline CNF has 21,232 clauses, 1,632 variables, 111 cross-domain conflict links and 81 non-precedence conflict links.

Each operation's selected start can be ruled out by source-derived binary conflicts. Arc consistency alone removes 143 starts for deadline 54 but does not refute the formula. **Singleton arc consistency** temporarily selects a start, propagates unsupported alternatives through the other mandatory operation domains, and rejects that selection when contradiction follows. Repeated rejections eventually produce an empty domain for deadline 54.

## Proof trust boundary

The generator records each global exclusion as a unary RUP clause, and each temporary, guarded exclusion as a binary RUP clause. Its output ends with the empty clause. Every learned clause must be accepted against the unchanged original DIMACS CNF using an **independent DRAT checker**. This checker also validates implied within-domain at-most-one relationships from the original auxiliary encoding; the structure extractor does not need to trust their semantics. Never count an emitted proof as VERIFIED until the external checker says VERIFIED.

The result does not establish an O(n) runtime bound, a general SAT algorithm, or superiority over CP-SAT. SAC is a known consistency algorithm; the contribution being investigated is automatic recovery of the constraint structure from raw CNF and construction of independent proof evidence.

## Reproduction

GitHub Actions run: https://github.com/Frane12/AndroidGameTest/actions/runs/45347378907

Frozen SHA256 sources:
- 54: `99910f35ed2401b2315618aa7ac23605ba876cfea79c3edadd1e468ef1c674ee`
- 55: `ec8a9bbb98f7742cedddf4c7430ce1185da7256427505b1b051bff1cbbb4dc20`

Download the run artifact `drnas-ft06-raw-cnf-sac-rup-drat-verified` and run:

```sh
python3 research/ft06_sac/structural_sac.py original_54.cnf --drat proof_54.drat --report report_54.json
drat-trim original_54.cnf proof_54.drat -U
python3 research/ft06_sac/structural_sac.py original_55.cnf --report report_55.json
```

The CI executes 13 SHA-controlled variants for each deadline, 13 independent DRAT verification passes for 54, 13 55-deadline controls without false UNSAT, and three native CDCL reference repetitions per deadline. It sets CPU affinity to one allowed logical CPU and preserves the original CNF bytes, proofs and checker outputs.

**Median same-runner results:** deadline 54 structural generator 0.055327 s, independent DRAT checker 0.054431 s, native DRNAS CDCL 0.023483 s. Deadline 55 structural UNKNOWN in 0.234373 s, native CDCL SAT in 0.0217 s. This demonstrates verified structural coverage, not current speed superiority.

## Next research directions

1. Extend beyond positive-source exact-one groups and binary conflict masks to arbitrary scheduling encodings (reified intervals, pseudo-Boolean and time-indexed cumulative constraints).
2. Detect workload lower bounds and edge-finding/energetic contradictions using recovered temporal geometry.
3. Move the hot RUP-producing SAC loop from Python into optional native C++ and compare **end-to-end** CPU and certified proof time.
4. Run source-disjoint, previously unseen public job-shop/PSPLIB cases without tuning on the evaluation set.
