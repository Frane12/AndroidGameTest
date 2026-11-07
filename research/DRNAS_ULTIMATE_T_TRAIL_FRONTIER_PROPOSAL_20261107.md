# DRNAS Ultimate T — Trail-coupled XOR Frontier (research proposal, 2026-11-07)

**Status:** HYPOTHESIS / unbuilt. The proposal is based on audited R1/R2 experiments; R2x 200-attempt final audit must finish before any release claim.

## 1. The actual mathematical problem

SAT asks whether a Boolean assignment satisfies
\[
F(x_1,\ldots,x_n)=\bigwedge_{i=1}^{m} C_i.
\]
General SAT is NP-complete. Neither a few exceptionally fast XOR instances nor polynomial-looking runtime on a restricted biological or engineering family proves a polynomial-time algorithm for unrestricted SAT.

When a source CNF contains a *complete* parity encoding, identify source-certified affine equations over GF(2),
\[
E: Ax=b \pmod 2,
\]
and other original clauses \(R\) that interact with those variables. The certification obligation is \(F\models E\), checked against unchanged source SHA and an independent parity replay. The residual structure is not automatically independent of the XOR constraints.

Existing DRNAS R153 is excellent when exact source-level GF(2) detection can directly solve a special case. The unresolved goal is a *mixed* instance in which neither GF(2) alone nor ordinary clause learning alone gives a quick answer.

## 2. What is actually observed

| Audited group | R153 / reference | Candidate | Interpretation |
|---|---|---|---|
| Ultimate R1, 45 original CNFs, 630 attempts | R153 30/90 solved, PAR2 3621.489201 | R1 30/90, PAR2 3621.517500 | R1 adds no material gain over the inherited R153 path |
| R1 historical R153/R195, 50 attempts per arm | Kissat 0/50 | R1 26/50 | Real specialized advantage, but historically selected and not blind |
| Ultimate R2 original, 20 original CNFs, 200 attempts | R153 14/40, PAR2 1383.061857 | R2 Clean 18/40, PAR2 1170.721950 | Benefit of the clean native CDCL fallback |
| Ultimate R2 original, same cohort | R2 Clean 18/40, PAR2 1170.721950 | R2 Live 18/40, PAR2 1176.449248 | Live does not improve aggregate PAR2 |
| R2 native GF2 communication | 40 completed reasons in development, 0 on new-to-R1 | 6 selected activations | Certified reason delivery is not yet shown causal to faster mixed-CNF solving |
| Early bounded-prep R2 test | R2 Clean 16/40, PAR2 1235.379087 | R2 Live 16/40, PAR2 1237.634491 | Cost control helps some individual quick formulas, not general results |

The repeated R2 experiment reused the same pinned 20-CNF manifest (SHA 2e6169009e985555e43e81d9b534f3bb307cef93963329694ef42459bef3c2e2). Cross-run aggregate differences can reflect timing/seed/timeout boundaries and should not be equated with clean causal evidence; within-run paired comparisons are the primary endpoint.

R2 Shadow is certification-only plus clean CDCL, not a true *runtime* shadow XOR propagator. The native R2 UNSAT results currently lack independent LRAT/FRAT evidence. Do not conceal either limitation.

## 3. Fundamental missing signal: useful information at the CDCL trail

Let \(\alpha\) be the current partial CDCL assignment. For a verified XOR row
\[
x_{v_1}\oplus\cdots\oplus x_{v_k}=b,
\]
let \(U\) denote unassigned variables, and define restricted parity
\[
b'=b\oplus\bigoplus_{v\notin U}\alpha(x_v).
\]

