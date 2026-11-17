# DRNAS XOR-LIN1 — prospective mixed original CNFs, revision V2

**Research date:** 2026-11-17. Experimental branch:
\`experiment/drnas-xorlin1-prospective-mixed12b-20261117\`.
Neither \`main\` nor the previously accepted XOR-LIN1 algorithm may change.

## Transparent v1 preflight and v2 selection

V1 preregistration (commit \`c104584\`) selected 12 exact GBD
source IDs. Its GitHub run
[44059383179](https://github.com/Frane12/AndroidGameTest/actions/runs/44059383179)
performed the certified XORLIN1 safety checks, HEAD metadata audit,
and began source-only downloads. The original REG-N CNF ID10
compressed to ~10.9 MB but decompressed beyond the *prespecified*
50 MB raw-input resource limit. V1 aborted **before** all source
SHA-256s were frozen and before any candidate or reference solver
was run on any of those 12 sources. No performance outcomes were seen.

V1 stays in Git history and is NOT retroactively reclassified as a
completed benchmark. V2 is a **new preregistered experiment** with
a single resource-based revision to ID10, replaced before any new
solver outcomes by an original non-XOR coloring UNSAT CNF, while
all other 11 source identities and both 20 MB compressed / 50 MB
decompressed caps remain fixed. New original ID10:
\`cliquecolouring_n41_k5_c4.sanitized.cnf.xz\`,
GBD \`ac347c21ca0759079c0be9a758e4e924\`,
isohash \`1b587e76d00b4e8c633f6fbd25e31a5a\`,
isohash2 \`4c216a25dbc112c6\`.
All twelve source hashes and two isohashes are locked in V2
\`research/xorlin1_prospective_mixed12/prespec.json\`
(commit \`77453e6\`), before source download/performance evaluation.

**V2 failure handling:** no further source substitutions after
performance observations, no outcome-dependent cap changes.

## Predeclared source families and controls

12 original GBD competition CNFs from 7 catalog families:
- IDs 0–3: Tseitin-formulas; catalog outcomes 3 UNSAT, 1 UNKNOWN
- IDs 4–5: XOR-chain; catalog UNSAT
- ID6: minimum-disagreement-parity, catalog SAT
- ID7: Hamiltonian, catalog SAT
- ID8: heule-nol, catalog SAT
- ID9: Hamiltonian, catalog UNSAT
- ID10: coloring, catalog UNSAT
- ID11: equivalence-chain-principle, catalog UNSAT

Catalog labels are **metadata only**. They do not enter solver
commands, source XOR classification, proof production or independent
SAT/UNSAT scoring. They can identify challenge/negative-control
groups only. Each selected source is SHA-frozen byte-for-byte,
and both GBD isohashes are compared with **all 107 previous
originals** in five separate frozen manifests; any identity overlap
halts the test.

These are previously unseen **instances** and multiple catalog
families, not family-independent source distributions or a complete
representative sample of arbitrary SAT workloads. The old 107
include Tseitin and graph instances. Public instances are not
globally secret.

## Frozen algorithm / independent checking

The XORLIN1 source-only CNF XOR-group recognizer, GF(2) elimination
and extended-VeriPB producer were certified in run
[44053818490](https://github.com/Frane12/AndroidGameTest/actions/runs/44053818490).
Their exact SHA-256s are frozen:

\`\`\`
research/xorlin1/extract.py
  7deba9716ec2165ff61434c7c326c63d564cecc5c272e9bade679484a7c151a3
research/xorlin1/emit_veripb.py
  f3636b39c9f02a7b0fdfa166b982667c64b6ffb19de64dc2229cdee8a9a4ec07
research/xorlin1/selftest.py
  19147961e174777c970695847d893518d50931377896c6936b606f0d626fd40a
research/math5/check_math5.py
  ebfec304d1823574bbf2530d3e277e468446965362f6a6a6ad7d8371473a381a
\`\`\`

Rerun prior adversarial preflight:
24 independently VeriPB-accepted GF(2) UNSAT controls, 48 known
SAT controls returning UNKNOWN, degree-4 multiple-incidence,
forged SHA rejection. No false UNSAT tolerated.

For each original case, six serial arms:
\`XORLIN1_SOURCE_ONLY\`,
\`XOR234_NATIVE_VERIPB\`,
\`X59_MATH5_VERIPB\`,
\`Kissat\`, \`CaDiCaL\`, \`CryptoMiniSat\`.
12 originals × 2 repeats × 6 arms = **144 paired E2E trials**.
One logical CPU per solver process, 8-second inclusive wall cap
(including source checks, proof generation, external proof
verification), strict timeout/unverified PAR2 penalty 16 seconds.
Only original-CNF VeriPB, DRAT/FRAT, or independently verified
SAT model counts strict. No nonstandard source JSON as a strict
proof. Missing, mismatched, duplicated, or contradictory results
are fatal critical failures. Each arm's actual strict PAR2 is
recorded even for unsupported/non-XOR originals.

Performance analysis will be explicit about successes, UNKNOWN
reasons, family-wise results and downsides on SAT/non-XOR controls;
the mixed-set total is not proof of universal speed superiority.
The final \`results/xorlin1_prospective_mixed12/final.json\`
is emitted only after all 144 trials pass aggregate audit.
No automatic main promotion.
