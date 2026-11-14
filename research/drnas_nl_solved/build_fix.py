#!/usr/bin/env python3
"""Remove AND occurrence bonuses from branching; preserve frozen references."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[2];B=R/'build'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
frozen=B/'drnas-nl-solved';old_hash=sha(frozen)
p=B/'drnas_nl_solved.cpp'
assert sha(p)=='b1b6bc8ddd870f4d0c7dd78ffeec0009df4d3459596980d4e948424aa9a273cb'
s=p.read_text()
def once(a,b):
    global s
    assert s.count(a)==1,(a[:100],s.count(a));s=s.replace(a,b)
once('    int64_t nl_gates_=0;', '    int64_t nl_gates_=0,nl_blocked_prior_variables_=0;')
once('''        if(m!="base"&&m!="inplace"&&m!="inputs"&&m!="both")
            throw std::runtime_error("invalid nonlinear focus mode");
        nl_inplace_=(m=="inplace"||m=="both");
        nl_inputs_=(m=="inputs"||m=="both");''', '''        if(m=="inputs"||m=="both")
            throw std::runtime_error("unsafe AND branching prior removed; use fixed or observe");
        if(m!="base"&&m!="inplace"&&m!="fixed"&&m!="observe")
            throw std::runtime_error("invalid nonlinear focus mode");
        nl_inplace_=(m!="base");
        nl_inputs_=(m=="observe");''')
once('''        // A heuristic only. Exact signed AND definitions are recognized from
        // three original clauses. No substitution, forced value or new clause.
        for(int v=0;v<n_;++v)if(inputs[static_cast<size_t>(v)]) {
            base_[v]+=0.25*inputs[static_cast<size_t>(v)]/(1.0+outputs[static_cast<size_t>(v)]);
            offer(v);
        }''', '''        // Recognition is observational only. Neither structural frequency
        // nor a local propagation count proves a branch impossible or useful.
        // Keep the original CDCL ordering, phases and conflict analysis.
        for(int v=0;v<n_;++v)if(inputs[static_cast<size_t>(v)])
            ++nl_blocked_prior_variables_;''')
once('    std::string nl_mode="base";', '    std::string nl_mode="fixed";')
assert s.count('nl_mode=="inplace"||nl_mode=="both"')==2
s=s.replace('nl_mode=="inplace"||nl_mode=="both"','nl_mode!="base"')
once('''        <<",\\"gate_scan_ms\\":"<<solver->nl_scan_ms_<<"}\\n";''', '''        <<",\\"gate_scan_ms\\":"<<solver->nl_scan_ms_
        <<",\\"blocked_prior_variables\\":"<<solver->nl_blocked_prior_variables_
        <<",\\"actual_branch_overrides\\":0,\\"policy\\":\\"preserve_cdcl_order\\"}\\n";''')
assert 'base_[v]+=0.25' not in s
src=B/'drnas_nl_fixed.cpp';src.write_text(s)
binary=B/'drnas-nl-fixed'
subprocess.run(['g++','-std=c++20','-O3','-DNDEBUG','-Wall','-Wextra','-Wpedantic','-Werror',
    '-DCOOP5_DYNAMIC_DEFAULT=0','-DCOOP52_FALLBACK_DEFAULT=0','-DCOOP53_REPAIR=1',str(src),'-o',str(binary)],check=True)
assert sha(frozen)==old_hash
report={'source_sha256':sha(src),'binary_sha256':sha(binary),'frozen_binary_sha256':old_hash,
    'frozen_unchanged':True,'static_AND_bonus_removed':True,'default_mode':'fixed',
    'new_mathematical_pruning':False,'observe_mode_changes_search':False}
(B/'NL_FIXED_BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
print('NL_FIXED_BUILD_PASS',json.dumps(report))
