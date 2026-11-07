# TK — XOR/CDCL research diagnostic and next experiment

Date: 2026-11-07. This branch contains diagnostics, an experimental protocol and a completed easier mixed paired benchmark; it does not contain a newly promoted solver.

## Verified findings

- R194 run https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737, commit 8229dc79bbb55577e1f0850ea3153a6740d18d38, 38 previously exposed formulas, two repetitions, six arms, 12 s cap and 456 trials. SAT models checked on original CNFs; native CMS/Kissat UNSAT results lack independent LRAT. Audit passed but is not proof of general speedup or a blind holdout.
- Recomputed from the four R194 trial job logs: of the 91.264 s PAR-2 advantage for CMS+R28 over CMS on 25 external instances, 91.000 s came from the seven complete-XOR sources (14 attempts); 4 mixed-residual sources timed out in every arm (8 attempts/arm); 8 non-XOR controls also all timed out. On 6 XOR-plus-units sources (12 attempts/arm), CMS was 79.670 s, R28+CMS 79.406 s, GF2 hybrid4+CMS 92.300 s. All solved counts were 12/12. These are aggregated PAR-2 seconds, not elapsed speedups per formula.
- C1 run https://github.com/Frane12/AndroidGameTest/actions/runs/42358062002, commit 186e240b0a5cad2c3ceb20115efa848af27b2039, 50 reused sources x 2 reps x 6 arms = 600 attempts. Cooldown 26/100, PAR-2 4362.496 vs clean 26/100, 4362.131; versus shadow 4362.410. No validated gain, and both C1 modes failed promotion.
- Examining the 600 C1_TRIAL log entries shows all 172 recorded cooldown reason completions and 3023 proposals concentrated in two timeout repetitions of ONE original, source SHA f512310ff59312431ced5edd09a473ebe1c11e6f2dc3baccf3cfde68dc493827. In C1's native-started cooldown attempts, 26/30 timed out without terminal telemetry. Recorded counters are lower bounds; absence of counters must not be treated as absence of activity. A reason completion is not proof of useful downstream conflicts or time savings.
- R191 https://github.com/Frane12/AndroidGameTest/actions/runs/42383032510 exported zero feedback candidates in aggregate. Its external cohort reported zero propagation calls; live invocation alone is therefore not evidence of CDCL coupling on that cohort.

## Reproducible diagnostic

Download C1 audit artifact, and run:
`python3 research/drnas_tk_reason_diagnostic.py path/to/all-trials.json --mode c1_lazy_cooldown`

The script rejects duplicate source/repetition records and reports per-source recorded proposals, completed reasons and missing terminal telemetry. Counts do not establish causation or capture missing counters. The original C1 audit is authoritative for its recorded fields.

## Follow-up research plan

1. On a separate development cohort collect bounded periodic telemetry before process timeout, including source SHA, solver binary/build, CDCL decisions/conflicts, reason requests/completions, row/watch scans, CPU and wall overhead. Verify telemetry survival at timeout; clearly separate no events from missing data.
2. Compare the same source and solver with clean, observed-only, and active source-certified reasons using randomized paired order and fixed seeds. Measure the on/off effect rather than extrapolating from number of proposals. Include a telemetry-disabled control to quantify instrumentation overhead.
3. Determine whether reasons participate in conflict analysis and later learned clauses when the backend exposes this safely; otherwise report the metric as unavailable. Replay or verify derived reason entailment, guard backtracking and reason lifetime, validate SAT models against original inputs, independently check available UNSAT proofs and explicitly report missing proofs.
4. Selectively test work on short active XOR rows and rows touching residual-CNF variables, with fixed resource ceilings and safe fallback. This is a hypothesis, not an established optimization.
5. Stratify complete XOR, XOR plus units, genuine mixed residual and non-XOR controls. Keep held-out sources and families unseen during tuning, with SHA and family leakage checks; compare CMS, CaDiCaL/Kissat and same-backend controls end-to-end. Report solved, paired win/loss/tie, per-family PAR-2, overhead and timeouts; include longer caps and do not infer performance from timeout ties. Do not promote without correctness, real activation and predeclared holdout gates.

## Completed easier mixed diagnostic (2026-11-07)

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42391271033
Harness fix commit: 8bc044249aef60651d680cb5c372e393204b0bd1.
Final status: TK_MIXED_AUDIT_PASS; 12 deterministic planted SAT formulas, three repetitions, three arms, 108 attempts, 8 s cap. This is a generated development cohort, not external or globally blind validation.

| Arm | Solved | PAR-2 / capped elapsed sum (s) | Extra time versus clean | Recorded proposals / completed reasons |
| --- | ---: | ---: | ---: | ---: |
| Clean | 36/36 | 1.575181 | reference | 0 / 0 |
| Shadow | 36/36 | 1.722849 | +9.37% | 0 / 0 |
| Active cooldown | 36/36 | 1.740688 | +10.51% | 0 / 0 |

All generated witnesses and solver SAT models were checked. All requested modes started, but no proposals or completed reasons were recorded. These small cases establish that the repaired paired harness runs; they do not establish a benefit from XOR reasons, and relative differences at this scale are dominated by millisecond overhead. Do not promote C1 from this test. R28+CMS remains a candidate for further validation; the external R199 run is separate and still requires its own final audit.

The previous harness incorrectly required eligible=true from the clean negative control. The fix requires source SHA and actual native mode for every arm, plus eligibility for shadow and active. It rejects UNSAT on known-SAT planted sources and reports PAR-2 separately from elapsed time so paired timeouts do not produce artificial time savings. Local checks covered all 12 planted witnesses and real streaming XOR probes, negative activation/SHA/status cases, and a 108-row all-timeout PAR-2 audit; the real GitHub run subsequently passed all three shards and the final audit.
