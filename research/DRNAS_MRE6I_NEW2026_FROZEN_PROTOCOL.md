# DRNAS MRE6i — precommitted XOR structural gate + cross-representation proof protocol

Date: 2026-11-08
Branch: experiment/drnas-mre6i-prefilter-new2026-20261108
Successful SOURCE FREEZE run: https://github.com/Frane12/AndroidGameTest/actions/runs/42509063941
Workflow: .github/workflows/drnas-mre6i-cheap-xor-gate-new2026.yml
Experiment design: 8 SHA-frozen CNF sources × 2 frozen native seeds × 5 modes = 80 true SAT/UNSAT full solves, 35 s maximum end-to-end wall per attempt, timeout PAR2=70 s.

## Source provenance and strict cohort distinctions

- 2 REUSED_known_solved_diagnostic SAT2026 originals copied SHA-identically from the completed MRE7 frozen official subset. NOT blind.
- 4 NEW_official_reference_medium SAT2026 CNFs selected entirely from official public CaDiCaL3[Main2026] verified status and published runtime strata, SHA-salted deterministic order and fixed source size limits. No DRNAS solve time or structural suitability is used to select them. Historical exclusion registry and all prior six MRE7 originals are excluded where identifiable; the historical registry is NOT exhaustive, so full historical source-disjointness is not guaranteed.
  * New SAT: ee44c3f464238366729bf2cb16eb412a (CaDiCaL3 ref 3.94 s)
  * New SAT: 8117a2ac08e1acf52f660663efe2a5ca (CaDiCaL3 ref 14.08 s)
  * New UNSAT: 805a742eb8b4e0df3561ca8e0670670b (ref 113.24 s)
  * New UNSAT: 372021735d9e46002b862aa2a038a818 (ref 642.71 s).
  Because none of the eligible fresh UNSAT candidates fell into the originally intended 0.75–5 s band, the external-reference-only UNSAT strata were broadened BEFORE any DRNAS benchmark to 0.75–180 s and 180–3600 s. These UNSAT cases may be too hard for the fixed 35 s CMS limit and must be counted as timeouts, not silently removed.
- 2 NEW_synthetic_XOR_controls: fixed-seed, planted SAT, respectively 240 and 480 variables, with multiple complete XOR3 CNF blocks and random planted 3CNF clauses. Guarantees meaningful mathematical activation/abstention coverage but does NOT count as real-world speed evidence.

All 8 source bytes are SHA-locked in mre6i_sources/manifest.json and source.sha256, and verified independently in each runner job.

## Five source-paired configurations

1. native_no_xor: frozen exact CryptoMiniSat 5.11.15 source SHA 3b709118fd08eb1d15f25e0e239dbc596f967b60, source CNF unchanged.
2. source_xor: baseline CMS with only original-CNF independently replayed source XOR blocks (if source CNF size <= 35,000).
3. fast_gf2_no_xor: reference MRE6h in-process proof replay + signed equivalence quotient without XOR import.
4. mre6i_gate_no_xor: prefilter before XOR scanning, same exact GF2 proof and signed quotient but no XOR import.
5. mre6i_gate_with_xor: prefilter and verified GF2 signed quotient, optionally transporting independently proven source XOR rows.

OTF Gaussian disabled for all modes; native C++ CMS bridge and frozen native seeds are equal within each source/rep pair.

## Gate algorithm, limitations and correctness

The inexpensive structural gate samples the first at most 6,000 original CNF clauses for a variable set of width k=2…6 appearing at least 2^(k-1) times, a NECESSARY condition for a fully encoded k-variable parity relation. This is NOT sufficient proof and all candidate source rows MUST subsequently pass exhaustive original-CNF truth-table replay. If none appears in the sample, the method abstains rather than rewriting the CNF.

This sampling admits safe **false-negative abstention** when the relevant XOR encoding lies later in the original CNF. The gate is therefore a selective speed/cost heuristic, NOT an exact negative detector. Comparisons to the exhaustive MRE6h baseline and explicit gate telemetry quantify the missed opportunity risk.

The certified signed SCC quotient itself requires both implication directions to replay against original CNF or independently replayed GF2-derived binary lemmas, and any SAT model must be reconstructed and checked on every ORIGINAL CNF clause. No independent UNSAT LRAT is generated; results are official-status crosschecked only.

## Reporting requirements

Provide solved count, cap timeouts, PAR2 seconds and × speedup vs clean CMS; report separately NEW official, REUSED anchor, NEW synthetic cohorts. Report prefilter attempted/abstained and source-row count, GF2 derived binary lemmas, eliminated variables, preprocessing CPU/wall cost and actual native solve CPU for completed solves. Distinguish an observed synthetic mechanism from real-source out-of-sample performance. Preserve failed tests and never alter source inclusion in response to DRNAS trial performance.
