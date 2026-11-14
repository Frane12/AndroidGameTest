#!/usr/bin/env python3
"""Build observation-only learned-clause use monitor from exact frozen X5 source.

Track each clause learned during conflicts 1..100, and actual later use as
a BCP or conflict-analysis reason within 100/500 conflicts after its birth.
Counts are reported with exact exposure denominators and original LBD bins.
Tracking IDs survive clause garbage collection, and deleted rows persist as
data only. No effect on CDCL policy, result, proof, or decision order.
"""
from pathlib import Path
import hashlib,json,subprocess

R=Path(__file__).resolve().parents[1]
BASE=R/"src/drnas_x5.cpp"
SRC=R/"build/drnas_clause_usage3.cpp"
BIN=R/"build/drnas-clause-usage3"
PIN="9768340a8bed3bac3e43f0fb29780c4d5165c50283f90eae141733a7b76106fc"

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(s,old,new):
    n=s.count(old)
    if n!=1:raise RuntimeError(("CLAUSE_USAGE3_SOURCE_DRIFT",n,old[:130]))
    return s.replace(old,new)

def main():
    assert sha(BASE)==PIN,("FROZEN_NATIVE_SOURCE_CHANGED",sha(BASE))
    s=BASE.read_text()
    s=once(s,"    int64_t last_used = 0;\n};",
      """    int64_t last_used = 0;
    // Observation-only stable identity for early learned clauses.
    int quality_id=-1;
};""")
    s=once(s,"    const char* mode() const { return mode_.c_str(); }",
      r'''    const char* mode() const { return mode_.c_str(); }
    void reportUsage3() const {
        // Same cohort in every solve: first 100 conflict-learned clauses.
        // Only fully exposed clauses enter each 100-/500-conflict denominator.
        int64_t born[3]={},exposed100[3]={},exposed500[3]={};
        int64_t used100[3]={},used500[3]={},bcp100[3]={},bcp500[3]={};
        int64_t analysis100[3]={},analysis500[3]={},deleted[3]={};
        int64_t length_sum[3]={},lbd_sum[3]={};
        for(const auto& q:quality_records_){
            const int bin=q.lbd<=2?0:(q.lbd<=6?1:2);
            ++born[bin];length_sum[bin]+=q.length;lbd_sum[bin]+=q.lbd;
            if(q.deleted_at>=0)++deleted[bin];
            const int64_t age=stats_.conflicts-q.birth_conflict;
            if(age>=100) {
                ++exposed100[bin];
                if(q.bcp100+q.analysis100>0)++used100[bin];
                bcp100[bin]+=q.bcp100;analysis100[bin]+=q.analysis100;
            }
            if(age>=500) {
                ++exposed500[bin];
                if(q.bcp500+q.analysis500>0)++used500[bin];
                bcp500[bin]+=q.bcp500;analysis500[bin]+=q.analysis500;
            }
        }
        std::cerr<<"CLAUSE_USAGE3 {\"final_conflicts\":"<<stats_.conflicts
                 <<",\"first100_learned\":"<<quality_records_.size()
                 <<",\"cumulative_window_definition\":\"post_birth_conflicts\"
                 <<"\",\"bins\":[";
        for(int i=0;i<3;++i){
            if(i)std::cerr<<",";
            std::cerr<<"{\"label\":\""<<(i==0?"LBD<=2":i==1?"LBD3-6":"LBD>=7")
                     <<"\",\"born\":"<<born[i]
                     <<",\"lbd_sum\":"<<lbd_sum[i]
                     <<",\"length_sum\":"<<length_sum[i]
                     <<",\"deleted_eventually\":"<<deleted[i]
                     <<",\"eligible100\":"<<exposed100[i]
                     <<",\"used100_distinct\":"<<used100[i]
                     <<",\"bcp100_events\":"<<bcp100[i]
                     <<",\"analysis100_events\":"<<analysis100[i]
                     <<",\"eligible500\":"<<exposed500[i]
                     <<",\"used500_distinct\":"<<used500[i]
                     <<",\"bcp500_events\":"<<bcp500[i]
                     <<",\"analysis500_events\":"<<analysis500[i]<<"}";
        }
        std::cerr<<"]}\n";
    }''')
    s=once(s,
      "    std::vector<Clause> clauses_;",
      """    struct QualityRecord {
        int64_t birth_conflict=0,deleted_at=-1;
        int lbd=0,length=0;
        int64_t bcp100=0,analysis100=0,bcp500=0,analysis500=0;
    };
    std::vector<QualityRecord> quality_records_;
    void qualityUse(int id,bool analysis) {
        if(x46_clone_ || id<0 || static_cast<size_t>(id)>=quality_records_.size())
            return;
        QualityRecord& q=quality_records_[static_cast<size_t>(id)];
        const int64_t delta=stats_.conflicts-q.birth_conflict;
        if(delta<=0 || delta>500)return;
        if(analysis) {
            ++q.analysis500;
            if(delta<=100)++q.analysis100;
        }else{
            ++q.bcp500;
            if(delta<=100)++q.bcp100;
        }
    }
    std::vector<Clause> clauses_;""")
    s=once(s,
      "                clauses_[cid].glue=glue;\n                clauses_[cid].last_used=stats_.conflicts;",
      """                clauses_[cid].glue=glue;
                clauses_[cid].last_used=stats_.conflicts;
                if(!x46_clone_ && stats_.conflicts<=100) {
                    const int id=static_cast<int>(quality_records_.size());
                    quality_records_.push_back(
                        QualityRecord{stats_.conflicts,-1,glue,
                            static_cast<int>(clauses_[cid].lits.size()),0,0,0,0});
                    clauses_[cid].quality_id=id;
                }""")
    s=once(s,
      "        reasons_[v] = reason;\n        if (x5_retain_",
      """        reasons_[v] = reason;
        if(!probing_ && reason>=0 && clauses_[reason].quality_id>=0)
            qualityUse(clauses_[reason].quality_id,false);
        if (x5_retain_""")
    s=once(s,
      "            Clause& c = clauses_[conflict];\n            c.activity +=",
      """            Clause& c = clauses_[conflict];
            if(!probing_ && c.quality_id>=0)qualityUse(c.quality_id,true);
            c.activity +=""")
    s=once(s,
      "                clauses_[candidates[k]].deleted=true;\n                ++stats_.reduce_removed;",
      """                clauses_[candidates[k]].deleted=true;
                const int quality_id=clauses_[candidates[k]].quality_id;
                if(quality_id>=0)
                    quality_records_[static_cast<size_t>(quality_id)].deleted_at=stats_.conflicts;
                ++stats_.reduce_removed;""")
    s=once(s,
      '        const Stats& s=solver->stats();\n        std::cerr<<"X5_STATS ',
      '        const Stats& s=solver->stats();\n        solver->reportUsage3();\n        std::cerr<<"X5_STATS ')
    SRC.parent.mkdir(parents=True,exist_ok=True)
    SRC.write_text(s)
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror",str(SRC),"-o",str(BIN)],cwd=R,check=True)
    print("CLAUSE_USAGE3_BUILD",json.dumps({
        "pinned_original":sha(BASE),"instrumented_source":sha(SRC),
        "binary":sha(BIN),"original_result_policy_unchanged":True,
        "first100_clause_cohort":True,"later_BCP_and_conflict_analysis_use":True,
        "exact_age100_age500_denominators":True,"no_main_edits":True},sort_keys=True),flush=True)

if __name__=="__main__":main()
