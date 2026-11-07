#!/usr/bin/env python3
"""DRNAS NMR R4: bounded exploration, persistent utility and event-driven feedback.

All SAT semantics are delegated to exact source-identical CaDiCaL instances.
Training outcomes are paired walltime/PAR2 rewards; never use answer labels as
model inputs. Evaluation does not update persistent memory.
"""
from __future__ import annotations
import collections
import hashlib
import json
import math
import pathlib
import sqlite3
import subprocess
import tempfile
import time

import new_horizon_sat as nh
import nmr_online as nn
import nmr_r3_policy as r3

VERSION="DRNAS-NMR-R4-V1"
MODES=("clean","r3_gate","r4_safe","r4_explore","forced_sat","forced_unsat")
MIN_ELIGIBLE_BYTES=2048
MIN_ELIGIBLE_CAP=1.0
ACTIVATION_REMAINING_S=.75
EXPLORATION_SAMPLE_RATE=0.125
MAX_WATCH_WINDOWS=6
MAX_EXPLORATION_FRACTION=0.125
SWITCH_MARGIN=1.30
BENEFIT_MARGIN_S=.02

def need(ok,msg):
    if not ok:raise RuntimeError("NMR4_FAIL_CLOSED: "+str(msg))

def eligible(source,cap):
    return cap>=MIN_ELIGIBLE_CAP and pathlib.Path(source).stat().st_size>=MIN_ELIGIBLE_BYTES

def feature_bucket(info):
    # Source-only coarse structural context, not file names or instance hash.
    if info["complete_xor3"]>=2 and info["boundary_occurrences"]>0:return "mixed_xor"
    if info["complete_xor3"]>=2:return "xor"
    if info["bin_fraction"]>=.60:return "binary"
    if info["horn_fraction"]>=.8:return "horn"
    return "other"

class UtilityBandit:
    """Read-only holdout or persistent training-only SQLite model."""
    def __init__(self,path,writable):
        self.path=pathlib.Path(path)
        self.writable=writable
        self.base=r3.UtilityMemory(self.path,writable)
        self.db=self.base.conn
        if writable:
            self.db.execute("""CREATE TABLE IF NOT EXISTS r4_rewards(
                id INTEGER PRIMARY KEY,
                bucket TEXT NOT NULL,
                arm INTEGER NOT NULL,
                source_sha TEXT NOT NULL,
                baseline_par2_s REAL NOT NULL,
                candidate_par2_s REAL NOT NULL,
                delta_s REAL NOT NULL,
                activation_s REAL NOT NULL,
                observations INTEGER NOT NULL,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_sha,arm,recorded_at))""")
            self.db.commit()
        else:
            need(self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='r4_rewards'").fetchone(),
                 "R4 rewards table missing")

    def samples(self,bucket,arm):
        return self.db.execute(
            "SELECT delta_s,activation_s FROM r4_rewards WHERE bucket=? AND arm=?",
            (bucket,arm)).fetchall()

    def global_stats(self,arm):
        return self.db.execute(
            "SELECT delta_s,activation_s FROM r4_rewards WHERE arm=?",(arm,)).fetchall()

    def recommend(self,bucket):
        """Fail closed: no empirical positive evidence => no 2nd solver."""
        options=[]
        for arm in (1,2):
            sample=self.samples(bucket,arm)
            n=len(sample)
            if n<4:continue
            gains=[float(z[0]) for z in sample]
            wins=sum(x>BENEFIT_MARGIN_S for x in gains)
            positives=sum(max(0,x) for x in gains)
            losses=sum(max(0,-x) for x in gains)
            if wins<2 or positives<=losses:continue
            # Conservative: only activate if observed net benefit per trial
            # is positive and enough solved pairs benefited.
            mean=sum(gains)/n
            if mean<=BENEFIT_MARGIN_S:continue
            # Wilson lower bound on a binary improvement proxy.
            phat=wins/n
            z=1.64
            low=(phat+z*z/(2*n)-z*math.sqrt(
                phat*(1-phat)/n+z*z/(4*n*n)))/(1+z*z/n)
            if low<.35:continue
            options.append((mean,arm,wins,n,low))
        return max(options,default=None)

    def update_reward(self,bucket,arm,sha,baseline,candidate,activation,
                      observations,features=None):
        need(self.writable and arm in (1,2),"reward writes only for training arms")
        reward=float(baseline)-float(candidate)
        with self.db:
            self.db.execute("INSERT INTO r4_rewards(bucket,arm,source_sha,"
                "baseline_par2_s,candidate_par2_s,delta_s,activation_s,observations)"
                " VALUES(?,?,?,?,?,?,?,?)",(bucket,arm,sha,baseline,candidate,
                reward,activation,observations))
        # Keep R2/R3 actual MLP weights actively learning from paired walltime.
        if features is not None:
            self.base.model.policy.update(features,int(reward>BENEFIT_MARGIN_S),lr=.015)
            self.base.model.save(sha,1,1,0)

    def close(self):self.base.close()

