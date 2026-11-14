#!/usr/bin/env python3
"""RET6: continuous learned-clause retention ablations on pinned native X5.

All modules except OFF share the EXACT X5 retention activity updates, LBD
refresh, LBD-first sorting, and core search. At EVERY learned-clause reduction:
  OFF         original --x5-no-retain control
  FULL        original --x5-retain policy (LBD2 or recent1000 or LBD6+recent30000)
  LBD_ONLY    only unconditional LBD <=2 protection, delete 1/3
  RECENT_ONLY only last-use <=1000 protection, delete 1/3
  QUOTA_ONLY  no protection, delete 1/3
  FULL_HALF   FULL protections, delete 1/2 instead of 1/3
No new proof clauses, no main changes, never treat UNKNOWN as solved.
"""
from pathlib import Path
import hashlib,json,subprocess

R=Path(__file__).resolve().parents[1]
BASE=R/"src/drnas_x5.cpp"
OUT=R/"build/drnas_ret6.cpp"
BIN=R/"build/drnas-ret6"
PIN="9768340a8bed3bac3e43f0fb29780c4d5165c50283f90eae141733a7b76106fc"

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(s,a,b):
    cnt=s.count(a)
    if cnt!=1:raise RuntimeError(("RET6_PINNED_SOURCE_DRIFT",cnt,a[:120]))
    return s.replace(a,b)

