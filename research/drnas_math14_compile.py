from pathlib import Path
import subprocess,os
p=Path('mre_atlas23/native_certificate.cpp');s=p.read_text()
anchor='   solver.add_cnf(work);'
assert s.count(anchor)==1
s='#include "drnas_math14.hpp"\n'+s.replace(anchor,'   math14::enrich(work);\n'+anchor)
q=p.with_name('native_math14.cpp');q.write_text(s)
subprocess.run([os.getenv('CXX','g++'),'-O3','-std=c++17','-I','research','-I','mre_atlas23','-I','mre_atlas15',str(q),'-o','mre_atlas23/bin/drnas_math14'],check=True)

