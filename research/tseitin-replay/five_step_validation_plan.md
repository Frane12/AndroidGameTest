# Five-step SAT validation

1. Freeze exact candidate commits and binary checksums; separate live from shadow.
2. Preselect 400 SHA-distinct, previously unseen CNF formulas across official, external XOR, external non-XOR and application families.
3. Run paired comparisons against pinned Kissat, CaDiCaL and current competition solvers on identical hardware with verified SAT witnesses.
4. Report solved count, paired PAR-2, uncertainty, regressions, and scatterplots; label UNSAT without proof unverified.
5. Train early structural GF(2) gate on development only and test on independent held-out formulas.

No frozen V15.3.1 changes. Do not ingest until full raw audit and successful SQLite artifact. Existing R132 run 42050320220 is incomplete at registration; R131 42048686203 is retrospective. Historical analytics artifact 13423658142 remains baseline.
