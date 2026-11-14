#!/usr/bin/env python3
"""DELTA4: isolated wider-size CDCL bridge, proof-carrying cross-window resolution.

Replays the pinned DELTA3 source-only generators. Does not change main,
DELTA3, original CNFs, proof checker, or reference binaries.
"""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"build"
PARENT=ROOT/"research/drnas_deltacoop3/build.py"

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def once(s, old, new):
    if s.count(old)!=1:
        raise RuntimeError(("DELTA4_SOURCE_DRIFT",old[:110],s.count(old)))
    return s.replace(old,new)

class SourceOnly(ast.NodeTransformer):
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call):
            name=ast.unparse(node.value.func)
            if name in ("print","subprocess.run"):
                return ast.Pass()
        return self.generic_visit(node)

def main():
    # Reconstruct text only, preserving every inherited source pin check.
    tree=ast.fix_missing_locations(SourceOnly().visit(ast.parse(PARENT.read_text())))
    env={"__file__":str(PARENT),"__name__":"delta4_text_only"}
    exec(compile(tree,str(PARENT),"exec"),env)
    env["main"]()
    source=(B/"drnas_deltacoop3.cpp").read_text()
    engine=(B/"delta_coop1.hpp").read_text()
    engine=once(engine,
        '    int declared_variables=0;',
        '''    int declared_variables=0;
    int64_t d4_input_clauses=0,d4_reservoir_replacements=0;
    bool d4_large_formula=false;''')
    engine=once(engine,
        '''        if(originals.size()>=12000){disabled=true;originals.clear();return;}
        originals.push_back(c);''',
        '''        ++d4_input_clauses;
        if(originals.size()<12000){originals.push_back(c);return;}
        // Deterministic bounded reservoir: later original clauses remain
        // eligible even in million-clause inputs. No status/labels consulted.
        uint64_t z=static_cast<uint64_t>(d4_input_clauses)+0x9e3779b97f4a7c15ULL;
        z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;
        z=(z^(z>>27))*0x94d049bb133111ebULL;
        z^=z>>31;
        const uint64_t pos=z/static_cast<uint64_t>(1); // explicit full-width hash
        const uint64_t slot=pos%static_cast<uint64_t>(d4_input_clauses);
        if(slot<12000){originals[static_cast<size_t>(slot)]=c;
            ++d4_reservoir_replacements;}''')
    engine=once(engine,
        '        if(n>4096){disabled=true;originals.clear();return;}',
        '''        if(n>1000000){disabled=true;originals.clear();return;}
        d4_large_formula=n>4096;''')
    (B/"delta4_coop1.hpp").write_text(engine)

    h=(B/"delta3_join.hpp").read_text()
    h=once(h,
        '    int64_t bridge_emit_events=0;',
        '''    int64_t bridge_emit_events=0;
    int64_t d4_reduction_pairs=0,d4_nonaffine_pairs=0;
    int64_t d4_scan_calls=0,d4_structural_calls=0,d4_injections=0;''')
    h=once(h,
        'if(m!="local"&&m!="shadow"&&m!="join"&&m!="bridge"&&m!="bridge-shadow")',
        'if(m!="local"&&m!="shadow"&&m!="join"&&m!="bridge"&&m!="bridge-shadow"&&m!="d4"&&m!="d4-shadow"&&m!="d4-struct")')
    h=once(h,
        'if(join_mode=="bridge-shadow"){',
        'if(join_mode=="bridge-shadow"||join_mode=="d4-shadow"){')
    # Generalized interaction signal is an EXACT join reduction. Local
    # nonaffinity is recorded separately; do not describe every reduction
    # as a proved beyond-affine witness.
    h=once(h,
        '++pair_evaluations;tuples_removed+=r.removed;',
        '''++pair_evaluations;tuples_removed+=r.removed;
                if(r.removed>0) {
                    ++d4_reduction_pairs;
                    const bool nonaffine=(tables[i].defect>0||tables[j].defect>0);
                    if(nonaffine)++d4_nonaffine_pairs;
                    const bool general=(join_mode=="d4"||join_mode=="d4-shadow");
                    const bool structural=(join_mode=="d4-struct"&&nonaffine);
                    if((general||structural) && d4_scan_calls<12 &&
                       Tick::now()<deadline) {
                        ++d4_scan_calls;
                        if(structural)++d4_structural_calls;
                        const int64_t before=bridge_injected;
                        resolveBridge(a,b,values,emit,out,deadline);
                        d4_injections+=bridge_injected-before;
                    }
                }''')
    h=once(h,
       '          <<",\\"analysis_ms\\":"<<ms<<"}\\n";',
       '''          <<",\\"d4_input_clauses\\":"<<d4_input_clauses
          <<",\\"d4_large_formula\\":"<<(d4_large_formula?1:0)
          <<",\\"d4_reservoir_replacements\\":"<<d4_reservoir_replacements
          <<",\\"d4_reduction_pairs\\":"<<d4_reduction_pairs
          <<",\\"d4_nonaffine_pairs\\":"<<d4_nonaffine_pairs
          <<",\\"d4_scan_calls\\":"<<d4_scan_calls
          <<",\\"d4_structural_calls\\":"<<d4_structural_calls
          <<",\\"d4_injections\\":"<<d4_injections
          <<",\\"analysis_ms\\":"<<ms<<"}\\n";''')
    (B/"delta4_join.hpp").write_text(h)
    source=once(source,'#include "delta_coop1.hpp"',
                '#include "delta4_coop1.hpp"')
    source=once(source,'#include "delta3_join.hpp"',
                '#include "delta4_join.hpp"')
    p=B/"drnas_deltacoop4.cpp"
    p.write_text(source)
    out=B/"drnas-deltacoop4"
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
                    "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                    str(p),"-o",str(out)],cwd=ROOT,check=True)
    report={"parent":"DELTA3",
            "parent_binary_sha256":sha(B/"drnas-deltacoop3"),
            "delta4_binary_sha256":sha(out),
            "generated_source_sha256":sha(p),
            "engine_sha256":sha(B/"delta4_coop1.hpp"),
            "join_sha256":sha(B/"delta4_join.hpp"),
            "arch":"single logical CPU per solver",
            "source_only_and_no_main_changes":True}
    (B/"DELTA4_BUILD.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DELTA4_BUILD",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
