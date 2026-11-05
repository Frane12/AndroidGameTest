#!/usr/bin/env bash
set -euo pipefail
mkdir -p r133d-results /tmp/r133d-parity
python3 research/r93_export_verified_rows.py selftest
python3 research/r133d_short_signal_selector.py selftest
git clone -q https://github.com/arminbiere/cadical.git /tmp/cadical
pushd /tmp/cadical
git checkout -q rel-2.1.0
git rev-parse HEAD > "$GITHUB_WORKSPACE/r133d-results/cadical_commit.txt"
./configure
make -j2
g++ -std=c++17 -O2 -Wall -I./src "$GITHUB_WORKSPACE/research/r133c_native_gf2_cdcl_bridge.cpp" ./build/libcadical.a -o /tmp/r133d-native
popd
/tmp/r133d-native selftest | tee r133d-results/watch-selftest.txt
/tmp/r133d-native gf2selftest | tee r133d-results/gf2-selftest.txt
curl -fsSL --retry 3 --max-time 90 https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/DIMACS/PARITY/parity.tar.gz -o /tmp/r133d-parity/parity.tar.gz
echo 'd18ef13699ec3aafe0e70861fc1b9316205a6264c818cf2f69ebf3478534ba4f  /tmp/r133d-parity/parity.tar.gz' | sha256sum --check
tar -xzf /tmp/r133d-parity/parity.tar.gz -C /tmp/r133d-parity
python3 -u research/r133d_value_benchmark.py --binary /tmp/r133d-native --satlib /tmp/r133d-parity --out r133d-results | tee r133d-results/benchmark.log
grep -q '^R133D_FIXTURE_PASS' r133d-results/benchmark.log
grep -q '^R133D_FINAL_AUDIT' r133d-results/benchmark.log
