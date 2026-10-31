#!/usr/bin/env python3
"""Turn pinned V10.1 unphased 256-conflict telemetry into a standalone diagnostic.

Fail if source anchors change. No changes to the original solver file.
"""
from pathlib import Path
import argparse
p=argparse.ArgumentParser()
p.add_argument('--source',required=True)
p.add_argument('--dest',required=True)
a=p.parse_args()
s=Path(a.source).read_text()
anchors=[
    ('                 <<"\\tv96_durable_predicted="<<int(durable)\n                 <<std::endl;',
     '                 <<"\\tv96_durable_predicted="<<int(durable)\n'
     '                 <<"\\tcpu_256_ns="<<a.cpu_256_ns\n                 <<std::endl;'),
    ('    if(a.stage1==0) {\n        if(v96) {',
     '    if(v100_diag_policy(policy)) {\n'
     '        std::cout<<"V13_PREFIX_COMPLETE"<<std::endl;\n'
     '        std::exit(0); // Research subprocess: no post-256 search or late phases.\n'
     '    }\n'
     '    if(a.stage1==0) {\n        if(v96) {')
]
for old,new in anchors:
    if s.count(old)!=1:
        raise RuntimeError('V13 source drift: expected one anchor '+repr(old[:100]))
    s=s.replace(old,new,1)
Path(a.dest).write_text('#include <cstdlib> // std::exit in isolated probe\n'+s)
print('V13_PREFIX_PATCH_OK 2',flush=True)
