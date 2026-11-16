# DRNAS MATH5 standard VeriPB — frozen real67 verified PAR2

2026-11-16, independent experimental branch only:
`experiment/drnas-math5-veripb-real67-20261116`.

## Exactly what changed

This experiment wraps the previously frozen, single-process **native X59+MATH5**
solver (from successful GRAND UNIFIED run `43853390060`) with a sequential,
external, **source-verified VeriPB 3.0 proof translation stage**. The
underlying native solver is not rebuilt or edited. A single logical CPU is
pinned for each solver/checker attempt. This is NOT a concurrent portfolio
and does NOT claim that VeriPB runs inside the X59 C++ executable.

On each original CNF:

1. Charge source SHA, native startup, all preprocessing and solver time to
   one shared 8-second E2E cap.
2. If native emits SAT, verify the complete original source model.
3. If native emits a source-bound MATH5 JSON UNSAT certificate, require
   `research/math5/check_math5.py` to verify it independently against the
   unchanged original DIMACS.
4. Then invoke `research/math5/emit_veripb_eo_multiplicity.py` to generate
   source-grounded cutting-planes proof. Its deliberately narrow supported
   family is uniform-degree positive exactly-one incidence contradictions,
   q selected EO groups, each variable occurring d>=2 times, q mod d!=0.
   Mixed XOR/root-unit MATH5 proofs are UNSUPPORTED in this exporter; they
   remain custom-source verified, never standard-scored.
5. Require external `veripb-tool/bin/veripb --cnf ORIGINAL.cnf proof.pbp`
   to return success and explicitly print `s VERIFIED UNSATISFIABLE`
   **before** strict success is assigned. Any incomplete, rejected,
   timeout or unsupported proof receives strict PAR2 penalty 16 seconds.
6. If the native route yields a DRAT trace rather than MATH5, use the
   independent frozen `drat-trim` checker. All unsupported cases fall back
   safely to ordinary native search within the same wall cap.

The source input SHA, C++ frozen binary hashes, standard verifier binaries,
new exact exporter SHA and benchmark code SHA are recorded in the run's
immutable `protocol.json` and verified in every job.

## Nine scientific safeguards

* One logical CPU per *solver trial*; all 8 arms run serially inside each
  source/rep pair. Different GitHub shards are independent runner machines.
* No source-name/expected-label ever fed to any solver.
* SAT requires a direct model check against unchanged original source.
* Standard VeriPB, DRAT, FRAT are scored separately from custom JSON.
* **Both** structural-inclusive and competition-standard strict E2E PAR2
  are always reported. The primary scientific comparison is strict.
* The source and binaries are SHA-pinned from the completed GRAND UNIFIED
  `43853390060` artifact. No cherry-picking by solving outcome.
* Complete 67-source, 2-repetition, 8-arm matrix = **1,072 trials**.
  Any absent/repeated trial aborts aggregation; timeouts are not pruned.
* Critical checker failure, a bad SAT model, contradictory independently
  verified SAT/UNSAT answers, or wrong certification flag makes the run fail.
* Paired differences include a 95% confidence interval clustered by
  original CNF family (not treating two repetitions as independent families).

## Frozen comparison arms

1. `X59_MATH5_VERIPB` — **new** native X59+MATH5 plus external standard
   VeriPB export and independent verifier within same 8 s cap.
2. `X59_MATH5` — unmodified historical source-verified MATH5 JSON score.
3. `X59_OFF` — unchanged frozen native X59 CDCL baseline.
4. `CORE1_FROZEN` — pinned previously combined constructor/ARG3/MATH5.
5. `CXX_BDD3` — pinned PCMAX+IPG1+BDD2/3+MG7 CDCL native union.
6. `Kissat`, 7. `CaDiCaL`, 8. `CryptoMiniSat` — unchanged references.

Those are *separate serial candidate arms*, not an unverified attempt to
compile all distinct X59, X5, and BDD algorithms into one executable.

## Reproduce on frozen exact sources/binaries

GitHub Actions:
`.github/workflows/drnas-math5-veripb-real67.yml`

Restore `grand-union-sha-pinned-binaries-sources` from run
`43853390060` and unpack `grand_unified_frozen.tgz` at repository root.

```sh
python3 -m py_compile research/math5_standard_real67/benchmark.py
python3 research/math5_standard_real67/benchmark.py prepare
python3 research/math5_standard_real67/benchmark.py shard --index 0
# ... shards 1 through 9, each writing immutable trials.jsonl
python3 research/math5_standard_real67/benchmark.py report
```

CI performs `prepare`, all 10 shards, and `report` as separate jobs;
a complete result is `results/math5_veripb_real67/final.json`.
The GitHub Actions summary contains strict and structural PAR2 totals,
standard certificates by input ID, critical issues and family bootstraps.
Compact live logs print per-source/rep; all solver-level evidence remains
in `trials.jsonl`.

## Previous evidence, not yet new real67 findings

A completed independent VeriPB 3.0.2 verification on two original
`count` SAT2026 formulas, source IDs 25 and 31, four E2E attempts:
all 4/4 standard proofs accepted, aggregate 0.847491 s versus
Kissat 0/4 within 8 s (strict PAR2 64 s). That was a targeted
**post-discovery** result and is not a complete family-blind benchmark.
This new full67 audit tests whether the strict proof benefit remains
when all originally frozen inputs and overheads are counted.

No claim of overall numerical victory or a completed CI result is
valid **until** the new workflow finishes successfully, with the
complete 1,072-row matrix. Reusing these 67 already examined original
CNFs remains retrospective development evidence, not a prospective
source/family-disjoint blind generalization study.

Promotion to `main` is **not authorized** by this experiment; an
independently frozen future holdout, checker-included PAR2 gain,
zero false answers, and explicit user review are still required.
