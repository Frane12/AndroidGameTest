#!/usr/bin/env python3
"""Apply after LTM8_KEEP50; changes only the generated experimental engine."""
from pathlib import Path
import shutil
root=Path('mre_atlas23')
for name in ('policy','members'):
    shutil.copyfile(f'research/drnas_ltm8_{name}.hpp',root/f'ltm8_{name}.hpp')
h=root/'drnas_native_core_c.hpp'
s=h.read_text()
def one(a,b):
    global s
    if s.count(a)!=1: raise RuntimeError(f'LTM8 patch drift: {a[:100]!r}: {s.count(a)}')
    s=s.replace(a,b,1)
one('namespace drnas {','#include "ltm8_policy.hpp"\nnamespace drnas {')
# Avoid constructing temporary strings for successful hot-path checks.
one('static void require(bool ok, const std::string& message)', 'static void require(bool ok, const char* message)')
one('    int atlas15_compute_lbd(const std::vector<int>&cl) const {', '''    #include "ltm8_members.hpp"
    int atlas15_compute_lbd(const std::vector<int>&cl) const {
        if(ltm8_.enabled){
            if(++ltm8_stamp_==0){std::fill(ltm8_levels_.begin(),ltm8_levels_.end(),0);++ltm8_stamp_;}
            int count=0;
            for(int lit:cl){int lev=levels_[var(lit)];
                if(lev>0 && ltm8_levels_[lev]!=ltm8_stamp_){ltm8_levels_[lev]=ltm8_stamp_;++count;}}
            return std::max(1,count);
        }''')
one('        std::vector<uint8_t> seen(n_ + 1, 0);', '        std::vector<uint8_t> local_seen;\n        if(!ltm8_.enabled)local_seen.assign(size_t(n_)+1,0);\n        auto& seen=ltm8_.enabled?ltm8_seen_:local_seen;')
one('        return {std::move(learned), backtrack_level};', '        // Resolved trail variables were cleared during analysis; only the\n        // final learned variables can remain marked. No O(n) zeroing per conflict.\n        if(ltm8_.enabled)for(int lit:learned)seen[var(lit)]=0;\n        return {std::move(learned), backtrack_level};')
one('    bool atlas15_restart_due()const{','''    bool atlas15_restart_due()const{
        if(ltm8_.enabled){
            const auto age=stats_.conflicts-atlas15_last_restart_;
            return age>=uint64_t(ltm8_.restart_min) &&
                (atlas15_short_lbd_>atlas15_long_lbd_*ltm8_.restart_factor || age>=uint64_t(ltm8_.restart_max));
        }''')
one('                bump_ /= decay_;','''                if(ltm8_.enabled && ltm8_.observe(atlas15_last_lbd_,stats_.watch_visits+stats_.propagations+stats_.decisions))ltm8_apply();
                bump_ /= decay_;''')
one('const int v = atlas13_c_enabled_ ? atlas13_pick_branch_variable() : pick_branch_variable();','const int v = ltm8_.enabled ? ltm8_pick() : atlas13_c_enabled_ ? atlas13_pick_branch_variable() : pick_branch_variable();')
one('                decision_marks_.push_back(trail_.size());','''                decision_marks_.push_back(trail_.size());
                if(ltm8_.enabled && ltm8_.flip_permil && ltm8_.next()%1000<unsigned(ltm8_.flip_permil))phases_[v]=-phases_[v];''')
# Correct C7's live learned count; deleted slots must not count toward resource cap.
one('            atlas15_lbd_.erase(cid);\n            ++atlas15_deleted_;','''            atlas15_lbd_.erase(cid);
            atlas15_born_.erase(cid);
            --atlas15_live_learned_;
            ++atlas15_deleted_;''')
header=s
p=root/'native.cpp';s=p.read_text()
s=s.replace('mode=="LTM8_KEEP50"','(mode=="LTM8_KEEP50"||mode=="LTM8_FAST"||mode=="LTM8_CHAOS")')
one('  const bool use_gauss=', '  const bool use_gauss=((mode=="LTM8_FAST"||mode=="LTM8_CHAOS") && orig.vars<=2000 && orig.clauses.size()<=12000)||')
one('   solver.add_cnf(work);','''   if(mode=="LTM8_FAST"||mode=="LTM8_CHAOS")solver.ltm8_enable(mode=="LTM8_CHAOS",trial_seed,orig);
   solver.add_cnf(work);''')
one('  const auto e2e=', '  solver.ltm8_finish();\n  const auto e2e=')
h.write_text(header);p.write_text(s)
print('LTM8_ADAPTIVE_PATCH_PASS fast=true chaos=true persistent_policy=true')
