# DRNAS Global Memory v1

This is a shared evidence index, not an autonomous claim that all DRNAS
solvers learn from all past benchmarks or that speedups are verified
outside their original source-specific checks.

## Data and source of truth

- Importer: research/drnas_global_memory.py
- Regression tests: tests/test_drnas_global_memory.py
- Workflow: .github/workflows/drnas-global-memory.yml
- Persistent data branch: experiment/drnas-global-memory-store-20261113
- Database: research/memory/global/global.sqlite.gz
- Human-readable status: research/memory/global/latest.json
- Legacy X47 learning archive: experiment/drnas-x47-memory-store-20261113
  at research/memory/x47/memory.sqlite.gz

The first pass indexes historical GitHub Actions run metadata and scans
available Actions artifacts. Parsing is limited to small UTF-8 JSON and
JSONL result files with recognizable source manifests. Huge proof files, APK
outputs, unmatched schemas and expired archives are not imported as
individual samples. Check latest.json artifact-state breakdown before
claiming completeness. A historical run record does not imply its benchmark
observations were ingested.

## Training / validation / holdout safety

- Only legacy_experiences.split=train can appear in the read-only
  eligible_training view, and matching holdout source SHA blocks eligibility.
- Imported benchmark artifacts are evidence-only (role=holdout), even if
  their self-reported manifest declares split=train.
- Prior validation examples remain validation-only.
- Sealed holdout reports remain sealed historical audit data.
- Verified-result flags in imported GitHub trials are claims of the original
  job's checker; the importer does not independently rerun SAT witnesses
  or UNSAT proofs.
- No imported artifact or GitHub run automatically changes a live solver,
  retrains the frozen model, or promotes a candidate.
- Any future candidate training requires a fresh namespace, true train-only
  pairs, locked validation, unseen final holdout, verified SAT witnesses /
  independently certified UNSAT, and paired improvement/regression gates.

## Idempotency and observability

- GitHub run ID, artifact ID, source SHA and artifact/source/arm/repetition
  prevent duplicates without erasing independent repeated measurements.
- PAR2, time, family, original SHA, frozen model and guard SHA are preserved
  where available. Cross-build PAR2 is not automatically comparable.
- Explicit artifact states: parsed, unsupported, expired, oversized,
  unrelated, pending, retry.
- All memory snapshots are committed to an independent persistent branch.
- Triggered on selected workflow completions, scheduled every three hours
  on the default branch, and manually via workflow dispatch.

The reports table retains original compatible JSON summaries, allowing
multiple build families to coexist without contamination.
