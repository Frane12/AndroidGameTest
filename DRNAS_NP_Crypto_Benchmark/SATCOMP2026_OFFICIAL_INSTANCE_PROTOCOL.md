# DRNAS NP — SAT Competition 2026 official-instance research PAR-2

**GitHub Actions run**: https://github.com/Frane12/AndroidGameTest/actions/runs/41204322891

## Authoritative official source

The SAT Competition 2026 organizers published an official 400-entry
Main Track URI index on August 10, 2026:

https://github.com/satcompetition/2026/blob/main/downloads/track_main_2026.uri

The selected instance list is fetched from immutable official commit
`3e2dee7cf5aa643c77bf946280a3c1c520756ef9`. The 400 hash IDs
and full URI index SHA256 are captured. A deterministic sample of 24 is
chosen **before any downloads or solves**, random seed `20261031`.
All original CNFs must originate from the exact listed Global
Benchmark Database (GBD) `/file/<hash>` addresses. Failed/oversize
downloads are recorded, NEVER replaced with unrelated/easier benchmarks.
The run artifact contains the exact selected identities, original byte
SHA256, decompressed DIMACS SHA256, parsing details and all failures.

## Honest scoring scope

This is a local GitHub Actions **reproduction using original official
competition instances**, *not* an official SAT Competition ranking.

Official Main Track 2026 used a **5000 second** time limit, an official
KIT/HoreKa cluster, the full selection of 400 instances, and
SAT witness / UNSAT proof checking.

Our limited smoke study instead uses:
- One Ubuntu 24.04 GitHub-hosted runner.
- **24** uniformly selected original official benchmark hash IDs.
- Up to 18MiB downloaded source and 32MiB decompressed text per case.
- Local per-attempt **12s** cap and 2 counterbalanced repeats.
- The same in-process `libcadical` compiled C++ wrapper in both arms:
  `base` and `auto`.
- Freeze to the exact `v1.0` learned rule from the *earlier*, unrelated
  benchmark: majority phase if **n >= 300** and
  **clauses / variables >= 3**, otherwise no hints.
- No retraining on official 2026 cases, no winner-specific tuning.
- Official-like local PAR-2: each completed run contributes measured
  full external process wall time; each timeout/error contributes **24s**
  (twice the LOCAL 12s cap), on *exactly the same downloaded cases*.
- Status consistency between methods is checked and SAT witnesses are
  checked against input clauses. **No independent DRAT/FRAT UNSAT proof
  checking is currently implemented, so this is NOT an eligible
  official Main Track submission.**

Only original official CNFs that were successfully acquired can be
tested. A source unavailable to GitHub/too large for sample caps is
recorded as a sample-acquisition failure and excluded from the common
downloaded-case PAR-2 denominator. This creates size/network coverage
bias and is not a complete official-competition score.

The run reports:
- How many of 24 selected official files downloaded successfully;
- Exact hashes and fixed-source provenance;
- Full status and time for both arms on every downloaded file;
- Solved counts and local PAR-2; percentage improvement
  `100 * (1 - PAR2_auto / PAR2_base)`;
- Count and per-run relative gain only when *both* methods finished;
- All resource and methodological limitations.

The prior **+1.54%** observed on private research benchmarks is NOT
a prediction of the performance here. If the results are poor or
inconclusive they remain public in the audit manifest.

## Future scientifically proper evaluation

A sufficiently equipped independent system should use ALL 400
original 2026 instances, 5000-second limit, competition-grade memory
and CPU environment, externally verified SAT witnesses AND UNSAT
proofs, and exact submitted solver source versions.
Even then that remains an independent reproduction, never an
"officially recognized performance" until recognized by organizers.
