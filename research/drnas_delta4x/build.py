#!/usr/bin/env python3
"""Generate DELTA4X without modifying any frozen source or executable."""
import ast
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/'build'
PARENT=ROOT/'research/drnas_deltacoop4/build.py'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,a,b):
    if s.count(a)!=1: raise RuntimeError(('DELTA4X_SOURCE_DRIFT',s.count(a),a[:150]))
    return s.replace(a,b)
class TextOnly(ast.NodeTransformer):
    def visit_Expr(self,n):
        if isinstance(n.value,ast.Call) and ast.unparse(n.value.func) in ('print','subprocess.run'):
            return ast.Pass()
        return self.generic_visit(n)

def main():
    refs=[B/'drnas-deltacoop4',B/'drnas-deltacoop3',B/'drnas-deltacoop2',
          B/'drnas-deltacoop1',B/'drat-trim',ROOT/'cross/x59/build/kissat',ROOT/'cross/x59/build/cadical']
    before={str(p.relative_to(ROOT)):sha(p) for p in refs}
    tree=ast.fix_missing_locations(TextOnly().visit(ast.parse(PARENT.read_text())))
    env={'__file__':str(PARENT),'__name__':'delta4x_source_only'}
    exec(compile(tree,str(PARENT),'exec'),env);env['main']()
    s=(B/'drnas_deltacoop4.cpp').read_text()
    # This second guard was NOT raised by DELTA4's Engine.initialize patch.
    old='        if(n_>4096)coop_.disabled=true;'
    assert s.count(old)==1,'EXPECTED_INHERITED_DIMENSION_BUG_NOT_FOUND'
    s=once(s,old,'        if(n_>1000000)coop_.disabled=true;')
    s=once(s,'drnas_coop4::JoinEngine coop_;','drnas_coop4::Delta4XEngine coop_;')
    s=once(s,'#include "delta4_join.hpp"','#include "delta4x_engine.hpp"')
    shutil.copyfile(ROOT/'research/drnas_delta4x/engine.hpp',B/'delta4x_engine.hpp')
    # The old dead-dispatch test knew only D4's block/budget state. X has an
    # independent bounded original-clause index, useful even with no blocks.
    s=once(s,'''if(!coop_.enabled() || (coop_.prepared && coop_.blocks.empty()) ||
                   coop_.passes>=24 ||
                   coop_.ms>=30 || coop_.lemmas>=256)''',
           '''if(!coop_.enabled() || !coop_.ready(stats_.decisions,stats_.conflicts))''')
    s=once(s,'    bool coop4_origin=false;',
             '    bool coop4_origin=false;\n    bool delta4x_origin=false;')
    s=once(s,'''            int cid=storeClause(std::move(c),true);++stats_.learnt;
            clauses_[cid].glue=computeGlue(clauses_[cid].lits);''',
             '''            int cid=storeClause(std::move(c),true);++stats_.learnt;
            clauses_[cid].delta4x_origin=coop_.onStored(clauses_[cid].lits,values_);
            clauses_[cid].glue=computeGlue(clauses_[cid].lits);''')
    s=once(s,'''        if(!c.coop4_origin || c.deleted || x46_clone_ || probing_)return;''',
             '''        if(c.delta4x_origin && !c.deleted && !x46_clone_ && !probing_) {
            if(conflict)++coop_.xconflicts;else ++coop_.xreason_analysis;
        }
        if(!c.coop4_origin || c.deleted || x46_clone_ || probing_)return;''')
    s=once(s,'''        trail_.push_back(lit);
        return true;
    }
    void newDecisionLevel()''',r'''        trail_.push_back(lit);
        if(!probing_ && !x46_clone_) {
            if(reason>=0 && clauses_[static_cast<size_t>(reason)].delta4x_origin) {
                const auto& why=clauses_[static_cast<size_t>(reason)].lits;
                if(std::find(why.begin(),why.end(),lit)==why.end())
                    throw std::runtime_error("DELTA4X_IMPLIED_LITERAL_NOT_IN_REASON");
                for(int other:why)if(other!=lit && value(other)!=-1)
                    throw std::runtime_error("DELTA4X_REASON_NOT_UNIT");
                ++coop_.xenqueues;
                if(coop_.xenqueues<=32) {
                    std::cerr<<"DELTA4X_CAUSAL {\"literal\":"<<lit
                        <<",\"decision_level\":"<<decisionLevel()<<",\"clause\":";
                    drnas_coop4::Delta4XEngine::vec(why);
                    std::cerr<<",\"antecedents_false\":[";
                    bool first=true;for(int other:why)if(other!=lit){
                        if(!first){std::cerr<<",";}
                        first=false;std::cerr<<other;
                    }
                    std::cerr<<"]}\n";
                }
            }
            coop_.trailChange(lit,values_);
        }
        return true;
    }
    void newDecisionLevel()''')
    s=once(s,'''        trail_lim_.resize(target);
        qhead_ = static_cast<int>(trail_.size());
    }''',
             '''        trail_lim_.resize(target);
        qhead_ = static_cast<int>(trail_.size());
        if(!probing_ && !x46_clone_)coop_.refresh(values_);
    }''')
    s=once(s,'        coop_.reportJoin();','        coop_.reportJoin(); coop_.reportX();')
    assert 'if(n_>4096)coop_.disabled=true;' not in s
    assert 'delta4x_origin=coop_.onStored' in s and 'DELTA4X_REASON_NOT_UNIT' in s
    p=B/'drnas_delta4x.cpp';p.write_text(s)
    flags=['-std=c++20','-Wall','-Wextra','-Wpedantic','-Werror',
           '-DCOOP5_DYNAMIC_DEFAULT=0','-DCOOP52_FALLBACK_DEFAULT=0','-DCOOP53_REPAIR=1']
    subprocess.run(['g++',*flags,'-O3','-DNDEBUG',str(p),'-o',str(B/'drnas-delta4x')],cwd=ROOT,check=True)
    if '--ubsan' in sys.argv:
        subprocess.run(['g++',*flags,'-O1','-g','-fsanitize=undefined','-fno-sanitize-recover=all',
                        str(p),'-o',str(B/'drnas-delta4x-ubsan')],cwd=ROOT,check=True)
    assert before=={str(p.relative_to(ROOT)):sha(p) for p in refs},'FROZEN_BINARY_CHANGED'
    report={'name':'DELTA4X','source_sha256':sha(p),'binary_sha256':sha(B/'drnas-delta4x'),
            'header_sha256':sha(B/'delta4x_engine.hpp'),'all_frozen_binaries_unchanged':True,
            'hidden_4096_configure_gate_found_and_fixed':True,'independent_index_dispatch_fixed':True,
            'clause_storage_and_actual_enqueue_audited':True,'global_substitution':False,
            'base_commit':'72c5b0ba6d1403d250a944d1f17392a67ab13ad5','frozen':before}
    (B/'DELTA4X_BUILD.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print('DELTA4X_BUILD',json.dumps(report,sort_keys=True),flush=True)
if __name__=='__main__':main()
