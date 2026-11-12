#!/usr/bin/env python3
"""LTM8 PHP: isolated lower deletion quota, preserving soundness checks.
Run after ATLAS36, LTM6 and LTM7 native patches.
"""
from pathlib import Path

header=Path("mre_atlas23/drnas_native_core_c.hpp")
source=Path("mre_atlas23/native.cpp")
h=header.read_text()
permit='require(pct==90 || pct==75,"ATLAS36 invalid percentage");'
assert h.count(permit)==1,("quota guard drift",h.count(permit))
h=h.replace(permit,'require(pct==90 || pct==75 || pct==50,"ATLAS36 invalid percentage");')

s=source.read_text()
mode='mode=="A36_75"'
count=s.count(mode)
assert count>=3,("A36_75 mode dispatch drift",count)
# Extend all A36_75 dispatch sites, including the quota-setting if branch.
# Keep the BASE, LTM6 and LTM7 code paths untouched.
s=s.replace(mode,'(mode=="A36_75"||mode=="LTM8_KEEP50")')
# Previous anchor was not unique in generated code; turn the existing
# quota setting into an explicit per-mode choice at every such call site.
quota='solver.atlas36_enable_quota(75);'
quota_count=s.count(quota)
assert quota_count>=1,("quota setter missing",quota_count)
s=s.replace(quota,'solver.atlas36_enable_quota(mode=="LTM8_KEEP50"?50:75);')
assert s.count('mode=="LTM8_KEEP50"')==count+quota_count
header.write_text(h)
source.write_text(s)
print(f"LTM8_KEEP50_PATCH_PASS dispatch_sites={count} quota_sites={quota_count} BASE_unchanged=true",flush=True)

# Compile both new policies through the existing workflow entry point.
import runpy
runpy.run_path("research/drnas_ltm8_adaptive_build.py", run_name="__main__")
