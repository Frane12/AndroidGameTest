#!/usr/bin/env python3
"""Generate experimental solver; frozen src/drnas_x5.cpp is never modified."""
import hashlib,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[2]
src=ROOT/'src/drnas_x5.cpp'
s=src.read_text()
# Git blob identity of the frozen source in the parent commit.
blob=hashlib.sha1(b'blob '+str(len(src.read_bytes())).encode()+b'\0'+src.read_bytes()).hexdigest()
assert blob=='08ef5b13c0ab8c64bd93a4af3606cdc7d0b8e132',blob

def replace(a,b):
 global s
 assert s.count(a)==1,(a[:60],s.count(a))
 s=s.replace(a,b)
replace('namespace {\nusing Clock', '#include "../research/drnas_coop3/coop.hpp"\n\nnamespace {\nusing Clock')
replace('    void configureX5(','''    drnas_coop3::Engine coop_;
    int coop_hint_=-1;
    void configureCoop(const std::string& mode,bool eager) {
        coop_.mode=mode;
        coop_.delayed=!eager;
        // Avoid copying any original clauses for disabled high-dimensional cases.
        if(n_>4096)coop_.disabled=true;
    }
    void initializeCoop() { coop_.initialize(n_); }
    void reportCoop() const { coop_.report(); }
    Prop cooperate() {
        coop_hint_=-1;
        if(!coop_.enabled() || x46_clone_)return Prop{};
        auto out=coop_.step(values_,stats_.decisions,stats_.conflicts,
            [&](const std::vector<int>& c){writeProofClause(c);});
        coop_hint_=out.hint;
        for(auto& c:out.clauses){
            std::stable_sort(c.begin(),c.end(),[&](int a,int b){
                if((value(a)==0)!=(value(b)==0))return value(a)==0;
                return levels_[std::abs(a)-1]>levels_[std::abs(b)-1];
            });
            int free=0,unit=0,maxlevel=0;bool sat=false;
            for(int l:c){if(value(l)==0){++free;unit=l;}
                if(value(l)==1)sat=true;
                maxlevel=std::max(maxlevel,levels_[std::abs(l)-1]);}
            int cid=storeClause(std::move(c),true);++stats_.learnt;
            clauses_[cid].glue=computeGlue(clauses_[cid].lits);
            if(sat)continue;
            if(free==0){
                cancelUntil(maxlevel);++coop_.conflicts;
                return Prop{PropResult::CONFLICT,cid,0};
            }
            if(free==1){
                // Assert at the highest antecedent level; root units survive restarts.
                if(maxlevel<decisionLevel()){cancelUntil(maxlevel);coop_hint_=-1;}
                if(!enqueue(unit,cid))throw std::runtime_error("COOP3 unit enqueue failed");
                ++coop_.propagations;
            }
        }
        return propagate(-1);
    }
    void configureX5(''')
replace('        const int cid = storeClause(std::move(clean), false);','        coop_.add(clean);\n        const int cid = storeClause(std::move(clean), false);')
replace('''            p = propagate(-1);
            if (p.result == PropResult::TIMEOUT)''','''            p = propagate(-1);
            if (p.result == PropResult::OK) p=cooperate();
            if (p.result == PropResult::TIMEOUT)''')
replace('''            int v = selectVariable();
            if (v == -1)''','''            int v = selectVariable();
            if(coop_.mode=="on" && coop_hint_>=0 && values_[coop_hint_]==0 && v>=0) {
                if(v!=coop_hint_){offer(v);v=coop_hint_;++coop_.applied_hints;}
            }
            if (v == -1)''')
replace('    std::string input, mode="trace", trace_file;', '    std::string input, mode="trace", trace_file,coop_mode="off";\n    bool coop_eager=false;')
replace('        else if (opt=="--x5-no-minimize")', '        else if (opt=="--coop3" && i+1<argc) coop_mode=argv[++i];\n        else if (opt=="--coop3-eager") coop_eager=true;\n        else if (opt=="--x5-no-minimize")')
replace('    if (input.empty() || (mode!=', '    if(coop_mode!="off"&&coop_mode!="observe"&&coop_mode!="algebra"&&coop_mode!="on"&&coop_mode!="gate")throw std::runtime_error("invalid COOP3 mode");\n    if (input.empty() || (mode!=')
replace('            solver->configureX5(', '            solver->configureCoop(coop_mode,coop_eager);\n            solver->configureX5(')
replace('    solver->finishParsing();', '    solver->finishParsing();\n    solver->initializeCoop();')
replace('    const Result r=solver->solve();', '    const Result r=solver->solve();\n    if(show_stats)solver->reportCoop();')
build=ROOT/'build';build.mkdir(exist_ok=True)
(build/'drnas_coop3.cpp').write_text(s)
subprocess.run(['g++','-std=c++20','-O3','-DNDEBUG','-Wall','-Wextra','-Wpedantic','-Werror',str(build/'drnas_coop3.cpp'),'-o',str(build/'drnas-coop3')],check=True)
print('COOP3_BUILD',hashlib.sha256((build/'drnas-coop3').read_bytes()).hexdigest())
