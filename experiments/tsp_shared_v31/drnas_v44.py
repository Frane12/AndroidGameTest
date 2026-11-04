#!/usr/bin/env python3
"""DRNAS TSP v4.4: adaptive, feedback-based escape policy.
FROZEN BEFORE HOLDOUT SEEDS 6/7/8. Use size prior and observed new-global-best
gain by *active* restarted agents; every fourth restart wave probes another
policy. Existing global incumbent is immutable and separately verified.
Correlation between restart lineage and gains is not proof of causality.
"""
import time
import numpy as np
from drnas_v4 import prepare, tour_len, two_opt_candidate, three_opt_candidate, double_bridge
from numba import njit

@njit
def bounded_uphill_two_opt(t,pos,d,nn,offset,limit):
    """Find a modest uphill move; pick a near-target cost to diversify safely."""
    n=len(t)
    best_i=-1; best_j=-1; best_delta=0.
    target=0.42*limit
    deviation=1.e30
    for k in range(45):
        i=(offset+53*k)%n
        a=t[i];b=t[(i+1)%n]
        for q in range(1,min(nn.shape[1],32),2):
            c=nn[a,q]
            j=pos[c]
            if j<=i+1 or (i==0 and j==n-1):
                continue
            e=t[(j+1)%n]
            delta=float(d[a,c])+float(d[b,e])-float(d[a,b])-float(d[c,e])
            if delta<=0.001 or delta>limit:
                continue
            deviation_here=abs(delta-target)
            if deviation_here<deviation:
                deviation=deviation_here
                best_i=i
                best_j=j
                best_delta=delta
    if best_i<0:
        return 0.,0
    i=best_i+1;j=best_j
    while i<j:
        x=t[i];y=t[j]
        t[i]=y;t[j]=x
        pos[x]=j;pos[y]=i
        i+=1;j-=1
    if i==j:pos[t[i]]=i
    return best_delta,1

def select_escape_policy(n,waves,attempts,gains,best_updates):
    """0 = double-bridge, 1 = bounded uphill two-opt. Frozen policy."""
    baseline=0 if n<3500 else 1
    alt=1-baseline
    if best_updates[alt]>=2 and attempts[alt]>0:
        alt_yield=float(gains[alt])/float(attempts[alt])
        base_yield=float(gains[baseline])/float(max(1,attempts[baseline]))
        if alt_yield>1.10*base_yield and alt_yield>0:
            return alt
    if waves%4==3:
        return alt
    return baseline

