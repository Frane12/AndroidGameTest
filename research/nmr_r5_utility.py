#!/usr/bin/env python3
"""DRNAS Neural R5: reward-trained source-context MLP with strict abstention.

Learn ONLY from R4 paired TRAIN partition: delta(PAR2) includes all controller
costs. Never train on evaluation cases. The network predicts gain/cap for each
secondary exact CaDiCaL expert. A separate conservative empirical confidence
gate prevents unconstrained deployment. No neural output alters SAT semantics.
"""
from __future__ import annotations
import hashlib
import json
import math
import pathlib
import random
import statistics
import time
import tempfile
import new_horizon_sat as nh
import nmr_r4_policy as r4

VERSION = "DRNAS-NEURAL-R5-UTILITY-GATED-v1"
INPUTS, HIDDEN, ARMS = 10, 8, 2
MIN_SAMPLES, REQUIRED_MARGIN_S = 4, 0.02
CONFIDENCE_Z = 1.64
MODES = ("clean", "r4_safe", "r5_shadow", "r5_reward_only", "r5_neural")

def need(ok, why):
    if not ok:
        raise RuntimeError("R5_FAIL_CLOSED: " + str(why))

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def features(info, size, cap):
    """Only inexpensive structural source properties and time allowance."""
    x = [
        math.log1p(info["n"]) / 12.0,
        math.log1p(info["m"]) / 12.0,
        math.log1p(size) / 16.0,
        info["scanned"] / 2048.0,
        clamp(info["complete_xor3"] / 24.0, 0, 1),
        info["boundary_fraction"],
        info["bin_fraction"],
        info["horn_fraction"],
        info["covered"] / max(1, info["scanned"]),
        math.log1p(cap) / 5.0
    ]
    need(len(x) == INPUTS and all(math.isfinite(float(v)) for v in x),
         "invalid static features")
    return [float(clamp(v, 0, 2)) for v in x]

class RewardMLP:
    """Deterministic small 10->8->2 neural net, SGD on real paired gain/cap."""
    def __init__(self, state=None):
        if state is None:
            rng = random.Random(VERSION)
            self.w1 = [[rng.uniform(-.07, .07) for _ in range(INPUTS)]
                       for _ in range(HIDDEN)]
            self.b1 = [0.] * HIDDEN
            self.w2 = [[rng.uniform(-.07, .07) for _ in range(HIDDEN)]
                       for _ in range(ARMS)]
            self.b2 = [0.] * ARMS
        else:
            need(state.get("version") == VERSION, "wrong model version")
            self.w1 = state["w1"]
            self.b1 = state["b1"]
            self.w2 = state["w2"]
            self.b2 = state["b2"]
        need(len(self.w1) == HIDDEN and all(len(w) == INPUTS for w in self.w1)
             and len(self.b1) == HIDDEN and len(self.w2) == ARMS
             and all(len(w) == HIDDEN for w in self.w2)
             and len(self.b2) == ARMS, "shape mismatch")
        need(all(math.isfinite(float(v)) for w in self.w1 for v in w)
             and all(math.isfinite(float(v)) for v in self.b1)
             and all(math.isfinite(float(v)) for w in self.w2 for v in w)
             and all(math.isfinite(float(v)) for v in self.b2),
             "non-finite checkpoint")

    def predict(self, x):
        need(len(x) == INPUTS, "bad feature vector")
        h = [math.tanh(self.b1[j] +
             sum(a*b for a,b in zip(self.w1[j], x))) for j in range(HIDDEN)]
        y = [self.b2[k] +
             sum(a*b for a,b in zip(self.w2[k], h)) for k in range(ARMS)]
        return y, h

    def step(self, x, arm, target, lr):
        need(arm in (1, 2), "bad arm")
        y, h = self.predict(x)
        k = arm - 1
        error = clamp(y[k] - target, -2., 2.)
        old_w2 = self.w2[k][:]
        for j in range(HIDDEN):
            self.w2[k][j] -= lr * (error*h[j] + .0005*self.w2[k][j])
        self.b2[k] -= lr*error
        for j in range(HIDDEN):
            grad = error*old_w2[j]*(1-h[j]*h[j])
            for i in range(INPUTS):
                self.w1[j][i] -= lr*(grad*x[i]+.0005*self.w1[j][i])
            self.b1[j] -= lr*grad

    def dump(self):
        return dict(version=VERSION, w1=self.w1, b1=self.b1,
                    w2=self.w2, b2=self.b2)

