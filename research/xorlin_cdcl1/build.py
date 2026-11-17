#!/usr/bin/env python3
"""Build experimental one-PID C++ X59 CDCL + embedded certified XORLIN1.

No external solver process is launched by the resulting executable.
The embedded Python interpreter is used only to preserve the existing
independently certified GF(2) proof algorithms in this first pilot.
"""
import hashlib,pathlib,shlex,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/"build/drnas-xorlin-cdcl1"
SRC=ROOT/"research/xorlin_cdcl1/solver.cpp"
OLD=ROOT/"src/drnas_x59.cpp"
assert SRC.is_file() and OLD.is_file()
for sub in ("research/xorlin1/extract.py","research/xorlin1/emit_veripb.py",
            "research/math5/check_math5.py"):
    assert (ROOT/sub).is_file(),sub
includes=shlex.split(subprocess.check_output(
    ["python3-config","--includes"],text=True))
link=shlex.split(subprocess.check_output(
    ["python3-config","--embed","--ldflags"],text=True))
OUT.parent.mkdir(parents=True,exist_ok=True)
cmd=["g++","-std=c++20","-O2","-DNDEBUG","-Wall","-Wextra",
     "-Wpedantic","-Wno-unused-function"]+includes+[str(SRC),"-o",str(OUT)]+link
subprocess.run(cmd,check=True)
code=OUT.read_bytes()
print("XORLIN_CDCL1_BUILT",{"sha256":hashlib.sha256(code).hexdigest(),
      "bytes":len(code),
      "cpp_sha256":hashlib.sha256(SRC.read_bytes()).hexdigest(),
      "frozen_CDCL_sha256":hashlib.sha256(OLD.read_bytes()).hexdigest(),
      "single_native_executable":True,
      "embedded_Python":True,
      "no_internal_solver_subprocess":True},flush=True)
