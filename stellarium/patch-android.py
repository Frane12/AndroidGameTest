#!/usr/bin/env python3
"""Strict Android-only adaptations to pinned upstream Stellarium v26.3."""
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch-android.py /path/to/AndroidManifest.xml")
path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
replacements = {
    'package="org.stellarium.stellarium"': 'package="org.drnas.stellarium.native"',
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