def run(n, seed, d, nn, budget=30.0, mode="v44", start=None,
        stall_seconds=1.6, restart_cooldown=1.4, restart_agents=4,
        agent_stall_seconds=1.2):
    if start is None: start=time.perf_counter()
    tours,pos,scores,initial_s,early8=prepare(n,seed,d,nn,start)
    champion=int(np.argmin(scores))
    best=float(scores[champion])
    best_tour=tours[champion].copy()
    clock=time.perf_counter()-start
    trace=[early8,(clock,best)]
    last_progress=clock
    last_wave=-1.0e10
    rng=np.random.default_rng(44000+seed)
    steps=two_moves=three_moves=best_updates=0
    restarts=restart_waves=perturbations=escape_best_updates=0
    route_copies=communication_s=0
    local_optimum_hits=0
    skipped_waves=0
    agent_local_improvements=0
    selected_agent_ids=set()
    restart_policy=np.full(64,-1,dtype=np.int32)
    policy_attempts=np.zeros(2,dtype=np.int64)
    policy_gains=np.zeros(2,dtype=np.float64)
    policy_best_updates=np.zeros(2,dtype=np.int64)
    policy_waves=np.zeros(2,dtype=np.int64)
    policy_probes=0
    selected_policy_last=-1
    uphill_kicks=0
    uphill_kick_cost=0.
    no_candidate_kicks=0
    epoch=0
    # Agent 0..63 correspond to fixed worker identities.
    restart_until=np.zeros(64,dtype=np.int64)
    selected_restart=np.empty(0,dtype=np.int32)
    agent_last_improve=np.full(64,clock,dtype=np.float64)
    agent_last_restarted=np.full(64,-1.0e10,dtype=np.float64)
    order=np.argsort(scores)
    elite=order[:16];explore=order[16:]

    def update_best(w):
        nonlocal best,best_tour,last_progress,best_updates,escape_best_updates
        # Verify candidate before updating global record; score drift cannot fabricate gain.
        if scores[w] >= best-0.001:
            return
        exact=tour_len(tours[w],d)
        scores[w]=exact
        if exact < best-0.001:
            gain=best-exact
            if restart_until[w]>epoch and restart_policy[w]>=0:
                k=int(restart_policy[w])
                policy_gains[k]+=gain
                policy_best_updates[k]+=1
                escape_best_updates+=1
            best=exact
            best_tour=tours[w].copy()
            t=time.perf_counter()-start
            trace.append((t,best))
            last_progress=t
            best_updates+=1

    while time.perf_counter()-start < budget:
        for idx in elite:
            w=int(idx)
            if (epoch%5==4) or (restart_until[w]>epoch and epoch%3==2):
                delta,code=three_opt_candidate(tours[w],pos[w],d,nn,(epoch*239+w*31)%n,98,13)
                if code>=0:
                    three_moves+=1
            else:
                delta,code=two_opt_candidate(tours[w],pos[w],d,nn,(epoch*239+w*31)%n,24,240)
                if code>=0:
                    two_moves+=1
            steps+=1
            if code>=0:
                scores[w]+=delta
                agent_last_improve[w]=time.perf_counter()-start
                agent_local_improvements+=1
                update_best(w)
            if time.perf_counter()-start >= budget:break

        if epoch%2==0 and time.perf_counter()-start<budget:
            for idx in explore:
                w=int(idx)
                delta,code=two_opt_candidate(tours[w],pos[w],d,nn,(epoch*67+w*61)%n,20,130)
                steps+=1
                if code>=0:
                    two_moves+=1
                    scores[w]+=delta
                    agent_last_improve[w]=time.perf_counter()-start
                    agent_local_improvements+=1
                    update_best(w)
                if time.perf_counter()-start >= budget:break

        epoch+=1
        if epoch%5==0 and time.perf_counter()-start<budget:
            comm_started=time.perf_counter()
            order=np.argsort(scores)
            active=selected_restart[restart_until[selected_restart]>epoch] if len(selected_restart) else np.empty(0,dtype=np.int32)
            if len(active):
                choose=[int(w) for w in active]
                choose_set=set(choose)
                for w in order:
                    if len(choose)>=16:break
                    if int(w) not in choose_set:
                        choose.append(int(w));choose_set.add(int(w))
                elite=np.asarray(choose,dtype=np.int32)
                explore=np.asarray([int(w) for w in order if int(w) not in choose_set],dtype=np.int32)
            else:
                elite=order[:16]; explore=order[16:]
            # Keep v4's low-frequency shared-best propagation, separated from restarts.
            worst=int(order[-1])
            if scores[worst] > best*1.02 and restart_until[worst] <= epoch:
                tours[worst,:]=best_tour
                pos[worst,tours[worst]]=np.arange(n,dtype=np.int32)
                scores[worst]=best
                route_copies+=1
            communication_s+=time.perf_counter()-comm_started

        now=time.perf_counter()-start
        if (mode=="v44" and n>60 and now>=2.0 and
            now-last_progress>=stall_seconds and
            now-last_wave>=restart_cooldown and now<budget-0.2):
            started=time.perf_counter()
            # Do not kick any of the 16 best tours or currently improving agents.
            # A restart is justified only by BOTH global and per-agent stagnation.
            ranked=np.argsort(scores)
            protected=set(map(int,ranked[:16]))
            eligible=[
                int(w) for w in ranked[16:]
                if now-agent_last_improve[int(w)]>=agent_stall_seconds
                and now-agent_last_restarted[int(w)]>=restart_cooldown
                and restart_until[int(w)]<=epoch
            ]
            eligible.sort(key=lambda w: (
                -(now-agent_last_improve[w]),
                -float(scores[w]-best),
                w
            ))
            chosen=eligible[:max(0,min(restart_agents,4))]
            if not chosen:
                skipped_waves+=1
                last_wave=now
                continue
            if len(protected.intersection(chosen))!=0:
                raise ValueError("v4.4 attempted to restart protected elite")
            selected_restart=np.array(chosen,dtype=np.int32)
            policy=select_escape_policy(n,restart_waves,policy_attempts,policy_gains,policy_best_updates)
            policy_waves[policy]+=1
            policy_attempts[policy]+=len(chosen)
            if policy!=(0 if n<3500 else 1):
                policy_probes+=1
            selected_policy_last=policy
            for i,w in enumerate(chosen):
                tours[w,:]=best_tour
                pos[w,tours[w]]=np.arange(n,dtype=np.int32)
                route_copies+=1
                kicked=0
                if policy==0:
                    minspace=max(5,n//40)
                    if n>=7*minspace:
                        raw=np.sort(rng.choice(np.arange(minspace,n-minspace),size=3,replace=False))
                        cuts=[int(raw[0]),int(raw[1]),int(raw[2])]
                        for j in range(1,3):
                            if cuts[j]-cuts[j-1]<minspace:
                                cuts[j]=cuts[j-1]+minspace
                        if cuts[2]>=n-minspace:
                            cuts=[n//5,n//2,4*n//5]
                    else:
                        cuts=[n//5,n//2,4*n//5]
                    double_bridge(tours[w],pos[w],cuts[0],cuts[1],cuts[2])
                    kicked=1
                    if i%2==1:
                        double_bridge(tours[w],pos[w],n//6,n//3,2*n//3)
                        kicked+=1
                else:
                    limit=max(2000.,0.00055*best)
                    for k in range(2+(i%2)):
                        move_delta,applied=bounded_uphill_two_opt(
                            tours[w],pos[w],d,nn,
                            int(rng.integers(0,n))+w*67+k*113,limit
                        )
                        if applied:
                            uphill_kicks+=1
                            uphill_kick_cost+=move_delta
                            kicked+=1
                if kicked==0:
                    no_candidate_kicks+=1
                scores[w]=tour_len(tours[w],d)
                perturbations+=kicked
                restart_policy[w]=policy
                restart_until[w]=epoch+36
                agent_last_restarted[w]=time.perf_counter()-start
                agent_last_improve[w]=agent_last_restarted[w]
                selected_agent_ids.add(w)
            restarts+=len(chosen);restart_waves+=1
            last_wave=time.perf_counter()-start
            communication_s+=time.perf_counter()-started

    final=tour_len(best_tour,d)
    if len(set(map(int,best_tour)))!=n or abs(final-best)>=0.1:
        raise ValueError("Invalid v4.4 incumbent permutation or length")
    return dict(events=trace,final=final,elapsed=time.perf_counter()-start,
                initialization_seconds=initial_s,steps=steps,two_opt_moves=two_moves,
                three_opt_moves=three_moves,best_updates=best_updates,
                restart_waves=restart_waves,restarted_agents=restarts,perturbations=perturbations,
                escape_best_updates=escape_best_updates,route_copies=route_copies,
                comm_seconds=float(communication_s),
                agent_local_improvements=agent_local_improvements,
                selected_agents_unique=len(selected_agent_ids),
                skipped_restart_waves=skipped_waves,
                protected_elite_slots=16,
                agent_stall_seconds=agent_stall_seconds,
                uphill_kicks=uphill_kicks, uphill_kick_cost=uphill_kick_cost,
                no_candidate_kicks=no_candidate_kicks,
                policy_bridge_waves=int(policy_waves[0]),
                policy_bounded_waves=int(policy_waves[1]),
                policy_probes=int(policy_probes),
                policy_bridge_best_updates=int(policy_best_updates[0]),
                policy_bounded_best_updates=int(policy_best_updates[1]),
                policy_bridge_gain=float(policy_gains[0]),
                policy_bounded_gain=float(policy_gains[1]),
                policy_at_end=int(selected_policy_last),
                mode=mode)

def warmup():
    from drnas_v4 import warmup as baseline_warmup
    baseline_warmup()
    t=np.arange(40,dtype=np.int32); p=t.copy()
    d=np.ones((40,40),dtype=np.float32)
    nn=np.empty((40,32),dtype=np.int32)
    for i in range(40):
        nn[i]=[(i+j+1)%40 for j in range(32)]
    bounded_uphill_two_opt(t,p,d,nn,1,50.)
    assert select_escape_policy(2000,0,np.zeros(2,dtype=np.int64),np.zeros(2),np.zeros(2,dtype=np.int64))==0
    assert select_escape_policy(5000,0,np.zeros(2,dtype=np.int64),np.zeros(2),np.zeros(2,dtype=np.int64))==1
    assert select_escape_policy(2000,3,np.zeros(2,dtype=np.int64),np.zeros(2),np.zeros(2,dtype=np.int64))==1
