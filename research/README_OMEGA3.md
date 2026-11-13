# DRNAS MATH Ω3 — source-frozen prospective external SAT study

Status: experimental. NOT a SAT Competition ranking, a new theorem, a standalone
DRNAS SAT engine, or a claim of general superiority. The experimental branch
is isolated from \`main\`; no APK or Android build is involved.

## Frozen source selection

- 300 paths selected before any outcome-dependent search in
  \`research/omega3_frozen_300.json\`, from the exact external
  \`Tractables/cnfs\` commit \`de4731f68e5a5bb6629269b3be1d19b44e812763\`.
- 170 holdout and 130 validation across 11 preselected source categories,
  with family-level separation. No model training or optimizer tuning occurs.
- Each external Git blob SHA-1 is verified before decompression, and every
  original uncompressed DIMACS SHA-256 is retained. Duplicate SHA-256 values
  must be excluded from the global aggregate. All invalid/oversized sources
  count as missing evidence, never as solved.
- The source collection includes authentic, independently assembled circuit,
  hardware-model-checking and configuration formulas, plus model-counting
  competition and random SAT formulas. Some inputs were originally intended
  for model counting: here we test ONLY SAT of their base CNF, NOT counting,
  projection or weights. Formula origins and failure rates are shown separately.
- Small published SATLIB-like families / R194 known data are not used for
  tuning a champion here. SHA/family overlaps with the earlier project
  must be audited explicitly before calling a subset genuinely blind.

## Fixed treatment arms (one logical CPU per solver)

1. \`KISSAT\`: unmodified exact binary from DRNAS R194 archive, SHA-256
   \`c96ebe32a7e333a02acad462679a0bbfbeeec54a7f9210421c4c0c8d53bbf95f\`.
2. \`CMS\`: Ubuntu 24.04 \`cryptominisat\` package. Runner logs version and SHA.
3. \`OMEGA3\`: pure source-certified XOR3, source-complete exact-k (k=1..3,
   widths 2..4), graph-cut when possible, bounded GF(2) Gaussian elimination
   with row ancestry, independent source-fragment semantic verifier.
   If no verified UNSAT proof exists under 0.2 s, run frozen Kissat on remaining
   time. No SAT inference from an incomplete parity basis.

Total cap: 2 seconds per arm and original formula (including detector cost).
Order alternates by frozen source SHA. Six parallel GitHub CI shards with one
logical CPU **within each paired solver run**; parallel shards are not counted
as multicore speedup.

## Verification and scoring

- Original SAT: independently verify every solver's assignment against
  the exact original CNF.
- Ω3 UNSAT: independent verifier reconstructs every <=4-variable clause
  premise, truth-table-checks each derived row, and XORs all rows to 0=1.
- Kissat/CMS UNSAT: labelled \`UNSAT_UNVERIFIED\` until independent original-CNF
  DRAT/LRAT proof checking is provided; **never** count these as independently
  verified UNSAT claims.
- Keep separate reported and independently verified PAR-2 scores. The
  former may include solver-reported UNSAT; the latter penalizes uncertified
  UNSAT. A valid SAT model or independently certified UNSAT is required for
  independently verified PAR-2. Report coverage, timeouts, source skips,
  inconsistencies, per-family regressions, and total source integrity.
- A performance improvement is credible only if paired multi-family results,
  uncertainty intervals and the blind holdout confirm it **after all overhead**.
  Negative findings must be retained.
- Runner uploads only JSON summaries, logs, binary pins, manifest and proofs
  (when present); it does not re-publish potentially restricted external CNFs.

## Falsification criteria

If Ω3 finds zero source-certified cross-theory contradictions on all 300,
the narrow extractor does not transfer to this corpus; do not present
synthetic Ω2 wins as general SAT speedup. If detected proofs are already
fast under CMS/Kissat, the method may add no net benefit. If source
download/verification or reference installation fails, report that as
INCOMPLETE, never as a positive test result.

Source collection: https://github.com/Tractables/cnfs
Original DRNAS reference: https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737
