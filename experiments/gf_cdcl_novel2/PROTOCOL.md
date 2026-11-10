# GF-CDCL NOVEL2 — cross-row GF(2) novelty gate
Date: 2026-11-10
Branch: `experiment/drnas-gf-cdcl-novel2-20261110`

## Preregistered hypothesis
Two independently original-CNF-entailed XOR rows can imply a short new XOR relation. This relation can propagate a variable under the CDCL trail when conventional unit propagation of the original CNF cannot. Deliver only cross-row consequences from `gf2_pairwise_closure` in the `novel2` mode. All other source rows are passive. Shadow arm executes the same derived-row checks without changing the trail. The baseline direct arm uses the previously existing mixed-source+derived propagation.

## Positive control
- Original complete-CNF parity encoding: `x1 xor x2 xor x3=0`, `x1 xor x2 xor x4=0`; original CNF unit `x3`.
- Repeat ordinary CNF UP on the original clause encoding: `x4` remains unassigned.
- Algebraic GF(2) sum gives `x3 xor x4=0`; therefore `x4` becomes true.
- Independently exhaustive 16-assignment proof that the derived relation and binary reason `(x4 or not x3)` follow from the two original parity rows.
- Direct native implication, complete IPASIR-UP reason, backtrack undo, shadow-no-delivery tested.

## Frozen nonblind first smoke
- 40 previously used XORABC3 original SHA; source-only select top 2 by number of short, independent derived XOR rows (no outcomes or execution times).
- Four same-binary variants: clean, direct, novel2, novel2_shadow.
- Two repetitions, six-second nominal cap, one logical CPU, 16 attempts. SHA, SAT witness, native reason counters and wall E2E recorded.
- Backend UNSAT has no independent original LRAT in this smoke, therefore excluded from strict verified-solved summaries. Count SAT only if original-CNF witness checks.
- Reason counter is completed reason clauses, not necessarily a distinct net-new CDCL assignment; `derived_direct_proposals` is a proposal metric, not proof of benefit or original-CNF UP novelty in a specific live state.
- A synthetic positive-control result alone is insufficient to promote. Only advance if measured derived proposals, appropriate proof and E2E benefit emerge.

## Stop/promotion gates
- Always stop on failed native mathematical tests, missing source certifications, missing original SHA, missing SAT witness, or unexpected solver exit.
- If `novel2` does not deliver a single derived reason on the smoke, inspect trail scheduling and row selection; do not automatically launch 400+ trials.
- If delivered, compare with source-only, clean, and cost-controlled shadow on an independently preregistered unseen set. Include independent UNSAT proofs before claiming general SAT/UNSAT results.
- No modifications to main.
