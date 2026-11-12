#!/usr/bin/env python3
"""REX2: guarded native CDCL branching experiment on generated LTM8 engine.

LTM8 helpers are included from ltm8_members.hpp, NOT defined directly in the
generated core header. Only the REX2_GRAPH arm changes its branch selection.
"""
from pathlib import Path

root=Path("mre_atlas23")
members=root/"ltm8_members.hpp"
core=root/"drnas_native_core_c.hpp"
source=root/"native.cpp"
assert members.exists() and core.exists() and source.exists(), "Run LTM8 compile first"
m=members.read_text()
h=core.read_text()
s=source.read_text()

def replace_once(body, old, new, where):
    count=body.count(old)
    if count != 1:
        raise RuntimeError(f"REX2 patch drift in {where}: {old[:90]!r} count={count}")
    return body.replace(old,new,1)

# Private engine state and decision logic. The indexed heap contains only
# unassigned variables; enqueue() removes the chosen variable automatically.
m=replace_once(m,"    int ltm8_pick(){",'''    bool rex2_enabled_=false;
    std::vector<int> rex2_degree_;
    uint64_t rex2_choices_=0,rex2_overrides_=0;
    int rex2_pick(){
        if(heap_.empty())return 0;
        const int base=pick_branch_variable();
        if(!base)return base;
        ++rex2_choices_;
        // Bound overhead to one in eight live decisions, 24 indexed-heap vars.
        if((rex2_choices_&7u)!=0 || rex2_degree_.empty())return base;
        int chosen=base;
        int best=rex2_degree_[size_t(base)];
        const size_t limit=std::min(size_t(24),heap_.size());
        for(size_t i=0;i<limit;++i){
            const int v=heap_[i];
            if(v<=0 || size_t(v)>=rex2_degree_.size() || values_[v])continue;
            if(rex2_degree_[size_t(v)]>best){
                best=rex2_degree_[size_t(v)];
                chosen=v;
            }
        }
        if(chosen!=base)++rex2_overrides_;
        return chosen;
    }
    int ltm8_pick(){''',"ltm8_members")

# Public calls from native.cpp (the include contains a private/public split).
m=replace_once(m,"public:",'''public:
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
            <<" overrides="<<rex2_overrides_<<std::endl;
    }''',"ltm8_members_public")

h=replace_once(h,
    'const int v = ltm8_.enabled ? ltm8_pick() : atlas13_c_enabled_ ? atlas13_pick_branch_variable() : pick_branch_variable();',
    'const int v = rex2_enabled_ ? rex2_pick() : ltm8_.enabled ? ltm8_pick() : atlas13_c_enabled_ ? atlas13_pick_branch_variable() : pick_branch_variable();',
    "native_core_decision")

s=replace_once(s,'   solver.add_cnf(work);',
    '   if(mode=="REX2_GRAPH")solver.rex2_enable(orig);\n   solver.add_cnf(work);',"native_run_setup")
s=replace_once(s,'  solver.ltm8_finish();',
    '  solver.ltm8_finish();\n  solver.rex2_report();',"native_run_report")

# REX2 and LTM8_FAST must have exactly the same runtime configuration.
# Inherit FAST at *all* mode dispatch sites; only branching differs.
fast='mode=="LTM8_FAST"'
if s.count(fast)<4:raise RuntimeError(f"REX2 FAST dispatch drift: {s.count(fast)}")
s=s.replace(fast,'(mode=="LTM8_FAST"||mode=="REX2_GRAPH")')
# No file is changed unless ALL anchors above match.
members.write_text(m)
core.write_text(h)
source.write_text(s)
print("REX2_NATIVE_PATCH_PASS bounded_heap=true every_8th=true top24=true",flush=True)
