#!/usr/bin/env bash
set -euo pipefail
mkdir -p build/deps
fetch() {
  local repository="$1" revision="$2" destination="$3"
  git init -q "$destination"
  git -C "$destination" remote add origin "https://github.com/$repository.git"
  git -C "$destination" fetch -q --depth=1 origin "$revision"
  git -C "$destination" checkout -q --detach FETCH_HEAD
  test "$(git -C "$destination" rev-parse HEAD)" = "$revision"
}
fetch marijnheule/drat-trim 2e3b2dc0ecf938addbd779d42877b6ed69d9a985 build/deps/drat
cc -O2 build/deps/drat/drat-trim.c -o build/drat-trim
fetch arminbiere/kissat 8af8e56f174b778aef3aa45af9f739b2a5f492c2 build/deps/kissat
(cd build/deps/kissat && ./configure && make -j2)
cp build/deps/kissat/build/kissat build/kissat
fetch arminbiere/cadical c60730422e758ef1cebe7aeddf2dda31c996bf04 build/deps/cadical
(cd build/deps/cadical && ./configure && make -j2)
cp build/deps/cadical/build/cadical build/cadical
fetch digama0/frat aa18581497830b49a6ab6cbc9e0dc778c14885b5 build/deps/frat
(cd build/deps/frat && cargo generate-lockfile && cargo build --release --locked)
cp build/deps/frat/target/release/frat-rs build/frat-rs
cp build/deps/frat/Cargo.lock build/frat-Cargo.lock
cp "$(command -v cryptominisat5)" build/cms
build/kissat --version > build/reference_versions.txt
build/cadical --version >> build/reference_versions.txt
build/cms --version >> build/reference_versions.txt
dpkg-query -W cryptominisat libcryptominisat5-5.11t64 >> build/reference_versions.txt
sha256sum build/kissat build/cadical build/cms build/drat-trim build/frat-rs > build/reference_sha256.txt
