#!/usr/bin/env python3
"""REX2 experimental native branch selector; patch generated LTM8 engine only."""
from pathlib import Path
root=Path("mre_atlas23")
h=root/"drnas_native_core_c.hpp";s=h.read_text()
anchor="    int ltm8_pick(){"
assert s.count(anchor)==1
s=s.replace(anchor,'''    bool rex2_enabled_=false;
    std::vector<int> rex2_degree_;
    uint64_t rex2_choices_=0,rex2_overrides_=0;
    int rex2_pick(){
        // No speculative propagation: bounded candidate ranking in the live CDCL heap.
        if(heap_.empty())return 0;
        const int base=pick_branch_variable();
        if(!base)return base;
        ++rex2_choices_;
        // Every eighth decision only; no change to propagation, clauses or proofs.
        if((rex2_choices_&7u)!=0 || rex2_degree_.empty())return base;
        int chosen=base;int best=rex2_degree_[size_t(base)];
        const size_t limit=std::min(size_t(24),heap_.size());
        for(size_t i=0;i<limit;++i){
            const int v=heap_[i];
            if(v<=0 || size_t(v)>=rex2_degree_.size())continue;
            if(rex2_degree_[size_t(v)]>best){
                best=rex2_degree_[size_t(v)];chosen=v;
            }
        }
        if(chosen!=base)++rex2_overrides_;
        return chosen;
    }
    void rex2_enable(const CNF& src){
        rex2_enabled_=true;
        rex2_degree_.assign(size_t(n_)+1,0);
        for(const auto& clause:src.clauses){
            if(clause.size()>12)continue;
            for(int lit:clause){
                const size_t v=size_t(lit<0?-int64_t(lit):int64_t(lit));
                if(v<rex2_degree_.size())rex2_degree_[v]+=int(clause.size())-1;
            }
        }
    }
    void rex2_report()const{
        if(rex2_enabled_)std::cout<<"REX2_STATS choices="<<rex2_choices_
            <<" overrides="<<rex2_overrides_<<"\\n";
    }
    int ltm8_pick(){''',1)
# Existing LTM8 pick is the only selection point; REX2 uses the same sound CDCL core.
needle='const int v = ltm8_.enabled ? ltm8_pick() : atlas13_c_enabled_ ? atlas13_pick_branch_variable() : pick_branch_variable();'
assert s.count(needle)==1
s=s.replace(needle,'const int v = rex2_enabled_ ? rex2_pick() : ltm8_.enabled ? ltm8_pick() : atlas13_c_enabled_ ? atlas13_pick_branch_variable() : pick_branch_variable();')
h.write_text(s)
p=root/"native.cpp";s=p.read_text()
needle='   solver.add_cnf(work);'
assert s.count(needle)==1
s=s.replace(needle,'''   if(mode=="REX2_GRAPH")solver.rex2_enable(orig);
'''+needle)
needle='  solver.ltm8_finish();'
assert s.count(needle)==1
s=s.replace(needle,needle+'\n  solver.rex2_report();')
# Existing native mode validation must explicitly permit REX2.
needle='mode=="LTM8_CHAOS"'
assert s.count(needle)>=3
# Extend all mode whitelists, but do not alter Gaussian eligibility or LTM8 initialization.
s=s.replace('(mode=="LTM8_KEEP50"||mode=="LTM8_FAST"||mode=="LTM8_CHAOS")','(mode=="LTM8_KEEP50"||mode=="LTM8_FAST"||mode=="LTM8_CHAOS"||mode=="REX2_GRAPH")')
p.write_text(s)
print("REX2_NATIVE_PATCH_PASS graph_decisions=true every_8th=true max_candidates=24",flush=True)
