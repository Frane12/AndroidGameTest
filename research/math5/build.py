#!/usr/bin/env python3
"""Build current MATH5 with compact binary DRAT enabled by default.
`--proof-text` explicitly selects the historical format for diagnostics.
"""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
subprocess.run([sys.executable,str(ROOT/'research/math5_proofio/build.py')],cwd=ROOT,check=True)
