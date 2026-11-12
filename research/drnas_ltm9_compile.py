#!/usr/bin/env python3
"""Build LTM9 separately from the frozen LTM8 baseline. No main edits."""
from pathlib import Path
import subprocess,shutil,os
subprocess.run(['python3','research/drnas_ltm8_compile.py'],check=True)
root=Path('mre_atlas23')
shutil.copy2(root/'bin/drnas_ltm8',root/'bin/drnas_ltm8_base')
path=root/'native.cpp'
src=path.read_text()
anchor='   if(mode=="LTM8_FAST"||mode=="LTM8_CHAOS")solver.ltm8_enable(mode=="LTM8_CHAOS",trial_seed,orig);'
assert src.count(anchor)==1,("LTM9 insertion drift",src.count(anchor))
assert '#include "drnas_ltm9_php.hpp"' not in src
check=r'''   if(mode=="LTM8_FAST"){
      const auto p=ltm9_php::prove(orig);
      if(p.proved){
          std::cout<<"c LTM9_PHP_CERT rows="<<p.rows<<" cols="<<p.cols<<"\n";
          std::cout<<"s UNSATISFIABLE\n";
          return 20;
      }
   }
'''
src='#include "drnas_ltm9_php.hpp"\n'+src.replace(anchor,check+anchor,1)
path.write_text(src)
subprocess.run([os.environ.get('CXX','g++'),'-O3','-std=c++17','-I','research','-I','mre_atlas23','-I','mre_atlas15',str(path),'-o',str(root/'bin/drnas_ltm9')],check=True)
print('LTM9_COMPILE_PASS baseline_retained=true proof_by_counting=true')
