# DRNAS NeuroFlow v0.6.2 — fast Horn recognizer study

This is a research experiment, not a claim of a novel SAT complexity result.

## What changed since 0.6.1?
- The global OFF mode invokes the existing exact solver immediately, with zero feature extraction.
- An inexpensive literal pass computes signed minority frequency, presence of unit clauses, and majority-flip candidates.
- Only plausible inputs get a second, cheap check: the number of clauses still non-Horn after majority polarity changes.
- If exactly zero clauses violate the Horn criterion, use the verified Horn solver directly.
- Otherwise, attempt sound renamable-Horn 2-SAT recognition with a fixed time cap; on failure or timeout, fall back to the original exact solver.
- For SAT outputs, reconstruct and verify a satisfying assignment against the original formula. The model never predicts SAT/UNSAT outcomes to route cases.
- Gate thresholds are selected using paired training measurements including all probing overhead. No test timings enter selection.

## Independent evaluation
- GitHub Actions run: https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-neuroflow-v062.yml
- Training formulas: 100 SHA-audited original SATLIB instances selected in v0.6.1 + 72 fresh constructed control cases.
- Test formulas: 100 previously unselected SATLIB instances + 72 other constructed control cases.
- Archive exhaustion: uf75-325, uuf75-325 and flat30-60 each have zero unused originals after prior tests. They are intentionally excluded from BOTH splits instead of reused.
- Test families: uf20-91, uf50-218, uuf50-218, uf100-430, uuf100-430, and separate constructed renamable-Horn SAT/UNSAT + near-Horn controls.
- Each held-out case measured three times in counterbalanced order.
- Comparison: original DRNAS, adaptive fast Horn v0.6.2, always-on fast Horn and the v0.6 disabled controller with 17-feature overhead.
- Original SATLIB formulas retain SHA256 provenance; canonical DIMACS is semantically equivalent.
- CryptoMiniSat 5.11.15 validates SATLIB outcomes, not used as an in-process speed baseline.
- Tiny CNFs are exhaustively solved to validate strategies.

## Caveat

The SATLIB family set is smaller than the previous 160 because archives have been exhausted. The constructed controls are intentionally Horn-like and must not be represented as a random representative SAT sample. Any speedup is domain-conditional; pooled medians are sensitive to family mix. Performance of the selector and the solver should be evaluated separately with costs counted.
