#!/usr/bin/env python3
"""Bundle authentic pinned Stellarium 26.3 runtime data into the Qt Android APK.

StelFileMgr::init() on Android only searches assets:/ and external /sdcard/
for CHECK_FILE=data/ssystem_major.ini. The previous APK shipped no data
assets and deterministically hit qFatal("Couldn't find install directory
location."). Qt's androiddeployqt copies android/assets/ into APK assets/.
"""
from pathlib import Path
import shutil
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: stage-assets.py upstream-stellarium")
source = Path(sys.argv[1]).resolve()
destination = source / "android/assets"
if not (source / "src/core/StelFileMgr.cpp").is_file():
    raise SystemExit("Refusing: source is not a Stellarium checkout")
if not (source / "data/default_cfg.ini").is_file():
    raise SystemExit("Configure CMake first: generated data/default_cfg.ini is absent")

# Keep source trees intact; Android deployment copies these authentic
# catalogs/fonts/textures from the checked-out v26.3 sources.
# Modern sky culture and Guereins landscape are the upstream defaults.
directories = [
    "data",
    "stars",
    "textures",
    "nebulae/default",
    "landscapes/guereins",
    "landscapes/zero",
    "skycultures/modern",
]
files = [
    "skycultures/common_star_names.fab",
    "skycultures/translations.fab",
]
def ignore_build_files(dirpath, names):
    return {name for name in names if name in ("CMakeLists.txt",) or name.endswith((".qrc", ".cmake"))}
bytes_written = 0
total_files = 0
for rel in directories:
    src = source / rel
    dst = destination / rel
    if not src.is_dir():
        raise SystemExit(f"Required Stellarium runtime directory missing: {src}")
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore_build_files)
for rel in files:
    src = source / rel
    dst = destination / rel
    if not src.is_file():
        raise SystemExit(f"Required Stellarium runtime file missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
for f in destination.rglob("*"):
    if f.is_file():
        bytes_written += f.stat().st_size
        total_files += 1
for required in (
    "data/ssystem_major.ini",
    "data/default_cfg.ini",
    "stars/hip_gaia3/defaultStarsConfig.json",
    "skycultures/modern/index.json",
    "landscapes/guereins/landscape.ini",
):
    if not (destination / required).is_file():
        raise SystemExit(f"Runtime resource missing after staging: {required}")
print(f"PASS: packaged authentic Stellarium runtime assets: {total_files} files, {bytes_written:,} bytes")
print(f"Android runtime data root: {destination}")
