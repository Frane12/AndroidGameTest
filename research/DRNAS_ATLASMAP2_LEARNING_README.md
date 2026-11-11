# DRNAS MAP2-L — Persistent, explainable strategy memory

**Status:** isolated experiment. `main` unchanged.  
**Base:** ATLAS-MAP2 source-certified live CDCL trail.  
**Goal:** after each **training invocation** remember which structural method was actually useful, *why*, and with what original-CNF evidence. Reuse the strategy, **never reuse an unproven logical deduction**.

## What is stored

The JSON `--memory` journal contains one record **per distinct original source SHA-256** and a structural-signature summary. Each record contains:

- source SHA, variables/clauses, complete source XOR-2 pair count, eligible parity components and a coarse structural signature;
- matched **A / MAP2_SHADOW / MAP2_LIVE** results on the *same original CNF*, full end-to-end seconds and PAR-2, SAT witness verification, decisions, conflicts, actual injected CDCL implications and passive opportunities;
- a plain-English explanation of the **method**, its causal mechanism, evidence for the outcome, speed ratio, decision/conflict deltas and explicit limitations;
- the selector's aggregate evidence, conservative confidence gate and a human-readable reason for the selected mode.

**There is no cache of assignments, SAT answers, unverified equivalences or proof obligations.** On every new formula the native MAP2 detector must find both exact source clauses again. History only selects whether to spend effort on live MAP2.

## Two distinct phases (strict no-leak policy)

**Train:** `--phase train` runs A, SHADOW and LIVE on the same original CNF. It verifies each SAT witness on the input formula before accepting the result. It then atomically appends a new SHA-distinct record. Duplicate source SHA does not inflate evidence. UNKNOWN and UNSAT without independent certification cannot count as positive speed evidence.

**Evaluate:** `--phase eval` loads the existing journal and chooses `A` or `LIVE` from *frozen training data*. It **does not modify the memory file**, and the evaluation SHA is never added to the training samples.

A signature activates LIVE only if **at least three distinct original SHA** in that signature have verified SAT outcomes, genuine source-entailed CDCL reasons, **median A/LIVE E2E speed ratio at least 1.10**, and **no >15% regressions** among usable training samples. Otherwise the conservative choice is A. This gate is a preliminary heuristic, not a statistical significance test or guaranteed performance gain. The program records each decision and explanation.

### Usage

```sh
mkdir -p mre_atlasmap2/bin
python3 research/drnas_atlas1_generate.py --out mre_atlasmap2/atlas1_table.hpp
g++ -std=c++17 -O2 -I mre_atlasmap2 research/drnas_atlasmap2.cpp -o mre_atlasmap2/bin/drnas_atlasmap2

# Updates memory and explanation after one paired training experiment:
python3 research/drnas_atlasmap2_learn.py train.cnf \
  --binary mre_atlasmap2/bin/drnas_atlasmap2 \
  --memory experiments/map2_memory.json --phase train --cap 6 \
  --report experiments/train_report.json

# Uses that memory but cannot change it (clean prospective evaluation):
python3 research/drnas_atlasmap2_learn.py unseen.cnf \
  --binary mre_atlasmap2/bin/drnas_atlasmap2 \
  --memory experiments/map2_memory.json --phase eval --cap 6 \
  --report experiments/holdout_report.json
```

Use a persistent `--memory` path across **successive training invocations**; the file is atomically rewritten and retained between local runs. A GitHub Actions runner is ephemeral: the CI job uploads the memory and reports as an artifact, **not** as an automatically writable shared database. For a truly cross-workflow persistent learner, restore a versioned training-only memory artifact or keep the memory in a controlled data branch; never silently mix holdout outcomes into it.

## Meaningful benchmark

`research/drnas_atlasmap2_learning_bench.py` generates **12 different source-locked planted SAT mixed-CNF problems** (24 variables, 7 certified parity edges plus 90 planted 3-CNF clauses and one source unit), deterministic SHA and seed. Six source SHAs train MAP2-L; six **disjoint source SHAs** form a never-trained frozen holdout.

Each cohort additionally receives **3 matched repeats** of native A, SHADOW and LIVE, one logical CPU, 2-second cap, with per-arm PAR-2 and solved counts, original SAT witness verification, live implications, passive opportunities, decisions and conflicts. It also checks:

- every training record has a method explanation and observed benefit;
- duplicate training SHA cannot inflate sample counts;
- the memory file remains **byte-identical throughout holdout evaluation**;
- all holdout SHA remain absent from the memory;
- selection on holdout is driven exclusively by frozen training evidence.

This is **a designed mixed-structure functional/causal experiment**, not an official unseen SAT competition result. The 12 formulas are artificially constructed with planted SAT witnesses, so they are not a demonstration of broad superiority. Real-world external source-locked holdouts and independently checked original-CNF UNSAT certificates are separate future milestones.

**Core interpretation:** a live implication is only a potentially useful operation. It is *not* proof of faster search. Always compare original E2E PAR-2, solved counts, decisions and conflicts with the baseline and shadow under the same CPU constraints.

**GitHub CI:** `.github/workflows/drnas-atlasmap2-learn.yml` publishes `audit.json`, `train_memory.json`, per-formula explanations and the exact original CNFs as artifacts.
