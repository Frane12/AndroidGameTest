# DRNAS NP Lab v0.3 — NeuroFlow policy experiment (2026-10-31)

Reproducible final run: https://github.com/Frane12/AndroidGameTest/actions/runs/41186501569
Raw results artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41186501569/artifacts/13036909320

## Why this is NeuroFlow-inspired, not a driver or neural-network port

The controller transfers the design philosophy from the user's GPU NeuroFlow experiments:
bounded work before committing, remembered outcomes, hysteresis and cooldown, tracked decision costs,
shadow observation, graceful fallback, and a strict separation between optimization policies
and correctness-critical computations. No source from the private GPU driver repository is
published or reused. This is a lightweight Python rule-based controller, NOT an NPU model.

## Mathematical solver module

Renamable Horn recognition is a *known polynomial method*:
for each CNF clause, every literal pair yields a binary constraint on
whether each variable should be polarity-flipped. A 2-SAT solution
chooses flips that make every transformed clause Horn (<=1 positive literal).
The Horn solver then finds SAT/UNSAT and a SAT assignment is mapped back and checked
against original CNF. Non-matching inputs use the v0.2 exact solver.

## Independent and control benchmark

GitHub Actions Ubuntu 24.04, Python 3.12, CryptoMiniSat 5.11.15.
160 original SATLIB instances and 24 separate *constructed* renamable-Horn controls.
Each instance was run once using matched in-process timing for v0.2, NeuroFlow adaptive
and NeuroFlow shadow. CryptoMiniSat was invoked for result consistency; comparisons
of speed below are between v0.2 and adaptive, not between Python and CMS.
Results must be repeated on held-out corpora before any generality claim.

- All 184 case outcomes matched v0.2, NeuroFlow and CryptoMiniSat; all SAT models from
  Python were explicitly validated against original formula.
- SATLIB 160: **zero** recognized renamable-Horn structures; NeuroFlow *did not* improve
  generic SATLIB performance. Median per-instance additional time across all 160
  was **0.777ms**, 30/160 individual adaptive wins, mostly dominated by overhead/noise.
- Constructed 24 controls: with refined profile keys **18/24 recognized** (prior
  coarse profile recognized 3/24). Just 7/24 adaptive wins, median per-instance
  extra time about **0.34ms**. Thus more recognition is NOT automatically more speed.
- For SAT controls with n=60, median v0.2=3.819ms vs adaptive=2.061ms,
  with 3/4 recognized. For UNSAT controls with n=60, v0.2=1.478ms vs
  adaptive=1.949ms: overhead was larger than the possible saving.
- SAT controls n=100 were mostly not recognized (1/4), because the current
  bucket and cooldown still conflate some unrelated instances. The policy
  requires finer classification and a dedicated exploitation/exploration
  balance instead of blindly increasing recognition.

## Correctness validations

- 900 random CNFs exhaustively checked by brute force, in 3 policy modes;
- 385 earlier random CNF regressions;
- 520 equivalence-preserving rewrite truth-table tests;
- 480 earlier random SAT/UNSAT brute-force reference checks;
- 8 camouflaged parity systems;
- three additional constructed renamable-Horn families and an XOR contradiction.

## Research implications

The useful principle is adaptive representation selection with
total-cost accounting. The specific policy version remains EXPERIMENTAL.
The 0.3 result does not outperform CryptoMiniSat or the v0.2 baseline generally.
A subsequent study should:
1. Separate cheap recognition from expensive transformation and measure each phase;
2. Maintain reliable local expected-gain estimates with A/B on train instances,
   freeze policy and test on entirely unseen instances;
3. Refine signature and recheck cadence using quantitative expected gain, not merely a cooldown;
4. Compare on mixed arithmetic/parity/industrial benchmark collections;
5. Run repeats and compare per-instance paired samples and timeouts.
