#!/usr/bin/env python3
"""Reproducibly generate experimental MATH5 from pinned MATH4, leaving originals unchanged.
Run from anywhere: python3 research/math5/build.py
Produces build/drnas-math5 and the same-compiler build/drnas-math4-local.
"""
from pathlib import Path
import hashlib
import os
import subprocess
r=Path(__file__).resolve().parents[2]
expected={
 'src/drnas_hall3.cpp':'211bf59ba5be9acbc78779dd35e9374a3fd27f246d54f1c80b9ea9136a5adbb9',
 'src/math4_xor_unit.hpp':'ba88103abfca50012c2f2567d8ee3f2ec1c77943d7d5b1d31613cc097501e908'}
for path,digest in expected.items():
 if hashlib.sha256((r/path).read_bytes()).hexdigest()!=digest:
  raise SystemExit('Refusing unpinned MATH4 source: '+path)
gen=r/'build/math5-src';gen.mkdir(parents=True,exist_ok=True)
# Retain original MATH4 code unmodified. New experimental header shares its design,
# not its trust: an independent checker validates all emitted source premises.
s=(r/'src/math4_xor_unit.hpp').read_text().replace('MATH4','MATH5').replace('math4','math5')
s=s.replace('#include <vector>','#include <vector>\n#include <set>')
s=s.replace('int forbidden_parity=0;','int forbidden_parity=0;\n    std::vector<int> exact_one;')
s=s.replace('Equation{support,p}','Equation{support,p,{}}')
a=s.index('inline std::string emit_certificate('); b=s.index('inline Result xor_unit(',a)
s=s[:a]+r'''inline std::string emit_certificate(const std::string& digest,
                                    const std::vector<Equation>& rows,
                                    const std::vector<int>& assigned_units,
                                    const std::vector<uint64_t>& trace,
                                    int& selected_rows,int& selected_units){
    std::ostringstream os;
    os<<"{\"format\":\"drnas-math5-eo-xor-unit-v1\",\"source_sha256\":\""
      <<digest<<"\",\"xor_rows\":[";
    bool first=true;
    selected_rows=selected_units=0;
    for(size_t i=0;i<rows.size();++i) {
        if(!has_bit(trace,i)||!rows[i].exact_one.empty())continue;
        if(!first)os<<',';
        first=false;
        os<<"{\"vars\":[";
        for(size_t j=0;j<rows[i].vars.size();++j){
            if(j)os<<',';
            os<<rows[i].vars[j];
        }
        os<<"],\"forbidden_parity\":"<<rows[i].forbidden_parity<<'}';
        ++selected_rows;
    }
    os<<"],\"exact_one_groups\":[";
    first=true;
    for(size_t i=0;i<rows.size();++i) {
        if(!has_bit(trace,i)||rows[i].exact_one.empty())continue;
        if(!first)os<<',';
        first=false;
        os<<'[';
        for(size_t j=0;j<rows[i].exact_one.size();++j){
            if(j)os<<',';
            os<<rows[i].exact_one[j];
        }
        os<<']';++selected_rows;
    }
    os<<"],\"root_units\":[";
    first=true;
    for(size_t i=0;i<assigned_units.size();++i) {
        if(!has_bit(trace,rows.size()+i))continue;
        if(!first)os<<',';
        first=false;
        os<<assigned_units[i];++selected_units;
    }
    os<<"]}";
    return os.str();
}
'''+s[b:]
needle='    if(equations.size()<2){'
assert needle in s
bridge=r'''    // Exact-one bridge: a source ALO plus ALL source pairwise mutex clauses.
    // For signed literals sum [l_i]=1 implies XOR(abs(l_i))=1 XOR #negative.
    // A lone ALO or AMO never licenses a parity equation.
    std::set<std::pair<int,int>> binary;
    for(size_t ci=0;ci<clauses.size();++ci){
        if((ci&511)==0&&!deadline.live()){
            out.reason="math5_eo_index_budget";return finish();
        }
        const auto& c=clauses[ci];
        if(c.size()==2 && c[0]!=c[1] && c[0]!=-c[1])
            binary.emplace(std::min(c[0],c[1]),std::max(c[0],c[1]));
    }
    std::set<std::pair<std::vector<int>,int>> seen;
    for(const auto& eq:equations)seen.emplace(eq.vars,eq.forbidden_parity);
    size_t exact_one_count=0;
    for(size_t ci=0;ci<clauses.size();++ci){
        if((ci&127)==0&&!deadline.live()){
            out.reason="math5_eo_scan_budget";return finish();
        }
        const auto& c=clauses[ci];
        if(c.size()<3||c.size()>128)continue;
        std::vector<int> support;
        int negatives=0;
        for(int l:c){support.push_back(std::abs(l));negatives+=(l<0);}
        std::sort(support.begin(),support.end());
        if(std::adjacent_find(support.begin(),support.end())!=support.end())continue;
        const int forbidden=negatives&1;
        if(seen.count({support,forbidden}))continue;
        bool all=true;
        for(size_t i=0;i<c.size()&&all;++i){
            if((i&15)==0&&!deadline.live()){
                out.reason="math5_eo_pair_budget";return finish();
            }
            for(size_t j=0;j<i;++j){
                const int a=-c[i],b=-c[j];
                if(!binary.count({std::min(a,b),std::max(a,b)})){all=false;break;}
            }
        }
        if(!all)continue;
        equations.push_back(Equation{support,forbidden,c});
        seen.emplace(std::move(support),forbidden);
        ++exact_one_count;
        if(exact_one_count>=2048||equations.size()>=4096)break;
    }
    out.rounds=int(exact_one_count);
'''
s=s.replace(needle,bridge+needle,1)
s=s.replace('// MATH5 -- strictly source-certified XOR algebra + root unit propagation.',
'''// MATH5 -- experimental exact-one -> XOR bridge, original source clauses only.
// Mathematical rule is established, NOT a novelty claim. No AMO-only parity.
// Extends source XOR + root-UP with verified exact-one equations; same process.''')
s=s.replace('out.reason="math5_xor_plus_root_up_verified";',
'''out.reason="math5_eo_xor_root_up_proof_proposed";''')
(gen/'math5_exactone_xor.hpp').write_text(s)
base=(r/'src/drnas_hall3.cpp').read_text()
t=base.replace('#include "math4_xor_unit.hpp"','#include "math4_xor_unit.hpp"\n#include "math5_exactone_xor.hpp"')
t=t.replace('hall3=false, math4=false;', 'hall3=false, math4=false, math5=false;')
t=t.replace('else if (opt=="--math4") { pcmax_enabled=true; math4=true; }',
'''else if (opt=="--math4") { pcmax_enabled=true; math4=true; }
        else if (opt=="--math5") { pcmax_enabled=true; math5=true; }''')
t=t.replace('(hall3||math4)', '(hall3||math4||math5)').replace('proof_path.empty() || hall3 || math4','proof_path.empty() || hall3 || math4 || math5')
t=t.replace('capacity_result=math4\n', '''capacity_result=math5
                ? pcmax::analyze_math5(pcmax_original,declared_vars,digest,options)
                : math4
''')
assert t!=base
(gen/'drnas_math5.cpp').write_text(t)

flags=['-std=c++20','-O3','-DNDEBUG','-Wall','-Wextra','-Wpedantic','-Werror','-DDRNAS_PCMAX_MODULE','-I'+str(r/'src')]
for source,dest in ((gen/'drnas_math5.cpp',r/'build/drnas-math5'),(r/'src/drnas_hall3.cpp',r/'build/drnas-math4-local')):
 subprocess.run([os.environ.get('CXX','g++'),*flags,str(source),'-lcrypto','-o',str(dest)],check=True)
for path in (gen/'math5_exactone_xor.hpp',gen/'drnas_math5.cpp',r/'build/drnas-math5',r/'build/drnas-math4-local'):
 print(hashlib.sha256(path.read_bytes()).hexdigest(),path.relative_to(r))
