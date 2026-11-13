#!/usr/bin/env python3
"""Generate separately instrumented COOP4 audit build; base solver remains intact."""
import hashlib, pathlib, subprocess
R=pathlib.Path(__file__).resolve().parents[2]
subprocess.run(["python3",str(R/"research/drnas_coop4/build.py")],cwd=R,check=True)
s=(R/"build/drnas_coop4.cpp").read_text()
def rep(a,b):
    global s
    assert s.count(a)==1,(a[:90],s.count(a))
    s=s.replace(a,b)

rep('#include "../research/drnas_coop4/coop.hpp"',
    '#include "../research/drnas_coop4_audit/coop.hpp"')
rep('    int coop_hint_=-1;', '''    int coop_hint_=-1;
    bool audit_fresh_=false, hint_stale_=false;
    int audit_suggested_phase_=0,audit_small_count_=0,audit_other_count_=0;
    int64_t audit_proposals_=0,audit_stale_=0,audit_suppressed_=0;
    int64_t audit_selected_=0,audit_overrides_=0,audit_stale_applied_=0;
    int64_t audit_phase_opposite_=0,audit_phase_comparable_=0;
    void configureCoop4HintFresh(bool yes){audit_fresh_=yes;}''')
rep('    void reportCoop() const { coop_.report(); }',r'''    void reportCoop() const {
        coop_.report();
        std::cerr<<"COOP4_HINT_AUDIT {\"fresh\":"<<(audit_fresh_?"true":"false")
                 <<",\"proposals\":"<<audit_proposals_
                 <<",\"stale_proposals\":"<<audit_stale_
                 <<",\"suppressed\":"<<audit_suppressed_
                 <<",\"selected\":"<<audit_selected_
                 <<",\"overrides\":"<<audit_overrides_
                 <<",\"stale_overrides\":"<<audit_stale_applied_
                 <<",\"phase_comparable\":"<<audit_phase_comparable_
                 <<",\"phase_opposite_small_branch\":"<<audit_phase_opposite_<<"}\n";
    }''')
rep('''        coop_hint_=out.hint;
        for(auto& c:out.clauses){''','''        coop_hint_=out.hint;
        hint_stale_=false;
        audit_suggested_phase_=out.phase_small_branch;
        audit_small_count_=out.solutions_in_small_branch;
        audit_other_count_=out.solutions_in_other_branch;
        const size_t audit_trail=trail_.size();
        const int audit_level=decisionLevel();
        if(coop_hint_>=0)++audit_proposals_;
        for(auto& c:out.clauses){''')
rep('''        return propagate(-1);
    }
    void configureX5(''','''        const Prop pr=propagate(-1);
        if(coop_hint_>=0 && values_[static_cast<size_t>(coop_hint_)]==0
           && pr.result==PropResult::OK) {
            hint_stale_=(audit_trail!=trail_.size() ||
                         audit_level!=decisionLevel());
            if(hint_stale_) {
                ++audit_stale_;
                if(audit_fresh_) {
                    ++audit_suppressed_;
                    coop_hint_=-1;
                }
            }
        }
        return pr;
    }
    void configureX5(''')
rep('''            if(coop_.mode=="on" && coop_hint_>=0 && values_[coop_hint_]==0 && v>=0) {
                if(v!=coop_hint_){offer(v);v=coop_hint_;++coop_.applied_hints;}
            }''','''            if(coop_.mode=="on" && coop_hint_>=0 && values_[coop_hint_]==0 && v>=0) {
                ++audit_selected_;
                if(audit_suggested_phase_!=0 &&
                   audit_small_count_<audit_other_count_) {
                    ++audit_phase_comparable_;
                    if(phase_[static_cast<size_t>(coop_hint_)]!=audit_suggested_phase_)
                        ++audit_phase_opposite_;
                }
                if(v!=coop_hint_){
                    ++audit_overrides_;
                    if(hint_stale_)++audit_stale_applied_;
                    offer(v);v=coop_hint_;++coop_.applied_hints;
                }
            }''')
rep('    bool coop_eager=false;', '    bool coop_eager=false,coop4_audit_fresh=false;')
rep('''        else if (opt=="--coop4-policy" && i+1<argc) coop4_policy=argv[++i];''',
'''        else if (opt=="--coop4-policy" && i+1<argc) coop4_policy=argv[++i];
        else if (opt=="--coop4-audit-fresh") coop4_audit_fresh=true;''')
rep('''            solver->configureCoop4Policy(coop4_policy);
            solver->configureX5(''','''            solver->configureCoop4Policy(coop4_policy);
            solver->configureCoop4HintFresh(coop4_audit_fresh);
            solver->configureX5(''')
build=R/"build"
src=build/"drnas_coop4_audit.cpp"
src.write_text(s)
subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
 "-Wpedantic","-Werror",str(src),"-o",str(build/"drnas-coop4-audit")],
 cwd=R,check=True)
print("COOP4_HINT_AUDIT_BUILD",hashlib.sha256(
 (build/"drnas-coop4-audit").read_bytes()).hexdigest(),flush=True)
