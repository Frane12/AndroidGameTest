#!/usr/bin/env python3
"""DRNAS Audacity Android target-platform normalization.

The pinned Muse Framework GetPlatformInfo.cmake checks CMAKE_HOST_SYSTEM_NAME,
which is Linux on a GitHub runner even when building for Android. That
incorrectly enables desktop Linux libraries (notably Qt DBus / ALSA).
Apply a narrow, asserted patch only to the unpacked upstream submodule.
"""
from pathlib import Path
import sys

source_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("audacity-source").resolve()
platform_file = source_root / "muse/buildscripts/cmake/GetPlatformInfo.cmake"
if not platform_file.is_file():
    raise SystemExit(f"Missing pinned Muse platform detector: {platform_file}")

original = platform_file.read_text()
already = 'if(CMAKE_SYSTEM_NAME STREQUAL "Android")'
if already in original:
    print("[DRNAS] Muse target Android detection already patched")
    raise SystemExit(0)

platform_check = "if(${CMAKE_CXX_COMPILER} MATCHES"
expected_host_checks = original.count("CMAKE_HOST_SYSTEM_NAME")
if original.count(platform_check) != 1 or expected_host_checks != 4:
    raise SystemExit(
        f"Unexpected Muse platform detector structure: compiler checks={original.count(platform_check)}, "
        f"host checks={expected_host_checks}. Review upstream before patching."
    )

patched = original.replace(
    platform_check,
    'if(CMAKE_SYSTEM_NAME STREQUAL "Android")\n'
    '    set(OS_IS_ANDROID 1)\n'
    'elseif(${CMAKE_CXX_COMPILER} MATCHES',
    1,
).replace("CMAKE_HOST_SYSTEM_NAME", "CMAKE_SYSTEM_NAME")

assert "set(OS_IS_ANDROID 1)" in patched
assert "CMAKE_HOST_SYSTEM_NAME" not in patched
platform_file.write_text(patched)
print("[DRNAS] Patched Muse platform detection to use Android target, not Linux build host")
print(f"[DRNAS] Updated only: {platform_file}")
