#!/usr/bin/env python3
"""CLCF5: isolate which first-reduction learned clauses deserve retention.

Four modes share the EXACT pinned native X5 CDCL, all pre-reduction learning,
branching, proof, restarts and analysis. At the FIRST effective reduction only,
keep the same number of clauses while ranking candidate deletion by:
  BASE  - original activity/length order (unmodified)
  LBD   - delete higher-LBD clauses first
  RECENT- delete clauses with oldest actual BCP/conflict-analysis use
  HASH  - deterministic pseudorandom order (sham-selection control)
No solver runs in parallel; no unproved clauses, model shortcuts or main edits.
"""
from pathlib import Path
import hashlib,json,subprocess

R=Path(__file__).resolve().parents[1]
BASE=R/"src/drnas_x5.cpp"
SRC=R/"build/drnas_clause_cf5.cpp"
OUT=R/"build/drnas-clause-cf5"
PIN="9768340a8bed3bac3e43f0fb29780c4d5165c50283f90eae141733a7b76106fc"

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(s,old,new):
    n=s.count(old)
    if n!=1:raise RuntimeError(("CLCF5_SOURCE_DRIFT",n,old[:160]))
    return s.replace(old,new)

def build():
    assert sha(BASE)==PIN,("X5_ORIGINAL_SOURCE_CHANGED",sha(BASE))
    s=BASE.read_text()
    s=once(s,"    int64_t last_used = 0;\n};",
      """    int64_t last_used = 0;
    int64_t cf5_last_use = -1000000000;
    int cf5_tracking_id = -1;
};""")
    s=once(s,"    const char* mode() const { return mode_.c_str(); }",
      r'''    const char* mode() const { return mode_.c_str(); }
    void configureCf5(const std::string& policy) {
        if(policy!="BASE" && policy!="LBD" && policy!="RECENT" && policy!="HASH")
            throw std::runtime_error("CLCF5_INVALID_POLICY");
        cf5_policy_=policy;
    }
    void reportCf5() const {
        int64_t candidate_bins[3]={},retained_bins[3]={},deleted_bins[3]={};
        int64_t events100_bcp[3]={},events100_analysis[3]={};
        int64_t events500_bcp[3]={},events500_analysis[3]={};
        int64_t used100[3]={},used500[3]={},preuse_kept[3]={};
        for(const auto& q:cf5_first_cohort_) {
            const int b=q.glue<=2?0:q.glue<=6?1:2;
            ++candidate_bins[b];
            if(q.deleted) {++deleted_bins[b];continue;}
            ++retained_bins[b]; preuse_kept[b]+=q.preuse;
            events100_bcp[b]+=q.bcp100;events100_analysis[b]+=q.analysis100;
            events500_bcp[b]+=q.bcp500;events500_analysis[b]+=q.analysis500;
            used100[b]+=q.bcp100+q.analysis100>0;
            used500[b]+=q.bcp500+q.analysis500>0;
        }
        std::cerr<<"CLCF5_STATS {\"policy\":\""<<cf5_policy_
                 <<"\",\"first_effective_reduce\":"<<(cf5_first_done_?"true":"false")
                 <<",\"first_reduce_conflicts\":"<<cf5_first_conflicts_
                 <<",\"first_reduce_decisions\":"<<cf5_first_decisions_
                 <<",\"first_candidate_digest\":"<<cf5_first_digest_
                 <<",\"candidates\":"<<cf5_first_cohort_.size()
                 <<",\"deleted\":"<<cf5_first_deleted_
                 <<",\"post100_observed\":"
                 <<(cf5_first_done_ && stats_.conflicts>=cf5_first_conflicts_+100?"true":"false")
                 <<",\"post500_observed\":"
                 <<(cf5_first_done_ && stats_.conflicts>=cf5_first_conflicts_+500?"true":"false")
                 <<",\"by_LBD\":[";
        for(int b=0;b<3;++b) {
            if(b)std::cerr<<",";
            std::cerr<<"{\"label\":\""<<(b==0?"LBD<=2":b==1?"LBD3-6":"LBD>=7")
                     <<"\",\"candidates\":"<<candidate_bins[b]
                     <<",\"retained\":"<<retained_bins[b]
                     <<",\"deleted\":"<<deleted_bins[b]
                     <<",\"pre500_recently_used_retained\":"<<preuse_kept[b]
                     <<",\"post100_distinct_used\":"<<used100[b]
                     <<",\"post100_bcp\":"<<events100_bcp[b]
                     <<",\"post100_analysis\":"<<events100_analysis[b]
                     <<",\"post500_distinct_used\":"<<used500[b]
                     <<",\"post500_bcp\":"<<events500_bcp[b]
                     <<",\"post500_analysis\":"<<events500_analysis[b]<<"}";
        }
        std::cerr<<"]}\n";
    }''')
    s=once(s,"    bool x5_minimize_=true, x5_retain_=false, x5_gc_=true, x5_restarts_=false;",
      """    bool x5_minimize_=true, x5_retain_=false, x5_gc_=true, x5_restarts_=false;
    std::string cf5_policy_="BASE";
    bool cf5_first_done_=false;
    int64_t cf5_first_conflicts_=-1,cf5_first_decisions_=-1;
    int64_t cf5_first_deleted_=0;
    uint64_t cf5_first_digest_=0;""")
    s=once(s, "    std::vector<Clause> clauses_;",
      """    struct Cf5Record {
        int glue=0,preuse=0;
        bool deleted=false;
        int64_t bcp100=0,analysis100=0,bcp500=0,analysis500=0;
    };
    std::vector<Cf5Record> cf5_first_cohort_;
    // Measurement is passive; records survive watched clause GC.
    void cf5Use(int cid,bool analysis) {
        if(x46_clone_ || probing_ || cid<0) return;
        Clause& c=clauses_[static_cast<size_t>(cid)];
        if(!c.learnt)return;
        if(!cf5_first_done_) {
            c.cf5_last_use=stats_.conflicts;
            return;
        }
        if(c.cf5_tracking_id<0)return;
        const int64_t age=stats_.conflicts-cf5_first_conflicts_;
        if(age<0 || age>500)return;
        Cf5Record& q=cf5_first_cohort_[static_cast<size_t>(c.cf5_tracking_id)];
        if(analysis) {
            ++q.analysis500;
            if(age<=100)++q.analysis100;
        }else{
            ++q.bcp500;
            if(age<=100)++q.bcp100;
        }
    }
    std::vector<Clause> clauses_;""")
    s=once(s,"        reasons_[v] = reason;\n        if (x5_retain_",
      """        reasons_[v] = reason;
        if(!probing_ && reason>=0)cf5Use(reason,false);
        if (x5_retain_""")
    s=once(s,"            Clause& c = clauses_[conflict];\n            c.activity +=",
      """            Clause& c = clauses_[conflict];
            if(!probing_ && c.learnt)cf5Use(conflict,true);
            c.activity +=""")
    s=once(s,
      "        if(candidates.size()>=128) {\n            std::sort(candidates.begin(),candidates.end(),[&](int a,int b) {",
      r'''        if(candidates.size()>=128) {
            const bool first=!cf5_first_done_;
            if(first) {
                cf5_first_done_=true;
                cf5_first_conflicts_=stats_.conflicts;
                cf5_first_decisions_=stats_.decisions;
                cf5_first_cohort_.reserve(candidates.size());
                cf5_first_digest_=1469598103934665603ULL;
                for(int cid:candidates) {
                    cf5_first_digest_^=static_cast<uint64_t>(cid);
                    cf5_first_digest_*=1099511628211ULL;
                    const Clause& item=clauses_[static_cast<size_t>(cid)];
                    cf5_first_digest_^=static_cast<uint64_t>(item.glue);
                    cf5_first_digest_*=1099511628211ULL;
                    Clause& c=clauses_[static_cast<size_t>(cid)];
                    const int pre=(c.cf5_last_use>=stats_.conflicts-500)?1:0;
                    c.cf5_tracking_id=static_cast<int>(cf5_first_cohort_.size());
                    cf5_first_cohort_.push_back(Cf5Record{c.glue,pre});
                }
            }
            std::sort(candidates.begin(),candidates.end(),[&](int a,int b) {
                // The choice is made at the FIRST effective reduction only.
                // All modes delete precisely the same number of unlocked,
                // nonbinary learned clauses. Later reduction is baseline.
                if(first) {
                    const Clause& ca=clauses_[static_cast<size_t>(a)];
                    const Clause& cb=clauses_[static_cast<size_t>(b)];
                    if(cf5_policy_=="LBD" && ca.glue!=cb.glue)
                        return ca.glue>cb.glue;
                    if(cf5_policy_=="RECENT") {
                        const int64_t au=ca.cf5_last_use,bu=cb.cf5_last_use;
                        if(au!=bu)return au<bu;
                    }
                    if(cf5_policy_=="HASH") {
                        auto fingerprint=[&](const Clause& c) {
                            uint64_t h=1469598103934665603ULL;
                            for(int lit:c.lits) {
                                h^=static_cast<uint64_t>(static_cast<int64_t>(lit));
                                h*=1099511628211ULL;
                            }
                            return h;
                        };
                        const uint64_t ah=fingerprint(ca),bh=fingerprint(cb);
                        if(ah!=bh)return ah<bh;
                    }
                }''')
    s=once(s,"                clauses_[candidates[k]].deleted=true;\n                ++stats_.reduce_removed;",
      """                Clause& c=clauses_[static_cast<size_t>(candidates[k])];
                if(first && c.cf5_tracking_id>=0) {
                    cf5_first_cohort_[static_cast<size_t>(c.cf5_tracking_id)].deleted=true;
                    ++cf5_first_deleted_;
                }
                c.deleted=true;
                ++stats_.reduce_removed;""")
    s=once(s, "    std::string x46_model_path,x47_guard_path,proof_path;",
      """    std::string x46_model_path,x47_guard_path,proof_path;
    std::string cf5_policy="BASE";""")
    s=once(s, '        else if (opt=="--x5-restarts") x5_restarts=true;',
      '''        else if (opt=="--x5-restarts") x5_restarts=true;
        else if (opt=="--cf5-policy" && i+1<argc) cf5_policy=argv[++i];''')
    s=once(s,"            solver->configureX5(x5_minimize,x5_retain,x5_gc,x5_restarts,",
      "            solver->configureCf5(cf5_policy);\n            solver->configureX5(x5_minimize,x5_retain,x5_gc,x5_restarts,")
    s=once(s, '        const Stats& s=solver->stats();\n        std::cerr<<"X5_STATS ',
      '        const Stats& s=solver->stats();\n        solver->reportCf5();\n        std::cerr<<"X5_STATS ')
    SRC.parent.mkdir(exist_ok=True)
    SRC.write_text(s)
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror",str(SRC),"-o",str(OUT)],
                    cwd=R,check=True)
    print("CLCF5_BUILD",json.dumps({
        "source_sha256":sha(BASE),"patched_sha256":sha(SRC),
        "binary_sha256":sha(OUT),"same_delete_count_first_reduction":True,
        "no_new_proof_clauses":True,"no_solver_rewrite_outside_first_reduction":True,
        "main_modified":False},sort_keys=True),flush=True)

if __name__=="__main__":build()
