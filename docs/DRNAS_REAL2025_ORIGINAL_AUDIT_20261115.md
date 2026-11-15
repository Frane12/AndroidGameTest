# DRNAS SAT REAL2025: independent original CNF benchmark

Completed 2026-11-15. Outcome: negative result for general speedup.

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/43710355714
Source freeze: https://github.com/Frane12/AndroidGameTest/actions/runs/43710031198

## Provenance

SAT Competition 2025 Main GBD list at repository commit 1de9acf01846f96fd3d6a460bc2238ce3bb4e3a6.
22 catalog positions (11+18*i) frozen before any solver evaluation.
19 downloaded originals; 3 excluded only by precommitted byte-size limits.
All SHA-256 source hashes retained with full original source bytes.
Catalog SHA256: d02406bb212498ea1d2d9f2e968f9a8f6ad3b6bc479ae1b1368d5b4d638a9120
Frozen manifest SHA256: 47cc882a3893b2ecaf543341040d41c417eb13d8eb940198d37143715f65db4e

Excluded exact SHA duplicates relative to CF7 prior 100 and two named
historical cases. Earlier exposure elsewhere has NOT been exhaustively
excluded, so the correct claim is source-outcome blind for this specific
evaluation, not universally never before examined.

## Protocol

5 arms: X59 binary OFF, identical X59 binary ON with 100-ms source SAT
constructor, pinned Kissat, CaDiCaL and CryptoMiniSat. Two repetitions
on 19 unchanged original CNF files = 190 attempts, one logical CPU per
solver, 8 seconds total end-to-end. SAT requires a complete source
model checked independently; UNSAT requires independently verified
DRAT or FRAT within the same time cap. Unverified or timed-out results
are PAR2=16 seconds. Four GitHub Actions shards parallelize the
evaluation infrastructure, not a solver process. Full records retained.

## Results

| Arm | Certified answers/38 | SAT | UNSAT | Verified PAR2 sum s |
| --- | ---: | ---: | ---: | ---: |
| CaDiCaL | 10 | 6 | 4 | 448.949739 |
| CryptoMiniSat | 10 | 6 | 4 | 461.812326 |
| Kissat | 8 | 4 | 4 | 480.474740 |
| X59 OFF | 8 | 4 | 4 | 480.439588 |
| X59 ON | 8 | 4 | 4 | 480.468674 |

X59 ON was about 0.006% worse in overall PAR2 than X59 OFF, with no
additional solved case. Source-level paired changes: 0 wins, 4 losses,
15 ties. Neither config improves general coverage on this source cohort.

GBD b9ed6fd14f4fc969ec966a4b54c36872 (960 variables, 62749 clauses)
is the one source on which CaDiCaL and CMS verified SAT but X59 and
Kissat timed out at 8 seconds. CaDiCaL took about 0.253 seconds;
CMS about 6.7-6.8 seconds. This is the most informative development
target, NOT a validated holdout anymore now that its result is known.

Source catalog positions 11 and 173: verified SAT for all arms.
Positions 281 and 389: verified UNSAT for all arms, standard proof
checkers included. There were no incorrect or contradictory verified
answers across solvers.

No new constructive SAT model appeared in accepted original-CNF
results. Timed-out trials can lack detailed structural telemetry, so
no claim is made that none attempted a module.

## Limitations and next science

The selected source size caps bias the official sample; 8s is not
official competition cutoff/hardware. The current result cannot
establish SAT Competition ranking, universal absence of benefit or
full historical blindness. The earlier synthetic XORHARD2 result was
strongly positive for a designed structure; this genuine heterogeneous
cohort provides an important negative generalization check.

A first benchmark run was blocked before solver execution by a single
FRAT-checker reference SHA typo. The actual archived checker SHA was
pinned and the exact same source-manifest and solver implementation
were evaluated successfully; no source was added or replaced.

Do not promote from this cohort. Develop clause preprocessing,
structural recognition and native CDCL performance on separate train
inputs, then freeze another independent official source set.