def main():
    assert sha(BASE)==PIN,("X5_BASE_SOURCE_CHANGED",sha(BASE))
    s=BASE.read_text()
    s=once(s,
      "    void writeProofClause(const std::vector<int>& lits) {",
      r'''    void configureRetain6(const std::string& policy) {
        if(policy!="OFF" && policy!="FULL" && policy!="LBD_ONLY" &&
           policy!="RECENT_ONLY" && policy!="QUOTA_ONLY" &&
           policy!="FULL_HALF")
            throw std::runtime_error("RET6_BAD_POLICY");
        r6_policy_=policy;
        // These modes share all of the X5 RETAIN activity and glue updates.
        x5_retain_=policy!="OFF";
    }
    void reportRetain6() const {
        std::cerr<<"RET6_STATS {\"policy\":\""<<r6_policy_
                 <<"\",\"reduction_calls\":"<<r6_calls_
                 <<",\"effective_reductions\":"<<r6_effective_
                 <<",\"first_reduce_conflicts\":"<<r6_first_conflicts_
                 <<",\"first_reduce_decisions\":"<<r6_first_decisions_
                 <<",\"first_reduce_hash\":\""<<std::hex<<r6_first_hash_
                 <<std::dec<<"\",\"protected_low\":"<<r6_low_
                 <<",\"protected_recent\":"<<r6_recent_
                 <<",\"protected_combo\":"<<r6_combo_
                 <<",\"total_candidates\":"<<r6_candidates_
                 <<",\"total_deleted\":"<<r6_deleted_
                 <<",\"post_first_500_BCP_reasons\":"<<r6_bcp500_
                 <<",\"post_first_500_analysis_reasons\":"<<r6_analysis500_
                 <<",\"post_first_500_low_LBD_reasons\":"<<r6_low500_
                 <<",\"post_first_500_mid_LBD_reasons\":"<<r6_mid500_
                 <<",\"post_first_500_high_LBD_reasons\":"<<r6_high500_
                 <<",\"post_first_500_fully_exposed\":"
                 <<(r6_first_conflicts_>=0 &&
                    stats_.conflicts>=r6_first_conflicts_+500?"true":"false")
                 <<"}\n";
    }
    void r6ReasonUse(int cid,bool analysis) {
        if(x46_clone_ || probing_ || cid<0 ||
           r6_first_conflicts_<0 ||
           stats_.conflicts<=r6_first_conflicts_ ||
           stats_.conflicts>r6_first_conflicts_+500)return;
        const Clause& c=clauses_[static_cast<size_t>(cid)];
        if(!c.learnt)return;
        if(analysis)++r6_analysis500_; else ++r6_bcp500_;
        if(c.glue<=2)++r6_low500_;
        else if(c.glue<=6)++r6_mid500_;
        else ++r6_high500_;
    }
    void writeProofClause(const std::vector<int>& lits) {''')
    s=once(s,
      "    bool x5_minimize_=true, x5_retain_=false, x5_gc_=true, x5_restarts_=false;",
      r'''    bool x5_minimize_=true, x5_retain_=false, x5_gc_=true, x5_restarts_=false;
    std::string r6_policy_="OFF";
    int64_t r6_calls_=0,r6_effective_=0,r6_first_conflicts_=-1;
    int64_t r6_first_decisions_=-1,r6_candidates_=0,r6_deleted_=0;
    int64_t r6_low_=0,r6_recent_=0,r6_combo_=0;
    int64_t r6_bcp500_=0,r6_analysis500_=0,r6_low500_=0;
    int64_t r6_mid500_=0,r6_high500_=0;
    uint64_t r6_first_hash_=0;''')
    s=once(s,
      "        reasons_[v] = reason;\n        if (x5_retain_",
      """        reasons_[v] = reason;
        if(!probing_ && reason>=0)r6ReasonUse(reason,false);
        if (x5_retain_""")
    s=once(s,
      "            Clause& c = clauses_[conflict];\n            c.activity +=",
      """            Clause& c = clauses_[conflict];
            if(!probing_ && c.learnt)r6ReasonUse(conflict,true);
            c.activity +=""")
    s=once(s,
      "    void reduceLearnts() {\n        std::vector<int> candidates;",
      r'''    void reduceLearnts() {
        ++r6_calls_;
        if(r6_calls_==1) {
            r6_first_conflicts_=stats_.conflicts;
            r6_first_decisions_=stats_.decisions;
            uint64_t h=1469598103934665603ULL;
            auto mix=[&](uint64_t x){h^=x;h*=1099511628211ULL;};
            mix(static_cast<uint64_t>(stats_.conflicts));
            mix(static_cast<uint64_t>(stats_.decisions));
            for(const Clause& c:clauses_)if(c.learnt&&!c.deleted){
                mix(c.lits.size());
                for(int l:c.lits)mix(static_cast<uint64_t>(static_cast<int64_t>(l)));
            }
            r6_first_hash_=h;
        }
        std::vector<int> candidates;''')
    s=once(s,
      """            if(x5_retain_ && (c.glue<=2 || stats_.conflicts-c.last_used<1000 ||
                (c.glue<=6 && stats_.conflicts-c.last_used<30000))) {
                ++stats_.protected_clauses;continue;
            }
            candidates.push_back(cid);""",
      r'''            if(x5_retain_) {
                const int64_t age=stats_.conflicts-c.last_used;
                const bool low=c.glue<=2;
                const bool recent=age<1000;
                const bool combo=c.glue<=6 && age<30000;
                bool protected_clause=false;
                if(r6_policy_=="FULL" || r6_policy_=="FULL_HALF")
                    protected_clause=low||recent||combo;
                else if(r6_policy_=="LBD_ONLY")
                    protected_clause=low;
                else if(r6_policy_=="RECENT_ONLY")
                    protected_clause=recent;
                // QUOTA_ONLY disables the protections but retains
                // dynamic glue, activity and one-third deletion quota.
                if(protected_clause) {
                    ++stats_.protected_clauses;
                    if(low)++r6_low_;
                    else if(recent)++r6_recent_;
                    else ++r6_combo_;
                    continue;
                }
            }
            candidates.push_back(cid);''')
    s=once(s,
      """        if(candidates.size()>=128) {
            std::sort(candidates.begin(),candidates.end(),[&](int a,int b) {""",
      """        if(candidates.size()>=128) {
            ++r6_effective_;
            r6_candidates_+=static_cast<int64_t>(candidates.size());
            std::sort(candidates.begin(),candidates.end(),[&](int a,int b) {""")
    s=once(s,
      """            for(size_t k=0;k<candidates.size()/(x5_retain_?3:2);++k) {
                clauses_[candidates[k]].deleted=true;
                ++stats_.reduce_removed;
            }""",
      """            const size_t divisor=(!x5_retain_||r6_policy_=="FULL_HALF")?2:3;
            for(size_t k=0;k<candidates.size()/divisor;++k) {
                clauses_[candidates[k]].deleted=true;
                ++stats_.reduce_removed;
                ++r6_deleted_;
            }""")
    s=once(s,
      "    std::string x46_model_path,x47_guard_path,proof_path;",
      """    std::string x46_model_path,x47_guard_path,proof_path,r6_policy="OFF";""")
    s=once(s,
      '        else if (opt=="--x5-restarts") x5_restarts=true;',
      '''        else if (opt=="--x5-restarts") x5_restarts=true;
        else if (opt=="--r6-policy" && i+1<argc) r6_policy=argv[++i];''')
    s=once(s,
      """            solver->configureX5(x5_minimize,x5_retain,x5_gc,x5_restarts,
                                proof_path.empty()?nullptr:&proof);""",
      """            solver->configureX5(x5_minimize,x5_retain,x5_gc,x5_restarts,
                                proof_path.empty()?nullptr:&proof);
            solver->configureRetain6(r6_policy);""")
    s=once(s,
      '        const Stats& s=solver->stats();\n        std::cerr<<"X5_STATS ',
      '        const Stats& s=solver->stats();\n        solver->reportRetain6();\n        std::cerr<<"X5_STATS ')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(s)
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror",str(OUT),"-o",str(BIN)],cwd=R,check=True)
    print("RET6_BUILD",json.dumps({
        "source_pin_sha256":sha(BASE),"patched_sha256":sha(OUT),
        "binary_sha256":sha(BIN),"no_main_modifications":True,
        "continuous_changes_at_every_reduction":True,
        "no_new_unproved_inferences":True
    },sort_keys=True),flush=True)

if __name__=="__main__":main()
