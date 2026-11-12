#!/usr/bin/env python3
"""Build an instrumented LTM9 binary on the experimental audit branch.

Frozen drnas_ltm8_base and drnas_ltm9 are built normally. A separate
drnas_ltm9_certificate binary emits the actual counted PHP rows, so an
independent checker can validate them directly against the source CNF.
No change to the mathematical detector's selection algorithm.
"""
from pathlib import Path
import os
import subprocess

subprocess.run(["python3","research/drnas_ltm9_compile.py"],check=True)
root=Path("mre_atlas23")
header=Path("research/drnas_ltm9_php.hpp").read_text()
before="struct Result { bool proved=false; unsigned rows=0, cols=0; };"
after="struct Result { bool proved=false; unsigned rows=0, cols=0; std::vector<std::vector<int>> witness; };"
assert header.count(before)==1,"LTM9 Result structure changed"
header=header.replace(before,after,1)
before="return {true,static_cast<unsigned>(rows.size()),static_cast<unsigned>(k)};"
after="return {true,static_cast<unsigned>(rows.size()),static_cast<unsigned>(k),rows};"
assert header.count(before)==1,"LTM9 witness construction changed"
header=header.replace(before,after,1)
(root/"ltm9_certificate.hpp").write_text(header)

native=(root/"native.cpp").read_text()
assert native.count('#include "drnas_ltm9_php.hpp"')==1
native=native.replace('#include "drnas_ltm9_php.hpp"',
                      '#include "ltm9_certificate.hpp"',1)
anchor=r'std::cout<<"c LTM9_PHP_CERT rows="<<p.rows<<" cols="<<p.cols<<"\n";'
assert native.count(anchor)==1,"LTM9 report site changed"
replacement=anchor + r'''
          for(const auto& row:p.witness){
              std::cout<<"c LTM9_PHP_ROW";
              for(int lit:row)std::cout<<" "<<lit;
              std::cout<<" 0\n";
          }'''
native=native.replace(anchor,replacement,1)
source=root/"native_certificate.cpp"
source.write_text(native)
subprocess.run([os.environ.get("CXX","g++"),"-O3","-std=c++17","-I","research",
                "-I","mre_atlas23","-I","mre_atlas15",str(source),
                "-o",str(root/"bin/drnas_ltm9_certificate")],check=True)
print("LTM9_CERT_INSTRUMENT_PASS original_baseline_untouched=true separate_binary=true",flush=True)
