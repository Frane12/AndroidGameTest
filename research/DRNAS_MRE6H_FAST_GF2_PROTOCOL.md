# DRNAS MRE6h — in-process certified GF(2) / CPU-aware representation experiment

Date: 2026-11-08
Experimental branch: experiment/drnas-mre6h-fast-gf2-cpu-20261108
Benchmark GitHub run: https://github.com/Frane12/AndroidGameTest/actions/runs/42507215971
Source baseline: same six SHA-frozen, previously used MRE7/MRE6f/MRE6g SAT2026 originals
Source frozen artifacts: run 42503866092, with original source.sha256 verification.
Native solver: exact pinned MRE5-instrumented CryptoMiniSat 5.11.15 revision
3b709118fd08eb1d15f25e0e239dbc596f967b60, OTF Gauss disabled.

## Scientific question

MRE6g genuinely removed four original CNF variables by GF(2)-certified
signed SCC equivalences on one reused SAT2026 problem. However, end-to-end
wall was still higher than CMS+source XOR: 7.350+7.037 vs
6.578+6.735 seconds on its two paired native seeds (MRE6g run).
The prior method spent ~0.145s each on spawning a child, separately
re-parsing CNF, full GF(2)+bounded resolution, proof JSON serialization,
then independent re-verification in parent.

**MRE6h isolates whether retaining exactly proof-correct mathematical
equivalence extraction while avoiding child process and generic resolution,
plus optional suppression of redundant source XOR import, improves total
CPU cost.** It makes no claim that fewer variables guarantee lower
backend solve cost.

## Mathematical proof method

- Detect source XORs only from complete parity CNF patterns, replaying
  every violating assignment against the ORIGINAL CNF.
- Form GF(2) rows as bit masks and record provenance bitsets.
- Produce equations of width two by bounded elimination and optional
  inexpensive XOR pairs (each is exact mod2 arithmetic).
- Project each x_i XOR x_j = b to the TWO CNF binary implications, and
  replay each derived lemma with independent MRE1.verify_proofs over the
  original CNF and exact source rows. An unproven lemma cannot be used.
- Build signed SCC equivalence graph and require a certified implication
  path in both directions. Negative representatives x_i = NOT x_j are
  supported.
- Substitute proven representatives simultaneously in the original CNF,
  transforming imported XOR rows where enabled. On SAT, reconstruct the
  eliminated original values and verify EVERY original clause.

Caps: 150 source XOR rows; 48 derived certified clauses; local 20,000
pair checks; SCC graph and short-proof time budget on the fast path
~0.30s. In comparison, the old MRE6g mechanism remains unchanged as
a separate matched benchmark arm.

## 60 full-solving comparisons

6 original official SAT2026 CNFs (3 SAT, 3 UNSAT; 2 reused known-solved
anchors and 4 externally reference-selected medium inputs); two frozen
native seeds per original; five strategies; 35 seconds complete
end-to-end wall per attempt, PAR2=70 seconds on timeout.

1. native_no_xor: original CMS, no optional XOR import.
2. source_xor: original CMS plus proof-checked source XOR rows.
3. graph_scc_gf2: unchanged legacy MRE6g SCC+child GF2, optionally
   importing source XOR rows.
4. fast_gf2_with_xor: MRE6h in-process proof-producing GF(2) and
   signed equivalence quotient, with verified transported source XOR rows.
5. fast_gf2_no_xor: same certified quotient, without *additional*
   source XOR rows imported into CMS; the original CNF is retained with
   mathematically safe signed variable substitution.

The experiment must audit exact original SHA, paired native seed and
settings, number of verified SAT models, independent official UNSAT
status consistency, both full wall and completed native process CPU,
preprocessing wall/CPU, eliminated variable count and abstention status.

## Research caveats

- This is a reused development cohort, NOT a new blind formula holdout.
- GF(2) proof generation and verified quotient are separate from
  clause-specific live CDCL CPU attribution.
- The native CPU timer only covers solve(); Python preprocessing CPU and
  full wall include other operations. A timeout lacks final native
  solve CPU counters. No independent UNSAT LRAT certificate is generated.
- A candidate that is faster on the already reused active formula must
  still pass a fresh source-disjoint official benchmark before any
  production selector promotion.
- All five modes must be evaluated on all six originals even if no
  useful equivalence is found, with safe abstentions counted.
