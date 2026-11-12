from pathlib import Path
import os, subprocess
root=Path('mre_atlas23')
assert (root/'bin/drnas_ltm8_base').exists(), 'build frozen LTM9 certificates first'
# Existing binaries remain frozen. Compile the experimental policy separately.
(root/'ltm8_policy.hpp').write_text(Path('research/drnas_ltm13_policy.hpp').read_text())
subprocess.run([os.getenv('CXX','g++'),'-O3','-std=c++17','-I','research','-I',str(root),'-I','mre_atlas15',str(root/'native_certificate.cpp'),'-o',str(root/'bin/drnas_ltm13')],check=True)
print('LTM13_COMPILE_PASS')
