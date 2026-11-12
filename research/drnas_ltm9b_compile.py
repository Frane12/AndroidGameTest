#!/usr/bin/env python3
"""Compile LTM9B with explicit proof rows, retain original LTM9 executable."""
import os,shutil,subprocess
from pathlib import Path
subprocess.run(['python3','research/drnas_ltm9_compile.py'],check=True)
root=Path('mre_atlas23')
shutil.copy2(root/'bin/drnas_ltm9',root/'bin/drnas_ltm9_original')
src=root/'native.cpp'
s=src.read_text()
inc='#include "drnas_ltm9_php.hpp"'
assert s.count(inc)==1,('LTM9B include drift',s.count(inc))
s=s.replace(inc,'#include "drnas_ltm9b_php.hpp"',1)
anchor='std::cout<<"c LTM9_PHP_CERT rows="'
assert s.count(anchor)==1,('LTM9B certificate drift',s.count(anchor))
s=s.replace(anchor,'''for(const auto& row:p.witness){
             std::cout<<"c LTM9B_PHP_ROW";
             for(int lit:row)std::cout<<" "<<lit;
             std::cout<<" 0\\n";
          }
          std::cout<<"c LTM9B_PHP_CERT rows="''',1)
src.write_text(s)
subprocess.run([os.environ.get('CXX','g++'),'-O3','-std=c++17',
 '-I','research','-I','mre_atlas23','-I','mre_atlas15',str(src),
 '-o',str(root/'bin/drnas_ltm9b')],check=True)
print('LTM9B_COMPILE_PASS LTM9_baseline_preserved=true explicit_PHP_certificate=true')