- If \(|U|=1\), its one unknown literal \(\ell\) is *logically forced*; provide the sound reason clause \(\ell\vee\bigvee_{v\notin U}\neg\alpha_v\).
- If \(|U|=0\) and \(b'=1\), the source-certified row proves a conflict under the current trail; it needs a correct conflict explanation.
- If \(|U|\ge2\), this row alone generally cannot propagate. Spending O(k) per solver event with zero chance of a new unit can only introduce overhead.

Crucially, a delivered **reason clause** need not improve runtime if it confirms a propagation that ordinary CNF unit propagation would already have obtained. A useful event must precede clean propagation, shorten the implication/conflict path, or improve the learned clause.

## 4. T architecture (separate certified computation from utility selection)

### T0: R153 safe exact router and clean native baseline

Keep the trusted R153 exact XOR early decision. On genuine R153 fallback, start the existing clean native CaDiCaL solver without spending a full up-front Gaussian budget. Preserve the original CNF bytes and reference binaries.

### T1: Live, incremental XOR frontier over residual clauses

Build a lightweight variable-to-parity-row index only after a bounded structural probe. For each original *source-certified* row, maintain (i) count of unassigned variables, (ii) assigned parity, and (iii) a short reason construction path. Update on the actual CDCL assignment and backtrack callbacks, without re-running full elimination on every event.

Define a *frontier* between parity structure and residual clause graph: variables appearing both in a certified XOR component and in residual clauses. Prioritize watched rows near the CDCL trail with \(|U|\le2\), especially when the unassigned variable is also in active residual clauses. This is an **opportunity** heuristic, not a theorem that the result will be faster.

### T2: Lazy, source-first causal transfer

Import certified source rows first. Only propose a reason when \(|U|=1\) or a contradiction when \(|U|=0\), and only when the literal is not already assigned consistently. Independently verify emitted reason structure and the original source SHA. Track:

- candidate frontier rows, exact unit/conflict proposals, completed reason clauses;
- whether the proposed unit was already implied by ordinary CDCL BCP (causal-redundancy control);
- affected residual variable activity, original clauses visited, backtracks/conflicts and propagator nanoseconds;
- current native CDCL state and one-step implication-graph differences versus shadow.

### T3: Derive Gaussian rows only on observed value

If source-only live interaction shows new, useful trail consequences, and a component remains hard, compute a small, sparse, bounded, independently certified Gaussian closure for that component only. Never derive over all components speculatively; never import proof-free parity guesses. The source-level XOR certificate remains a soundness requirement independent of the performance gate.

### T4: Adaptive cost gates, with deterministic fallback

Use a bounded performance window (e.g. 256 conflicts) to assess \(\text{useful new reasons}/\text{scans}\), cost of reason construction, and stagnation of residual CDCL propagation. Disable optional parity work for a component if observed benefit is negligible or if its measured overhead breaches a precommitted cap. Never discard pending correct explanations for previously emitted propagations.

**Architectural difference from R2x:** R2x pays much of the optional parity preparation *before* seeing CDCL trail information. T is intended to make useful propagation on the actual trail the trigger for additional computation.

## 5. Six-arm falsifiable causal benchmark

Fixed arms on exactly identical original SHA sources, same CaDiCaL binary, pinned seeds and one CPU:
1. `t_clean`: original R2x clean CDCL, no XOR preprocessing.
2. `t_frontier_shadow`: same source XOR indexing and live trail scans, but no imported reasons.
3. `t_source_live`: certified original XOR frontier propagations only.
4. `t_derived_live`: source frontier plus bounded proof-replayed derived XOR rows.
5. `t_adaptive_live`: source-first live with the precommitted utility/stagnation gate.
6. `r153`: frozen R153 exact XOR with its reference fallback.

**Development:** Reuse R2/R2x 20 formulas and optionally a strictly named historical training cohort to debug soundness and choose thresholds. These are not blind and never count as final proof.

**Blind holdout:** Freeze at least 30 further SHA-disjoint *original* SAT 2025/2026/industrial CNFs before seeing any candidate run. Stratify by *static features* (10 source-XOR-heavy, 10 mixed residual-coupled, 10 weak/no-XOR) without using solve outcomes. Require source SHA-disjointness from R1/R2/R2x and from earlier tuning inputs. Run 6 arms × 2 repetitions × 30 sources = 360 new-source attempts, paired randomized arm order, unchanged per-formula caps (30 s primary; an independent 90 s hard-case confirmation), single-core CPU pinning and frozen binary hashes. Repeat positive claims across additional seeds and independent families.

**Primary endpoints:** solved SAT+UNSAT and within-cohort PAR-2; report paired win/loss/tie, censored survival statistics and stratified bootstrap confidence intervals. Avoid treating TIMEOUT/fast-ratio as a finite speedup. Correctness requires SAT original-clause witness validation and independent native UNSAT proof when available. Mark absence of LRAT/FRAT conspicuously. Separately measure the true benefit of GF(2) communication via a native runtime shadow that performs the **same scans** without delivering implications.

## 6. Objective promotion gate: what counts as a breakthrough?

Promote T only if all these conditions hold:
- Every SAT witness is checked on unchanged original SHA, certified XOR derivations are replayed, no solver-status contradiction; for native UNSAT research claims provide machine-checkable LRAT/FRAT or explicitly keep them provisional.
- On truly new original mixed CNFs, `t_source_live` or `t_adaptive_live` beats both clean and correctly implemented runtime shadow in an a-priori primary endpoint, with reproducible gains across **at least five distinct formulas and more than one source family**.
- Positive paired PAR-2 improvement survives uncertainty analysis and no meaningful category-wide regression (including weak/non-XOR controls); the cost-gate cannot silently sacrifice solved instances for an average microbenchmark.
- The winning formulas show actual certified new reasons or conflicts delivered on CDCL-critical paths rather than only source parity detection or reasons on development controls.
- The positive result is replicated without changing eligibility rules, seeds, caps, or choosing cases after observing outcomes.

If any item fails, do not claim a general SAT breakthrough. Publish a narrower, accurate explanation of which structural subfamily benefited.

## 7. Complexity and engineering hypotheses

For XOR row-variable incidence graph with \(M\) edges, building the source row index is \(O(M)\) given trusted rows, and incremental updates for one assigned variable are proportional to its incident-row degree, not to the entire matrix. This does **not** bound total CDCL search complexity; it only proposes a better amortized cost for cooperating parity propagation.

If Gaussian elimination is used, naive dense elimination may be cubic in row/variable dimension; source-first component-local sparse computations may reduce practical costs, without any universal worst-case claim. Measure wall time, callbacks, row visits, reasons and allocated bytes.

**T's central falsifiable question:** *Does certified parity information delivered exactly at the active residual/CDCL frontier cause early propagations and useful conflicts often enough to amortize its certification, bookkeeping and explanation cost on genuine previously unseen mixed SAT instances?*

This is a concrete NP-complete problem decomposition experiment, not a claim to have solved P versus NP.

## Sources

- R1 frozen audit: https://github.com/Frane12/AndroidGameTest/actions/runs/42344094697
- Original R2 frozen audit: https://github.com/Frane12/AndroidGameTest/actions/runs/42346485260
- Budget-experiment R2 audit: https://github.com/Frane12/AndroidGameTest/actions/runs/42347804147
- R2x same-original-source run: https://github.com/Frane12/AndroidGameTest/actions/runs/42348940571
- SQL cumulative evidence: research/drnas_sat_benchmark_history_20261107.sql
