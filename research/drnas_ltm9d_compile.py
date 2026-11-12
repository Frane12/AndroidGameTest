#!/usr/bin/env python3
"""Compile LTM9D with native GF2 proof-first, preserving frozen LTM9B and LTM9."""
import os,subprocess,shutil
from pathlib import Path
subprocess.run(['python3','research/drnas_ltm9b_compile.py'],check=True)
root=Path('mre_atlas23')
shutil.copy2(root/'bin/drnas_ltm9b',root/'bin/drnas_ltm9b_original')
p=root/'native.cpp';s=p.read_text()
anchor='   if(mode=="LTM8_FAST"){\n      const auto p=ltm9_php::prove(orig);'
assert s.count(anchor)==1,('GF2 insertion drift',s.count(anchor))
s=s.replace(anchor,'''   if(mode=="LTM8_FAST"){
      const auto g=ltm9d_gf2::prove(orig);
      if(g.proved){
          std::cout<<"c LTM9D_GF2_CERT equations="<<g.equations<<" width="<<g.width<<"\\n";
          std::cout<<"s UNSATISFIABLE\\n";
          return 20;
      }
   }
'''+anchor,1)
s='#include "drnas_ltm9d_gf2.hpp"\n'+s
p.write_text(s)
subprocess.run([os.environ.get('CXX','g++'),'-O3','-std=c++17',
 '-I','research','-I','mre_atlas23','-I','mre_atlas15',str(p),
 '-o',str(root/'bin/drnas_ltm9d')],check=True)
print('LTM9D_NATIVE_GF2_COMPILE_PASS baseline_LTM9B_preserved=true')
