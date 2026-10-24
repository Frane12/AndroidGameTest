#!/usr/bin/env bash
# DRNAS Audacity 4: genuine upstream CMake Android cross-configuration probe.
set -Eeuo pipefail

STAGE="${1:-configure}"
case "$STAGE" in
  configure|build) ;;
  *) echo "Usage: $0 configure|build" >&2; exit 64 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/audacity-source"
BUILD="$ROOT/audacity-build"
QT_VERSION="${DRNAS_QT_VERSION:-6.10.0}"
QT_BASE="${DRNAS_QT_BASE:-$HOME/Qt/$QT_VERSION}"
QT_HOST_PATH="$QT_BASE/gcc_64"
QT_ANDROID_PATH="$QT_BASE/android_arm64_v8a"
QT_TOOLCHAIN="$QT_ANDROID_PATH/lib/cmake/Qt6/qt.toolchain.cmake"
NDK_VERSION="27.2.12479018"

mkdir -p "$ROOT/audacity-logs" "$BUILD"
exec > >(tee -a "$ROOT/audacity-logs/preflight.log") 2>&1

echo "[DRNAS] stage: $STAGE"
echo "[DRNAS] date: $(date -u --iso-8601=seconds)"
echo "[DRNAS] source: $SRC"
echo "[DRNAS] Qt host: $QT_HOST_PATH"
echo "[DRNAS] Qt Android: $QT_ANDROID_PATH"
echo "[DRNAS] Android SDK: ${ANDROID_HOME:-missing}"
echo "[DRNAS] CMake: $(cmake --version | head -n 1)"
echo "[DRNAS] NDK: ${ANDROID_HOME:-}/ndk/$NDK_VERSION"

test -f "$SRC/CMakeLists.txt" || { echo "Upstream Audacity source missing"; exit 40; }
test -f "$SRC/muse/framework/cmake/MuseDeclareOptions.cmake" || { echo "Audacity Muse submodule missing"; exit 41; }
test -f "$QT_TOOLCHAIN" || { echo "Qt Android 6.10 toolchain missing"; exit 42; }
test -d "$QT_HOST_PATH" || { echo "Qt 6.10 desktop host tools missing"; exit 43; }
test -d "${ANDROID_HOME:-/missing}/ndk/$NDK_VERSION" || { echo "Android NDK r27c missing"; exit 44; }

git -C "$SRC" log -1 --format='[DRNAS] upstream commit: %H'
echo "[DRNAS] Running original Audacity CMake configuration for Android"

cmake -S "$SRC" -B "$BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_TOOLCHAIN_FILE="$QT_TOOLCHAIN" \
  -DQT_HOST_PATH="$QT_HOST_PATH" \
  -DANDROID_SDK_ROOT="$ANDROID_HOME" \
  -DANDROID_NDK_ROOT="$ANDROID_HOME/ndk/$NDK_VERSION" \
  -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-28 \
  -DAU4_BUILD_CONFIGURATION=app \
  -DAU4_BUILD_MODE=dev \
  -DAU_BUILD_CLOUD_AUDIOCOM=OFF \
  -DAU_BUILD_USAGEINFO_MODULE=OFF \
  -DAU_MODULE_EFFECTS_VST=OFF \
  -DAU_MODULE_EFFECTS_NYQUIST=OFF \
  -DAU_USE_LIBCURL=OFF \
  -DMUSE_ENABLE_UNIT_TESTS=OFF

echo "[DRNAS] Android configure passed"
if [[ "$STAGE" == build ]]; then
  echo "[DRNAS] Compiling genuine Audacity target (may fail on unported desktop dependencies)"
  cmake --build "$BUILD" --parallel 3
  echo "[DRNAS] Original Audacity target build passed (APK packaging is separate)"
fi
