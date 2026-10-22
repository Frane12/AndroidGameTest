#!/usr/bin/env python3
"""Strict Android-only adaptations to pinned upstream Stellarium v26.3."""
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch-android.py /path/to/AndroidManifest.xml")
path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
replacements = {
    'package="org.stellarium.stellarium"': 'package="org.drnas.stellarium.port"',
    'android:label="Stellarium"': 'android:label="DRNAS Stellarium Native"',
}
for original, replacement in replacements.items():
    if source.count(original) != 1:
        raise SystemExit(f"Upstream Android manifest changed: {original}")
    source = source.replace(original, replacement)
# Avoid requesting unrestricted access to the entire device file system
# merely to display the first sky viewport. SAF import comes later.
source = source.replace(
    '    <uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" />\n',
    "",
)
path.write_text(source, encoding="utf-8")
print("DRNAS Android package identifier, label, permissions: patched")


# JPL's binary ephemeris structs must stay byte-packed, but the pinned
# upstream header sets #pragma pack(1) *before* importing libc++ <cstdint>
# and <cstdio>. This contaminates standard type definitions and causes Qt's
# AlignedQArrayData to fail Clang's alignment checks on Android ARM64.
# Import standard headers at native alignment and scope pack(1) to structs.
jpl_header = path.parent.parent / "src/core/planetsephems/jpl_int.h"
jpl = jpl_header.read_text(encoding="utf-8")
old_jpl = "#pragma pack(1)\n\n#include <cstdint>\n#include <cstdio>"
new_jpl = "#include <cstdint>\n#include <cstdio>\n\n#pragma pack(push, 1)"
if jpl.count(old_jpl) != 1 or jpl.count("#pragma pack()") != 1:
    raise SystemExit("Pinned Stellarium JPL packing guard changed; refusing blind edit")
jpl = jpl.replace(old_jpl, new_jpl).replace("#pragma pack()", "#pragma pack(pop)")
jpl_header.write_text(jpl, encoding="utf-8")
print("Android JPL ephemeris: preserved packed structs, fixed libc++ header alignment")


# Remove upstream's obsolete Android all-files-access prompt from main.cpp.
# The Android manifest above deliberately drops MANAGE_EXTERNAL_STORAGE, and
# the first on-device sky viewport needs no unrestricted file-system access.
# This is the only usage of private Qt JNI headers in the pinned main.cpp.
# Qt's public application bootstrap remains unmodified.
main_path = path.parent.parent / "src/main.cpp"
main = main_path.read_text(encoding="utf-8")
private_includes = (
    "#ifdef Q_OS_ANDROID\n"
    "#include <QJniObject>\n"
    "#include <QJniEnvironment>\n"
    "#include <QtCore/private/qjnihelpers_p.h>\n"
    "#include <QtCore/private/qandroidextras_p.h>\n"
    "#endif\n"
)
if main.count(private_includes) != 1:
    raise SystemExit("Pinned Stellarium Qt JNI imports changed; refusing blind edit")
main = main.replace(private_includes, "", 1)
block_start = '\n#ifdef Q_OS_ANDROID\n\tif (!QJniObject::callStaticMethod<jboolean>("android/os/Environment", "isExternalStorageManager"))'
block_end = "\n#endif\n\n\t// Init the file manager"
if main.count(block_start) != 1 or main.count(block_end) != 1:
    raise SystemExit("Pinned Stellarium Android storage prompt changed; refusing blind edit")
start = main.index(block_start)
end = main.index(block_end, start)
main = main[:start] + main[end + len("\n#endif"):]
main_path.write_text(main, encoding="utf-8")
print("Android main.cpp: dropped unused Qt private JNI headers and obsolete all-files permission prompt")

# Android needs app-private storage for its writable configuration, not
# ~/.stellarium if QDir::homePath() resolves outside the app sandbox.
anchor = '\t// Init the file manager\n\tStelFileMgr::init();'
replacement = (
    '#ifdef Q_OS_ANDROID\n'
    '\tconst QString drnasUserDir = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);\n'
    '\tif (drnasUserDir.isEmpty())\n'
    '\t\tqFatal("DRNAS Android: app-private data directory unavailable");\n'
    '\tqputenv("STEL_USERDIR", drnasUserDir.toUtf8());\n'
    '\tqInfo().noquote() << "DRNAS Android user data:" << drnasUserDir;\n'
    '#endif\n\n'
    '\t// Init the file manager\n'
    '\tStelFileMgr::init();'
)
if main.count(anchor) != 1:
    raise SystemExit("Pinned Stellarium file-manager init changed; refusing blind patch")
main = main.replace(anchor, replacement, 1)
include_anchor = '#include <QDir>\n#include <QFile>'
if main.count(include_anchor) != 1:
    raise SystemExit("Pinned Stellarium Qt includes changed")
main = main.replace(include_anchor, '#include <QDir>\n#include <QStandardPaths>\n#include <QFile>', 1)
main_path.write_text(main, encoding="utf-8")
print("Android main.cpp: use private writable app data directory for Stellarium configuration")