def train(rows, source_split, source_dir, out_path):
    """Fit rewards from training-only original sources, never holdout."""
    by_sha = {c["sha256"]: c for c in source_split["training"]}
    holdout = {c["sha256"] for c in source_split["testing"]}
    need(len(by_sha) == 34 and len(holdout) == 40
         and set(by_sha).isdisjoint(holdout), "training/test separation")
    data, counts = [], {1:0, 2:0}
    seen = set()
    for r in rows:
        sha, arm = r["sha256"], int(r["arm"])
        need(sha in by_sha and sha not in holdout and arm in (1,2),
             "non-training reward")
        need((sha,arm) not in seen, "duplicate reward")
        seen.add((sha,arm))
        c = by_sha[sha]
        src = pathlib.Path(source_dir)/(c["id"]+".cnf")
        need(hashlib.sha256(src.read_bytes()).hexdigest() == sha,
             "train source digest drift")
        need(abs(float(r["benefit_s"]) -
                 (float(r["baseline_par2_s"])-float(r["candidate_par2_s"]))) < 1e-5,
             "reward not paired")
        if not r["useful_training_sample"]:
            continue
        info = nh.fingerprint(src)
        x = features(info,src.stat().st_size,float(c["cap_s"]))
        y = clamp(float(r["benefit_s"])/float(c["cap_s"]), -1, 1)
        data.append((x,arm,y))
        counts[arm] += 1
    need(len(seen)==68 and len(data)>=8 and min(counts.values())>=4,
         "too few useful training samples")
    net = RewardMLP()
    history = []
    for epoch in range(1,81):
        batch = list(data)
        random.Random(VERSION+str(epoch)).shuffle(batch)
        for x,arm,y in batch:
            net.step(x,arm,y,0.025/(1+epoch/24.0))
        mse = statistics.mean((net.predict(x)[0][arm-1]-y)**2
                              for x,arm,y in data)
        if epoch in (1,10,40,80):
            history.append(dict(epoch=epoch, training_mse=round(mse,8)))
    model = net.dump()
    model.update(trained_samples=len(data), samples_by_arm=counts,
                 train_sources=34, known_holdout_not_blind=True,
                 history=history,
                 reward="paired (clean PAR2 - forced expert PAR2)/cap; costs included")
    pathlib.Path(out_path).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(out_path).write_text(json.dumps(model,sort_keys=True,indent=2)+"\n")
    return model

def empirical_gate(memory, bucket, cap):
    """Lower confidence bound from source-disjoint TRAIN rewards per bucket."""
    candidates = []
    for arm in (1,2):
        samples = memory.samples(bucket, arm)
        gains = [float(row[0]) for row in samples]
        n = len(gains)
        if n < MIN_SAMPLES:
            continue
        mean = statistics.mean(gains)
        sd = statistics.stdev(gains) if n > 1 else 0.
        lower = mean-CONFIDENCE_Z*sd/math.sqrt(n)
        wins = sum(v > REQUIRED_MARGIN_S for v in gains)
        if wins < 2 or lower <= REQUIRED_MARGIN_S:
            continue
        candidates.append(dict(arm=arm,n=n,mean_gain_s=mean,
                               lower_gain_s=lower))
    return sorted(candidates,key=lambda z:-z["lower_gain_s"])

