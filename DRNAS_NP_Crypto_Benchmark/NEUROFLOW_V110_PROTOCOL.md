# DRNAS NP v1.1 — Native C++ two-rule structural AutoSelector

**Branch:** `experiment/drnas-np-v110-native-selectivity`
**GitHub Actions:** https://github.com/Frane12/AndroidGameTest/actions/runs/41203423970

## Reason for v1.1

Version 1.0 obtained +1.543% total time saving and +1.733% median relative
saving on 42 matched completed repetitions of 14 test instances, and 48/51
completed runs versus 45/51 for plain CaDiCaL on the 17 cases with an
independent CryptoMiniSat answer. Critically, the selected majority
heuristic **lost SAT completions** in that very same experiment (21/30 vs
24/30) despite completing more UNSAT cases.

V1.1 targets fewer regressions rather than cherry-picking 10–20x outliers.

## Native implementation

The Linux C++ program `native_v110/drnas_nf110.cpp` uses the **same**
in-process CaDiCaL backend, the same DIMACS parser and the same original
clauses across all variants. During the initial parse it optionally
records signed literal counts.

The frozen selector uses at most TWO priority-ordered interpretable
conditions, each selecting either all-majority or signed-imbalance
selective `Solver::phase()` decision hints. All candidates use only
structural features:

- Variable count and clauses per variable;
- Minority sign ratio across all literals;
- Share of binary (length-2) clauses;
- Share of long (length-4+) clauses;
- Unit clause share.

No SAT/UNSAT labels, oracle results or solver outcomes are fed to the
model during inference, and it never changes SAT formula semantics.
When disabled (zero rules), the native auto route uses the same
feature-free parser and CaDiCaL solver as baseline.

A `phase()` hint is NOT a unit clause, assumption, solution,
certificate or transformation. SAT results are verified against the
original CNF, and CryptoMiniSat independently verifies completed
SAT/UNSAT statuses.

## Training, freeze and previously untouched holdout

- **100 TRAIN files**, all *already* examined in v0.6.3, v0.9.1 or v1.0:
  60 original external CNFs from two publishers, 20 Byt-Wyze from v0.9.1
  and 20 from v1.0. Any reused formula is excluded from the new holdout.
- Baseline, all-majority and selective-majority are measured with
  2 counterbalanced repeats per training case.
- Within TRAIN, stratify an internal tuning and validation split by
  source family. Search a predefined grid of shallow structural rules.
  A rule is accepted only if its training gain exceeds a noise margin,
  its independent validation subset shows **positive average
  completion-aware utility**, and there are **no extra timeouts among
  the validation cases to which it applies**. Rejected rules are NOT
  installed. The frozen model may contain 0, 1, or 2 rules.
- Frozen text policy SHA256 is printed BEFORE downloading any new files.
- **42 NEW untouched published CNFs:** 30 synthetic third-party Byt-Wyze
  files balanced by *published filename* SAT/UNSAT category, plus
  12 actual circuit-encoding CNFs from the published LGSynth89,
  ISCAS85b, and ISCAS89 collections.
  Each original source URL, upstream commit and raw-file SHA256 plus
  normalized DIMACS SHA256 is archived. No prior filename from the
  100 TRAIN files may recur.
- Run every new formula three times in rotated order: plain CaDiCaL,
  frozen AutoSelector, fixed all-majority, fixed selective-majority.
  The same C++ executable and libCaDiCaL library solve the same clauses.
  2.2-second wall cap per attempt, results of independent CryptoMiniSat
  oracle recorded. All errors, reference unknowns, and timeouts are
  visible.

## Metrics and scientific restrictions

Never report the difference between two medians of unequal cases as
percentage speedup. The summary reports:

1. Median paired relative gain (%) on only reference-confirmed
   completed baseline/mode pairs.
2. Total elapsed-time saving (%) on **exactly the same** completed pairs.
3. Number of additional or missing completed attempts out of all
   reference-known cases and all attempted cases.
4. Mean completion-aware capped utility (including penalties for
   failing to finish), SAT and UNSAT family results separately.

This is a limited, relatively small multi-family engineering benchmark
from **two known sources**; one source comprises synthetic instances.
It is not broad evidence of SAT superiority over CaDiCaL and does not
address P vs NP.

**Current platform:** native Linux C++ on the GitHub Actions
Ubuntu 24.04 runner; no Android APK or ARM64 Android build is claimed.
