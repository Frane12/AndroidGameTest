#!/usr/bin/env python3
"""ATLAS40 pressure: forked clause decision tree, A36 quota=75 unchanged."""
from pathlib import Path
h=Path("mre_atlas23/drnas_native_core_c.hpp")
s=h.read_text()
needle="if(atlas39_mode_==2)score-=500;"
assert s.count(needle)==1,("ATLAS40 score drift",s.count(needle))
s=s.replace(needle,needle+"\n            else if(atlas39_mode_==3){\n                    const bool high_bcp = stats_.watch_visits > 20ULL*std::max<uint64_t>(1,stats_.propagations);\n                                        if(high_bcp && kv.second<=15 && atlas39_hits_[size_t(cid)]>=3)score-=650;\n                                        else if(!high_bcp && kv.second<=9 && stats_.conflicts-atlas15_born_.at(cid)<=4500)score-=250;\n                }",1)
assert s.count('require(mode==1||mode==2,"ATLAS39 invalid utility mode");')==1
s=s.replace('require(mode==1||mode==2,"ATLAS39 invalid utility mode");','require(mode==1||mode==2||mode==3,"ATLAS40 invalid utility mode");',1)
mark="if(atlas39_mode_==2){\\n            ++atlas39_reduction_events_;"
assert "if(atlas39_mode_==2){\n            ++atlas39_reduction_events_;" in s
s=s.replace("if(atlas39_mode_==2){\n            ++atlas39_reduction_events_;",
            "if(atlas39_mode_>=2){\n            ++atlas39_reduction_events_;",1)
h.write_text(s)
p=Path("mre_atlas23/native.cpp")
s=p.read_text()
needle='mode=="A39_PROTECT"'
assert s.count(needle)>=2,("ATLAS40 dispatch drift",s.count(needle))
s=s.replace(needle,'(mode=="A39_PROTECT"||mode=="A40_TREE")')
assert 'solver.atlas39_enable(mode=="A39_SHADOW"?1:2)' in s
s=s.replace('solver.atlas39_enable(mode=="A39_SHADOW"?1:2)',
            'solver.atlas39_enable(mode=="A39_SHADOW"?1:(mode=="A40_TREE"?3:2))',1)
p.write_text(s)
print("ATLAS40_BUILD_PASS variant=pressure clause_reuse_LBD_age_tree=true 75_fixed=true",flush=True)
