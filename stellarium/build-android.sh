#!/usr/bin/env bash
# Actual cross-compile of upstream Stellarium 26.3, not a fake Qt wrapper.
set -euo pipefail
MODE="${1:-configure}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT/.build/stellarium-android"
mkdir -p "$BUILD_DIR" "$ROOT/out"
case "$MODE" in
  configure)
    : "${STELLARIUM_SOURCE_DIR:?Set STELLARIUM_SOURCE_DIR to upstream Stellarium checkout}"
    : "${QT_ANDROID:?Set QT_ANDROID to official Qt Android arm64 SDK}"
    : "${QT_HOST:?Set QT_HOST to official Qt host SDK}"
    : "${ANDROID_HOME:?Android SDK required}"
    : "${NDK_VERSION:?Pinned Android NDK required}"
    QT_CMAKE="$QT_ANDROID/lib/cmake/Qt6/qt.toolchain.cmake"
    test -s "$QT_CMAKE"
    test -s "$ANDROID_HOME/ndk/$NDK_VERSION/build/cmake/android.toolchain.cmake"
    cmake -S "$STELLARIUM_SOURCE_DIR" -B "$BUILD_DIR" -G Ninja \
      "-DCMAKE_TOOLCHAIN_FILE=$QT_CMAKE" \
      "-DQT_HOST_PATH=$QT_HOST" \
      "-DCMAKE_PREFIX_PATH=$QT_ANDROID" \
      "-DANDROID_SDK_ROOT=$ANDROID_HOME" \
      "-DANDROID_NDK=$ANDROID_HOME/ndk/$NDK_VERSION" \
      -DANDROID_ABI=arm64-v8a \
      -DANDROID_PLATFORM=android-26 \
      -DCMAKE_BUILD_TYPE=Release \
      -DSTELLARIUM_RELEASE_BUILD=OFF \
      -DENABLE_QT6=ON \
      -DENABLE_PCH=OFF \
      -DENABLE_NLS=OFF \
      -DENABLE_PODIR=OFF \
      -DENABLE_MEDIA=OFF \
      -DENABLE_SPEECH=OFF \
      -DENABLE_SHOWMYSKY=OFF \
      -DENABLE_GPS=OFF \
      -DENABLE_SCRIPTING=OFF \
      -DENABLE_QTWEBENGINE=OFF \
      -DENABLE_XLSX=OFF \
      -DENABLE_INDI=OFF \
      -DENABLE_TESTING=OFF \
      -DUSE_PLUGIN_SCENERY3D=OFF \
      -DUSE_PLUGIN_OCULUS=OFF \
      -DUSE_PLUGIN_TELESCOPECONTROL=OFF \
      -DUSE_PLUGIN_REMOTECONTROL=OFF \
      -DUSE_PLUGIN_REMOTESYNC=OFF \
      -DENABLE_EXPORT_COMPILE_COMMANDS=ON
    ;;
  compile)
    # Remove only a redundant explicit NDK sysroot system header path from
    # generated Ninja commands. Clang already inherits it from --sysroot;
    # listing it ahead of libc++ breaks include_next <math.h>/<string.h>.
    python3 "$ROOT/stellarium/fix-ndk-headers.py" "$BUILD_DIR/build.ninja" "$ANDROID_HOME/ndk/$NDK_VERSION"
    cmake --build "$BUILD_DIR" --target stellarium --parallel 4
    ;;
  package)
    cmake --build "$BUILD_DIR" --target stellarium_make_apk --parallel 4
    ;;
  *)
    echo "Usage: $0 {configure|compile|package}" >&2; exit 2
    ;;
esac
