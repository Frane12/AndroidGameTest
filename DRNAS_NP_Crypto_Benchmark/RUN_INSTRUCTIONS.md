# DRNAS NP Lab benchmark run

The workflow runs on pushes to this isolated experiment branch (including this commit). It installs the Ubuntu 24.04 CryptoMiniSat package, validates the DRNAS solver, generates 34 deterministic SAT instances and measures both solvers on the same runner.

Results are uploaded under **drnas-versus-cryptominisat** in the associated GitHub Actions run. For a manual rerun, the workflow must also be available on the repository default branch to expose GitHub's Run workflow control.

No commits were made to main.
