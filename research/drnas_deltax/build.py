#!/usr/bin/env python3
"""Build the isolated DELTAX proof-carrying guarded-equivalence CDCL engine.

Replays the pinned DELTA3 source-only transforms without rebuilding or
modifying DELTA1/2/3 binary references, main, source inputs or other branches.
DELTAX is experimental; it installs valid CNF reasons, NOT blind substitutions.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"build"
PARENT=ROOT/"research/drnas_deltacoop3/build.py"
PIN_DELTA3_METHOD="1cbb8d73f44306af14c940835fa474d0e71c1c7d0f5f7a0e2b07453bd1329f94"

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def once(s,old,new):
    count=s.count(old)
    if count!=1:
        raise RuntimeError(f"DELTAX_SOURCE_DRIFT count={count}, text={old[:110]!r}")
    return s.replace(old,new)

class NoCompiler(ast.NodeTransformer):
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call) and ast.unparse(node.value.func) in ("subprocess.run","print"):
            return ast.Pass()
        return self.generic_visit(node)

def main():
    B.mkdir(parents=True,exist_ok=True)
    # Parent requires immutable delta2 method and all transitive source hashes.
    assert (ROOT/"research/drnas_deltacoop3/bridge_method.inc").is_file()
    tree=ast.fix_missing_locations(NoCompiler().visit(ast.parse(PARENT.read_text())))
    env={"__name__":"deltax_source_only","__file__":str(PARENT)}
    exec(compile(tree,str(PARENT),"exec"),env)
    env["main"]()

    s=(B/"drnas_deltacoop3.cpp").read_text()
    h=(B/"delta3_join.hpp").read_text()
    h=once(h,"    void setJoinMode(const std::string& m){",
           (ROOT/"research/drnas_deltax/alias_methods.inc").read_text()+
           "\n    void setJoinMode(const std::string& m){")
    h=once(h,
           '&&m!="bridge-shadow")',
           '&&m!="bridge-shadow"&&m!="deltax"&&m!="deltax-shadow")')
    h=once(h,
           '                                resolveBridge(a,b,values,emit,out,deadline);\n                            }',
           '''                                resolveBridge(a,b,values,emit,out,deadline);
                            }
                            if((join_mode=="deltax"||join_mode=="deltax-shadow") &&
                               deltax_witnesses_<4 && Tick::now()<deadline){
                                resolveDeltax(a,b,values,out,deadline);
                            }''')
    (B/"deltax_join.hpp").write_text(h)
    s=once(s,'#include "delta3_join.hpp"',
           '#include "deltax_join.hpp"')

    # Clause provenance persists across CDCL clause storage and garbage
    # collection; reason uses are counted at the actual CDCL reason boundary.
    s=once(s,"    bool coop4_origin=false;",
           "    bool coop4_origin=false;\n    bool deltax_origin=false;")
    s=once(s,
           '''        if(!c.coop4_origin || c.deleted || x46_clone_ || probing_)return;''',
           '''        if(c.deltax_origin && !c.deleted && !x46_clone_ && !probing_)
            coop_.deltaxRecordUse(conflict);
        if(!c.coop4_origin || c.deleted || x46_clone_ || probing_)return;''')
    s=once(s,
           '''            int cid=storeClause(std::move(c),true);++stats_.learnt;
            clauses_[cid].glue=computeGlue(clauses_[cid].lits);''',
           '''            int cid=storeClause(std::move(c),true);++stats_.learnt;
            if(coop_.deltaxIsClause(clauses_[cid].lits))
                clauses_[cid].deltax_origin=true;
            clauses_[cid].glue=computeGlue(clauses_[cid].lits);''')
    # The trail retains original assignment reasons. When the guard becomes
    # false, the derived clause is used by BCP; when undone, alias OBSERVER
    # tracks deactivation. No rewriting of values, watches or variables.
    s=once(s,
           '''        trail_.push_back(lit);
        return true;
    }
    void newDecisionLevel()''',
           '''        trail_.push_back(lit);
        if(!probing_ && !x46_clone_)
            coop_.deltaxOnTrailChange(lit,values_);
        return true;
    }
    void newDecisionLevel()''')
    s=once(s,
           '''        trail_lim_.resize(target);
        qhead_ = static_cast<int>(trail_.size());
    }''',
           '''        trail_lim_.resize(target);
        qhead_ = static_cast<int>(trail_.size());
        if(!probing_ && !x46_clone_)
            coop_.deltaxRefreshAliases(values_);
    }''')
    s=once(s,"        coop_.reportJoin();",
           "        coop_.reportJoin(); coop_.reportDeltax(values_);")
    p=B/"drnas_deltax.cpp";p.write_text(s)
    out=B/"drnas-deltax"
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
                    "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                    str(p),"-o",str(out)],check=True,cwd=ROOT)
    report={
        "from_delta3_run":43587320318,
        "source_sha256":sha(p),
        "header_sha256":sha(B/"deltax_join.hpp"),
        "deltax_methods_sha256":sha(ROOT/"research/drnas_deltax/alias_methods.inc"),
        "binary_sha256":sha(out),
        "original_delta3_binary_sha256":sha(B/"drnas-deltacoop3"),
        "source_generation":"pinned-source-only; no reference rebuild",
        "global_variable_substitution":False,
        "proof_carrying_live_cdcl_clauses":True,
        "compiler":subprocess.check_output(["g++","--version"],text=True).splitlines()[0]
    }
    (B/"DELTAX_BUILD.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DELTAX_BUILD",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()
