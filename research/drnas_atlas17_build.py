#!/usr/bin/env python3
"""ATLAS17: instrument BCP and adapt learned-clause retention only in C7.

Generated from the ATLAS16 frozen builder. Never change the C5/C6 controls,
SATLIB inputs, original CNF, or SAT/UNSAT inference rules.
"""
from pathlib import Path

root=Path("mre_atlas17")
root.mkdir(exist_ok=True)
s=Path("mre_atlas16/drnas_native_core_c.hpp").read_text()

def one(a,b):
    global s
    assert s.count(a)==1, ("patch mismatch",a,s.count(a))
    s=s.replace(a,b,1)

one("    bool atlas16_keep_=false;", """
    bool atlas17_adaptive_=false, atlas17_high_pressure_=false;
    uint64_t atlas17_last_watch_=0, atlas17_last_prop_=0;
    uint64_t atlas17_pressure_cycles_=0, atlas17_low_cycles_=0;
    bool atlas16_keep_=false;""".strip("\n"))
one("""                if(atlas15_enabled_ && stats_.conflicts%10000==0)atlas15_reduce_db();""",
"""                // Legacy C5/C6 scheduling is deliberately identical to ATLAS16.
                // C7 activates its own measured 1500-conflict sampling schedule.
                if(atlas15_enabled_ &&
                   ((atlas17_adaptive_ && stats_.conflicts%1500==0) ||
                    (!atlas17_adaptive_ && stats_.conflicts%10000==0)))
                    atlas15_reduce_db();""")

one("""        if(stats_.conflicts%1500!=0)return;
        ++atlas15_reductions_;""", """        if(stats_.conflicts%1500!=0)return;
        if(atlas17_adaptive_){
            const uint64_t dw=stats_.watch_visits-atlas17_last_watch_;
            const uint64_t dp=stats_.propagations-atlas17_last_prop_;
            atlas17_last_watch_=stats_.watch_visits;
            atlas17_last_prop_=stats_.propagations;
            // The threshold is pre-registered. Watch visits are a BCP proxy,
            // not wall-clock time. No inference may depend on this decision.
            atlas17_high_pressure_=(dp>0 && dw>8*dp);
            if(atlas17_high_pressure_)++atlas17_pressure_cycles_;
            else ++atlas17_low_cycles_;
            // Less deletion if the current BCP burden is low.
            if(!atlas17_high_pressure_ && stats_.conflicts%3000!=0)return;
        }
        ++atlas15_reductions_;""")
one("""        const size_t count=std::max<size_t>(1,candidates.size()/8);""",
"""        // C6 always 1/8. C7: 1/4 under high BCP pressure, 1/16 otherwise.
        const size_t divisor=atlas17_adaptive_?(atlas17_high_pressure_?4:16):8;
        const size_t count=std::max<size_t>(1,candidates.size()/divisor);""")
one("""    void atlas16_enable_keep(){require(atlas15_enabled_,"enable CDCL first");atlas16_keep_=true;}""",
"""    void atlas16_enable_keep(){require(atlas15_enabled_,"enable CDCL first");atlas16_keep_=true;}
    void atlas17_enable_adaptive(){
        require(atlas16_keep_,"C7 adaptive requires C6 retention");
        atlas17_adaptive_=true;
    }
    uint64_t atlas17_pressure_cycles()const{return atlas17_pressure_cycles_;}
    uint64_t atlas17_low_cycles()const{return atlas17_low_cycles_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)

src=Path("mre_atlas16/native.cpp").read_text()
assert src.count('mode=="C6_KEEP_GAUSS"')>=2
assert src.count('mode=="C6_KEEP"')>=2
src=src.replace('mode=="C6_KEEP_GAUSS"',
                'mode=="C6_KEEP_GAUSS"||mode=="C7_ADAPT_GAUSS"')
src=src.replace('mode=="C6_KEEP"', 'mode=="C6_KEEP"||mode=="C7_ADAPT"')
anchor='solver.atlas16_enable_keep();'
assert src.count(anchor)==1
src=src.replace(anchor,anchor+
    '\n    if(mode=="C7_ADAPT"||mode=="C7_ADAPT_GAUSS")solver.atlas17_enable_adaptive();',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,
'''           <<" propagations="<<st.propagations
           <<" watch_visits="<<st.watch_visits
           <<" xor_checks="<<st.xor_checks
           <<" atlas17_pressure_cycles="<<solver.atlas17_pressure_cycles()
           <<" atlas17_low_cycles="<<solver.atlas17_low_cycles()
''' +anchor,1)
(root/"native.cpp").write_text(src)
assert 'atlas17_enable_adaptive()' in src
assert 'atlas17_high_pressure_' in s
print("ATLAS17_BUILD_PATCH_PASS isolated=true c5_c6_frozen=true adaptive_bcp_watch_pressure=true")
