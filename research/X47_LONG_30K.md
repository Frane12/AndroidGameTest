# X4.7 LONG: 30,000 sources, twelve training cycles, persistent memory

The native solver is unchanged from `8a0aaae94d07cb9b4bef4b5c385f7ad29f3420dd`.
SHA256 `3151815338420a2d6070300ba0858c36194ff095256543cab1ed97da6f1bfece`.
This tests whether substantially more experience improves the existing single
polarity intervention at decision four, with the same two bounded BCP probes and
24 features. This is a research experiment, not a claim of positive learning.

| Partition | Sources | Use |
|---|---:|---|
| Training | 18,000 | Cumulative curriculum and residual tree fitting |
| Tune | 3,000 | Thresholds, retirement and checkpoint selection |
| Audit | 3,000 | Open once after selection; never tune against it |
| Holdout | 6,000 | Frozen policy, five arms, three repeats |

There are 30 generator regimes: 16 base families, 11 related signed/renamed
variants and 3 disjoint-union mixtures. They are **not 30 independent mathematical
classes**. Parent families are disjoint between train, validation and holdout.
Every performance source is constructed SAT; independently exhaustive SAT/UNSAT
correctness controls remain separate. No external competition-solver or industrial
generalization claim follows from this experiment.

Collection compares both polarities from the same search state, using 50,000
propagations per continuation and no timing-based training labels. Unknown pairs
receive a deterministic 100,000 work penalty for policy selection, and are excluded
from regression targets. Every SAT witness is independently checked against its CNF.
Metadata, family names, witness, SHA and future outcomes never enter inference.

Cycles 1–6 progressively include 1/6 to all training sources per regime, ordered by
observed search work. Cycles 7–12 continue fitting residuals on the full set. The first
cycle creates 16 depth-two trees; subsequent cycles add eight. Inference is bounded
to 64 trees. Every two cycles up to eight additional trees are retired if removal
does not worsen tune work. Unused features are excluded from subsequent splits and
reconsidered every four cycles. Feature extraction stays unchanged to preserve the
native X4.7 build. Neither original CNF variables nor sound learned clauses are
deleted by this model-maintenance routine. The best validation checkpoint is frozen,
even if it occurred before the final cycle.

SQLite stores raw matched-state experience, all checkpoints, pruning events and
separately sealed test summaries. Every two cycles and at freeze/completion, a gzip
snapshot and metadata are committed to
`experiment/drnas-x47-memory-store-20261113`. This is a durable Git branch, not an
expiring Actions cache. Removal affects active models; historical evidence remains
available for auditing and rollback. On a later fresh namespace, only prior training
rows are replayed, and the previous accepted model can be continued. Historical
validation/test rows never enter training. An already completed namespace is rejected
for further training. A changed protocol/native hash requires a separate memory branch.
An interrupted pre-holdout run can continue from a persisted accepted checkpoint;
it performs another twelve cycles rather than pretending they are the same cycles.

The holdout compares CORE, the original X4.7 tree, LONG, fixed probe rule and SHAM.
SHAM pays for probes/model evaluation but keeps the original decision. The original
model is copied byte-for-byte from successful X4.7 run `43359617323`, SHA256
`30ba1f41bc0f43cd5fc434bd891cc08849aecbb78bb87ebecaa49668f1c14123`.
All arms run serially in a randomized order per formula/repeat, pinned to one logical
CPU. Up to two independent shard runners run at once. A runtime cap of 80 ms is used;
complete process startup and inference overhead count in end-to-end PAR2. Actual
median/p95 durations are reported: formulas are not selected after seeing test timings
and are not guaranteed to take 10–80 ms.

The primary performance criterion is a lower 95% paired bootstrap bound above 10%
improvement over both CORE and the original X4.7. Repeats are averaged per formula
before bootstrap, so they are not treated as independent samples. Attribution to
learning also requires a positive lower bound against the fixed rule, AUC lower bound
above 0.5 on complete nontrivial held-out pairs, and the independent audit guard.
Family uncertainty over six held-out regimes is reported separately. AUC is conditional
on uncensored informative pairs; PAR2 includes every test formula. Secondary results
are exploratory. Checkpoint or threshold selection never uses the holdout.

One workflow executes correctness/small-pipeline verification, eight collection
shards, one twelve-cycle training job, six evaluation shards and a final report.
It makes 60,000 matched-continuation runs plus 90,000 timed held-out arm runs, apart
from correctness controls. Artifacts retain raw results for 90 days; long-term memory
is in the dedicated Git branch. The main branch and Android APK are not involved.

Run locally from the repository root (Python 3.12, NumPy 2.3.5, compiled X4.7):

```bash
python research/drnas_x47_long.py collect --shards 1 --out inputs/collect-0
python research/drnas_x47_long.py train --inputs inputs --out models
python research/drnas_x47_long.py evaluate --shards 1 --models models --out inputs/eval-0
python research/drnas_x47_long.py finish --inputs inputs --models models --out final
```

`X47_MEMORY_STORE` enables persistence to a checked-out writable memory branch.
Without it, the local SQLite/gzip checkpoints still exist, but no remote durability
is claimed. Namespace, seeds, protocol, source and model hashes are recorded.
