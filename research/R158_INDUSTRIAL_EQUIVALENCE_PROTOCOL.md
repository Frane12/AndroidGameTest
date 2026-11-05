# DRNAS R158 — Industrial Circuit Equivalence Challenge

Status: PROTOCOL ONLY — no benchmark results or performance claims.

## Research question
Can frozen DRNAS XOR/GF(2)-aware strategies improve verified SAT solving on genuine, externally sourced circuit-equivalence/miter CNFs compared with pinned Kissat, CaDiCaL and CryptoMiniSat on the same runner?

## Cohort freeze (before solver timings)
- Select 20–30 original external hardware-equivalence/miter CNFs with documented source URLs, source family, year, license, original filename, compressed/uncompressed SHA-256 and GBD identifier when available.
- Exclude all hashes from accessible prior DRNAS development/test manifests, including R152–R157. Record exclusion-list SHA-256 and limitations of coverage.
- Distinguish official SAT Competition instances from other external industrial CNFs. Do not relabel generated miters as official.
- Freeze source list, deterministic order, split and solver binary/source SHA before timing. No selection using measured R158 outcomes.
- Freeze development and untouched test by *source family*, not only file hash. Report provenance and overlap audit.

## Execution plan
- Comparator modes: unchanged R153, R157 experimental (only if verified build), pinned Kissat, CaDiCaL, CryptoMiniSat; keep V15.3.1 as a separately identified optional reference.
- Same CPU runner class and affinity, fixed timeout 60 s, 3 paired repetitions per formula and solver. Record random execution order/seed, CPU model, kernel, runner image, binary hashes and build flags.
- PAR-2 timeout penalty 120 s; retain raw wall time, exit code, SAT/UNSAT/UNKNOWN, timeout, stderr and resource usage. Never treat all-timeout as a win.
- Check every SAT assignment against original CNF; UNSAT requires independently checkable proof or independent verified reference, explicitly label any unverified UNSAT. No invalid witness/proof is acceptable.
- Store one immutable raw JSON/CSV per shard, paired formula-level results, cohort/fold aggregate, stratified formula bootstrap 95% CI, >=2x regressions/wins and all source hashes.
- Audit must refuse missing trials, duplicate pairs, source drift, binary drift, differing CPU pinning, missing witness/proof, or mismatched SAT/UNSAT answers.
- Primary endpoint: held-out test cohort PAR-2 relative to same-runner Kissat; secondary: CaDiCaL, CryptoMiniSat, R153, R157. Report per-formula solved and paired runtime; no global speed claim from a cherry-picked instance.
- An observed >=100x speedup is a *candidate* only if both solvers solve the same formula (not censored by timeout), 3 paired repeats confirm it, correctness is checked, and an independent runner replication is obtained.
- Never claim official world record without independent external confirmation.

## Stages
1. Source discovery and provenance-only freeze.
2. Dry-run 1–2 development instances and correctness audit.
3. Frozen full benchmark (no refreeze after seeing timings).
4. Independent rerun of any candidate extreme gains.

Useful external sources: https://benchmark-database.de/ and https://satcompetition.github.io/2026/downloads.html
