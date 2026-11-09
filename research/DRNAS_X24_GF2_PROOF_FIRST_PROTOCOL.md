# DRNAS X24 — GF(2) Proof-First native C++ (2026-11-09)

Experimental branch: experiment/drnas-x24-gf2-proof-first-20261109.
No changes to stable main, frozen X22/X23/X23G, or baseline binaries.

## Main hypothesis

Do not just visit the SAT search space faster: extract a mathematically sound
representation in which some search is not needed. X24 implements CNF ->
fully source-certified XOR equations -> sparse GF(2) row reduction ->
independently replayed short consequences -> redundant CNF clauses.

The C++ analyzer never edits CNF. For every k=2/3/4 XOR block it requires
all 2^(k-1) distinct original clauses covering the entire forbidden parity
half-cube. Each E certificate records exact original clause indices;
each D certificate records equation indices combined by XOR. Incomplete or
partially guessed XOR patterns have no authority. The independent Python
checker rereads the ORIGINAL CNF and verifies every source clause, pattern
parity, source ID, and GF(2) combination. Only then does it append implied
units, binary (in)equality clauses, or a contradiction. Original clauses
are never removed. These are independently replayable mathematical
implications, NOT external LRAT/FRAT certificates.

If extraction exceeds 0.75 s, fails, or replay fails, original Kissat +
CaDiCaL are used (fail-closed). All preprocessing enters the 15-second E2E cap.
With successful replay, Kissat sees original CNF; CaDiCaL sees augmented CNF.
Every SAT model is checked against original SHA CNF. For UNSAT scoring,
original Kissat+CaDiCaL agreement from frozen X22 is required; NOT LRAT.

## Protocol

- 24 original-source SHA cases previously used by X21/X22: replay, NOT blind.
- 2 repetitions, 3 arms: original dual race; X22 signed SCC quotient race;
  native C++ GF(2) proof-first augmented dual race.
- 8 parallel shards x 18 tests = 144 SHA-matched end-to-end measurements.
- 15 s wall cap, 30 s PAR2 penalty; two pinned logical CPUs.
- Pinned input/reference binary hashes from completed X22 run 42591977333.
- Native+replayer synthetic XOR tests, partial XOR rejection, contradictory
  XOR test, random small CNF and exhaustive SAT-equivalence proof checks.
- Final report: solved, PAR2, CPU, replay yield, implied-clause count, regressions.
- No auto-promotion to stable branches.

If no complete XOR half-cubes occur in the 24 source cases, an absence of
benefit is an informative negative result. The next step is a genuinely
unseen real XOR-enriched holdout with pre-registered source SHA exclusions.
