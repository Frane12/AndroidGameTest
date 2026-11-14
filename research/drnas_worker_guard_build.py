#!/usr/bin/env python3
"""Build a source-pinned, experiment-only X5 worker domain guard.

Uses the frozen original src/drnas_x5.cpp and edits only a generated clone.
The OFF arm is the exact same binary without the opt-in flag.
"""
import hashlib
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"src/drnas_x5.cpp"
TARGET=ROOT/"build/drnas_worker_guard_x5.cpp"
EXE=ROOT/"build/drnas-worker-domain"
EXPECTED="9768340a8bed3bac3e43f0fb29780c4d5165c50283f90eae141733a7b76106fc"

def once(source,old,new):
    n=source.count(old)
    if n!=1:raise RuntimeError(("SOURCE_ANCHOR_DRIFT",n,old[:130]))
    return source.replace(old,new,1)

def main():
    actual=hashlib.sha256(BASE.read_bytes()).hexdigest()
    assert actual==EXPECTED,("FROZEN_X5_SOURCE_SHA_CHANGED",actual)
    s=BASE.read_text()
    s=once(s,"namespace {\nusing Clock = std::chrono::steady_clock;",
      "#include <functional>\nnamespace {\nusing Clock = std::chrono::steady_clock;\n#include \"../research/drnas_worker_domain_guard.hpp\"")
    s=once(s,"    bool x5_minimize=true,x5_retain=false,x5_gc=true,x5_restarts=false;",
      "    bool x5_minimize=true,x5_retain=false,x5_gc=true,x5_restarts=false;\n"
      "    bool domain_guard=false;double domain_budget_ms=2.0;")
    s=once(s,'        else if (opt=="--x5-no-minimize") x5_minimize=false;',
      '        else if (opt=="--domain-guard") domain_guard=true;\n'
      '        else if (opt=="--domain-budget-ms" && i+1<argc) domain_budget_ms=std::stod(argv[++i]);\n'
      '        else if (opt=="--x5-no-minimize") x5_minimize=false;')
    s=once(s,'    if (!trace_file.empty() && mode!="trace") throw std::runtime_error("--transitions requires --mode trace");',
      '    if(!std::isfinite(domain_budget_ms) || domain_budget_ms<0 || domain_budget_ms>20)\n'
      '        throw std::runtime_error("invalid domain guard budget");\n'
      '    if (!trace_file.empty() && mode!="trace") throw std::runtime_error("--transitions requires --mode trace");')
    s=once(s,"    std::vector<int> clause;\n",
      "    std::vector<int> clause;\n"
      "    std::vector<std::vector<int>> domain_clauses;\n"
      "    bool domain_capture=false;\n")
    s=once(s,
      '            solver->configureX5(x5_minimize,x5_retain,x5_gc,x5_restarts,\n'
      '                                proof_path.empty()?nullptr:&proof);',
      '            solver->configureX5(x5_minimize,x5_retain,x5_gc,x5_restarts,\n'
      '                                proof_path.empty()?nullptr:&proof);\n'
      '            domain_capture=domain_guard && declared_vars<=2500 && declared_clauses<=100000;\n'
      '            if(domain_capture)domain_clauses.reserve(static_cast<size_t>(declared_clauses));')
    s=once(s,"                solver->addOriginal(std::move(clause));clause.clear();++seen_clauses;",
      "                if(domain_capture)domain_clauses.push_back(clause);\n"
      "                solver->addOriginal(std::move(clause));clause.clear();++seen_clauses;")
    s=once(s,"    solver->finishParsing();",
r'''    solver->finishParsing();
    if(domain_guard) {
        WorkerDomainAnswer answer;
        if(domain_capture)answer=tryWorkerDomainSAT(declared_vars,domain_clauses,domain_budget_ms);
        else answer.reason="size_gate";
        std::cerr<<"DOMAIN_GUARD {\"eligible\":"<<(answer.eligible?"true":"false")
                 <<",\"solved\":"<<(answer.solved?"true":"false")
                 <<",\"exhausted\":"<<(answer.exhausted?"true":"false")
                 <<",\"nodes\":"<<answer.nodes
                 <<",\"elapsed_ms\":"<<std::fixed<<std::setprecision(5)<<answer.elapsed_ms
                 <<",\"reason\":\""<<answer.reason<<"\"}"<<"\n";
        if(answer.solved) {
            std::cout<<"s SATISFIABLE\n";
            for(int v=1;v<=declared_vars;++v) {
                if((v-1)%20==0)std::cout<<"v ";
                std::cout<<(answer.model[static_cast<size_t>(v)]>0?v:-v)<<" ";
                if(v%20==0)std::cout<<"0\n";
            }
            if(declared_vars%20)std::cout<<"0\n";
            return static_cast<int>(Result::SAT);
        }
    }''')
    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(s)
    cmd=["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
         "-Wpedantic","-Werror",str(TARGET),"-o",str(EXE)]
    subprocess.run(cmd,cwd=ROOT,check=True)
    print("DOMAIN_BUILD_PASS",hashlib.sha256(EXE.read_bytes()).hexdigest(),
          "frozen_sha",actual,flush=True)

if __name__=="__main__":main()
