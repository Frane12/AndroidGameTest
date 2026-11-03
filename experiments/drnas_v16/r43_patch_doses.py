#!/usr/bin/env python3
"""R43: 16 and 64 capped doses in already-frozen R42 native policy source.
Requires R40 -> R41 -> R42 patches, then this strictly anchored extension.
No modifications to CaDiCaL decision / propagation / proof logic.
"""
import argparse,hashlib
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--source",required=True);p.add_argument("--out",required=True)
a=p.parse_args();s=Path(a.source).read_text()
old='''        } else if(mode=="v91_cap32") {
            a=ablation(f,"v91_rescue",false,seed,true,32);
        } else if(mode=="v91_cap128") {'''
new='''        } else if(mode=="v91_cap16") {
            a=ablation(f,"v91_rescue",false,seed,true,16);
        } else if(mode=="v91_cap32") {
            a=ablation(f,"v91_rescue",false,seed,true,32);
        } else if(mode=="v91_cap64") {
            a=ablation(f,"v91_rescue",false,seed,true,64);
        } else if(mode=="v91_cap128") {'''
assert s.count(old)==1,"R43 anchor mismatch; do not patch different native source"
s=s.replace(old,new)
out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(s)
print("R43_NATIVE_PATCH_PASS",hashlib.sha256(s.encode()).hexdigest(),flush=True)
