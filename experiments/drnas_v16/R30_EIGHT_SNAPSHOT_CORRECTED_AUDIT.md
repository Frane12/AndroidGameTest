# DRNAS SAT R30 — post-hoc audit of eight nominal extra-GF(2)-unit snapshots

Date: 2026-11-03
Original completed run: https://github.com/Frane12/AndroidGameTest/actions/runs/41625096987
Original data artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41625096987/artifacts/13224948055
SHA-frozen CNF artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41625096987/artifacts/13225442284

**CORRECTED CONCLUSION:** All eight snapshot records labelled as providing new GF(2) unit assignments came from three UNSAT synthetic XOR formulas where the **verified XOR system already gives 0=1 at the root trail**, before any CDCL conflict. Four formula/checkpoint combinations appear twice in matched repeats. These unit counts are **not** evidence of eight useful, non-contradictory additional propagations.

## Replicated observations (both repeats matched)

| Formula | Snapshot threshold / actual conflict | Raw GF2 singleton deductions after original-CNF BCP | Next recorded conflict checkpoint | New learned clauses before next checkpoint |
|---|---:|---|---:|---:|
| xor3_hidden_00.cnf | 256 / 258 | x47=1, x53=1 | 1024 | 674 |
| xor3_hidden_02.cnf | 256 / 257 | x63=0 | 1028 | 704 |
| xor3_mixed_00.cnf | 1024 / 1026 | x70=1 | 4097 | 2959 |
| xor3_mixed_00.cnf | 4096 / 4097 | x66=1, x67=1 | no later snapshot | unknown |

- 2 repeats × 4 unique checkpoint combinations = **8 snapshot records**.
- Each R30 GF(2) contradiction flag was TRUE and original-CNF plain BCP conflict flag was FALSE.
- Additional CDCL conflicts between the checkpoints: respectively 766, 771 and 3071; the 4097 snapshot has no later conflict checkpoint. These counts show observed *continued work*, not a causal explanation for it.
- The later solver trail is not the same assignment context. In \`hidden_00\`, x53=1 appears at the next checkpoint as a reason-propagated literal, while x47 is assigned the **opposite** value there (x47=0). In \`hidden_02\`, x63=0 reappears as a *decision*, not a proven learned consequence. In \`mixed_00\`, x70 is not assigned at the next checkpoint. Do **not** claim these events prove or disprove algebraic intervention benefit.
- Both original and passive solver runs ultimately reported UNSAT, with exactly the same SAT/UNSAT status.

## Independent original-CNF proof audit

For each of the three SHA-frozen formulas:
- 264 variables; \`hidden_00\` and \`hidden_02\` have 384 original clauses, \`mixed_00\` has 404.
- Independently verify **192 sound single-variable resolvents** obtained from 192 disjoint pairs of original clauses.
- Verify **48 complete 3-variable parity-CNF blocks**, each with all four forbidden-sign clauses.
- GF(2) coefficient matrix has rank **47**, but the augmented system has rank **48**. XORing all 48 derived equations cancels every variable and gives **0=1**.
- This already holds at the original empty assignment; plain original-CNF BCP finds no root-level contradiction.
- This is standard algebraic parity reasoning and a synthetic property of the constructed formulas, not a new complexity result or evidence of general SAT improvement.

Source SHA256:
- \`xor3_hidden_00.cnf\`: \`72dcd2d25f64049fac81f096725723c5c138b29eaf54e9164915edbfcd0faacf\`
- \`xor3_hidden_02.cnf\`: \`d7c5f5edac54098cc455501e010dd4ccf9b0646ecad1ff77418439ff1460bd39\`
- \`xor3_mixed_00.cnf\`: \`ec18c41985e54fcef3edc2b1617075ee0d97556e3650e93c244afb35e8e52f9a\`

## Source of the misleading signal

The R30 retrospective analyzer \`rank_units\` records reduced-system single-variable equations even when the same equation subset also yields a contradiction. Its \`verified_GF2_extra_units\` field did not check the \`contradiction\` flag before labeling them "extra units". In an inconsistent conjunction any literal is formally entailed, so unit evidence is not an informative optimization predictor. **The signal taxonomy must change before training a selector.**

Recommended mutually exclusive priority order at each checkpoint:
1. \`GF2_UNSAT_PROVEN\` (proof trace validated; return to solver only after a separately reviewed intervention implementation).
2. \`GF2_ADDITIONAL_UNITS_IN_CONSISTENT_SYSTEM\` (non-contradictory verified units under identical original-CNF BCP closure).
3. \`GF2_NO_NEW_INFERENCE\`.
4. \`NO_VALID_SNAPSHOT\` if trail export is incomplete or input scan is guarded.

Do not train on the 8 nominal unit signals as positive examples. For future work, test truly **consistent mixed XOR/CNF** cases where a gap exists without a root contradiction; track the original trail projection, future conflict outcomes, and a causal randomized intervention only after a frozen development model.

**Scope:** This is a completed post-hoc audit of saved R30 SHA-verified original CNF inputs and logs. No new R30 CDCL run or runtime intervention was conducted in this report.
