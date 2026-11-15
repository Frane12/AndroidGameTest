# DRNAS SAT-CONSTRUCT REAL600

Scope: 600 **public original SATLIB DIMACS** CNFs, 100 per named family:
`uf50-218` (SAT), `uuf50-218` (UNSAT),
`uf100-430` (SAT), `uuf100-430` (UNSAT),
`flat30-60` (SAT), `RTI_k3_n100_m429` (SAT).

These are external benchmark originals, not DRNAS-generated CNFs. They are well-known public benchmark families: this study is **retrospective, not blind or prospectively novel**. It cannot substantiate general performance on all real-world industrial CNFs. The last two families widen structure diversity beyond pure uniform 3-SAT.

## Fixed preregistered experiment
- All six official SATLIB source URLs are encoded in `benchmark.py`. Source choice is filename-only SHA-256 sorting (100 per family); never outcome-dependent.
- Download complete official source archives before any trial. Store each archive SHA-256, exact original DIMACS bytes, each input SHA-256, source member names and metadata in `sat_construct_600_inputs/manifest.json`. Fail closed on fewer than 100 usable originals or duplicate source SHA.
- Four isolated CI shards, one logical CPU pinned per runner, one solver process at a time; no portfolio.
- Six arms: native structural constructor; X59 + 25 ms constructor; same X59 off; pinned Kissat, CaDiCaL, CryptoMiniSat.
- One measured trial per SHA and arm (3,600 trials). Each cap is **2.0 seconds verified end-to-end**, including solver startup, reading and independent checker. Timeout, UNKNOWN, unverified answers score 4 s PAR2.
- For SAT: independently parse **original** DIMACS and check every clause against the complete reported model.
- For UNSAT: accept only independently verified DRAT or FRAT. The standalone constructor **never claims UNSAT**, so report SAT-only and mixed PAR2 separately.
- CPU and RSS per subprocess, source SHA, model check status, certificate kind and per-family detail recorded in compact JSONL files. CI log prints only one progress line per 25 sources per shard and final summaries.
- Checks fail for invalid SAT models, invalid status contracts, cross-solver contradictory verified answers or source-label disagreement. No direct changes to main, APK, frozen references, or automatic promotion.
- Source archive URLs are retrieved on the CI runner; if an archive disappears or becomes unreadable the freeze step fails and no solver test is run.

## Read the output
GitHub Actions workflow `DRNAS SAT-CONSTRUCT REAL600 verified SATLIB`:
`sat-construct-real600-frozen` contains all input SHA-256 and binary versions,
`sat-construct-real600-shard-N` contains per-trial evidence,
and `sat-construct-real600-final` contains comparison tables, totals, source metadata and summary.

No broad scientific superiority claim is valid from this single public suite.
