"""Strict subprocess budget, independent of the unchanged native solver."""
import resource
import subprocess
import time
from native_paired import BIN


def solve_deadline(path,seed,remaining):
    if remaining<=0:
        return 0,"",0.0
    def limit():
        # Wall-clock timeout is authoritative; CPU/AS are additional guards.
        cpu=max(1,int(remaining)+1)
        resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu+1))
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    cmd=[str(BIN),str(path),'--mode','A','--time',str(remaining),
         '--seed',str(seed)]
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,
                         timeout=remaining,preexec_fn=limit)
    except subprocess.TimeoutExpired:
        return 0,"",time.perf_counter()-start
    if p.returncode not in (0,10,20):
        raise RuntimeError(f"Native solver failed rc={p.returncode}: {p.stderr[-1000:]}")
    return p.returncode,p.stdout,time.perf_counter()-start