def parse(line):
    return dict(tok.split("=",1) for tok in line.split()[1:] if "=" in tok)

def until(proc,prefix):
    while True:
        line=proc.stdout.readline()
        if not line:
            err=proc.stderr.read()[-1500:] if proc.poll() is not None else ""
            raise RuntimeError("NMR4_DRIVER_EOF: "+err)
        if line.startswith(prefix):
            return parse(line)

def read_outcome(proc,status):
    model={}
    while True:
        line=proc.stdout.readline()
        need(line,"driver finished without NMR4_END")
        if line.startswith("NMR4_END"):break
        if status=="SAT" and line.startswith("v "):
            for lit in map(int,line[2:].split()):
                if lit:model[abs(lit)]=lit>0
    return model

def finalize(source,mode,status,model,elapsed,cap,reason,windows=0,callbacks=0,
             activation=0.,arm=0,scan=0.,bucket=None,feature=None,prechecked=False):
    if elapsed>=cap:status="TIMEOUT"
    if status=="SAT":
        if not prechecked:nh.verify_model(source,model)
        proof="SAT_WITNESS_VERIFIED_SOURCE"
    elif status=="UNSAT":
        proof="NATIVE_UNSAT_NO_INDEPENDENT_LRAT"
    else:proof="CAP"
    return dict(mode=mode,status=status,elapsed_s=min(float(cap),elapsed),
                reason=reason,windows=windows,callback_wakeups=callbacks,
                activation_s=activation,selected_arm=arm,scan_s=scan,
                bucket=bucket,feature=feature,source_sha=nh.sha(source),proof=proof)

