# DRNAS SAT / ATLAS — Global mathematical experiment rule

**Scope:** every new SAT/mathematical experiment (including ATLAS, PCMAX, graph/coloring/clique, XOR/GF(2), matching/Hall, structural preprocessing and cross-module experiments) in this repository. Unrelated Android application projects are out of scope.

**Primary objective (HR):** Svaki fallback na CDCL je istraživački signal da strukturna matematička metoda još nešto ne razumije. Istraži uzrok, razvij i provjeri novo pravilo. Cilj je da DRNAS SAT / ATLAS ubuduće rješava problem bez potrebe za CDCL-om.

## Non-negotiable experiment policy

1. **Structural-first; no silent CDCL substitution.** The mathematical/ATLAS experiment arm must clearly distinguish structural reasoning from a conventional CDCL backend. When structural reasoning cannot complete within budget, report `STRUCTURAL_GAP`, `UNKNOWN` or `TIMEOUT`, as appropriate, rather than silently taking a CDCL answer as its own result.
2. **Every CDCL fallback is a research finding, not a structural success.** Even if Kissat/CaDiCaL/CryptoMiniSat proves SAT or UNSAT after fallback, the structural arm remains unresolved. Do not report the fallback solve as evidence that a mathematical module solved the original CNF.
3. **Investigate every gap.** Record the exact original input and SHA-256, problem family, n variables / m clauses, attempted modules and their evidence, the trigger and reason for fallback, budget consumed, unresolved structure or missing theorem, and a reproducible run/commit reference. Create a specific hypothesis for the missing invariant, lemma, reduction or inter-module communication.
4. **Repair through proof-grounded mathematics.** Design the smallest sound new structural rule/module, demonstrate it on a minimal counterexample, add negative controls, and verify its source-CNF soundness. Check SAT assignments against the original input; for UNSAT demand an independently checkable proof where claimed. A heuristic guess or backend UNSAT flag alone is not an independently verified proof.
5. **Retest and track transfer.** Re-run the triggering instance, family variations, nonmatching families and unseen/holdout instances; include regressions and negative results. State the setup, one-logical-CPU conditions, time limits and end-to-end cost. Only mark a gap `CLOSED_STRUCTURALLY` after the structural arm itself completes correctly with the stated verification.
6. **CDCL is allowed only as an isolated reference/diagnostic for this research goal.** Conventional solvers can provide baselines, counterexamples and provisional diagnostic answers. Label those runs `REFERENCE_CDCL` (or equivalent) and do not blend their solve counts/timing into the structural arm. Existing safety fallbacks must not be removed from production or completeness-critical code until a verified replacement is ready.
7. **Long-term direction: eliminate dependency on CDCL.** Do not treat lower fallback frequency as a proof of general polynomial complexity or universal superiority. Report the remaining unsolved families explicitly and continue to improve coverage with certified structural methods.

## Required fallback audit fields (adapt existing schema; do not invent a claim of automated enforcement)

- `original_cnf_sha256`, `family`, `variables`, `clauses`, `source_run`, `commit`
- `structural_modules_attempted`, `structural_status`, `fallback_trigger`, `reason`, `time_budget_s`
- `missing_structure_hypothesis`, `next_mathematical_action`, `verification_status`, `holdout_status`
- Keep `REFERENCE_CDCL` outcomes separate from structural-arm outcomes.

## Definition of done

For a fallback case, completion means: **a documented structural explanation + a sound implemented rule + source-level SAT model or independently checked UNSAT proof as applicable + reproducible rerun + negative controls**. Until then, the case stays open as a structural research gap.

This file is **research/contributor guidance**, not evidence that existing CI or solvers already enforce these requirements. Implement automated guardrails and telemetry in each experiment harness before claiming machine-enforced compliance.
