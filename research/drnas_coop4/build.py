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
replace('namespace {\nusing Clock', '#include "../research/drnas_coop4/coop.hpp"\n\nnamespace {\nusing Clock')
replace('    void configureX5(', (ROOT/'research/drnas_coop4/retention_methods.inc').read_text())
replace('    int64_t last_used = 0;', '    int64_t last_used = 0;\n    bool coop4_origin=false;\n    int64_t coop4_born=-1,coop4_last=-1;\n    uint16_t coop4_uses=0;')
replace('''        if (x5_retain_ && reason>=0 && clauses_[reason].learnt)
            clauses_[reason].last_used=stats_.conflicts;''','''        if (x5_retain_ && reason>=0 && clauses_[reason].learnt)
            clauses_[reason].last_used=stats_.conflicts;
        if(reason>=0)coop4RecordUse(reason,false);''')
replace('''            Clause& c = clauses_[conflict];
            c.activity += x5_retain_?clause_inc_:1.0;''','''            Clause& c = clauses_[conflict];
            coop4RecordUse(conflict,true);
            c.activity += x5_retain_?clause_inc_:1.0;''')
replace('''                if (stats_.conflicts >= next_reduce_) {''','''                coop4RetentionSweep();
                if (stats_.conflicts >= next_reduce_) {''')
replace('''        for(auto& edges:binary_implications_)for(auto& e:edges)e.second=remap[e.second];''','''        for(auto& edges:binary_implications_) {
            size_t j=0;
            for(auto e:edges)if(remap[static_cast<size_t>(e.second)]>=0) {
                e.second=remap[static_cast<size_t>(e.second)];
                edges[j++]=e;
            }
            edges.resize(j);
        }
        size_t saved=0;
        for(int cid:coop4_ids_)if(remap[static_cast<size_t>(cid)]>=0)
            coop4_ids_[saved++]=remap[static_cast<size_t>(cid)];
        coop4_ids_.resize(saved);''')
replace('''                ++stats_.binary_propagations;
                if (!enqueue(implied,reason))''','''                if(clauses_[static_cast<size_t>(reason)].deleted)continue;
                ++stats_.binary_propagations;
                if (!enqueue(implied,reason))''')
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
replace('    std::string input, mode="trace", trace_file;', '    std::string input, mode="trace", trace_file,coop_mode="off",coop4_policy="keep";\n    bool coop_eager=false;')
replace('        else if (opt=="--x5-no-minimize")', '        else if (opt=="--coop4" && i+1<argc) coop_mode=argv[++i];\n        else if (opt=="--coop4-eager") coop_eager=true;\n        else if (opt=="--coop4-policy" && i+1<argc) coop4_policy=argv[++i];\n        else if (opt=="--x5-no-minimize")')
replace('    if (input.empty() || (mode!=', '    if(coop_mode!="off"&&coop_mode!="observe"&&coop_mode!="algebra"&&coop_mode!="on"&&coop_mode!="gate"&&coop_mode!="retain")throw std::runtime_error("invalid COOP4 mode");\n    if (input.empty() || (mode!=')
replace('            solver->configureX5(', '            solver->configureCoop(coop_mode,coop_eager);\n            solver->configureCoop4Policy(coop4_policy);\n            solver->configureX5(')
replace('    solver->finishParsing();', '    solver->finishParsing();\n    solver->initializeCoop();')
replace('    const Result r=solver->solve();', '    const Result r=solver->solve();\n    if(show_stats)solver->reportCoop();')
build=ROOT/'build';build.mkdir(exist_ok=True)
(build/'drnas_coop4.cpp').write_text(s)
subprocess.run(['g++','-std=c++20','-O3','-DNDEBUG','-Wall','-Wextra','-Wpedantic','-Werror',str(build/'drnas_coop4.cpp'),'-o',str(build/'drnas-coop4')],check=True)
print('COOP4_BUILD',hashlib.sha256((build/'drnas-coop4').read_bytes()).hexdigest())
