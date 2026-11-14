#!/usr/bin/env python3
"""PRE-GUARD13: read-only root-state measurements, no solver decision changes."""
import hashlib, json, pathlib, subprocess
R=pathlib.Path(__file__).resolve().parents[1]
SOURCE=R/"build/drnas_clause_cf6.cpp"
OUT=R/"build/drnas-preguard-shadow13"
def main():
    s=SOURCE.read_text()
    needle='''        while (true) {
            if (timedOut() || x46CloneBudgetReached()) return Result::UNKNOWN;'''
    replacement='''        // PRE-GUARD shadow: read-only, after root propagation, before 1st decision.
        if (!x46_clone_) {
            int64_t assigned=0, unassigned_active=0;
            for(int v=0;v<n_;++v) {
                if(values_[v])++assigned;
                else if(positive_[v] || negative_[v])++unassigned_active;
            }
            int64_t satisfied=0, residual=0, root_binary=0,root_unit=0;
            for(int cid=0;cid<original_count_;++cid) {
                const Clause& c=clauses_[static_cast<size_t>(cid)];
                if(c.deleted)continue;
                bool sat=false;int open=0;
                for(int lit:c.lits) {
                    int z=value(lit);
                    if(z==1) {sat=true;break;}
                    if(z==0)++open;
                }
                if(sat)++satisfied;
                else {++residual;if(open==1)++root_unit;if(open==2)++root_binary;}
            }
            std::cerr<<"PREGUARD_ROOT {\\\"declared_vars\\\":"<<n_
                <<",\\\"original_clauses\\\":"<<original_count_
                <<",\\\"assigned\\\":"<<assigned
                <<",\\\"unassigned_active\\\":"<<unassigned_active
                <<",\\\"satisfied_originals\\\":"<<satisfied
                <<",\\\"residual_originals\\\":"<<residual
                <<",\\\"residual_unit\\\":"<<root_unit
                <<",\\\"residual_binary\\\":"<<root_binary
                <<",\\\"decisions\\\":"<<stats_.decisions
                <<",\\\"conflicts\\\":"<<stats_.conflicts<<"}"<<std::endl;
        }
''' + needle
    if s.count(needle)!=1:raise RuntimeError(("SOURCE_ANCHOR_DRIFT",s.count(needle)))
    # C++ escaped newline, not literal backslash-n
    # C++ std::endl ensures one valid JSON object per line.
    s=s.replace(needle,replacement)
    target=R/"build/drnas_preguard_shadow13.cpp"
    target.write_text(s)
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra","-Wpedantic","-Werror",str(target),"-o",str(OUT)],check=True)
    print("PREGUARD_BUILD "+json.dumps({"original_sha":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),"shadow_sha":hashlib.sha256(OUT.read_bytes()).hexdigest(),"source_patch":"one read-only root report, no decision change"}),flush=True)
if __name__=="__main__":main()
