#!/usr/bin/env python3
"""Instrument the immutable CORE with proof output only, failing on source drift."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'src/drnas_x41.cpp';s=p.read_text()
expected='805c298e99ca4bbfe785f93347c541512c1893df6eea80a45ba0a74c6cf49993'
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,'frozen source drift'
s=s.replace('    void addOriginal(std::vector<int> lits) {', '''    void setProof(std::ostream* p) {proof_=p;}
    void writeProofClause(const std::vector<int>& lits) {
        if(!proof_ || x46_clone_)return;
        for(int lit:lits)*proof_<<lit<<' ';
        *proof_<<"0\\n";
        if(!*proof_)throw std::runtime_error("proof write failed");
    }
    void addOriginal(std::vector<int> lits) {''')
s=s.replace('    const int n_;','    std::ostream* proof_=nullptr;\n    const int n_;',1)
s=s.replace('        const int cid = static_cast<int>(clauses_.size());','        if(learnt)writeProofClause(lits);\n        const int cid = static_cast<int>(clauses_.size());',1)
s=s.replace('    std::string x46_model_path,x47_guard_path;','    std::string x46_model_path,x47_guard_path,proof_path;')
s=s.replace('        else if (opt=="--stats")','        else if(opt=="--proof" && i+1<argc)proof_path=argv[++i];\n        else if (opt=="--stats")')
s=s.replace('    std::ifstream fd(input);','    std::ofstream proof;\n    if(!proof_path.empty()){proof.open(proof_path);if(!proof)throw std::runtime_error("proof open failed");}\n    std::ifstream fd(input);')
s=s.replace('            if(x46_conflicts>0)solver->configureX46','            solver->setProof(proof_path.empty()?nullptr:&proof);\n            if(x46_conflicts>0)solver->configureX46')
s=s.replace('    const double solve_finish_elapsed=solver->elapsed();','    if(r==Result::UNSAT)solver->writeProofClause({});\n    if(proof.is_open()){proof.flush();if(!proof)throw std::runtime_error("proof flush failed");}\n    const double solve_finish_elapsed=solver->elapsed();')
(ROOT/'build').mkdir(exist_ok=True)
(ROOT/'build/frozen-proof.cpp').write_text(s)
print('FROZEN_CORE_SHA256',expected)
