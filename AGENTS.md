# DRNAS experimental work

For future MATH5 builds and new benchmarks, use compact binary DRAT by default, as requested by the user on 2026-11-15. Build through `python3 research/math5/build.py`; the canonical `build/drnas-math5` must emit binary DRAT with ordinary `--proof FILE`, without requiring an additional flag. `--proof-text` is an explicit diagnostic override only.

Do not silently reuse the old text-only MATH5 binary from historical artifacts as the current build. GENERAL100 preparation on this branch rebuilds MATH5, verifies the default binary proof using the independent checker, then freezes updated hashes before measuring. Keep MATH4 and third-party reference identities fixed for comparisons.

Preserve running experiments and historical source/binary hashes. Do not change a benchmark after its inputs/protocol are frozen. Old-commit reruns intentionally retain their old behavior and must be identified as historical replays. Keep work on experimental branches and leave main unchanged unless the user explicitly requests otherwise.
