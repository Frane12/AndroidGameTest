#!/usr/bin/env python3
"""DRNAS System Intelligence R1: black-box response identification.
Educational finite-state control experiment, not an ECDLP attack.
"""
import argparse
import csv
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

PRIMES = (17, 31, 127, 509, 2039)

def rng_for(*parts):
    h = hashlib.sha256('|'.join(map(str, ('DRNAS_SYSTEM_R1', *parts))).encode()).digest()
    return random.Random(int.from_bytes(h, 'big'))

def madd(a,b,p): return ((a[0]+b[0])%p,(a[1]+b[1])%p)
def msub(a,b,p): return ((a[0]-b[0])%p,(a[1]-b[1])%p)
def mvec(a,x,p): return ((a[0][0]*x[0]+a[0][1]*x[1])%p,(a[1][0]*x[0]+a[1][1]*x[1])%p)
def mmul(a,b,p):
    return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(2))%p for j in range(2)) for i in range(2))
def inv2(a,p):
    d=(a[0][0]*a[1][1]-a[0][1]*a[1][0])%p
    if not d: return None
    t=pow(d,-1,p)
    return (((a[1][1]*t)%p,(-a[0][1]*t)%p),((-a[1][0]*t)%p,(a[0][0]*t)%p))
def randinvertible(r,p):
    while True:
        m=((r.randrange(p),r.randrange(p)),(r.randrange(p),r.randrange(p)))
        if inv2(m,p) is not None: return m
def state(r,p): return (r.randrange(p),r.randrange(p))

@dataclass
class BlackBox:
    p: int
    a: tuple
    b: tuple
    z: tuple
    nonlinear: bool = False

    def observe(self):
        v=mvec(self.a,self.z,self.p)
        if self.nonlinear:
            return ((v[0]+v[1]*v[1])%self.p,v[1])
        return v

    def act(self,u):
        self.z=madd(self.z,mvec(self.b,u,self.p),self.p)
        return self.observe()

    def clone_at(self,z): return BlackBox(self.p,self.a,self.b,z,self.nonlinear)

def calibrate(box):
    """Only observations and interventions. Do not inspect a, b, or z."""
    p=box.p
    o0=box.observe()
    o1=box.act((1,0))
    o2=box.act((0,1))
    col0=msub(o1,o0,p)
    col1=msub(o2,o1,p)
    estimate=((col0[0],col1[0]),(col0[1],col1[1]))
    return estimate,inv2(estimate,p)

def score_action(system, start, target, action):
    trial=system.clone_at(start)
    goal_obs=system.clone_at(target).observe()
    got=trial.act(action)
    return int(trial.z==target and got==goal_obs)

def run(n_systems=24,n_targets=48):
    records=[]
    models=[]
    for mode in ('linear','nonlinear'):
        for p in (PRIMES if mode=='linear' else PRIMES[:3]):
            for system_id in range(n_systems):
                setup=rng_for('setup',mode,p,system_id)
                a=randinvertible(setup,p)
                b=randinvertible(setup,p)
                calibration_state=state(rng_for('calibration',mode,p,system_id),p)
                system=BlackBox(p,a,b,calibration_state,mode=='nonlinear')
                c,inv_c=calibrate(system)
                # The harness alone sees hidden matrices; the agent does not.
                if mode=='linear':
                    assert c==mmul(a,b,p), 'response calibration mismatch'
                    assert inv_c is not None
                models.append({'mode':mode,'p':p,'id':system_id,'model':system,
                               'calibration':c,'inverse':inv_c})
    lookup={(m['mode'],m['p'],m['id']):m for m in models}
    for m in models:
        mode,p,system_id=m['mode'],m['p'],m['id']
        sys=m['model']; inv_c=m['inverse']
        alt=lookup[(mode,p,(system_id+1)%n_systems)]['inverse']
        for trial_id in range(n_targets):
            test_rng=rng_for('HOLDOUT',mode,p,system_id,trial_id)
            start=state(test_rng,p)
            target=state(test_rng,p)
            while target==start: target=state(test_rng,p)
            start_obs=sys.clone_at(start).observe()
            target_obs=sys.clone_at(target).observe()
            delta=msub(target_obs,start_obs,p)
            actions={
                'random':state(test_rng,p),
                'naive_observed_delta':delta,
                'learned_response':mvec(inv_c,delta,p) if inv_c else None,
                'shuffled_model':mvec(alt,delta,p) if alt else None,
            }
            if mode=='linear':
                actions['oracle']=mvec(inv2(mmul(sys.a,sys.b,p),p),delta,p)
            for name,u in actions.items():
                win=score_action(sys,start,target,u) if u is not None else 0
                records.append({'mode':mode,'p':p,'system_id':system_id,
                                'trial_id':trial_id,'policy':name,'success':win,
                                'actions_test':1 if u is not None else 0,
                                'calibration_actions':2 if name=='learned_response' and trial_id==0 else 0})
    summary=[]
    for mode in ('linear','nonlinear'):
        for p in (PRIMES if mode=='linear' else PRIMES[:3]):
            policies=sorted(set(r['policy'] for r in records if r['mode']==mode and r['p']==p))
            for policy in policies:
                rows=[r for r in records if r['mode']==mode and r['p']==p and r['policy']==policy]
                wins=sum(r['success'] for r in rows)
                summary.append({'mode':mode,'p':p,'bits_approx':p.bit_length(),
                                'policy':policy,'successes':wins,'trials':len(rows),
                                'success_rate':round(wins/len(rows),6),
                                'actions_test':sum(r['actions_test'] for r in rows),
                                'calibration_actions':sum(r['calibration_actions'] for r in rows),
                                'interventions_total':sum(r['actions_test']+r['calibration_actions'] for r in rows)})
    return summary,records

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--systems',type=int,default=24)
    ap.add_argument('--targets',type=int,default=48)
    ap.add_argument('--out',default='results')
    a=ap.parse_args()
    assert a.systems>=2 and a.targets>=1
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    summary,records=run(a.systems,a.targets)
    (out/'summary.json').write_text(json.dumps({'systems_per_cohort':a.systems,'holdout_targets_per_system':a.targets,
                                                'calibration_actions_per_system':2,'results':summary},indent=2)+'\n')
    for name,rows in [('summary.csv',summary),('trials.csv',records)]:
        with (out/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
            writer.writeheader(); writer.writerows(rows)
    for m in ('linear','nonlinear'):
        for p in (PRIMES if m=='linear' else PRIMES[:3]):
            row=[r for r in summary if r['mode']==m and r['p']==p]
            print(m,'p=',p,' '.join(f"{r['policy']}={r['successes']}/{r['trials']}" for r in row))
    assert all(r['successes']==r['trials'] for r in summary if r['mode']=='linear' and r['policy'] in ('learned_response','oracle'))
    assert all(r['successes']<=r['trials'] for r in summary)
    print('R1_VERIFY PASS; output:',out)

if __name__=='__main__':main()
