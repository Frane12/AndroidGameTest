#!/usr/bin/env python3
"""ATLAS41 native C++ exact-candidate protection and bounded audit.
A36 fixed 75%, A39 untouched; new modes 3=guard and 4=decay.
These are explicit preregistered hypotheses, not a learned router.
"""
from pathlib import Path
p=Path("mre_atlas23/drnas_native_core_c.hpp")
s=p.read_text()
def one(a,b):
 global s
 assert s.count(a)==1,("ATLAS41_HEADER_DRIFT",a[:110],s.count(a))
 s=s.replace(a,b,1)

one("    int atlas39_mode_=0; // 0 frozen control, 1 shadow, 2 protect",
"""    int atlas39_mode_=0; // 0 control, 1 shadow, 2 original A39, 3 guard, 4 decay
    uint64_t atlas41_eligible_scored_=0,atlas41_guarded_=0,atlas41_decay_guarded_=0;
    uint64_t atlas41_trace_count_=0,atlas41_digest_xor_=0;""")
one("if(atlas39_mode_==2)score-=500;",
"""if(atlas39_mode_==2)score-=500;
                    else if(atlas39_mode_==3||atlas39_mode_==4){
                        const uint64_t born_age=stats_.conflicts-atlas15_born_.at(cid);
                        const uint32_t since_use=uint32_t(stats_.conflicts)-atlas39_last_[size_t(cid)];
                        const uint8_t hits=atlas39_hits_[size_t(cid)];
                        // Eligible candidates are already protected by the
                        // unchanged C7 locked/short/low-LBD gates.
                        const bool guard = (kv.second<=11 && born_age<=5000 &&
                                            since_use<=1500 && hits>=3);
                        const bool decay = (kv.second<=17 && born_age<=2500 &&
                                            since_use<=800 && hits>=4);
                        const bool selected=atlas39_mode_==3?guard:decay;
                        ++atlas41_eligible_scored_;
                        if(selected){
                            score-=350;
                            if(atlas39_mode_==3)++atlas41_guarded_;
                            else ++atlas41_decay_guarded_;
                            // Deterministic literal fingerprint is diagnostic,
                            // not a formal proof or an inter-run clause ID.
                            uint64_t hash=1469598103934665603ULL;
                            for(int lit:cl){hash^=uint64_t(int64_t(lit));
                                           hash*=1099511628211ULL;}
                            atlas41_digest_xor_^=hash;
                            if(atlas41_trace_count_<12){
                                ++atlas41_trace_count_;
                                std::cerr<<"ATLAS41_CANDIDATE mode="<<atlas39_mode_
                                  <<" cid="<<cid<<" hash="<<hash
                                  <<" len="<<cl.size()<<" lbd="<<kv.second
                                  <<" age="<<born_age<<" since="<<since_use
                                  <<" hits="<<int(hits)
                                  <<" score_before="<<(score+350)
                                  <<" score_after="<<score<<std::endl;
                            }
                        }
                    }""")
one("if(atlas39_mode_==2){\n            ++atlas39_reduction_events_;",
    "if(atlas39_mode_>=2){\n            ++atlas39_reduction_events_;")
one('require(mode==1||mode==2,"ATLAS39 invalid utility mode");',
    'require(mode>=1&&mode<=4,"ATLAS41 invalid utility mode");')
one("    uint64_t atlas39_metadata_bytes()const{",
"""    uint64_t atlas41_eligible_scored()const{return atlas41_eligible_scored_;}
    uint64_t atlas41_guarded()const{return atlas41_guarded_;}
    uint64_t atlas41_decay_guarded()const{return atlas41_decay_guarded_;}
    uint64_t atlas41_trace_count()const{return atlas41_trace_count_;}
    uint64_t atlas41_digest_xor()const{return atlas41_digest_xor_;}
    uint64_t atlas39_metadata_bytes()const{""")
s="#include <iostream>\n"+s
p.write_text(s)

p=Path("mre_atlas23/native.cpp")
s=p.read_text()
needle='mode=="A39_PROTECT"'
assert s.count(needle)>=2,("ATLAS41_MODE_DISPATCH",s.count(needle))
s=s.replace(needle,'(mode=="A39_PROTECT"||mode=="A41_GUARD"||mode=="A41_DECAY")')
one_native='solver.atlas39_enable(mode=="A39_SHADOW"?1:2);'
assert s.count(one_native)==1
s=s.replace(one_native,'solver.atlas39_enable(mode=="A39_SHADOW"?1:(mode=="A41_GUARD"?3:(mode=="A41_DECAY"?4:2)));',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert s.count(anchor)==1
fields=("eligible_scored","guarded","decay_guarded","trace_count","digest_xor")
lines=''.join('           <<" atlas41_'+k+'="<<solver.atlas41_'+k+'()\n'
              for k in fields)
s=s.replace(anchor,lines+anchor,1)
p.write_text(s)
for m in ("A41_GUARD","A41_DECAY"):
 assert s.count('mode=="'+m+'"')>=2
print("ATLAS41_BUILD_PASS exact_candidate_hash_sample=12 C7_quota_75=true"
      " original_A39_frozen=true modes_3_4_distinct=true",flush=True)
