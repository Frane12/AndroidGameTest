#!/usr/bin/env python3
"""DRNAS COOP5.1: build fixed, dynamic frozen COOP5 and a hybrid 3rd executable.

Two existing builds are reproduced unmodified from the frozen X5-derived
source. Only the NEW hybrid binary changes the probe gate; no changes to
conflict learning, RUP/DRAT emission, or watched literal propagation.
"""
import hashlib,pathlib,subprocess
R=pathlib.Path(__file__).resolve().parents[2]
subprocess.run(["python3",str(R/"research/drnas_coop5/build.py")],cwd=R,check=True)
fixed=(R/"build/drnas-coop5-fixed").read_bytes()
dynamic=(R/"build/drnas-coop5-dynamic").read_bytes()
# Exact previously validated builds, avoid silently changing the baselines.
assert hashlib.sha256(fixed).hexdigest()=="4dc87df8c3dff7dee877563357117e9b21f3b9b4d9748bfdd569b005f9d8c8d5"
assert hashlib.sha256(dynamic).hexdigest()=="d2a584b8a5f015e36469a015e057b2223b88c7bee040d629c0f84d150b628a44"
s=(R/"build/drnas_coop5.cpp").read_text()
def rep(a,b):
    global s
    assert s.count(a)==1,(a[:90],s.count(a))
    s=s.replace(a,b)
rep('    bool coop5_dynamic_=COOP5_DYNAMIC_DEFAULT!=0;',
    '''    bool coop5_dynamic_=COOP5_DYNAMIC_DEFAULT!=0;
    bool coop51_hybrid_=COOP5_DYNAMIC_DEFAULT==2;
    int64_t coop51_forced_deep_=0,coop51_shallow_=0,coop51_deep_advice_=0;''')
rep('        coop5_gap_=coop5_dynamic_?64:24;',
    '        coop5_gap_=coop51_hybrid_?24:(coop5_dynamic_?64:24);')
rep('''    void coop5Adjust(bool proxy_good) {
        if(!coop5_dynamic_)return;''',
    '''    void coop5Adjust(bool proxy_good) {
        if(!coop5_dynamic_)return;
        if(coop51_hybrid_) {
            if(proxy_good) {
                coop5_failures_=0;
                coop5_gap_=std::max(24,coop5_gap_/2);
            } else if(++coop5_failures_>=3) {
                coop5_failures_=0;
                ++coop5_cooldowns_;
                coop5_gap_=std::min(128,coop5_gap_*2);
            }
            return;
        }''')
rep('''            if(coop5_dynamic_){
                coop5_gap_=std::min(256,coop5_gap_*2);
                coop5_inspections_=std::max(96,
                    coop5_inspections_>320?320:96);
            }''',
    '''            if(coop5_dynamic_){
                if(coop51_hybrid_) {
                    ++coop5_cooldowns_;
                    coop5_gap_=std::min(128,coop5_gap_*2);
                } else {
                    coop5_gap_=std::min(256,coop5_gap_*2);
                    coop5_inspections_=std::max(96,
                        coop5_inspections_>320?320:96);
                }
            }''')
rep('''        const int depth=coop5_inspections_;
        if(depth<=96)++coop5_depth96_;''',
    '''        // FIRST probe is deep, then one deep per four eligible pairs.
        // Keep short 96-inspection probes between; adapt cadence on feedback.
        // This avoids the DYNAMIC v5 failure to inspect the early rare
        // scheduling branch that FIXED resolved in the frozen real18 pilot.
        const int depth=coop51_hybrid_?
            ((coop5_attempts_%4==0)?320:96):coop5_inspections_;
        if(coop51_hybrid_){
            if(depth==320)++coop51_forced_deep_;
            else ++coop51_shallow_;
        }
        if(depth<=96)++coop5_depth96_;''')
rep('''        ++coop5_recommend_;
        coop5Adjust(true);''',
    '''        ++coop5_recommend_;
        if(coop51_hybrid_ && depth==320)++coop51_deep_advice_;
        coop5Adjust(true);''')
rep('''                 <<(coop5_dynamic_?"dynamic":"fixed")
                 <<"\",\"mode\":\""<<coop5_mode_''',
    '''                 <<(coop51_hybrid_?"hybrid":(coop5_dynamic_?"dynamic":"fixed"))
                 <<"\",\"mode\":\""<<coop5_mode_''')
rep('''                 <<",\"total_implied\":"<<coop5_total_implied_
                 <<"}\n";''',
    '''                 <<",\"total_implied\":"<<coop5_total_implied_
                 <<",\"hybrid_deep_pairs\":"<<coop51_forced_deep_
                 <<",\"hybrid_shallow_pairs\":"<<coop51_shallow_
                 <<",\"hybrid_deep_recommend\":"<<coop51_deep_advice_
                 <<",\"cadence_final\":"<<coop5_gap_
                 <<"}\n";''')
src=R/"build/drnas_coop51.cpp"
src.write_text(s)
binary=R/"build/drnas-coop51-hybrid"
subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=2",
                str(src),"-o",str(binary)],cwd=R,check=True)
print("COOP51_HYBRID_BUILD "+hashlib.sha256(binary.read_bytes()).hexdigest(),flush=True)
