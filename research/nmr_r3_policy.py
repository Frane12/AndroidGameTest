#!/usr/bin/env python3
"""DRNAS NMR R3: compatibility-preserving selective SGD / annealing.

Telemetry periods are only *candidate* recurrence in solver-event measurements.
Paired pilot feedback is a proxy, not ground truth about optimal solver speed.
A CaDiCaL solver owns every logical inference; the network never invents clauses.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import pathlib
import random
import sqlite3
import subprocess
import tempfile
import time

import new_horizon_sat as nh

VERSION = "NMR-R2-1"
INPUTS = 10
HIDDEN = 8
MAX_PAIRS = 8
MODES = ("clean", "shadow", "frozen", "live", "no_period", "train")


def need(check, msg):
    if not check:
        raise RuntimeError("NMR_FAIL_CLOSED: " + str(msg))


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def logistic(value):
    return 1.0 / (1.0 + math.exp(-clamp(value, -24.0, 24.0)))


class NeuralPolicy:
    """Compatible 10x8x1 MLP, selective annealed SGD, strict checkpoint."""
    def __init__(self, state=None):
        if state is None:
            rng = random.Random(2026110702)
            self.w1 = [[rng.uniform(-0.15, 0.15) for _ in range(INPUTS)]
                       for _ in range(HIDDEN)]
            self.b1 = [0.] * HIDDEN
            self.w2 = [rng.uniform(-0.15, 0.15) for _ in range(HIDDEN)]
            self.b2 = 0.
            self.updates = 0
        else:
            need(state.get("version") == VERSION, "checkpoint version")
            self.w1 = copy.deepcopy(state["w1"])
            self.b1 = state["b1"][:]
            self.w2 = state["w2"][:]
            self.b2 = float(state["b2"])
            self.updates = int(state["updates"])
            need(len(self.w1) == HIDDEN and
                 all(len(r) == INPUTS for r in self.w1) and
                 len(self.b1) == HIDDEN and len(self.w2) == HIDDEN,
                 "checkpoint dimensions")
            scalars = [v for r in self.w1 for v in r] + self.b1 + self.w2 + [self.b2]
            need(all(isinstance(x, (int, float)) and math.isfinite(x) for x in scalars),
                 "checkpoint not finite")
            need(0 <= self.updates <= 10_000_000, "bad update count")

    def dump(self):
        return dict(version=VERSION, w1=self.w1, b1=self.b1, w2=self.w2,
                    b2=self.b2, updates=self.updates)

    def predict(self, x):
        need(len(x) == INPUTS and all(math.isfinite(v) for v in x), "bad features")
        h = [math.tanh(self.b1[j] +
             sum(self.w1[j][k] * x[k] for k in range(INPUTS)))
             for j in range(HIDDEN)]
        return logistic(self.b2 + sum(self.w2[j] * h[j] for j in range(HIDDEN))), h

    def update(self, x, label, lr=0.025):
        need(label in (0, 1), "bad proxy label")
        p, h = self.predict(x)
        # R3 hypothesis: suppress redundant confidently correct proxy updates
        # and anneal SGD so a repeatedly trained controller stabilizes.
        # This label is STILL a short-clause/time proxy, not final solved time.
        if (label == 1 and p >= 0.85) or (label == 0 and p <= 0.15):
            return
        lr = lr / (1.0 + self.updates / 128.0)
        delta = p - label
        previous_w2 = self.w2[:]
        for j in range(HIDDEN):
            self.w2[j] = clamp(self.w2[j] - lr * delta * h[j], -4., 4.)
        self.b2 = clamp(self.b2 - lr * delta, -4., 4.)
        for j in range(HIDDEN):
            g = delta * previous_w2[j] * (1. - h[j]**2)
            for k in range(INPUTS):
                self.w1[j][k] = clamp(self.w1[j][k] - lr * g * x[k], -4., 4.)
            self.b1[j] = clamp(self.b1[j] - lr * g, -4., 4.)
        self.updates += 1


class PersistentMemory:
    """Committed SQLite learning history survives process restart."""
    def __init__(self, path, writable=True):
        self.path = pathlib.Path(path)
        self.writable = writable
        if writable:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path)
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS episodes (id INTEGER PRIMARY KEY, source_sha TEXT NOT NULL, pairs INTEGER, updates INTEGER, recurrence_hits INTEGER)")
            self.db.commit()
        else:
            need(self.path.is_file(), "missing frozen checkpoint")
            self.db = sqlite3.connect("file:" + str(self.path.resolve()) + "?mode=ro",
                                      uri=True)
        row = self.db.execute("SELECT value FROM state WHERE key='model'").fetchone()
        need(row is not None or writable, "missing initialized weights")
        self.policy = NeuralPolicy(json.loads(row[0]) if row else None)
        if row is None:
            self.save()

    def save(self, source_sha=None, pairs=0, updates=0, hits=0):
        need(self.writable, "attempted write to frozen memory")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)",
                            ("model",json.dumps(self.policy.dump(), sort_keys=True)))
            if source_sha:
                self.db.execute("INSERT INTO episodes(source_sha,pairs,updates,recurrence_hits) VALUES (?,?,?,?)",
                                (source_sha, pairs, updates, hits))

    def close(self):
        self.db.close()


def signature(w):
    offers = max(0, int(w["offers"]))
    short = max(0, int(w["short3"]))
    budget = max(1, int(w["conflict_budget"]))
    literals = max(0, int(w["literals"]))
    return (min(3, int(4 * short / max(1, offers))),
            min(3, int(4 * min(0.999, offers / budget))),
            min(3, int(4 * min(0.999, literals / max(1, offers) / 10.))))


class Recurrence:
    """Candidate periodic signatures must predict subsequent observations.

    No claim about periodicity of actual SAT satisfiability or formula geometry.
    """
    def __init__(self):
        self.samples = [[],[]]
        self.next = [None,None]
        self.hits = 0
        self.misses = 0
        self.lag = 0

    def observe(self, arm, measurement):
        s = signature(measurement)
        prediction = self.next[arm]
        if prediction is not None:
            if prediction[0] == s:
                self.hits += 1
                self.lag = prediction[1]
            else:
                self.misses += 1
        seq = self.samples[arm]
        seq.append(s)
        self.next[arm] = None
        for lag in (2, 3, 4):
            if len(seq) < 3*lag:
                continue
            last = seq[-3*lag:]
            a,b,c = last[:lag],last[lag:2*lag],last[2*lag:]
            if a == b == c and len(set(a)) > 1:
                self.next[arm] = (seq[-lag], lag)
                break

    @property
    def confidence(self):
        tests = self.hits + self.misses
        return self.hits / tests if tests else 0.


def parse(line):
    words = line.strip().split()
    return dict(word.split("=",1) for word in words[1:] if "=" in word)


def characteristics(info, a, b, rec, use_period=True):
    def ratio(win, num):
        return float(win[num]) / max(1, int(win["offers"]))
    def rate(win):
        return float(win["offers"]) / max(0.0001, float(win["dt_s"]))
    return [
        clamp(int(info["complete_xor3"]) / 16., 0., 1.),
        clamp(float(info["boundary_fraction"]), 0., 1.),
        clamp(float(info["bin_fraction"]), 0., 1.),
        clamp(float(info["horn_fraction"]), 0., 1.),
        clamp(ratio(b,"short3") - ratio(a,"short3"), -1., 1.),
        clamp((rate(b) - rate(a)) / max(1., rate(a)+rate(b)), -1., 1.),
        clamp(math.log((float(a["dt_s"])+.001)/
                       (float(b["dt_s"])+.001)), -2., 2.)/2.,
        clamp((int(b["literals"])/max(1,int(b["offers"])) -
               int(a["literals"])/max(1,int(a["offers"])))/20., -1., 1.),
        rec.confidence if use_period else 0.,
        clamp(rec.lag/4., 0., 1.) if use_period else 0.,
    ]


def proxy_target(a, b):
    # Same conflict budgets; shorter wall-clock plus short-clause-yield proxy.
    # This is NOT a measured global optimum label.
    def score(w):
        return (1. + float(w["short3"])/max(1,int(w["offers"]))) / (
                 float(w["dt_s"]) + 0.001)
    return int(score(b) > 1.08 * score(a))


def read_until(proc, marker):
    while True:
        line = proc.stdout.readline()
        if not line:
            err = proc.stderr.read()[-1500:] if proc.poll() is not None else ""
            raise RuntimeError("NMR_DRIVER_EOF "+err)
        if line.startswith(marker):
            return parse(line)


def outcome(proc, status_line):
    lines=[]
    while True:
        row=proc.stdout.readline()
        need(row, "unterminated native outcome")
        if row.startswith("NMR_END"):
            break
        lines.append(row)
    model={}
    if status_line["status"]=="SAT":
        for line in lines:
            if line.startswith("v "):
                for lit in map(int, line[2:].split()):
                    if lit:
                        model[abs(lit)] = lit>0
    return status_line["status"],model


def run_case(source, native_binary, clean_binary, cap, mode, memory=None):
    """No benchmark IDs, expected labels, family metadata or run results feed policy."""
    need(mode in MODES, "invalid mode")
    source=pathlib.Path(source)
    start=time.perf_counter()
    digest=nh.sha(source)
    if mode == "clean":
        with tempfile.TemporaryDirectory() as td:
            z=nh.run_one(source,clean_binary,cap,"clean",td)
        return dict(status=z["status"], elapsed_s=time.perf_counter()-start,
                    profile="default",windows=0,pairs=0,updates=0,
                    recurrence_hits=0,recurrence_misses=0,
                    recurrence_lag=0,structural_scan_s=0.,
                    proof=z["proof"],source_sha=digest)
    need(memory is not None,"missing memory")
    info=nh.fingerprint(source)
    scan_s=time.perf_counter()-start
    require_time=cap-scan_s
    if require_time < 0.2:
        return dict(status="TIMEOUT",elapsed_s=cap,profile="abstain",windows=0,
                    pairs=0,updates=0,recurrence_hits=0,recurrence_misses=0,
                    recurrence_lag=0,structural_scan_s=scan_s,
                    proof="CAP",source_sha=digest)
    # Frozen evaluation loads weights from persistent training, but cannot
    # contaminate future cases with held-out information.
    net = memory.policy if mode=="train" else NeuralPolicy(memory.policy.dump())
    initial_updates=net.updates
    monitor=Recurrence()
    windows=0
    pairs=0
    last=[None,None]
    selected=0
    status="TIMEOUT"
    model={}
    max_pairs=MAX_PAIRS
    proc=subprocess.Popen([str(pathlib.Path(native_binary).resolve()),
                           str(source.resolve()),str(require_time)],
                          stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        read_until(proc,"NMR_READY")
        result_line=None
        for pair in range(max_pairs):
            if time.perf_counter()-start >= cap-0.08:
                break
            # Adaptive temporal sampling resolution: smaller for rapid change,
            # larger when observations are stable. This is a conflict window,
            # not a claim of exact per-instruction introspection.
            if monitor.hits:
                budget = 64 if monitor.confidence < .65 else 128
            else:
                budget = 64 if pair<3 else 128 if pair<6 else 256
            for arm in ((0,1) if pair%2==0 else (1,0)):
                proc.stdin.write(f"STEP {arm} {budget}\n")
                proc.stdin.flush()
                w=read_until(proc,"NMR_WINDOW")
                w=dict(w)
                w["arm"]=arm
                windows+=1
                monitor.observe(arm,w)
                last[arm]=w
                if w["result"] in ("SAT","UNSAT"):
                    result_line=read_until(proc,"NMR_STATUS")
                    status,model=outcome(proc,result_line)
                    break
            if result_line is not None:
                break
            pairs+=1
            features=characteristics(info,last[0],last[1],monitor,
                                     mode!="no_period")
            p,_=net.predict(features)
            if mode in ("live","no_period","train"):
                net.update(features,proxy_target(last[0],last[1]))
            if mode != "shadow" and pairs>=2:
                # Same incumbent solver continues in process with all its clauses.
                # Margin reduces behavior on poorly calibrated probabilities.
                selected=1 if p>=.54 else 0
        if result_line is None:
            proc.stdin.write(f"FINISH {0 if mode=='shadow' else selected}\n")
            proc.stdin.flush()
            result_line=read_until(proc,"NMR_STATUS")
            status,model=outcome(proc,result_line)
        rc=proc.wait(timeout=3)
        need(rc==0,"native driver failed " + (proc.stderr.read()[-500:]))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
        proc.stdin.close()
        proc.stdout.close()
        proc.stderr.close()
    elapsed=time.perf_counter()-start
    if elapsed > cap + 0.10:
        status="TIMEOUT"
    if status=="SAT":
        nh.verify_model(source,model)
        proof="SAT_WITNESS_VERIFIED_ORIGINAL_CNF"
    elif status=="UNSAT":
        proof="NATIVE_UNSAT_NOT_INDEPENDENTLY_LRAT_CHECKED"
    else:
        proof="CAP"
    if mode=="train":
        memory.save(digest,pairs,net.updates-initial_updates,monitor.hits)
    return dict(status=status,elapsed_s=min(elapsed,cap),profile=("sat" if selected else "default"),
                windows=windows,pairs=pairs,updates=net.updates-initial_updates,
                recurrence_hits=monitor.hits,recurrence_misses=monitor.misses,
                recurrence_lag=monitor.lag,
                structural_scan_s=scan_s,proof=proof,source_sha=digest,
                exact_xor3=info["complete_xor3"],
                boundary_fraction=info["boundary_fraction"])


def selftest():
    a=NeuralPolicy()
    x=[0.25]*INPUTS
    p,_=a.predict(x)
    a.update(x,1)
    need(a.predict(x)[0] > p, "online gradient failed")
    with tempfile.TemporaryDirectory() as t:
        path=pathlib.Path(t)/"memory.sqlite"
        m=PersistentMemory(path,True)
        m.policy=a
        m.save("test",1,1,0)
        m.close()
        n=PersistentMemory(path,False)
        need(n.policy.dump()==a.dump(),"persistent restart mismatch")
        n.close()
    rec=Recurrence()
    def w(c):
        return {"offers":100,"short3":10 if c==0 else 90,
                "literals":200 if c==0 else 600,"conflict_budget":128}
    for bit in [0,1]*6:
        rec.observe(0,w(bit))
    need(rec.hits>=3 and rec.misses==0 and rec.lag==2,
         "positive temporal prediction failed")
    neg=Recurrence()
    for bit in [0,1,0,0,1,1,1,0,0,1,1,0]:
        neg.observe(0,w(bit))
    need(neg.hits==0, "nonperiodic false positive")
    const=Recurrence()
    for bit in [0]*14:
        const.observe(0,w(bit))
    need(const.hits==0 and const.lag==0,"constant not periodic")
    print("NMR_R2_SELFTEST_PASS",json.dumps({
        "network": "10x8x1", "persistence":True,
        "synthetic_lag":rec.lag, "predictive_hits":rec.hits,
        "nonperiodic_hits":neg.hits}),flush=True)


if __name__=="__main__":
    selftest()
