#!/usr/bin/env python3
"""DELTA3: proof-carrying short cross-block resolvents triggered by real join witnesses.

Regenerate text only from immutable DELTA2 sources. Never recompile or modify
the frozen DELTA2, DELTA1, Kissat, CaDiCaL, main, or source CNFs.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"build"
PARENT=ROOT/"research/drnas_deltacoop2/build.py"
PIN_JOIN="8aceb5ff094241dcc4c3919f0e4bc0000ea06155fcc88741104f75c1d6b3dce5"
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def once(src,a,b):
    if src.count(a)!=1:raise RuntimeError(("DELTA3_SOURCE_DRIFT",src.count(a),a[:130]))
    return src.replace(a,b)

class NoCompiler(ast.NodeTransformer):
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call):
            name=ast.unparse(node.value.func)
            if name in ("subprocess.run","print"):return ast.Pass()
        return self.generic_visit(node)

def main():
    # Execute inherited checked source transforms, but never its compiler.
    assert sha(ROOT/"research/drnas_deltacoop2/join.hpp")==PIN_JOIN
    tree=ast.fix_missing_locations(NoCompiler().visit(ast.parse(PARENT.read_text())))
    env={"__name__":"delta3_text_only","__file__":str(PARENT)}
    exec(compile(tree,str(PARENT),"exec"),env)
    env["main"]()
    src=B.joinpath("drnas_deltacoop2.cpp").read_text()
    h=(ROOT/"research/drnas_deltacoop2/join.hpp").read_text()
    h=once(h,
       '    int64_t nonlinear_tuple_events=0;',
       '''    int64_t nonlinear_tuple_events=0;
    int64_t bridge_witnesses=0,bridge_cross_proposals=0;
    int64_t bridge_unique_candidates=0,bridge_active_candidates=0;
    int64_t bridge_shadow_candidates=0,bridge_injected=0;
    int64_t bridge_satisfied_skips=0,bridge_known_skips=0;
    int64_t bridge_emit_events=0;''')
    method=(ROOT/"research/drnas_deltacoop3/bridge_method.inc").read_text()
    h=once(h,'    void setJoinMode(const std::string& m){',
           method+'\n    void setJoinMode(const std::string& m){')
    h=once(h,
       'if(m!="local"&&m!="shadow"&&m!="join")',
       'if(m!="local"&&m!="shadow"&&m!="join"&&m!="bridge"&&m!="bridge-shadow")')
    h=once(h,
       'if(w>=0){++nonlinear_tuple_events;emitWitness(a,b,values,r.support.vars,0,w,x);}',
       '''if(w>=0){
                            ++nonlinear_tuple_events;
                            emitWitness(a,b,values,r.support.vars,0,w,x);
                            if((join_mode=="bridge"||join_mode=="bridge-shadow") &&
                               bridge_witnesses<4 && Tick::now()<deadline){
                                ++bridge_witnesses;
                                resolveBridge(a,b,values,emit,out,deadline);
                            }
                        }''')
    h=once(h,
       '          <<",\\"analysis_ms\\":"<<ms<<"}\\n";',
       '''          <<",\\"bridge_witnesses\\":"<<bridge_witnesses
          <<",\\"bridge_cross_proposals\\":"<<bridge_cross_proposals
          <<",\\"bridge_unique_candidates\\":"<<bridge_unique_candidates
          <<",\\"bridge_active_candidates\\":"<<bridge_active_candidates
          <<",\\"bridge_shadow_candidates\\":"<<bridge_shadow_candidates
          <<",\\"bridge_injected\\":"<<bridge_injected
          <<",\\"bridge_satisfied_skips\\":"<<bridge_satisfied_skips
          <<",\\"bridge_known_skips\\":"<<bridge_known_skips
          <<",\\"analysis_ms\\":"<<ms<<"}\\n";''')
    (B/"delta3_join.hpp").write_text(h)
    src=once(src,'#include "../research/drnas_deltacoop2/join.hpp"',
             '#include "delta3_join.hpp"')
    p=B/"drnas_deltacoop3.cpp";p.write_text(src)
    out=B/"drnas-deltacoop3"
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
                    "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                    str(p),"-o",str(out)],cwd=ROOT,check=True)
    report={"frozen_delta2_run":43584992768,
            "frozen_delta2_binary_sha256":sha(B/"drnas-deltacoop2"),
            "source_gen_sha256":sha(p),
            "patched_join_header_sha256":sha(B/"delta3_join.hpp"),
            "bridge_method_sha256":sha(ROOT/"research/drnas_deltacoop3/bridge_method.inc"),
            "binary_sha256":sha(out),
            "compiler":subprocess.check_output(["g++","--version"],text=True).splitlines()[0]}
    (B/"DELTA3_BUILD.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DELTA3_BUILD",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":main()
