#!/usr/bin/env python3
"""Generate pinned Delta1 source without rebuilding its frozen executables.

The historical generators mix text transforms with compiler-specific binary
hash assertions. Replay ONLY their pinned text transforms; retain every
source-drift assertion. Compile a new executable, never overwrite references.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / 'build'
PINS = {
 'research/drnas_deltacoop1/build.py':'437e68854a1d8e1ed896bf1161aefd13c07fb111a96e08a38eaf5b280d3a2f82',
 'research/drnas_coop54/build.py':'a03efa3e675671550f40c0b8a9834a7e9609168641f2dc6a8106d3d884b19eb2',
 'research/drnas_contract/build.py':'4835763ce20fb01887453774cafaf7f9b355abc151f046feff2c514263998cc2',
 'research/drnas_coop52/build.py':'6ef756dc8f80cd3be3979e564eb700edd73ef6d1529f439c07892bf403920145',
 'research/drnas_coop5/build.py':'9dd6a55e4092cd69af09329c5fc39619a597211e24270f46c5043bea71127414',
 'research/drnas_coop4/build.py':'9bcaa74e06dba30d891ca1d367df9f62f44721e39054ea56c04845f519089671',
 'src/drnas_x5.cpp':'9768340a8bed3bac3e43f0fb29780c4d5165c50283f90eae141733a7b76106fc',
 'research/drnas_coop4/coop.hpp':'1849417412ae399f69d9cdec63a48293bd79d94eea0363c296ea227c916ca9a5',
 'research/drnas_coop4/retention_methods.inc':'f9f3ca52d683f90d01930fd49af03e1fc0cbb5b44a9b8530c3153627fafd9d75',
 'research/drnas_coop5/probe_methods.inc':'8efc5e351cd0dd6cff4f25ca857e965ec6f22d7b1db5126af82368f52a039e3f',
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def once(s, a, b):
    assert s.count(a) == 1, ('DELTA2_SOURCE_DRIFT', a[:100], s.count(a))
    return s.replace(a, b)

class SourceOnly(ast.NodeTransformer):
    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call):
            name = ast.unparse(node.value.func)
            if name in ('print', 'subprocess.run'):
                return ast.Pass()
        return self.generic_visit(node)
    def visit_Assert(self, node):
        # Exact binary identity checks only. Source blob checks remain active.
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == 'sha' for n in ast.walk(node.test)):
            return ast.Pass()
        return node

def main():
    for name, expected in PINS.items():
        assert sha(ROOT/name) == expected, ('PINNED_SOURCE_CHANGED', name)
    B.mkdir(exist_ok=True)
    for name in ('drnas_coop4','drnas_coop5','drnas_coop52','drnas_contract',
                 'drnas_coop54','drnas_deltacoop1'):
        p = ROOT/'research'/name/'build.py'
        tree = ast.fix_missing_locations(SourceOnly().visit(ast.parse(p.read_text())))
        exec(compile(tree, str(p), 'exec'), {'__file__': str(p), '__name__':'source_generation'})
    s = (B/'drnas_deltacoop1.cpp').read_text()
    s = once(s, '#include "delta_coop1.hpp"',
             '#include "delta_coop1.hpp"\n#include "../research/drnas_deltacoop2/join.hpp"')
    s = once(s, 'drnas_coop4::Engine coop_;', 'drnas_coop4::JoinEngine coop_;')
    s = once(s, '    void reportDelta() const {',
             '    void reportDelta() const {\n        coop_.reportJoin();')
    s = once(s, '    bool coop_eager=false;',
             '    std::string delta2_mode="local";\n    bool coop_eager=false;')
    s = once(s, '        else if (opt=="--coop4" && i+1<argc)',
             '        else if (opt=="--delta2" && i+1<argc) delta2_mode=argv[++i];\n'
             '        else if (opt=="--coop4" && i+1<argc)')
    s = once(s, '            solver->configureCoop(coop_mode,coop_eager);',
             '            solver->configureDelta2(delta2_mode);\n'
             '            solver->configureCoop(coop_mode,coop_eager);')
    s = once(s, '    void configureCoop(const std::string& mode,bool eager) {',
             '    void configureDelta2(const std::string& m) { coop_.setJoinMode(m); }\n'
             '    void configureCoop(const std::string& mode,bool eager) {')
    # Eligibility is checked before entering the CDCL bridge. Same gate in
    # local, shadow and join arms; OFF skips collection entirely.
    s = once(s, '        if(!coop_.enabled() || x46_clone_)return Prop{};',
             '        if(!coop_.enabled() || x46_clone_ ||\n'
             '           !coop_.ready(stats_.decisions,stats_.conflicts))return Prop{};')
    p = B/'drnas_deltacoop2.cpp'; p.write_text(s)
    cmd = ['g++','-std=c++20','-O3','-DNDEBUG','-Wall','-Wextra','-Wpedantic','-Werror',
           '-DCOOP5_DYNAMIC_DEFAULT=0','-DCOOP52_FALLBACK_DEFAULT=0','-DCOOP53_REPAIR=1',
           str(p),'-o',str(B/'drnas-deltacoop2')]
    subprocess.run(cmd,check=True,cwd=ROOT)
    report = {'frozen_delta1_run_commit':'5972149c8eb7470980e14061a519a473941724ef',
              'inputs':PINS,'generated_source_sha256':sha(p),
              'join_header_sha256':sha(ROOT/'research/drnas_deltacoop2/join.hpp'),
              'binary_sha256':sha(B/'drnas-deltacoop2'),
              'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0]}
    (B/'DELTA2_BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
    print('DELTA2_BUILD',json.dumps(report,sort_keys=True),flush=True)

if __name__ == '__main__': main()
