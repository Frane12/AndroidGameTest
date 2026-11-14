#!/usr/bin/env python3
"""COOP54: proven no-op bridge abstention and CDCL policy A/B.

Never modifies X5/COOP4 sources nor reference binaries/main. The single
new gate binary has identical logical operations except skipping component
dispatches which the component itself would immediately abstain from.
Other A/B arms toggle existing CDCL options on this same binary.
"""
from pathlib import Path
import hashlib,subprocess
R=Path(__file__).resolve().parents[2]; B=R/"build"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rep(s,a,b):
    if s.count(a)!=1:raise RuntimeError(f"COOP54_SOURCE_DRIFT count={s.count(a)} {a[:95]!r}")
    return s.replace(a,b)
subprocess.run(["python3",str(R/"research/drnas_contract/build.py")],check=True,cwd=R)
frozen_sha="d1f87b8f479db21b833d656fa88296dafd0d7d4638e80b59df3af2ce8724d511"
assert sha(B/"drnas-coop53-repair")==frozen_sha,"COOP53 frozen baseline changed"
s=(B/"drnas_coop53_repair.cpp").read_text()
# In the frozen COOP4 step() the following exhaust budgets and return
# an empty Output without inspecting clauses or producing any clause/hint:
# passes>=24 || ms>=30 || lemmas>=256. Both baseline and gate reset the hint.
s=rep(s,"    int coop_hint_=-1;",
    "    int64_t coop54_skipped_dead_dispatch_=0;\n    int coop_hint_=-1;")
s=rep(s,
'''            p = propagate(-1);
            coop5Settle(p.result == PropResult::CONFLICT);
            if (p.result == PropResult::OK) p=cooperate();''',
'''            p = propagate(-1);
            coop5Settle(p.result == PropResult::CONFLICT);
            if(p.result==PropResult::OK) {
                if(!coop_.enabled() || (coop_.prepared && coop_.blocks.empty()) ||
                   coop_.passes>=24 ||
                   coop_.ms>=30 || coop_.lemmas>=256) {
                    coop_hint_=-1;
                    ++coop54_skipped_dead_dispatch_;
                }else p=cooperate();
            }''')
s=rep(s,"        coop_.report(); coop5Report(); reportCoop53();",
  '''        coop_.report(); coop5Report(); reportCoop53();
        std::cerr<<"COOP54_DISPATCH {\\\"skipped_dead_dispatch\\\":"
                 <<coop54_skipped_dead_dispatch_<<"}\\n";''')
src=B/"drnas_coop54_gate.cpp";src.write_text(s)
binary=B/"drnas-coop54-gate"
subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
                "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                str(src),"-o",str(binary)],cwd=R,check=True)
print("COOP54_BUILD_OK",sha(binary),flush=True)
print("COOP54_BASELINE_COOP53_SHA",frozen_sha,flush=True)
