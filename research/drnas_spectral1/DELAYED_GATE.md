# DRNAS SPECTRAL1B — delayed rank-gated implementation

Parent SPECTRAL1 5s REAL36 retrospective run: 43469570515. It had 6/72 verified solutions and PAR2 661.941771 s, compared with same-binary OFF 24/72 and PAR2 482.195624 s. Its spectral preprocessing took only 32.28 ms total for 72 trials; the regression came from changed branch choices, not transform cost.

Implementation: src/drnas_spectral1b.cpp, preserving exact integer Walsh in src/drnas_spectral1.hpp. Same-executable control flag --spectral1-late (OFF omits it). The feature analyzes up to 64 bounded original-CNF windows with k<=8 Boolean variables, computes exact Walsh rank and influence, **ignores full spectral-rank windows**, and leaves existing CDCL branch scores unchanged for the first 255 conflicts. At conflict 256, if any rank-deficient local spectral signals exist, it updates bounded VSIDS base scores once and continues normal CDCL. No SAT/UNSAT claims or learned clauses from the spectrum.

Scientific hypothesis: do not disrupt easy SAT paths; allow structural spectral guidance only after ordinary CDCL demonstrably struggles. The 256-conflict gate is a predeclared engineering hypothesis for retrospective testing, not a statistically optimized threshold.

Safety verification: exact parity rank1 and OR rank3 C++ self-tests, full independent SAT models and DRAT proof checks for 17 synthetic CNFs in OFF/LATE modes, SHA frozen original REAL36 SAT2024 inputs and binaries. Benchmark: .github/workflows/drnas-spectral1b-late.yml. Exactly 36 unique source CNFs in seven families, 2 repetitions, 5 solver arms X5 frozen / SPECTRAL1B_OFF / SPECTRAL1B_ON / Kissat / CaDiCaL, 5s cap, 1 logical CPU each; PAR2 and family-bootstrap 95% CI. 360 rows expected; no promotion or fresh blind claim.

Next steps if this works: dynamic Walsh analysis on a bounded CDCL residual and a separate certificate-verified XOR lemma bridge. Do not confuse spectral compressibility with polynomial-time exact general SAT.
