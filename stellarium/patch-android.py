#!/usr/bin/env python3
"""Minimal Android-only port adjustments to the original Stellarium manifest."""
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
