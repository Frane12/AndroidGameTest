# HALL3 + CF7 STANDARD26

This experimental build closes the standalone guard's UNKNOWN path by continuing
the same native CF7 CDCL process. It is not a solver portfolio. The original
CLAUSE-HALL2 rule and native weighted BDD capacity rule share a bounded 750 ms
analysis budget. They inspect original clauses and do not add unproved clauses
to the CDCL database. The CF7 Solver class is byte-identical to its frozen source.

CF7 B2L32 was selected using all 700 trials of CROSS REAL100 run 43616738853.
Its verified PAR2 sum was 1525.638149 s, the lowest among the tested DRNAS builds;
Kissat was better at 1419.640602 s. The ten paired jobs succeeded, but the old
final aggregator failed on an artifact metadata path. `base-selection.json`
and `base-selection-trials.json` retain the complete evidence used for selection.
This comparison does not establish a universally best solver.

## Build and use

```sh
mkdir -p build
g++ -std=c++20 -O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror \
  -DDRNAS_PCMAX_MODULE src/drnas_hall3.cpp -lcrypto -o build/drnas-hall3
build/drnas-hall3 input.cnf --mode core --time 15 \
  --x5-no-minimize --x5-no-retain --cf5-policy B2L_32 \
  --hall3 --pcmax-budget-ms 750 \
  --pcmax-certificate new-structural.json --proof new-proof.drat
```

Both certificate filenames must be separate from the input and each other.
Use a new structural certificate filename for each run. Guard OFF is the same
command without `--hall3`, `--pcmax-budget-ms`, and `--pcmax-certificate`.
Structural detection is opt-in. SAT requires an independently checked model.
UNSAT requires either a checked structural JSON certificate or a checked DRAT
proof from CDCL. An empty/partial DRAT file alongside a structural certificate
is not a DRAT proof and must never be scored as one.

## Frozen protocol

- 24 unchanged DIMACS CNFs drawn from the actual 400-instance SAT Competition
  2026 Main Track URI list, covering 12 families; 3 repetitions each.
- Four arms: CF7_OFF and HALL3_ON from the same executable, Kissat, CaDiCaL.
- 15 s external wall cap including startup, input parsing, guard and search;
  one logical CPU per trial; arms execute sequentially on the same runner.
  Six independent paired shards, 288 total trials.
- Guard budget: 750 ms shared, with at most 300 ms for CLAUSE-HALL2 before
  native BDD analysis. The global wall cap still applies.
- Fixed salted-SHA source ordering and catalog-label balance, without solver
  screening. At most 12 MB compressed, 65 MB decompressed, 1 million variables,
  3 million clauses. A family with fewer than two eligible sources is skipped
  in favor of the next declared family. Every attempted exclusion is retained.
- Source selection is frozen before results. Excludes known IDs from tracked
  HALL2 files and all 100 CROSS REAL100 source SHA256 values. This is not a claim
  that no source has ever appeared in any historical branch or run.
- Solver results are never accepted based on catalog labels. Original-source
  SHA256, binaries and checkers are frozen and verified on every shard.
- Wrong SAT models, rejected proofs, contradictory verified results, missing
  trials, or duplicate trials fail the experiment. Timeouts and resource/checker
  limits get the full PAR2 penalty of 30 s.

Report three scores: MODEL/DRAT-only PAR2, independently verified PAR2 including
structural certificates, and verification-inclusive E2E PAR2. Verification time,
CPU and peak process RSS are recorded separately. Structural certificates are
not converted to DRAT/LRAT in this experiment and are not competition proofs.
The bootstrap resamples sources, not repeats, to avoid pseudoreplication.

`test_integration.py` uses 64 independent small truth-table oracles, signed Hall
SAT/UNSAT cases, native weighted scheduling cases, output-path separation, and
frozen CF7 model/proof parity. `test_recovery.py` replays all 116 frozen Hall2
synthetic controls through the complete hybrid. These controls are not part of
the 24-source standard benchmark.

No training or automatic main promotion is performed. All changes are confined
to the experimental branch. A 15 s, 24-source size-limited study is not an
official competition ranking or evidence of general superiority.

## Provenance

- CF7 source: commit `fdc5fa31495c1624b59161c3c293972ae0366c84` and the unchanged
  CF5/CF6 source transformations; generated CF7 SHA256
  `93b6526029181ea40419b3d2efecfe59b0b6ed1ad41de19ac122e3693375b4c6`.
- Hall2 source: commit `96892261f74670be842b334b43e4be27256672b3`.
- Reference binaries: archived `cf7-compiled-binaries` from run `43613581688`.
- Main list: https://satcompetition.github.io/2026/downloads/track_main_2026.uri
- Official source catalog commit: `d2f8f186dacc48b9bab7e4374aef0a3f46b96582`.

The local derivation retained the frozen source checks and recorded the compiler's
new binary hash. The earlier binary hash assertion was omitted only in a temporary
derivation of generated CF7 source; no existing frozen build script was edited.
