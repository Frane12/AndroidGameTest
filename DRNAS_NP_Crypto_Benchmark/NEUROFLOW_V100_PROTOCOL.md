# DRNAS NP v1.0 — Native structural AutoSelector

**Experimental research branch.** The project builds one C++ executable linked to the same in-process CaDiCaL library in all modes.

## Why v1.0?

The v0.9.1 independent third-party heldout showed a median relative gain on matched runs of **+5.52%** for selective phase hints, but the summed time on those same completed pairs was **6.94% slower**, because the largest regressions outweighed the many small gains. It also solved 54/54 reference-known runs versus baseline 48/54. Those findings demonstrate the need for a *routing decision*, not a globally enabled phase heuristic.

## v1.0 inference

The original CNF is parsed **once** in C++ and passed unchanged to CaDiCaL. Signed literal counts may be accumulated inside that parse and used to select one of:

- `base`: exact original CaDiCaL, no phase hints.
- `phase-majority`: preferred branching towards the majority literal sign.
- `phase-selective`: majority only for variables with at least 8 occurrences and 60% absolute sign imbalance.
- `auto`: a frozen simple interpretable structural gate choosing BASE, majority or selective. No SAT/UNSAT labels or solver outcomes are known at inference.

The model evaluates formula size, clauses-to-variables ratio, overall minority sign ratio, and long-clause share. It chooses search polarity via CaDiCaL's `Solver::phase(lit)` API. **No clauses, assumptions, or SAT proofs are changed.** SAT witnesses are checked against the original CNF.

When no training policy is authorized, or the frozen selector is disabled, `auto` uses the same parsing/solver path as the baseline (apart from lightweight policy input).

## Train/freeze/never-seen test

1. Download a pinned version of the 60 CNFs from the previous v0.9 external benchmark and 20 from the previous v0.9.1 study: all 80 are TRAIN data. They were previously tested by DRNAS, so we do not mislabel them as independent.
2. Measure baseline, majority and selective phases under the **same native CaDiCaL executable**, with two repeats and rotated order.
3. Split TRAIN by third-party source family into tuning and internal validation subsets. Choose at most **one simple gate**, requiring at least six tuning examples meeting the rule, plus positive conservative utility including timeout penalties. Enable only if internal validation also shows net improvement, at least three accepted validation cases, and **no drop in completion** on those cases. Else freeze **BASE/OFF**.
4. Hash and print the frozen text policy. Only **after that** generate 20 fresh predetermined third-party Byt-Wyze SAT/UNSAT CNFs, excluding all 36 filenames previously tested from this publisher. Original URLs, exact commit hash, raw SHA-256 and canonical SHA-256 are archived.
5. Benchmark frozen AUTO vs BASE vs forced majority and forced selective with three rotated repeats, independent CryptoMiniSat reference, and SAT-witness checking. No threshold changes after seeing the holdout.

### Statistical caveats

The holdout is 20 third-party **synthetic** formulas, from only **one publisher**. Family and file-size selection make it an engineering reproducibility test, not representative of arbitrary SAT instances.

The reported speed metrics must distinguish: (a) median of per-run relative gains, (b) total runtime on paired completed runs, and (c) how many runs each method solved. Faster conditional results are not sufficient if some cases time out. Any apparent advantage on this small holdout requires replication across other independent application domains.

### Links

Workflow: https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-np-v100-autoselector.yml

Binary compilation (Linux x86_64 GitHub runner):

```sh
g++ -std=c++17 -O2 -Wall -Wextra -pedantic native_v100/drnas_nf100.cpp \
    -lcadical -lz -pthread -o native_v100/drnas_nf100
native_v100/drnas_nf100 --input sample.cnf --mode base
native_v100/drnas_nf100 --input sample.cnf --mode auto \
    --policy native_v100/training/frozen_policy.txt
```

This is an experimental native **Linux C++** build, not yet an Android ARM64 build.
