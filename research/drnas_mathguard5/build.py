#!/usr/bin/env python3
"""MATH-GUARD5: source-only extension of frozen MG4 with ranked clauses.

All modes use ONE derived binary and ONE logical CPU per solver; main is untouched.
The score is declared before the benchmark: balanced original binary-degree
and total-occurrence support. This is a proxy, not a proof of usefulness.
Modes: 0=OFF, 1=SHADOW, 2=MG4_ALL, 3=MG4_SELECTIVE,
       4=MG5_TOP8, 5=MG5_BOTTOM8 negative control.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"build"
MG4=ROOT/"research/drnas_mathguard_delta4x/build.py"

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def once(s,old,new):
    n=s.count(old)
    if n!=1:raise RuntimeError(("MG5_SOURCE_DRIFT",n,old[:140]))
    return s.replace(old,new,1)

def main():
    subprocess.run([sys.executable,str(MG4)],cwd=ROOT,check=True)
    ref=B/"drnas_delta4x_mathguard.cpp"
    pinned=B/"drnas-delta4x-mathguard"
    before=digest(pinned)
    s=ref.read_text()
    s=once(s,"if(mode<0 || mode>3 ||","if(mode<0 || mode>5 ||")
    s=once(s,"    bool mg_budget_hit=false;",
        """    int64_t mg5_selected=0,mg5_score_sum=0;
    int64_t mg5_analysis_uses=0;
    bool mg_budget_hit=false;""")
    old='''        stats_.mg_candidates=static_cast<int64_t>(found.size());
        bool inject=mg_mode_==2 || (mg_mode_==3 && found.size()>=3);
        if(mg_mode_==3 && !inject)++stats_.mg_gate_skips;
        if(inject) {
            for(const auto& c:found) {'''
    new='''        stats_.mg_candidates=static_cast<int64_t>(found.size());
        // Score is independent of SAT/UNSAT labels and current search rewards.
        // A clause connecting two well-supported variables is ranked higher.
        // Negative-control arm deliberately ranks the SAME candidates low first.
        const auto score=[&](const ResultClause& c)->int64_t {
            const int v=std::abs(c.resolvent[0])-1;
            const int w=std::abs(c.resolvent[1])-1;
            const int64_t binary_support=std::min<int64_t>(binary_[v],binary_[w]);
            const int64_t occ_v=static_cast<int64_t>(positive_[v])+negative_[v];
            const int64_t occ_w=static_cast<int64_t>(positive_[w])+negative_[w];
            return 16*binary_support+std::min(occ_v,occ_w);
        };
        const bool ranked=(mg_mode_==4 || mg_mode_==5);
        if(ranked) {
            std::sort(found.begin(),found.end(),[&](const ResultClause& a,const ResultClause& b) {
                const auto sa=score(a),sb=score(b);
                if(sa!=sb)return mg_mode_==4?sa>sb:sa<sb;
                return a.resolvent<b.resolvent; // fixed deterministic tie-breaker
            });
        }
        bool inject=mg_mode_==2 || (mg_mode_==3 && found.size()>=3) || ranked;
        if(mg_mode_==3 && !inject)++stats_.mg_gate_skips;
        if(inject) {
            for(const auto& c:found) {
                if(ranked && stats_.mg5_selected>=8)break;'''
    s=once(s,old,new)
    s=once(s,
          '''                ++stats_.mg_installed;
                ++stats_.learnt;''',
          '''                ++stats_.mg_installed;
                ++stats_.learnt;
                if(ranked) {
                    ++stats_.mg5_selected;
                    stats_.mg5_score_sum+=score(c);
                }''')
    s=once(s,"            Clause& c = clauses_[conflict];",
        '''            if(conflict>=0 && !mg_clause_ids_.empty() &&
               mg_clause_ids_.count(conflict)!=0 && !probing_ && !x46_clone_)
                ++stats_.mg5_analysis_uses;
            Clause& c = clauses_[conflict];''')
    s=once(s,'        std::cerr<<"MATH_GUARD4_STATS {',
        r'''        std::cerr<<"MATH_GUARD5_STATS {\"mode\":"<<s.mg_mode
                 <<",\"selected\":"<<s.mg5_selected
                 <<",\"score_sum\":"<<s.mg5_score_sum
                 <<",\"conflict_analysis_uses\":"<<s.mg5_analysis_uses
                 <<"}\n";
        std::cerr<<"MATH_GUARD4_STATS {''')
    target=B/"drnas_delta4x_mathguard5.cpp"
    target.write_text(s)
    out=B/"drnas-delta4x-mathguard5"
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Wpedantic","-Werror",
                    "-O3","-DNDEBUG","-DCOOP5_DYNAMIC_DEFAULT=0",
                    "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                    str(target),"-o",str(out)],cwd=ROOT,check=True)
    if before!=digest(pinned):raise RuntimeError("FROZEN_MG4_BINARY_CHANGED")
    report=dict(
        source_sha256=digest(target),binary_sha256=digest(out),
        mg4_reference_sha256=before,
        delta4x_reference_sha256=digest(B/"drnas-delta4x"),
        one_logical_cpu=True,one_process=True,main_untouched=True,
        score="16*min(original_binary_occurrence_endpoints)+min(original_total_occurrence_endpoints)",
        candidate_pool=32,ranked_max_lemmas=8,
        policy_tuned_on_outcomes=False,ranked_is_proxy_not_proven_utility=True)
    (B/"MATH_GUARD5_BUILD.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MG5_BUILD "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
