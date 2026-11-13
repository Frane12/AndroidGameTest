# DRNAS Global Memory — evidence + guarded continual learning

## Where the live data lives

- Durable branch: experiment/drnas-global-memory-store-20261113
- Evidence + training database: research/memory/global/global.sqlite.gz
- Latest global evidence counts: research/memory/global/latest.json
- Latest native-X4.7 training decision: research/memory/global/latest_learning.json
- Active champion if one **passed** all gates: research/memory/global/champion_x47.json
- Historical frozen X47 memory: experiment/drnas-x47-memory-store-20261113

## Who updates what

**GitHub Actions — github-actions[bot]** writes all updates.

1. drnas-global-memory.yml runs approximately every 30 minutes (GitHub
   schedule is best effort), on named important completed benchmark workflows,
   on importer changes and by manual workflow dispatch. It indexes *all*
   GitHub run metadata, refreshes the latest artifact pages, incrementally
   imports small compatible evidence files and persists the data-only branch.
2. drnas-global-learning.yml runs daily, on learning-code changes and by
   manual workflow dispatch. It obtains the already-verified historical X47
   TRAIN pairs from the database, generates NEW 48 native paired TRAIN source
   examples, adds them permanently, fits a new X47 candidate, evaluates
   independent old validation, and opens a NEW 80-formula cross-family,
   two-repetition holdout only after the candidate is frozen.
3. Both workflows share one non-cancelling GitHub Actions concurrency group
   so they cannot write the persistent branch at the same time.
4. A passing candidate becomes a new frozen **champion policy** in the
   data branch, with model SHA and audit. A failing candidate is retained
   as an audit event and does **not** replace the champion or the native
   solver. Other native build engines need their own compatible learning
   adapters; arbitrary X5/X4.8 result rows are not wrongly used as X47 labels.

## Integrity rules

- Imported benchmark results are EVIDENCE-ONLY; all source-SHA and
  run/artifact provenance kept when available. The importer does not
  independently re-prove an archived answer.
- Existing 18,000 X47 TRAIN and 6,000 validation sources remain split-locked.
  A training source matching another benchmark holdout is excluded.
- Fresh continual training requires two independently witness-verified
  continuation variants from the SAME native solver state; censored work
  pairs are stored but never treated as labeled examples.
- Every fresh model cycle has a unique GitHub run ID namespace.
- Fresh sealed holdout formulas have SHA and family provenance, and newer
  cycles store each paired arm/repeat status, PAR2, conflicts, decisions and
  verified-result claim separately. They cannot enter future training.
- A candidate must beat both the incumbent (or CORE if no champion) and
  CORE with independent-source paired 95% bootstrap confidence, meet
  solved parity, improve validation, avoid severe regressions and pass
  family-level regression checks. Failing ANY check means no promotion.
- The model is only compatible with the pinned historic native X4.7 source
  (SHA256 9c78f45aa54a2556fb9f22e490a200b77e70a4360245d998c4dc96bd0b684ab3).
  No workflow silently changes the deployed solver's binary/default policy.

## Reading the dashboard

The top-level latest.json distinguishes:

- runs_indexed: GitHub runs with metadata, NOT benchmark formulas
- artifacts_indexed / artifact_states: progress of deep artifact import
- independent_observation_sources: SHA-distinct original benchmark CNFs
  in compatible per-trial artifacts
- observation_rows: each arm/repetition of those benchmark CNFs
- eligible_training_sources: legacy split-safe training sources
- continual_training_sources: new paired train-only experiences
- fresh_sealed_holdout_sources: independent lockout CNFs from learning cycles
- fresh_sealed_trial_rows: audit results with per-arm/per-repeat PAR2
- completed_learning_cycles / promoted_models: candidate cycles vs.
  champions actually accepted after strict gate

Import states pending/unsupported/oversized/expired stay visible. Importing
a GitHub run is NOT evidence that all its formulas have been independently
verified, and comparing raw PAR2 across unmatched machines and caps is invalid.

The first full continual cycle was GitHub run 43381083420. It added 48
new train sources (38 labeled) and 80 sealed holdouts; the candidate was
rejected because its PAR2 was slower. This is the intended safe behavior.
