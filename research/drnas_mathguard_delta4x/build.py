#!/usr/bin/env python3
"""Rebuild frozen DELTA4X text-only and add one-process proof-first MATH-GUARD.

Never recompiles or overwrites the frozen DELTA4X executable, main, or src.
Every arm (OFF/SHADOW/ON/SELECTIVE) runs exactly one derived binary.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"build"
PARENT=ROOT/"research/drnas_delta4x/build.py"
HERE=Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def one(src,old,new):
    n=src.count(old)
    if n!=1:raise RuntimeError(("MATHGUARD_SOURCE_DRIFT",n,old[:140]))
    return src.replace(old,new,1)

class SourceOnly(ast.NodeTransformer):
    def visit_Expr(self,n):
        if isinstance(n.value,ast.Call) and ast.unparse(n.value.func) in ("print","subprocess.run"):
            return ast.Pass()
        return self.generic_visit(n)

def main():
    refs=[B/"drnas-delta4x",B/"drat-trim"]
    refs=[p for p in refs if p.is_file()]
    frozen={str(p.relative_to(ROOT)):sha(p) for p in refs}
    expected=json.loads((B/"DELTA4X_BUILD.json").read_text())
    tree=ast.fix_missing_locations(SourceOnly().visit(ast.parse(PARENT.read_text())))
    scope={"__file__":str(PARENT),"__name__":"mathguard_source_only"}
    exec(compile(tree,str(PARENT),"exec"),scope)
    scope["main"]()
    source=B/"drnas_delta4x.cpp"
    if sha(source)!=expected["source_sha256"]:
        raise RuntimeError("FROZEN_DELTA4X_REGEN_SOURCE_SHA_MISMATCH")
    s=source.read_text()
    s=one(s,"#include <algorithm>\n",
            "#include <algorithm>\n#include <array>\n#include <map>\n#include <set>\n")
    s=one(s,"struct Stats {",
        """struct Stats {
    int64_t mg_mode=0,mg_orig_binary=0,mg_orig_ternary=0;
    int64_t mg_scanned=0,mg_pairs=0,mg_candidates=0;
    int64_t mg_installed=0,mg_gate_skips=0,mg_reason_enqueues=0;
    bool mg_budget_hit=false;
    double mg_wall_ms=0.0;""")
    s=one(s,
        "    void configureX59(bool enabled) { x59_stamp_glue_=enabled; }",
        """    void configureX59(bool enabled) { x59_stamp_glue_=enabled; }
    void configureMathGuard4(int mode,double budget_ms) {
        if(mode<0 || mode>3 || !(budget_ms>0.0 && budget_ms<=12.0 && std::isfinite(budget_ms)))
            throw std::runtime_error("bad MATH_GUARD4 mode or budget");
        mg_mode_=mode;mg_budget_ms_=budget_ms;
    }""")
    s=one(s,"    bool x59_stamp_glue_=false;",
        """    bool x59_stamp_glue_=false;
    int mg_mode_=0;
    double mg_budget_ms_=2.0;
    int64_t mg_orig_binary_=0,mg_orig_ternary_=0;
    std::set<int> mg_clause_ids_;""")
    s=one(s,
        "        const int cid = storeClause(std::move(clean), false);",
        """        if(clean.size()==2) ++mg_orig_binary_;
        if(clean.size()==3) ++mg_orig_ternary_;
        const int cid = storeClause(std::move(clean), false);""")
    s=one(s,"    Result solve() {",
        (HERE/"guard.inc").read_text()+"\n    Result solve() {")
    s=one(s,
        "        if (root_unsat_) return Result::UNSAT;\n        Prop p;",
        """        if (root_unsat_) return Result::UNSAT;
        if(!x46_clone_)runMathGuard4();
        Prop p;""")
    s=one(s,
        "        reasons_[v] = reason;",
        """        reasons_[v] = reason;
        if(reason>=0 && !mg_clause_ids_.empty() &&
           mg_clause_ids_.count(reason)!=0 && !probing_ && !x46_clone_)
            ++stats_.mg_reason_enqueues;""")
    s=one(s,"    bool x59_stamp_glue=false;",
        """    bool x59_stamp_glue=false;
    int mg4_mode=0;double mg4_budget_ms=2.0;""")
    s=one(s,
        '        else if (opt=="--x59-stamp-glue") x59_stamp_glue=true;',
        '''        else if (opt=="--x59-stamp-glue") x59_stamp_glue=true;
        else if (opt=="--math-guard4" && i+1<argc) mg4_mode=std::stoi(argv[++i]);
        else if (opt=="--math-guard4-budget-ms" && i+1<argc)
            mg4_budget_ms=std::stod(argv[++i]);''')
    s=one(s,
        "            solver->configureX59(x59_stamp_glue);",
        """            solver->configureX59(x59_stamp_glue);
            solver->configureMathGuard4(mg4_mode,mg4_budget_ms);""")
    s=one(s,
        '        std::cerr<<"X58_STATS {',
        '''        std::cerr<<"MATH_GUARD4_STATS {\\"mode\\":"<<s.mg_mode
                 <<",\\"orig_binary\\":"<<solver->mathguardOriginalBinary()
                 <<",\\"orig_ternary\\":"<<solver->mathguardOriginalTernary()
                 <<",\\"scanned\\":"<<s.mg_scanned
                 <<",\\"pairs\\":"<<s.mg_pairs
                 <<",\\"candidates\\":"<<s.mg_candidates
                 <<",\\"installed\\":"<<s.mg_installed
                 <<",\\"gate_skips\\":"<<s.mg_gate_skips
                 <<",\\"reason_enqueues\\":"<<s.mg_reason_enqueues
                 <<",\\"budget_hit\\":"<<(s.mg_budget_hit?"true":"false")
                 <<",\\"wall_ms\\":"<<std::fixed<<std::setprecision(7)<<s.mg_wall_ms
                 <<"}\\n";
        std::cerr<<"X58_STATS {''')
    s=one(s,
        "    const Stats& stats() const { return stats_; }",
        """    const Stats& stats() const { return stats_; }
    int64_t mathguardOriginalBinary() const {return mg_orig_binary_;}
    int64_t mathguardOriginalTernary() const {return mg_orig_ternary_;}""")
    path=B/"drnas_delta4x_mathguard.cpp"
    path.write_text(s)
    binary=B/"drnas-delta4x-mathguard"
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Wpedantic","-Werror",
                    "-O3","-DNDEBUG","-DCOOP5_DYNAMIC_DEFAULT=0",
                    "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                    str(path),"-o",str(binary)],cwd=ROOT,check=True)
    if frozen!={str(p.relative_to(ROOT)):sha(p) for p in refs}:
        raise RuntimeError("FROZEN_DELTA4X_BINARY_MUTATED")
    report=dict(derived_source_sha256=sha(path),derived_binary_sha256=sha(binary),
        frozen_source_sha256=sha(source),frozen_binary_sha256=sha(B/"drnas-delta4x"),
        one_logical_cpu=True,one_native_process=True,
        default_guard_off=True,proof="binary original resolution RUP",
        modes=["OFF","SHADOW","ON","SELECTIVE"],frozen_binary_unchanged=True)
    (B/"DELTA4X_MATHGUARD_BUILD.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DELTA4X_MATHGUARD_BUILD "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()
