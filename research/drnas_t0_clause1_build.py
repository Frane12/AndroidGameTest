#!/usr/bin/env python3
"""Generate an isolated observation-only X5 learned-clause telemetry executable.

Pinned exact X5 source. No changes to activity, clause deletion, literals,
decision order, proof or watches; instrumentation tags first 16 learned
clauses to measure their LATER use as a BCP / conflict-analysis reason.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"src/drnas_x5.cpp"
OUT=ROOT/"build/drnas_t0_clause1.cpp"
BIN=ROOT/"build/drnas-t0-clause1"
PIN="9768340a8bed3bac3e43f0fb29780c4d5165c50283f90eae141733a7b76106fc"

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(s,a,b):
    n=s.count(a)
    if n!=1:raise AssertionError(("SOURCE_DRIFT",n,a[:120]))
    return s.replace(a,b)

def main():
    assert sha(SRC)==PIN,("ORIGINAL_X5_SOURCE_CHANGED",sha(SRC))
    s=SRC.read_text()
    s=once(s,"    int64_t last_used = 0;",
      """    int64_t last_used = 0;
    // Diagnostics only: do not alter clause storage semantics.
    int64_t t0_birth_conflict=-1;
    bool t0_first16=false, t0_reused=false;""")
    s=once(s,"    int64_t trace_conflicts=0, trace_implied=0, trace_evicted=0;",
      """    int64_t trace_conflicts=0, trace_implied=0, trace_evicted=0;
    // Paired T0 diagnostics, observational, never consulted for decisions.
    int64_t t0_early8=0,t0_glue8=0,t0_len8=0,t0_lbd2_8=0,t0_jump8=0;
    int64_t t0_early16=0,t0_glue16=0,t0_len16=0,t0_lbd2_16=0,t0_jump16=0;
    int64_t t0_first_path_conflicts=0,t0_first_backtrack_conflicts=-1;
    int64_t t0_first_backtrack_decisions=-1,t0_early_reused_distinct=0;
    int64_t t0_early_reused_bcp=0,t0_early_reused_analysis=0;""")
    s=once(s,"    bool compare_reached_=false;",
      """    bool t0_initial_branch_live_=false;
    bool compare_reached_=false;""")
    s=once(s,"                const int glue=computeGlue(learned);",
      """                const int glue=computeGlue(learned);
                if (!x46_clone_ && stats_.decisions>0 && stats_.conflicts<=16) {
                    ++stats_.t0_early16;
                    stats_.t0_glue16+=glue;
                    stats_.t0_len16+=static_cast<int64_t>(learned.size());
                    stats_.t0_lbd2_16+=(glue<=2);
                    stats_.t0_jump16+=decisionLevel()-level;
                    if(stats_.conflicts<=8) {
                        ++stats_.t0_early8;
                        stats_.t0_glue8+=glue;
                        stats_.t0_len8+=static_cast<int64_t>(learned.size());
                        stats_.t0_lbd2_8+=(glue<=2);
                        stats_.t0_jump8+=decisionLevel()-level;
                    }
                }
                if(!x46_clone_ && t0_initial_branch_live_)
                    ++stats_.t0_first_path_conflicts;""")
    s=once(s,"                clauses_[cid].glue=glue;\n                clauses_[cid].last_used=stats_.conflicts;",
      """                clauses_[cid].glue=glue;
                clauses_[cid].last_used=stats_.conflicts;
                if(!x46_clone_ && stats_.decisions>0 && stats_.conflicts<=16) {
                    clauses_[cid].t0_first16=true;
                    clauses_[cid].t0_birth_conflict=stats_.conflicts;
                }""")
    s=once(s,"            Clause& c = clauses_[conflict];\n            c.activity +=",
      """            Clause& c = clauses_[conflict];
            if(!x46_clone_ && c.t0_first16 &&
               c.t0_birth_conflict < stats_.conflicts) {
                ++stats_.t0_early_reused_analysis;
                if(!c.t0_reused) {
                    c.t0_reused=true;
                    ++stats_.t0_early_reused_distinct;
                }
            }
            c.activity +=""")
    s=once(s,"        if (x5_retain_ && reason>=0 && clauses_[reason].learnt)",
      """        if(!x46_clone_ && reason>=0 &&
           clauses_[reason].t0_first16 &&
           clauses_[reason].t0_birth_conflict<stats_.conflicts) {
            ++stats_.t0_early_reused_bcp;
            if(!clauses_[reason].t0_reused) {
                clauses_[reason].t0_reused=true;
                ++stats_.t0_early_reused_distinct;
            }
        }
        if (x5_retain_ && reason>=0 && clauses_[reason].learnt)""")
    s=once(s,"            ++stats_.decisions;\n            beginTransition(chosen_lit);",
      """            ++stats_.decisions;
            if(!x46_clone_ && stats_.decisions==1) t0_initial_branch_live_=true;
            beginTransition(chosen_lit);""")
    s=once(s,"    void cancelUntil(int target) {\n        if (decisionLevel() <= target) return;",
      """    void cancelUntil(int target) {
        if (decisionLevel() <= target) return;
        if(!x46_clone_ && target==0 && t0_initial_branch_live_) {
            t0_initial_branch_live_=false;
            stats_.t0_first_backtrack_conflicts=stats_.conflicts;
            stats_.t0_first_backtrack_decisions=stats_.decisions;
        }""")
    s=once(s,"        const Stats& s=solver->stats();",
      """        const Stats& s=solver->stats();
        std::cerr<<"T0_CLAUSE_STATS {\\\"early8\\\":"<<s.t0_early8
            <<",\\\"glue_sum8\\\":"<<s.t0_glue8
            <<",\\\"length_sum8\\\":"<<s.t0_len8
            <<",\\\"lbd2_8\\\":"<<s.t0_lbd2_8
            <<",\\\"backjump_sum8\\\":"<<s.t0_jump8
            <<",\\\"early16\\\":"<<s.t0_early16
            <<",\\\"glue_sum16\\\":"<<s.t0_glue16
            <<",\\\"length_sum16\\\":"<<s.t0_len16
            <<",\\\"lbd2_16\\\":"<<s.t0_lbd2_16
            <<",\\\"backjump_sum16\\\":"<<s.t0_jump16
            <<",\\\"first_branch_alive_conflicts\\\":"<<s.t0_first_path_conflicts
            <<",\\\"first_backtrack_conflicts\\\":"<<s.t0_first_backtrack_conflicts
            <<",\\\"first_backtrack_decisions\\\":"<<s.t0_first_backtrack_decisions
            <<",\\\"early16_distinct_reused\\\":"<<s.t0_early_reused_distinct
            <<",\\\"early16_reuse_bcp\\\":"<<s.t0_early_reused_bcp
            <<",\\\"early16_reuse_analysis\\\":"<<s.t0_early_reused_analysis
            <<"}\\n";""")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(s)
    cmd=["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra","-Wpedantic","-Werror",str(OUT),"-o",str(BIN)]
    subprocess.run(cmd,cwd=ROOT,check=True)
    result={"original_sha256":sha(SRC),"instrumented_source_sha256":sha(OUT),
            "instrumented_binary_sha256":sha(BIN),
            "no_solver_policy_changes":True,"not_promoted":True}
    print("T0_CLAUSE_BUILD",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":main()
