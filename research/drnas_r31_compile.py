#!/usr/bin/env python3
"""R31: controlled BCP A/B/C without altering solver decisions outside BCP.

Frozen generated LTM8 FAST engine, three isolated builds:
BASE: unchanged watched clause implementation,
BLOCKER: previously implemented DRNAS_ONE2_BLOCKER caching,
BINFAST: new explicit 2-literal watched-clause fast path.
Same -O3 compiler options, no DRNAS_PROFILE overhead.
"""
import os
import pathlib
import random
import subprocess
import tempfile

ROOT = pathlib.Path("mre_atlas23")
CXX = os.environ.get("CXX", "g++")
subprocess.run(["python3", "research/drnas_ltm8_compile.py"], check=True)

header = ROOT / "drnas_native_core_c.hpp"
source = header.read_text()
anchor = '                require(clause.size() >= 2, "broken watch on unit clause");'
assert source.count(anchor)==1, ("R31 BCP drift", source.count(anchor))
fast = r"""
#ifdef DRNAS_R31_BINARY_FAST
                // A two-literal clause cannot move a watched literal.
                // Preserve the exact original watch, implication and
                // conflict behavior, but evaluate the other literal once.
                if (clause.size() == 2) {
                    if (clause[0] == -true_lit)
                        std::swap(clause[0], clause[1]);
                    require(clause[1] == -true_lit, "watch invariant violated");
                    const int other = clause[0];
                    const int value = lit_value(other);
#ifdef DRNAS_ONE2_BLOCKER
                    entry.blocker=other;
                    list[write++]=entry;
#else
                    list[write++]=cid;
#endif
                    if (value == 1) continue;
                    if (value == -1 || !enqueue(other,cid)) {
                        while (read<list.size()) list[write++]=list[read++];
                        list.resize(write);
                        return cid;
                    }
                    continue;
                }
#endif
"""
source = source.replace(anchor,anchor+"\n"+fast,1)
header.write_text(source)

native = ROOT/"native.cpp"
src = native.read_text()
# Output-only counters for comparing search work at verified exits.
anchor = '<<" conflicts="<<st.conflicts<<" decisions="<<st.decisions'
assert src.count(anchor)==1, ("R31 output drift",src.count(anchor))
src = src.replace(anchor,anchor
    + '<<" propagations="<<st.propagations'
    + '<<" watch_visits="<<st.watch_visits'
    + '<<" learned_clauses="<<st.learned_clauses'
    + '<<" restarts="<<st.restarts',1)
native.write_text(src)

binary = {}
for name, flag in (
    ("BASE",None),
    ("BLOCKER","-DDRNAS_ONE2_BLOCKER"),
    ("BINFAST","-DDRNAS_R31_BINARY_FAST"),
):
    target = ROOT/"bin"/("drnas_r31_"+name.lower())
    args = [CXX,"-O3","-std=c++17","-I","research",
            "-I","mre_atlas23","-I","mre_atlas15"]
    if flag:args.append(flag)
    subprocess.run(args+[str(native),"-o",str(target)],check=True)
    binary[name]=target

# Deterministic exhaustive oracle on small random SAT and UNSAT formulae.
# This explicitly checks the new fast path against truth, not just baseline.
import drnas_ltm11_real2 as B
def satisfiable(n,clauses):
    for bits in range(1<<n):
        if all(any(bool(bits&(1<<(abs(lit)-1)))==(lit>0) for lit in c)
               for c in clauses):
            return True
    return False

rng=random.Random(310031)
with tempfile.TemporaryDirectory() as td:
    p=pathlib.Path(td)/"oracle.cnf"
    cases=[
        (2,[[1,2],[-1,2],[1,-2]]),
        (1,[[1],[-1]]),
        (3,[[1,2],[-1,3],[-2,3]]),
    ]
    for i in range(32):
        n=5+(i%3)
        k=8+(i*7%28)
        clauses=[]
        for _ in range(k):
            v=rng.sample(range(1,n+1),rng.choice((2,2,3,4)))
            clauses.append([x if rng.getrandbits(1) else -x for x in v])
        cases.append((n,clauses))
    for ix,(n,clauses) in enumerate(cases):
        p.write_text("p cnf {} {}\n".format(n,len(clauses))+
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        expected=10 if satisfiable(n,clauses) else 20
        for mode,exe in binary.items():
            args=B.command("LTM8_FAST",p,17,3.0)
            args[0]=str(exe)
            proc=subprocess.run(args,capture_output=True,text=True,timeout=6)
            assert proc.returncode==expected,(
                ix,mode,expected,proc.returncode,proc.stderr[-400:])
            if expected==10:
                assert B.sat_witness_valid(p,n,proc.stdout), (ix,mode)
            assert "ATLAS13_TRIAL " in proc.stdout, (ix,mode)
            assert " watch_visits=" in proc.stdout, (ix,mode)
print("R31_ORACLE_PASS cases={} builds={} no_external_solver=true".format(
    len(cases),len(binary)),flush=True)
