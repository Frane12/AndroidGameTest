#!/usr/bin/env python3
"""Reproducible local build; no Actions dispatch and no benchmark launch."""
import os, pathlib, subprocess
root=pathlib.Path(__file__).resolve().parent.parent
os.chdir(root)
commands=[['python3','research/drnas_atlas13_generator.py'],['python3','research/drnas_atlas15_warm_patch.py'],['python3','research/drnas_atlas15_cdcl_patch.py'],['python3','research/drnas_atlas1_generate.py','--out','mre_atlas15/atlas1_table.hpp'],['python3','research/drnas_atlas9_export_table.py','research/atlas8_reduction_table.jsonl','mre_atlas15/atlas8_rules.hpp']]
commands += [['python3','research/drnas_'+name+'_build.py'] for name in ['atlas16','atlas17','atlas19','atlas23','atlas36','ltm6','ltm7','ltm8_php']]
for command in commands: subprocess.run(command,check=True)
pathlib.Path('mre_atlas23/bin').mkdir(exist_ok=True)
subprocess.run([os.environ.get('CXX','g++'),'-O3','-std=c++17','-I','mre_atlas23','-I','mre_atlas15','mre_atlas23/native.cpp','-o','mre_atlas23/bin/drnas_ltm8'],check=True)
print('LTM8_COMPILE_PASS modes=LTM8_FAST,LTM8_CHAOS')
