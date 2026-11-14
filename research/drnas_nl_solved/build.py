#!/usr/bin/env python3
"""Same-binary ablations on previously solved nonlinear original CNFs."""
from pathlib import Path
import hashlib,subprocess
R=Path(__file__).resolve().parents[2]
B=R/'build'
s=(B/'drnas_delta4x.cpp').read_text()
assert hashlib.sha256(s.encode()).hexdigest()=='ebd7801e816d4086fdfdc55773eab185f138aef0dc9d52219078145f52e41996', 'PINNED_DELTA4X_SOURCE_DRIFT'
def replace(a,b):
    global s
    assert s.count(a)==1,(a[:100],s.count(a))
    s=s.replace(a,b)
replace('#include "delta4x_engine.hpp"','#include "delta4x_engine.hpp"\n#include <unordered_set>')
extra=r'''
    bool nl_inplace_=false,nl_inputs_=false;
    int64_t nl_gates_=0;
    double nl_scan_ms_=0;
    void configureNL(const std::string& m,int count) {
        if(m!="base"&&m!="inplace"&&m!="inputs"&&m!="both")
            throw std::runtime_error("invalid nonlinear focus mode");
        nl_inplace_=(m=="inplace"||m=="both");
        nl_inputs_=(m=="inputs"||m=="both");
        if(nl_inplace_)clauses_.reserve(static_cast<size_t>(std::min(count,1000000)));
    }
    static uint64_t nlBinaryKey(int a,int b) {
        if(a>b)std::swap(a,b);
        return (static_cast<uint64_t>(static_cast<uint32_t>(a))<<32)|static_cast<uint32_t>(b);
    }
    void nonlinearInputPrior() {
        if(!nl_inputs_)return;
        const auto start=Clock::now();
        std::unordered_set<uint64_t> bins;
        bins.reserve(clauses_.size()/3+1);
        for(const auto& c:clauses_)if(!c.learnt&&c.lits.size()==2)
            bins.insert(nlBinaryKey(c.lits[0],c.lits[1]));
        std::vector<int> inputs(static_cast<size_t>(n_),0),outputs(static_cast<size_t>(n_),0);
        for(const auto& c:clauses_)if(!c.learnt&&c.lits.size()==3){
            for(size_t i=0;i<3;++i){
                const int z=c.lits[i],a=-c.lits[(i+1)%3],b=-c.lits[(i+2)%3];
                if(!bins.count(nlBinaryKey(-z,a))||!bins.count(nlBinaryKey(-z,b)))continue;
                ++nl_gates_;++inputs[static_cast<size_t>(std::abs(a)-1)];
                ++inputs[static_cast<size_t>(std::abs(b)-1)];++outputs[static_cast<size_t>(std::abs(z)-1)];
            }
        }
        // A heuristic only. Exact signed AND definitions are recognized from
        // three original clauses. No substitution, forced value or new clause.
        for(int v=0;v<n_;++v)if(inputs[static_cast<size_t>(v)]) {
            base_[v]+=0.25*inputs[static_cast<size_t>(v)]/(1.0+outputs[static_cast<size_t>(v)]);
            offer(v);
        }
        nl_scan_ms_=std::chrono::duration<double,std::milli>(Clock::now()-start).count();
    }
'''
replace('    drnas_coop4::Delta4XEngine coop_;','    drnas_coop4::Delta4XEngine coop_;\n'+extra)
old='''        std::vector<int> clean;
        clean.reserve(lits.size());
        for (int lit : lits) {
            if (lit == 0 || std::abs(static_cast<int64_t>(lit)) > n_) {
                throw std::runtime_error("DIMACS literal outside declared variable range");
            }
            if (!clean.empty() && clean.back() == lit) continue;
            if (!clean.empty() && clean.back() == -lit) { --original_count_; return; } // tautology
            clean.push_back(lit);
        }'''
new='''        std::vector<int> clean;
        if(nl_inplace_) {
            size_t kept=0;
            for(size_t i=0;i<lits.size();++i) {
                const int lit=lits[i];
                if(lit==0||std::abs(static_cast<int64_t>(lit))>n_)
                    throw std::runtime_error("DIMACS literal outside declared variable range");
                if(kept&&lits[kept-1]==lit)continue;
                if(kept&&lits[kept-1]==-lit){--original_count_;return;}
                lits[kept++]=lit;
            }
            lits.resize(kept);clean=std::move(lits);
        } else {
''' + old.replace('        std::vector<int> clean;\n','')+'''
        }'''
replace(old,new)
replace('    std::vector<int> clause;\n    // Buffered getline',
        '    std::vector<int> clause;\n    if(nl_mode=="inplace"||nl_mode=="both")clause.reserve(4);\n    // Buffered getline')
replace('                solver->addOriginal(std::move(clause));clause.clear();++seen_clauses;',
        '                solver->addOriginal(std::move(clause));clause.clear();++seen_clauses;\n                if(nl_mode=="inplace"||nl_mode=="both")clause.reserve(4);')
replace('        for (int cid : units_) {','        nonlinearInputPrior();\n        for (int cid : units_) {')
replace('    std::string delta2_mode="local";','    std::string nl_mode="base";\n    std::string delta2_mode="local";')
replace('        else if (opt=="--delta2" && i+1<argc)',
        '        else if (opt=="--nl-focus" && i+1<argc) nl_mode=argv[++i];\n        else if (opt=="--delta2" && i+1<argc)')
replace('            solver->configureDelta2(delta2_mode);',
        '            solver->configureNL(nl_mode,declared_clauses);\n            solver->configureDelta2(delta2_mode);')
replace('    const Result r=solver->solve();','    const double nl_parse_s=solver->elapsed();\n    const Result r=solver->solve();')
replace('    const double solve_finish_elapsed=solver->elapsed();',r'''    const double solve_finish_elapsed=solver->elapsed();
    if(show_stats)std::cerr<<"NL_FOCUS {\"mode\":\""<<nl_mode<<"\",\"parse_s\":"<<nl_parse_s
        <<",\"search_s\":"<<(solve_finish_elapsed-nl_parse_s)<<",\"gates\":"<<solver->nl_gates_
        <<",\"gate_scan_ms\":"<<solver->nl_scan_ms_<<"}\n";''')
p=B/'drnas_nl_solved.cpp';p.write_text(s)
flags=['-std=c++20','-O3','-DNDEBUG','-Wall','-Wextra','-Wpedantic','-Werror',
       '-DCOOP5_DYNAMIC_DEFAULT=0','-DCOOP52_FALLBACK_DEFAULT=0','-DCOOP53_REPAIR=1']
subprocess.run(['g++',*flags,str(p),'-o',str(B/'drnas-nl-solved')],check=True)
print('NL_SOLVED_BUILD_PASS')
