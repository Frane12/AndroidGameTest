# DRNAS XOR234 prospective original Tseitin graph10 — immutable evaluation plan

**Research date:** 2026-11-17  
**Experimental branch:** \`experiment/drnas-xor234-prospective-grid10-20261117\`.  
**Never touch** \`main\` or any pinned source/reference solver binary.

## Background

The source-checked MIXED XOR2/3/4 → VeriPB RED/RUP/CP exporter
\`research/math5/emit_veripb_xor234_split.py\` was tested on two *retrospective*
original SAT Competition Tseitin grids (ID5, ID6) and independently
certified in run
[44046723180](https://github.com/Frane12/AndroidGameTest/actions/runs/44046723180):
4 out of 4 accepted standard UNSAT certificates, 1.086181s
strict E2E PAR2 compared with 64s for the frozen Kissat/CaDiCaL/CMS
reference arms. These two source files were examined during proof
development; the outcome is not blind.

This workflow freezes **ten distinct original GBD sources** chosen using
only publicly available metadata *before* reading any of their CNF
bytes or running our new or reference solvers.
The 10 exact immutable GBD identifiers and the 32-character isohash
and 16-character isohash2 were committed FIRST in
\`research/xor234_prospective_tseitin10/prespec.json\`
(commit \`1d7a8f4a114e71bea5a31ecddc07d7f3940f8673\`).

## Source choices, original GBD metadata

| New ID | Original source filename | Catalog/track |
|---:|---|---|
| 0 | tseitin_grid_n11_m20.sanitized.cnf.xz | main_2024 |
| 1 | tseitingrid5x185_shuffled.cnf.xz | anni_2022 |
| 2 | tseitingrid6x175_shuffled.cnf.xz | anni_2022 |
| 3 | tseitingrid6x180_shuffled.cnf.xz | anni_2022 |
| 4 | tseitingrid6x200_shuffled.cnf.xz | main_2024 |
| 5 | marg5x5.shuffled-as.sat03-1455.cnf.xz | main_2024 |
| 6 | urqh1c5x5.shuffled-as.sat03-1468.cnf.mis-103.debugged.cnf.xz | main_2024 |
| 7 | hypercube5.shuffled-as.sat03-1435.cnf.xz | anni_2022 |
| 8 | hypercube4.shuffled-as.sat03-1434.cnf.xz | anni_2022 |
| 9 | urqh2x5.shuffled-as.sat03-1473.cnf.xz | anni_2022 |

GBD source: https://benchmark-database.de/?context=cnf

Source tracking **must not use filenames, family labels, catalog SAT/UNSAT
labels or source ID for solving or proof emission**. These fields
only serve preregistration, stratification and audit metadata.
The source recognizer receives the raw untouched CNF and an
independently generated, SHA-bound native MATH5 certificate.

All selected instances belong to the **broad Tseitin-formulas family**;
some may encode different graph degrees, XOR widths, or optional clauses.
Therefore we are making an **instance-level prospective generalization
claim only**, not an independent-family holdout claim. Publicly known
competition formulas are not globally secret.

## Source isolation and freeze gates

The 2026-11-17 completed original run \`44043273439\` supplies exact
reference SHA-pinned binaries and the frozen manifests for **97 previously
tested originals**: 67 + 10 + 10 + 10. All ten new instances are checked
against these 97 for exact GBD source hash, 32-digit isohash and 16-digit
isohash2. If any collides the test aborts without any solver execution.
All ten GBD sources are downloaded as-is, bounded to 20MB compressed and
50MB decompressed, syntax-validated as DIMACS, independently SHA256-frozen
and packed into an immutable archive *before* solver execution.

If any GBD file has become unavailable, is too large, or does not match
the preselected metadata, the stage fails closed: **no replacements**,
no opportunistic resampling after outcomes. If source manifest is
incomplete, even partial solver performance metrics are invalid.

## Comparison protocol

10 authentic CNFs × 2 repeated paired runs × 7 serial arms = **140 trials**:

- \`XOR234_NATIVE_VERIPB\`: unchanged native X59+MATH5 structural detection
  + previously certified mixed XOR2/3/4 source-bound extended proof
  + standard external VeriPB original-CNF validation.
- \`XOR234_SCOUT_THEN_MATH5\`: first attempt same proof path with 1.0s
  budget, then sequential old MATH5-with-standard-exporter fallback
  in the *remaining* shared 8s budget. Never a simultaneous portfolio.
- \`XOR3_OLD_VERIPB\`: previous unchanged XOR3-only exporter.
- \`X59_MATH5_VERIPB\`: previous unchanged native X59+MATH5 and restricted
  exact-one standard VeriPB exporter.
- \`Kissat\`, \`CaDiCaL\`, \`CryptoMiniSat\`: unchanged baseline binaries,
  independent SAT-model/DRAT/FRAT verification, one thread.

Every arm uses **one logical CPU**, same 8s E2E inclusive wall cap
(source SHA checks, native solve, source-certificate audit,
proof generation, external checker), timeout/unverified => PAR2=16s.
No structural custom JSON can be counted in strict UNSAT.
All independent verifier failures, source SHA mismatches, contradiction
between independently accepted SAT and UNSAT outcomes, missing or
duplicate trials are critical. No source outcomes are allowed to change
selection or extend caps after evaluation.

The workflow's independent adversarial preflight reruns 24 synthetic
VeriPB-verifiable UNSAT source tests and 48 known-SAT and 24 source-hash
tamper controls before downloading the selected original CNFs.

Five shards, at most three running in parallel; each shard runs all
7 arms **serially** for each of its two source IDs and two repetitions.
Final \`results/xor234_prospective_tseitin10/final.json\` is emitted
**only if all 140 trials are present and independently audited**.

The per-family cluster bootstrap is **not statistically meaningful**
with just one broad catalog family; focus on full source-by-source
paired differences, proofs and failures. No promotion to main.
