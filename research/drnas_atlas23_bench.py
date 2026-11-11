#!/usr/bin/env python3
"""ATLAS23 frozen ATLAS22 SHA cohort; paired C7 vs conservative C10/C11."""
import json,pathlib,sys
sys.path.insert(0,"research")
import drnas_atlas22_mid_hard as D
import drnas_atlas21_official as B
B.OUT=pathlib.Path("mre_atlas23");B.OUT.mkdir(exist_ok=True)
B.ARMS=("A","C7_ADAPT","C10_KEEP32","C11_KEEP64","KISSAT","CMS")
# Reuse exact source selection, cap and original verification from ATLAS22.
D.B=B
D.main()
