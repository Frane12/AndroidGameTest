#!/usr/bin/env python3
"""Narrow source-checkout-only patches for Audacity 4.0.1 Android ARM64.

Never change upstream refs or submodules in git. Fail loudly when pinned Muse
source layout changes, so an incompatible upstream update cannot silently
produce a misleading "successful" binary.
"""
from pathlib import Path
import sys

source_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("audacity-source").resolve()

# MuseScore's platform detector uses CMAKE_HOST_SYSTEM_NAME, i.e. Linux on the
# GitHub builder. That incorrectly selects DBus, JACK, ALSA and Linux C++ code.
platform_file = source_root / "muse/buildscripts/cmake/GetPlatformInfo.cmake"
if not platform_file.is_file():
    raise SystemExit(f"Missing pinned Muse platform detector: {platform_file}")
text = platform_file.read_text()
mark = 'if(CMAKE_SYSTEM_NAME STREQUAL "Android")'
if mark not in text:
    needle = "if(${CMAKE_CXX_COMPILER} MATCHES"
    host_count = text.count("CMAKE_HOST_SYSTEM_NAME")
    if text.count(needle) != 1 or host_count != 5:
        raise SystemExit(
            f"Unexpected Muse platform detector structure: compiler checks={text.count(needle)}, "
            f"host checks={host_count}."
        )
    text = text.replace(
        needle,
        'if(CMAKE_SYSTEM_NAME STREQUAL "Android")\n'
        '    set(OS_IS_ANDROID 1)\n'
        'elseif(${CMAKE_CXX_COMPILER} MATCHES',
        1,
    ).replace("CMAKE_HOST_SYSTEM_NAME", "CMAKE_SYSTEM_NAME")
    platform_file.write_text(text)
print("[DRNAS] Muse platform detection uses Android TARGET (not Linux host)")

# Muse's separate dependency builder passes only the compiler path, not the
# Android sysroot/toolchain to nested CMake runs. This would produce Linux
# aarch64 libraries instead of Android aarch64 libraries.
dep_file = source_root / "muse_deps/buildtools/build_dependency.cmake"
if not dep_file.is_file():
    raise SystemExit(f"Missing pinned Muse dependency builder: {dep_file}")
text = dep_file.read_text()
mark = 'DRNAS: forward the Android NDK toolchain into nested dependency builds'
if mark not in text:
    needle = "    if(CMAKE_C_COMPILER)\n"
    if text.count(needle) != 1:
        raise SystemExit("Unexpected Muse dependency CMake builder structure")
    injection = """    # DRNAS: forward the Android NDK toolchain into nested dependency builds
    if(BD_OS STREQUAL "android")
        if(NOT EXISTS "$ENV{ANDROID_NDK_ROOT}/build/cmake/android.toolchain.cmake")
            message(FATAL_ERROR "ANDROID_NDK_ROOT is required for Android dependencies")
        endif()
        list(APPEND _configure_args
            "-DCMAKE_TOOLCHAIN_FILE=$ENV{ANDROID_NDK_ROOT}/build/cmake/android.toolchain.cmake"
            "-DANDROID_ABI=arm64-v8a"
            "-DANDROID_PLATFORM=android-28")
    endif()

"""
    text = text.replace(needle, injection + needle, 1)

    # Android NDK's CMake find rules search target roots, not host paths.
    # Muse lists dependent installed libraries only as CMAKE_PREFIX_PATH.
    # Export them as CMAKE_FIND_ROOT_PATH too, so Vorbis sees the actual
    # Android libogg/include tree (and subsequent deps see their parents).
    root_anchor = '    if(_initial_cache)'
    if text.count(root_anchor) != 1:
        raise SystemExit("Unexpected Muse dependency init.cmake structure")
    find_roots = r"""    # DRNAS Android dependency sysroot lookup
    if(BD_OS STREQUAL "android" AND BD_DEPENDS_PREFIXES)
        string(APPEND _initial_cache "set(CMAKE_FIND_ROOT_PATH \"${BD_DEPENDS_PREFIXES}\" CACHE STRING \"\" FORCE)\n")
    endif()

"""
    text = text.replace(root_anchor, find_roots + root_anchor, 1)
    dep_file.write_text(text)
print("[DRNAS] Muse nested dependencies will use Android NDK, not host Linux compiler flags")

# Inspect rather than hide unsupported backends: PortAudio's Linux JACK
# option is selected only for BD_OS=linux. LIB_OS=android is supplied in
# the top-level CMake probe, so platform-specific backend work is explicit.
spec_file = source_root / "muse_deps/recipes/portaudio/spec.cmake"
spec = spec_file.read_text()
if 'if(BD_OS STREQUAL "linux")' not in spec or '-DPA_USE_JACK=ON' not in spec:
    raise SystemExit("Unexpected PortAudio Linux/JACK recipe structure")
print("[DRNAS] Pinned PortAudio recipe verified; Android will not request JACK")
