# DRNAS R197 — isolate CDCL resumption schedules; prospective original SAT2026 holdout

## Scientific question

R196 demonstrated that one CaDiCaL solve interrupted at 256 conflicts and
continued with the **same solver instance** can outperform uninterrupted
CaDiCaL on selected R195 CNFs, but it can also regress. The exact cause is
unidentified; keeping a solver alive preserves much more than clauses.

Source audit: https://github.com/Frane12/AndroidGameTest/actions/runs/42337423044
CaDiCaL SHA: 31f9aae44947c673dc6190c9beb399acb9ffec6a

CaDiCaL's incremental `Internal::init_search_limits` resets three
scheduler categories upon the next `solve()` entry, even after reaching a
256-conflict cap: restart limit, rephase limits, and
stabilization/reluctant scheduling (with possible stable-mode change).
These are plausible causal mechanisms, **not yet proven explanations**.

## Experiment A: surgical component ablations (development, NOT blind)

Four previously observed R195/R196 real original CNFs and four frozen seeds
(11,23,37,47) × seven modes = **112 trials**:

- `default`: uninterrupted patched CaDiCaL with normal behavior
- `split256`: normal 256-conflict interruption and continuation
- `split256_keep_restart`: skip *only* restart limit reinitialization
- `split256_keep_rephase`: skip *only* rephase limit/interval reinitialization
- `split256_keep_stabilize`: preserve stabilization mode/schedule and reluctant restart generator setup
- `split256_keep_all`: preserve all three schedule categories
- `split128_twice`: two 128-conflict intervals; number of solve entries control

The patch is limited to the three scheduler reset categories on
*incremental* solve entry. It does not explicitly modify learned clauses,
activity scores, phase arrays, reasoning or inference logic. There can be
interactions among schedule categories: single-component interventions
do not uniquely identify all solver state changes.

Machine-readable `R197_STATE when=before/after` records effective
restart limit, rephase limit, stabilization limit, active stable flag and
rephase counters across resumed solve entry. Final CaDiCaL native counters
cover conflicts, decisions, propagations and restarts. All overhead is
charged to the wall-clock.

## Experiment B: prospective holdout

A separate **eight new-to-R195/R196 original official SAT Competition 2026
CNFs** are chosen before testing by sorting public GBD IDs with a
precommitted SHA-256 ordering. Exclude all 37 R195 frozen original IDs and
SHA-256 values, plus any duplicate accepted source. Selection depends only
on source availability and size, not SAT labels or performance. Use three
frozen seeds (11,23,37), `default` vs `split256` only = **48 trials**.

**Important: these are new to the R195/R196 source sets, not proven
globally unseen across every historical DRNAS run.** The prospective
holdout tests transfer but does not by itself support a world-record or
independently blind claim. Neither the ablation results nor the holdout
results are allowed to change this experiment's frozen controls.

## Common controls and limitations

- CaDiCaL commit fixed to 31f9aae44947c673dc6190c9beb399acb9ffec6a
- All original CNFs pinned and SHA-checked before each attempt
- 45s cap; 2× cap penalty for timeout (PAR2)
- Matched source and seed in each arm
- SAT witnesses checked against original CNF
- Native UNSAT labels lack independently checked LRAT
- CPU and output costs charged; GitHub-hosted runner noise remains
- Audit rejects missing source×seed×mode arms and inconsistent SAT/UNSAT outcomes

## Decision rule

Use development ablation results to identify which schedule resets
correlate causally with outcome changes. Only the precommitted
`default` / `split256` pair is evaluated on the separate prospective
source pool. Do not market any universal SAT speedup unless more
independent benchmarks support it.

Files:
- research/r197_patch_cadical.py
- research/r197_state_driver.cpp
- research/r197_state_blind_benchmark.py
- .github/workflows/drnas-r197-state-isolation-blind.yml

CI: https://github.com/Frane12/AndroidGameTest/actions/runs/42340440152
