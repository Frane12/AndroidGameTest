# DRNAS XORLIN-CDCL1 V2 — final prospective mixed12 audit (2026-11-17)

**GitHub Actions:** https://github.com/Frane12/AndroidGameTest/actions/runs/44071331788

**Source-first selection:** V1 originally frozen before source download;
initial CI preflight import bug run 44070338062 and source-size preflight
run 44070631698 failed before **any solver performance outcomes**.
Source-only V2 revision is separately preserved at
\`de3cf2b8e46c5d4620d4240932ff6c69273fd0dd\`;
it replaced two resource-ineligible/risky catalog UNSAT originals
before running a solver, while retaining the other ten.
The V2 source manifest SHA-256 is
\`de9360812d92e81fdb6d96251c566d3390d1a709b1de75db02a518c5e164f578\`.
All 12 actual original source hashes are distinct from the
previous 119 originals by GBD hash, both isohashes and raw SHA.
The source labels are metadata, never evidence of correctness.

**Frozen candidate executable SHA-256:**
\`2046aee7f7cb1eb3dfc44b2e7a7b5a9f69b482230f106a4aaea93ab968f60646\`.
Identical binary for mathematical gate ON/OFF, intrinsic X59 C++ CDCL,
embedded SHA-pinned Python GF2 math, no second solver process.
The source parser, mathematical algorithms, resource budgets and
baseline binaries remained unchanged. One logical CPU per solver,
serial arms within each paired shard, 8s inclusive wall-clock E2E,
16s strict PAR2 penalty on UNKNOWN/timeouts/unverified results.

## Final GitHub independent audit

- **SUCCESS**, four of four shards plus aggregation; exact **120/120**
  attempts, 12 authentic originals × 2 repetitions × 5 arms.
- **0 critical errors**, **0 ON-solved-to-unsolved regressions** vs OFF.
- All certified results independently verified as original-CNF
  SAT model, VeriPB, DRAT or FRAT as appropriate.
- All candidate results on this sample are **SAT model verified**,
  not GF(2)/VeriPB UNSAT. Therefore the mathematical gate
  generated **no incremental certified UNSAT proofs** here.

| Solver | Strict verified / 24 | Distinct sources | Strict PAR2 total (s) |
|---|---:|---:|---:|
| Hybrid ON | 8 | 4 | **262.250680** |
| Hybrid OFF | 8 | 4 | **261.683749** |
| Kissat | 12 | 6 | **206.634933** |
| CaDiCaL | 12 | 6 | **207.024024** |
| CryptoMiniSat | 8 | 4 | **264.930663** |

Hybrid ON is **0.217% slower** in strict PAR2 than identical
Hybrid OFF, with identical strict coverage. ON is **26.915%
slower** than Kissat in strict PAR2 on this selected mixed12.
Do NOT claim a positive global speed result from this run.
Family distribution differs from the earlier Tseitin-only pilots.

**Individual original sources supported by the integrated CDCL route
(both repetitions, strictly verified SAT model):**
- ID0 hamiltonian SAT, \`x9-04045.sat.sanitized.cnf.xz\`
- ID2 agile SAT, \`bench_3169.smt2.cnf.xz\`
- ID5 bitvector SAT, \`g2-newton.8.3.i.smt2-cvc4.cnf.xz\`
- ID7 station-repacking SAT, \`43-116107.cnf.xz\`

**New certified UNSAT from the *references*, but NOT Hybrid ON/OFF:**
- ID3 \`DivU_545_9.cnf.sanitized.cnf.xz\`:
  independently DRAT-certified by Kissat and CaDiCaL,
  FRAT-certified by CryptoMiniSat, 2 repeats.
- ID11 \`6s16.cnf.xz\`: independently DRAT-certified by Kissat and
  CaDiCaL in both repeats.

**Notable SAT control not solved by Hybrid ON/OFF:**
- ID8 \`unif-k5-r21.3-v120-c2556-S1963731659-060.cnf.xz\`:
  CaDiCaL and CryptoMiniSat independently verified SAT model,
  Hybrid ON/OFF both exceeded E2E cap.

**Gate overhead on easier verified SAT originals:**
- ID0: Hybrid ON E2E 0.309/0.047s vs OFF 0.012/0.012s.
- ID2: ON 0.685/0.464s vs OFF 0.479/0.467s.
- ID5: ON 1.931/1.855s vs OFF 1.910/1.840s.
- ID7: ON 0.478/0.479s vs OFF 0.476/0.486s.
In this trial no GF2-certified UNSAT case improved throughput.
The observed ON runtime overhead on easy SAT is a reason
to redesign gate activation, not to promote the candidate.

## Scientific conclusion and next experiment

This is useful independent confirmation of **same-process CDCL fallback
correctness** on multiple real SAT originals with zero observed false
UNSAT and no lost strict solves relative to the identical gate-OFF
binary. It does **not** demonstrate performance synergy yet,
and the standalone XORLIN1 program's previous same-family results
cannot be transferred into an unseen mixed-source claim.

Keep this hybrid as **experimental**; no main promotion.
Next engineering iteration: no embedded CPython startup on clearly
non-XOR CNF, sub-millisecond native cheap structural pre-gate, and
eventually a native C++ GF(2)+proof emitter, preserving exact source
SHA, original VeriPB/DRAT correctness and one-CPU serial budget.
Then use a separate new preregistered development/validation/holdout
set and compare ON/OFF and latest baseline solvers.