def run_case(source,driver,clean_binary,r3_driver,cap,mode,memory=None,arm_override=None):
    need(mode in MODES,"invalid R4 experiment mode")
    source=pathlib.Path(source)
    st=time.perf_counter()
    # Extremely cheap fail-closed no-AI path. Preserves R3 behavior.
    if mode=="clean" or (mode in ("r4_safe","r4_explore") and not eligible(source,cap)):
        with tempfile.TemporaryDirectory() as tmp:
            result=nh.run_one(source,clean_binary,cap,"clean",tmp)
        return finalize(source,mode,result["status"],{},time.perf_counter()-st,
                        cap,"clean" if mode=="clean" else "cheap_abstain",
                        prechecked=True)
    if mode=="r3_gate":
        need(memory is not None,"R3 model missing")
        result=r3.run_case(source,r3_driver,clean_binary,cap,"utility_gate",memory.base)
        return dict(mode=mode,status=result["status"],elapsed_s=result["elapsed_s"],
                    reason=result["reason"],windows=result["windows"],
                    callback_wakeups=result["callback_wakeups"],
                    activation_s=result["activation_s"],selected_arm=0,
                    scan_s=result["scan_s"],bucket=None,feature=None,
                    source_sha=result["source_sha"],proof=result["proof"])
    if mode in ("r4_safe","r4_explore"):
        need(memory is not None,"utility memory missing")
        # Global absence of any positive sample allows abstention before scan.
        positive=memory.db.execute(
            "SELECT count(*) FROM r4_rewards WHERE delta_s>?",
            (BENEFIT_MARGIN_S,)).fetchone()[0]
        if mode=="r4_safe" and positive<2:
            with tempfile.TemporaryDirectory() as tmp:
                z=nh.run_one(source,clean_binary,cap,"clean",tmp)
            return finalize(source,mode,z["status"],{},time.perf_counter()-st,
                            cap,"no_positive_calibration",prechecked=True)
        # Exploration arm determined BEFORE reading held-out results, via
        # benchmark random assignment. Controller does not see case identity.
        explore_arm=arm_override if mode=="r4_explore" else None
        need(explore_arm in (None,1,2),"bad preregistered exploration arm")
        if mode=="r4_explore" and explore_arm is None:
            with tempfile.TemporaryDirectory() as tmp:
                z=nh.run_one(source,clean_binary,cap,"clean",tmp)
            return finalize(source,mode,z["status"],{},time.perf_counter()-st,
                            cap,"exploration_budget_abstain",prechecked=True)
    else: explore_arm=None
    info=nh.fingerprint(source)
    scan_s=time.perf_counter()-st
    bucket=feature_bucket(info)
    if mode in ("r4_safe","r4_explore") and explore_arm is None:
        recommendation=memory.recommend(bucket)
        if recommendation is None:
            with tempfile.TemporaryDirectory() as tmp:
                z=nh.run_one(source,clean_binary,max(.1,cap-scan_s),"clean",tmp)
            return finalize(source,mode,z["status"],{},
                            time.perf_counter()-st,cap,"no_contextual_gain",
                            scan=scan_s,bucket=bucket,prechecked=True)
        explore_arm=recommendation[1]
    requested_arm=({"forced_sat":1,"forced_unsat":2}.get(mode,explore_arm))
    need(requested_arm in (1,2),"no exploration arm")
    remaining=cap-scan_s
    if remaining<ACTIVATION_REMAINING_S:
        return finalize(source,mode,"TIMEOUT",{},cap,cap,"no_remaining_budget",
                        scan=scan_s,bucket=bucket)
    process=subprocess.Popen([str(pathlib.Path(driver).resolve()),
                              str(source.resolve()),str(remaining)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        bufsize=1,text=True)
    windows=[];callback_wakeups=0;activation_s=0.
    status="TIMEOUT";model={};selected_arm=0
    reason="not_selected"
    def cmd(command,prefix):
        process.stdin.write(command+"\n");process.stdin.flush()
        return until(process,prefix)
    try:
        until(process,"NMR4_READY")
        def observe(arm,budget):
            nonlocal status,model,callback_wakeups
            data=cmd(f"WATCH {arm} {budget}","NMR4_WINDOW")
            data["arm"]=arm
            data["conflict_budget"]=int(data["conflict_budget"])
            callback_wakeups+=int(data.get("wakeup")=="callback")
            windows.append(data)
            if data["result"] in ("SAT","UNSAT"):
                end=until(process,"NMR4_STATUS")
                status=end["status"];model=read_outcome(process,status)
                return True
            return False
        solved=False
        for budget in (256,512):
            if time.perf_counter()-st>=cap-.08:break
            if observe(0,budget):
                reason="default_pilot_solved";solved=True;break
        if not solved and time.perf_counter()-st<cap-ACTIVATION_REMAINING_S:
            tick=time.perf_counter()
            cmd(f"ACTIVATE {requested_arm}","NMR4_ACTIVATED")
            activation_s=time.perf_counter()-tick
            reason=("bounded_random_exploration" if mode=="r4_explore" else
                    "contextual_activation" if mode=="r4_safe" else
                    "forced_exploration")
            for budget in (256,512):
                if time.perf_counter()-st>=cap-.08:break
                if observe(requested_arm,budget):
                    status=status;selected_arm=requested_arm
                    reason="alternate_pilot_solved";solved=True;break
            if not solved:
                a=[x for x in windows if x["arm"]==0]
                b=[x for x in windows if x["arm"]==requested_arm]
                if a and b:
                    # Conservative decision: pilot yield is NOT correctness
                    # and only selects which exact solver to continue.
                    yield_s=lambda rows:(1+sum(int(x["short3"]) for x in rows))/(
                         .002+sum(float(x["dt_s"]) for x in rows))
                    if (yield_s(b)>SWITCH_MARGIN*yield_s(a) and
                            sum(float(x["dt_s"]) for x in b)<.3*cap):
                        selected_arm=requested_arm
                        reason="positive_live_pilot_margin"
                    else:
                        selected_arm=0;reason="retain_warm_default"
        if not solved:
            end=cmd(f"FINISH {selected_arm}","NMR4_STATUS")
            status=end["status"];model=read_outcome(process,status)
        rc=process.wait(timeout=4)
        need(rc==0,"bad R4 driver result: "+process.stderr.read()[-750:])
    finally:
        if process.poll() is None:
            process.kill();process.wait(timeout=4)
        process.stdin.close();process.stdout.close();process.stderr.close()
    feature=None
    if len(windows)>=2:
        a=windows[0];b=windows[1]
        recurrence=nn.Recurrence()
        recurrence.observe(0,a);recurrence.observe(0,b)
        feature=nn.characteristics(info,a,b,recurrence)
    return finalize(source,mode,status,model,time.perf_counter()-st,cap,
                    reason,len(windows),callback_wakeups,activation_s,
                    selected_arm,scan_s,bucket,feature)

def selftest():
    need(feature_bucket(dict(complete_xor3=3,boundary_occurrences=5,
                bin_fraction=.2,horn_fraction=.5))=="mixed_xor","mix fingerprint")
    need(feature_bucket(dict(complete_xor3=0,boundary_occurrences=0,
                bin_fraction=.7,horn_fraction=.5))=="binary","binary fingerprint")
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        path=pathlib.Path(t)/"nmr.sqlite"
        m=UtilityBandit(path,True)
        need(m.recommend("binary") is None,"untrained can't exploit")
        m.update_reward("binary",1,"abc",1.,2.,.05,2,[0.]*nn.INPUTS)
        need(m.recommend("binary") is None,"one sample not enough")
        m.close()
        n=UtilityBandit(path,False)
        need(len(n.samples("binary",1))==1,
             "training state lost after process restart")
        need(n.recommend("binary") is None,"no false positive")
        n.close()
    print("NMR4_SELFTEST_PASS",json.dumps(dict(persistence=True,
       safe_abstention=True,source_structural_buckets=True)),flush=True)

if __name__=="__main__":selftest()
