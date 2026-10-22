#!/usr/bin/env python3
"""Repair an Android-specific generated Ninja include ordering defect.

Qt/OpenGL imported targets can prepend the NDK sysroot/usr/include with
'-isystem'. The NDK compiler already supplies this directory implicitly
after libc++, and the duplicate early -isystem breaks libc++ include_next
(e.g. <cmath> cannot find its local math.h wrapper).

Only remove this redundant explicit include path; preserve --sysroot and
all real compiler, Qt, Stellarium and module include directories.
"""
import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("Usage: fix-ndk-headers.py build.ninja android-ndk-dir")
ninja_file, ndk_dir = Path(sys.argv[1]), Path(sys.argv[2])
toolchain = ndk_dir / "toolchains" / "llvm" / "prebuilt"
candidates = list(toolchain.glob("*/sysroot/usr/include"))
if len(candidates) != 1:
    raise SystemExit(f"Expected one NDK sysroot include, got: {candidates}")
include = str(candidates[0])
original = ninja_file.read_text()
# Ninja command strings hold ordinary spaces; don't remove the actual --sysroot.
pattern = re.compile(r"(?<!\S)-isystem\s+" + re.escape(include) + r"(?=\s|$)")
patched, count = pattern.subn("", original)
if count == 0:
    print("No redundant NDK -isystem include found; leaving Ninja unchanged")
else:
    ninja_file.write_text(patched)
    print(f"Removed {count} explicit NDK sysroot includes from Ninja (implicit --sysroot preserved)")
