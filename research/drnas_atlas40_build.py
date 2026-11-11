#!/usr/bin/env python3
"""ATLAS40 conservative: forked clause decision tree, A36 quota=75 unchanged."""
from pathlib import Path
h=Path("mre_atlas23/drnas_native_core_c.hpp")
s=h.read_text()
needle="if(atlas39_mode_==2)score-=500;"
assert s.count(needle)==1,("ATLAS40 score drift",s.count(needle))
s=s.replace(needle,"if(atlas39_mode_==2){\n                    if(kv.second<=10 && stats_.conflicts-atlas15_born_.at(cid)<=6000 && atlas39_hits_[size_t(cid)]>=2)score-=300;\n                }",1)
h.write_text(s)
p=Path("mre_atlas23/native.cpp")
s=p.read_text()
needle='mode=="A39_PROTECT"'
assert s.count(needle)>=2,("ATLAS40 dispatch drift",s.count(needle))
s=s.replace(needle,'(mode=="A39_PROTECT"||mode=="A40_TREE")')
assert 'solver.atlas39_enable(mode=="A39_SHADOW"?1:2)' in s
p.write_text(s)
print("ATLAS40_BUILD_PASS variant=conservative clause_reuse_LBD_age_tree=true 75_fixed=true",flush=True)
