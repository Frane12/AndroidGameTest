#!/usr/bin/env python3
"""DRNAS NMR R3 — cost-aware activation with online telemetry feedback.

R3 is a *heuristic controller*, never a proof system. Source-only size
abstention is followed by a cheap pilot on the *same retained* CaDiCaL solver.
Second expert is loaded lazily only when learned expected benefit exceeds
measured activation cost and a conservative margin. Memory is SQLite; test
workloads read it without writes. No family/instance ID or answer enters policy.
"""
from __future__ import annotations

import copy
import json
import math
import pathlib
import sqlite3
import subprocess
import tempfile
import time

import new_horizon_sat as nh
import nmr_online as old

MIN_FILE_BYTES = 70000  # preregistered cheap static no-AI gate
MIN_CAP_S = 1.0
PILOT_BUDGETS = (128, 256)
MARGIN_S = 0.02
MIN_CALIBRATION = 4
MAX_DEFAULT_WINDOWS = 6
MODES = ("clean","feedback_only","forced_probe","utility_gate","utility_gate_no_period")
NET_VERSION = "NMR-R3-UTILITY-v1"


def need(cond,msg):
    if not cond:
        raise RuntimeError("NMR3_FAIL_CLOSED: "+str(msg))


def rate(window):
    return int(window["short3"])/max(1,int(window["offers"]))


def telemetry_features(info, previous, latest, recurrence, periodic=True):
    return old.characteristics(info,previous,latest,recurrence,periodic)


def next_budget(previous, latest, rec, index):
    """Increase temporal resolution for change, decrease for stable periods."""
    if previous is None:
        return 128
    change=abs(rate(previous)-rate(latest))
    dt_ratio=float(latest["dt_s"])/max(.0001,float(previous["dt_s"]))
    drift = change>0.18 or dt_ratio>3.0 or dt_ratio<0.33
    if rec.next[0] is not None and rec.confidence>=0.8:
        return 64  # inspect predicted recurrence with smaller sampling stride
    if drift:
        return 64
    return min(2048,256*(2**max(0,index-2)))


class UtilityMemory:
    def __init__(self,path,writable):
        self.path=pathlib.Path(path)
        self.writable=writable
        self.model=old.PersistentMemory(self.path,writable=writable)
        self.conn=self.model.db
        if writable:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS utility ("
                "key TEXT PRIMARY KEY, trials INTEGER NOT NULL, wins INTEGER NOT NULL,"
                "positive_s REAL NOT NULL, negative_s REAL NOT NULL,"
                "activation_s REAL NOT NULL)")
            self.conn.commit()
        else:
            need(self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='utility'").fetchone() is not None,
                 "missing utility calibration")
        # All utility calibration is from training-only paired wall-clock runs.
        self.stats=self.conn.execute(
            "SELECT trials,wins,positive_s,negative_s,activation_s FROM utility WHERE key='global'"
        ).fetchone() or (0,0,0.,0.,0.)

    def read_stats(self):
        return self.stats

    def add_training(self,features,benefit_s,activation_s,source_sha):
        need(self.writable,"attempt to train on heldout")
        good=benefit_s>0.005
        # The supervision label is a *paired wall-time outcome*, not a
        # proxy for shorter learned clauses or known SAT status.
        self.model.policy.update(features,int(good),lr=0.018)
        n,w,pos,neg,activ=self.stats
        self.stats=(n+1,w+int(good),
                    pos+max(0.,benefit_s),neg+max(0.,-benefit_s),
                    activ+max(0.,activation_s))
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO utility(key,trials,wins,positive_s,negative_s,activation_s)"
                " VALUES('global',?,?,?,?,?)",self.stats)
        self.model.save(source_sha,1,1,0)

    def estimated_gain(self,features):
        n,w,pos,neg,activation=self.stats
        if n<MIN_CALIBRATION or w==0:
            return -float("inf"),0.0
        p,_=self.model.policy.predict(features)
        mean_gain=pos/max(1,w)
        mean_loss=neg/max(1,n-w)
        mean_activation=activation/max(1,n)
        expected=p*mean_gain-(1-p)*mean_loss-mean_activation
        return expected,p

    def close(self):
        self.model.close()


def parse(record):
    return dict(tok.split("=",1) for tok in record.split()[1:] if "=" in tok)


def read_line(proc,prefix):
    while True:
        line=proc.stdout.readline()
        if not line:
            err=proc.stderr.read()[-1200:] if proc.poll() is not None else ""
            raise RuntimeError("NMR3_DRIVER_EOF "+err)
        if line.startswith(prefix):
            return parse(line)


def model_from_result(proc,status):
    model={}
    while True:
        line=proc.stdout.readline()
        need(line,"missing end of native solver result")
        if line.startswith("NMR3_END"):
            break
        if status=="SAT" and line.startswith("v "):
            for lit in map(int,line[2:].split()):
                if lit:model[abs(lit)]=(lit>0)
    return model


