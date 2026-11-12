#!/usr/bin/env python3
"""LTM8 PHP: experimental conservative learned-clause deletion quota (50%).
Patch generated native code AFTER ATLAS36/LTM7. No change to soundness rules.
"""
from pathlib import Path
h=Path("mre_atlas23/drnas_native_core_c.hpp")
s=h.read_text()
old='require(pct==90 || pct==75,"ATLAS36 invalid percentage");'
assert s.count(old)==1
s=s.replace(old,'require(pct==90 || pct==75 || pct==50,"ATLAS36 invalid percentage");')
h.write_text(s)
p=Path("mre_atlas23/native.cpp")
s=p.read_text()
old='mode=="A36_75"'
assert s.count(old)>=2
# Add new mode to existing mode-dispatch predicates, not the setter statement.
s=s.replace('||mode=="A36_75"','||mode=="A36_75"||mode=="LTM8_KEEP50"')
anchor='if(mode=="A36_75")solver.atlas36_enable_quota(75);'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'\n    if(mode=="LTM8_KEEP50")solver.atlas36_enable_quota(50);')
assert 'mode=="LTM8_KEEP50"' in s
p.write_text(s)
print("LTM8_KEEP50_PATCH_PASS",flush=True)
