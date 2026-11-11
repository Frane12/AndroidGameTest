"""Strict one-CPU Linux wall-time runner for native DRNAS CDCL experiments.

The subprocess must finish within the *remaining* end-to-end budget.
A timeout is UNKNOWN. No timeout-derived result is promoted to SAT/UNSAT.
"""
import math
import resource
import subprocess
import time


def run_strict(binary, cnf_path, seed, remaining_s, *, mem_bytes=2*1024**3):
    if remaining_s <= 0:
        return 0, "", 0.0, "budget_exhausted"
    cpu_soft = max(1, int(math.ceil(remaining_s)) + 1)
    cpu_hard = cpu_soft + 1

    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft, cpu_hard))
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

    argv = [str(binary), str(cnf_path), "--mode", "A", "--time",
            str(remaining_s), "--seed", str(seed)]
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=remaining_s,
            preexec_fn=limits, check=False)
        elapsed = time.perf_counter()-start
        if elapsed > remaining_s:
            return 0, "", elapsed, "wall_budget_overrun"
        if completed.returncode not in (0,10,20):
            return 0, "", elapsed, "native_exit_%s" % completed.returncode
        return completed.returncode,completed.stdout,elapsed,"finished"
    except subprocess.TimeoutExpired:
        return 0, "", time.perf_counter()-start, "wall_timeout"