def result(source,status,model,elapsed,cap,mode,reason,windows,
           scans,observations,confidence,activation_s,feature=None,
           probability=None,expected_gain=None,already_verified=False,callback_wakeups=0):
    if elapsed>=cap:status="TIMEOUT"
    if status=="SAT":
        if not already_verified:
            nh.verify_model(source,model)
        proof="ORIGINAL_CNF_SAT_WITNESS_CHECKED"
    elif status=="UNSAT":
        proof="NATIVE_CDCL_UNSAT_NO_INDEPENDENT_LRAT"
    else:
        proof="CAP"
    return dict(status=status,elapsed_s=min(cap,elapsed),
                mode=mode,reason=reason,windows=windows,
                scan_s=scans,observations=observations,
                recurrence_hits=confidence.hits if confidence else 0,
                recurrence_misses=confidence.misses if confidence else 0,
                activation_s=activation_s,
                callback_wakeups=callback_wakeups,
                decision_feature=feature,
                probability=probability,
                expected_gain_s=expected_gain,
                proof=proof,source_sha=nh.sha(source))


def run_case(source,binary,clean_binary,cap,mode,mem=None):
    need(mode in MODES,"bad R3 mode")
    source=pathlib.Path(source)
    start=time.perf_counter()
    if mode=="clean" or (mode in ("utility_gate","utility_gate_no_period")
                          and (source.stat().st_size<MIN_FILE_BYTES or cap<MIN_CAP_S)):
        # This no-AI path has no fingerprint, no model, no second solver.
        with tempfile.TemporaryDirectory() as td:
            z=nh.run_one(source,clean_binary,cap,"clean",td)
        elapsed=time.perf_counter()-start
        return result(source,z["status"],{},elapsed,cap,mode,
                      "cheap_source_abstention" if mode!="clean" else "clean",
                      0,0,0,None,0.0,already_verified=True)
    need(mem is not None,"missing persistent model")
    if mode in ("utility_gate","utility_gate_no_period"):
        # Calibration is known before this formula is seen.
        n,w,pos,neg,activation=mem.read_stats()
        if n<MIN_CALIBRATION or w==0 or pos<=neg+activation:
            with tempfile.TemporaryDirectory() as td:
                z=nh.run_one(source,clean_binary,cap,"clean",td)
            return result(source,z["status"],{},time.perf_counter()-start,
                          cap,mode,"no_positive_training_calibration",
                          0,0,0,None,0.0,already_verified=True)
    info=nh.fingerprint(source)
    scan=time.perf_counter()-start
    if cap-scan<=0.25:
        return result(source,"TIMEOUT",{},cap,cap,mode,
                      "scan_budget_exceeded",0,scan,0,None,0.)
    process=subprocess.Popen(
        [str(pathlib.Path(binary).resolve()),str(source.resolve()),str(cap-scan)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,bufsize=1)
    observations=[]
    recurrence=old.Recurrence()
    window_count=0
    activation_s=0.
    status="TIMEOUT";model={}
    reason="none";feature=None;probability=None;expected_gain=None
    selected=0;activated=False
    local_model=old.NeuralPolicy(mem.model.policy.dump())
    def command(s,prefix):
        process.stdin.write(s+"\n")
        process.stdin.flush()
        return read_line(process,prefix)

    try:
        read_line(process,"NMR3_READY")
        def observe(arm,budget,watch=False):
            nonlocal window_count,status,model
            cmd="WATCH" if watch else "STEP"
            w=command(f"{cmd} {arm} {budget}","NMR3_WINDOW")
            w["conflict_budget"]=int(w["conflict_budget"])
            recurrence.observe(arm,w)
            observations.append(w)
            window_count+=1
            if w["result"] in ("SAT","UNSAT"):
                end=read_line(process,"NMR3_STATUS")
                status=end["status"]
                model=model_from_result(process,status)
                return True
            return False

        solved=False
        for budget in PILOT_BUDGETS:
            if time.perf_counter()-start>=cap-0.08:
                break
            if observe(0,budget):
                solved=True
                reason="pilot_solved"
                break

        if (not solved and len(observations)>=2 and
                time.perf_counter()-start<cap-0.12):
            periodic=mode!="utility_gate_no_period"
            feature=telemetry_features(info,observations[0],observations[1],
                                       recurrence,periodic)
            expected_gain,probability=mem.estimated_gain(feature)
            activation_allowed=mode in ("forced_probe","utility_gate",
                                        "utility_gate_no_period")
            activate=mode=="forced_probe"
            if mode.startswith("utility_gate"):
                activate=(expected_gain>MARGIN_S and probability>=0.75 and
                          cap-(time.perf_counter()-start)>=1.0)
            if not activate:
                reason=("utility_below_cost" if mode.startswith("utility_gate")
                        else "sleeping_passive_feedback")
                # Rest: no Python neural inference between ordinary samples.
                # Every WATCH uses O(1) C++ learner callbacks and only returns
                # to Python for a bounded budget or a detected regime change.
                while (window_count<MAX_DEFAULT_WINDOWS and
                       time.perf_counter()-start<cap-0.12):
                    prev=observations[-2] if len(observations)>=2 else None
                    last=observations[-1]
                    budget=next_budget(prev,last,recurrence,window_count)
                    if observe(0,budget,watch=True):
                        solved=True
                        reason="asleep_solver_completed"
                        break
                    if (observations[-1].get("wakeup")=="callback" and
                            activation_allowed):
                        # Decide AFTER the solver safely returns at the
                        # callback-triggered boundary, never inside learning().
                        feature=telemetry_features(info,observations[-2],
                                                   observations[-1],recurrence,
                                                   periodic)
                        expected_gain,probability=mem.estimated_gain(feature)
                        activate=(expected_gain>MARGIN_S and
                                  probability>=0.75 and
                                  cap-(time.perf_counter()-start)>=1.0)
                        reason=("callback_utility_positive" if activate else
                                "callback_utility_below_cost")
                        if activate:
                            break
            if activate and not solved:
                tick=time.perf_counter()
                command("ACTIVATE","NMR3_ACTIVATED")
                activation_s=time.perf_counter()-tick
                activated=True
                first=[x for x in observations if x["arm"]=="0"][:2]
                for budget in PILOT_BUDGETS:
                    if time.perf_counter()-start>=cap-0.10:
                        break
                    if observe(1,budget):
                        solved=True
                        reason="alternative_solved"
                        selected=1
                        break
                second=[x for x in observations if x["arm"]=="1"]
                if not solved and second:
                    # Compute benefit proxy only on observed, comparable pilots.
                    productivity=lambda items:(
                        (sum(int(x["short3"]) for x in items)+1) /
                        (sum(float(x["dt_s"]) for x in items)+0.003))
                    baseline_productivity=productivity(first)
                    alternative_productivity=productivity(second)
                    if (alternative_productivity>
                        1.4*baseline_productivity and
                        sum(float(x["dt_s"]) for x in second)<0.3*cap):
                        selected=1
                        reason="verified_pilot_productivity_margin"
                    else:
                        reason="retain_warm_default"
                # Training on a proxy only in local memory. The persistent
                # R3 model is trained on paired full wall-clock reward,
                # never on test/evaluation formulas.
                if len(second)>=2:
                    pair_features=telemetry_features(info,first[-1],second[-1],
                                                     recurrence,periodic)
                    label=old.proxy_target(first[-1],second[-1])
                    local_model.update(pair_features,label,lr=.005)
        if not solved:
            end=command(f"FINISH {selected}","NMR3_STATUS")
            status=end["status"]
            model=model_from_result(process,status)
        rc=process.wait(timeout=4)
        need(rc==0,"native error "+(process.stderr.read()[-800:]))
    finally:
        if process.poll() is None:
            process.kill();process.wait(timeout=4)
        process.stdin.close();process.stdout.close();process.stderr.close()
    return result(source,status,model,time.perf_counter()-start,cap,
                  mode,reason,window_count,scan,len(observations),
                  recurrence,activation_s,feature,probability,expected_gain,
                  callback_wakeups=sum(w.get("wakeup")=="callback" for w in observations))


def selftest():
    need(next_budget(None,{"short3":1,"offers":2,"dt_s":1.},old.Recurrence(),0)==128,
         "initial resolution")
    r=old.Recurrence()
    a={"short3":8,"offers":10,"dt_s":0.1}
    b={"short3":0,"offers":10,"dt_s":.1}
    need(next_budget(a,b,r,3)==64,"resolution not increasing on drift")
    need(next_budget(a,a,r,5)==2048,"stable resolution not widening")
    # Cost of introspection must be positive to justify switching.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path=pathlib.Path(td)/"model.sqlite"
        m=UtilityMemory(path,True)
        need(m.estimated_gain([0.]*old.INPUTS)[0]==-float("inf"),
             "unknown expected value should abstain")
        m.add_training([0.]*old.INPUTS,-.5,.01,"a")
        m.close()
        n=UtilityMemory(path,False)
        need(n.read_stats()[0]==1 and n.model.policy.updates==1,
             "persistent calibration lost")
        n.close()
    print("NMR3_SELFTEST_PASS",json.dumps(dict(
        abstention=True,adaptive_resolution=True,
        persistent_supervised_feedback=True)),flush=True)


if __name__=="__main__":
    selftest()