def _clean(source, clean_binary, cap):
    with tempfile.TemporaryDirectory() as tmp:
        z = nh.run_one(source,clean_binary,cap,"clean",tmp)
    need(z["status"] in ("SAT","UNSAT","TIMEOUT"),"clean outcome")
    return dict(status=z["status"],proof=("SAT_WITNESS_VERIFIED_SOURCE" if
        z["status"]=="SAT" else "NATIVE_UNSAT_NO_INDEPENDENT_LRAT" if
        z["status"]=="UNSAT" else "CAP"),selected_arm=0,
        activation_s=0.,callback_wakeups=0,windows=0,reason="clean")

def run_case(source,driver,clean_binary,r3_driver,cap,mode,memory,net):
    need(mode in MODES, "unknown mode")
    source=pathlib.Path(source)
    started=time.perf_counter()
    bucket=None
    chosen=0
    predicted=None
    lower=None
    reason="clean"
    if mode=="clean":
        z=r4.run_case(source,driver,clean_binary,r3_driver,cap,"clean",memory)
    elif mode=="r4_safe":
        z=r4.run_case(source,driver,clean_binary,r3_driver,cap,"r4_safe",memory)
    elif (not r4.eligible(source,cap)):
        z=r4.run_case(source,driver,clean_binary,r3_driver,cap,"clean",memory)
        reason="cheap_abstain"
    else:
        info=nh.fingerprint(source)
        bucket=r4.feature_bucket(info)
        x=features(info,source.stat().st_size,cap)
        scores=net.predict(x)[0]
        options=empirical_gate(memory,bucket,cap)
        if mode=="r5_shadow":
            reason="shadow_no_action"
        elif not info["analysis_within_budget"]:
            reason="scan_over_budget"
        else:
            for candidate in options:
                arm=candidate["arm"]
                estimate=cap*scores[arm-1]
                if mode=="r5_reward_only" or estimate > max(
                        REQUIRED_MARGIN_S,candidate["lower_gain_s"]*.25):
                    chosen=arm
                    predicted=estimate
                    lower=candidate["lower_gain_s"]
                    break
            if not chosen: reason="low_confidence_abstain"
        remaining=max(0.,cap-(time.perf_counter()-started))
        if remaining<=.2:
            z=dict(status="TIMEOUT",proof="CAP",selected_arm=0,
                   activation_s=0.,callback_wakeups=0,windows=0)
            reason="no_budget_after_scan"
        elif chosen:
            actual="forced_sat" if chosen==1 else "forced_unsat"
            z=r4.run_case(source,driver,clean_binary,r3_driver,
                          remaining,actual,memory)
            reason="reward_gated_arm" if mode=="r5_reward_only" else "neural_gated_arm"
        else:
            z=r4.run_case(source,driver,clean_binary,r3_driver,
                          remaining,"clean",memory)
    elapsed=time.perf_counter()-started
    if elapsed>=cap:
        z["status"]="TIMEOUT";z["proof"]="CAP"
    return dict(status=z["status"],elapsed_s=min(cap,elapsed),
        proof=z["proof"],selected_arm=z.get("selected_arm",0),
        requested_arm=chosen,bucket=bucket,
        predicted_gain_s=predicted,lower_gain_s=lower,
        reason=reason if reason!="clean" else z.get("reason","clean"),
        activation_s=z.get("activation_s",0.),
        callback_wakeups=z.get("callback_wakeups",0),
        windows=z.get("windows",0),
        source_sha=hashlib.sha256(source.read_bytes()).hexdigest())

def selftest():
    m=RewardMLP()
    x=[0.25]*INPUTS
    before=m.predict(x)[0][0]
    for _ in range(200):
        m.step(x,1,0.5,.04)
    after=m.predict(x)[0][0]
    need(after>before+.15,"reward learning failed")
    copied=RewardMLP(m.dump())
    need(abs(copied.predict(x)[0][0]-after)<1e-12,"checkpoint drift")
    need(not empirical_gate(type("M",(),{
        "samples":lambda self,b,a:[(-1.,.1)]*8})(),"binary",3),
        "negative rewards must abstain")
    print("R5_POLICY_SELFTEST_PASS",round(before,5),round(after,5),flush=True)

if __name__=="__main__":
    selftest()
