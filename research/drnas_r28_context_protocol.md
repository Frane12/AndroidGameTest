# R153/R160 algorithm base with persistent contextual learning

This experiment extends commit `f5e7ea76f0b0ea6dedc0db30ba1befceba47400b` on a separate branch. The frozen mathematical base remains R153 (R28 complete source parity equations plus original units), with the R160 design of exact algebra first and structural selection on abstention. R160's binary/Horn criterion, read at `b14abe967589f0dc9941fa76d553c320480101a5:research/r160_r153_r135_dispatch.cpp`, is used as a context feature. The old R160 external Kissat/CaDiCaL dispatch is intentionally replaced by our own native DRNAS continuation. This is a derived native solver, not a claim to reproduce the unchanged R160 dispatcher.

## Cheap execution path

- The exact GF(2) stage runs first. It does not open the learning database or change proof rules.
- Existing native clause statistics classify size, density, unit presence and clause mix into 72 structural contexts. The mix includes R160's >=32 observed clauses, binary fraction <20%, Horn fraction <50% criterion. Horn inspection is bounded to 2000 complete clause samples and 16384 literals from already-parsed source clauses; no extra text parse.
- Early search (first four windows) and established search maintain separate priors. LTM13 observes real conflicts every 64 conflicts and uses LBD/work feedback to change search parameters. The feedback is a surrogate, not a measured speedup or learned SAT theorem.
- Native search reads one <=64 KiB immutable text snapshot. There are at most 72 x 2 x 4 = 576 statistical cells. No SQLite calls, disk writes or model service in the conflict loop.
- Python's standard-library SQLite handles storage before/after each solve. In batch mode the connection and unchanged snapshot are reused. The database stores structural scores and original-source SHA hashes, not CNFs, assignments or learned clauses.

A single formula contributes at most four evidence units per context/phase/arm. Older weight decays by 2% on an update and is bounded to 128. Snapshot export requires weight >=8 (at least three distinct contributing formulas after decay), then reduces the initial prior to ONE observation. New within-formula observations can therefore override inherited memory quickly. Existing low-reward fallback to arm 0 remains. Confidence gating reduces risk but does not establish a performance gain.

## Persistent and verified

`drnas_memory/memory.sqlite` contains versioned `meta`, `stats`, and `formulas` tables. A transactional SHA deduplication check prevents the same source from being learned repeatedly. Each formula's new window counts/sums are committed once; loaded prior counts are never re-ingested. Only independently verified SAT or mathematical UNSAT results may contribute. Unknown, timeout, generic unverified UNSAT and invalid answers do not update scores. This deliberately biases initial training toward verified completed solves; timeout learning is not implemented.

Schema `DRNAS_R28_CONTEXT_V1` fixes feature mapping, arm semantics and reward definition. Changing these incompatibly requires a new schema/artifact version and explicit migration. Malformed native snapshots fall back to cold parameters. Corrupt or incompatible saved SQL artifacts fail validation rather than silently erasing knowledge.

Training and evaluation hashes are mutually exclusive permanently in the database. Evaluation statistics are frozen, checked by digest before/after the entire holdout. Formulas from previous training cannot become evaluation cases. These safeguards use exact source SHA; near-duplicate or isomorphic formulas are not automatically detected. Generated train/holdout use distinct seeds and CNF bodies, but are related synthetic distributions, not independent application families.

## Across builds

`.github/workflows/drnas-r28-context-learning.yml` supports push, workflow_dispatch and workflow_call. Before compiling, it locates the latest successful run of this workflow containing `drnas-context-memory-v1`, downloads it, checks SHA256, SQLite integrity and schema, then continues training with a new generation of formulas. It never restores snapshots from failed runs or PR events.

A second job on a fresh runner downloads the just-created database and existing compiled binaries, validates inherited generation/cells, learns additional new formulas, and publishes the final database for the NEXT workflow run. Both jobs are serial; no rebuilding is needed on the second runner. A workflow-wide concurrency group prevents competing writers. Memory artifacts have 90-day retention: if all compatible artifacts expire, the next run explicitly reports a cold start. This is persistent build storage, not an indefinitely retained external SQL service. Other project workflows must call this workflow or reuse the restore/run helpers; unrelated workflows are not automatically modified.

## Run locally

```sh
python3 research/drnas_r28_context_build.py
python3 research/drnas_r28_context_memory.py formula.cnf --db drnas_memory/memory.sqlite --split train --time 10
python3 research/drnas_r28_context_memory.py unseen.cnf --db drnas_memory/memory.sqlite --split eval --time 10
```

Both commands default to the DIRECT profile. Use `--cold` to compare the same context engine with an empty prior. Exact R153 algebra still precedes search. Do not use one formula as both train and eval.

## Evaluation and practical limits

The small automatic pilot compares frozen R153-based native DIRECT, the new context controller with empty priors, and the same controller with transferred priors. Only the cold-versus-warm comparison isolates transferred memory. It reports verified/reported PAR2, solved attempts, SQL/snapshot preparation cost, solver time, independent verification time and commit time. Practical E2E includes memory preparation and commit; verification is separately reported. A valid answer delivered after that practical budget is penalized in PAR2.

Each solver runs sequentially on one logical CPU. No external competition references are needed to test the memory mechanism itself; the separate historical nine-arm benchmark retains Kissat, CaDiCaL and CMS comparisons. The repeated synthetic holdout is a regression diagnostic, not a fresh blind test for promotion. This change does not claim a 30% speedup, a globally best solver, or that more memory always improves performance. A disjoint real-source study is still required before promotion.

## First CI verification (2026-11-12)

Run [43170470375](https://github.com/Frane12/AndroidGameTest/actions/runs/43170470375), commit `50ad1c358dc6e6247a3a29d10cac9eefc2164dbd`, completed both jobs successfully. The second runner restored generation 1 with exactly the same statistics SHA and produced generation 2. The saved SQLite database was 45056 bytes (44 KiB), with 40 active cells and 43 independently verified training sources out of 44 attempted. The compressed memory artifact was 6539 bytes.

| Stage (separate runners and cohorts) | Arm | Verified attempts | Verified PAR2, seconds |
| --- | --- | ---: | ---: |
| 18-source holdout, two repeats | Frozen native DIRECT | 36/36 | 2.400628 |
| Same holdout | Context, empty prior | 35/36 | 3.780630 |
| Same holdout | Context, saved prior | 36/36 | 1.471656 |
| 10-source subset after restore, two repeats | Frozen native DIRECT | 20/20 | 2.459060 |
| Same subset | Context, empty prior | 19/20 | 3.255090 |
| Same subset | Context, saved prior | 20/20 | 0.722647 |

The first saved-prior result is 38.7% lower PAR2 than the frozen native baseline and 2.57x the empty-prior score ratio. Preparation averaged 0.17ms and 0.22ms for saved-prior evaluations in the two jobs, respectively; this includes SHA lookup and split registration, not just snapshot reading. Do not combine these stages or call the second subset a new blind holdout.

A local continuation run had a small regression against its empty-prior control, despite correct persistence. The CI improvements are therefore pilot observations, not evidence of stable general superiority. Database inheritance and answer verification are confirmed independently of whether performance improves. The next workflow run exercises automatic artifact selection from this completed run, in addition to the already-tested fresh-runner restore.
