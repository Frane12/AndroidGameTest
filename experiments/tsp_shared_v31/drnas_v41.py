#!/usr/bin/env python3
"""DRNAS TSP v4.1: elite 2-opt/3-opt with triggered basin escapes.

- Preserve immutable incumbent; only non-elite agent states are perturbed.
- Trigger restarts after measured stagnation (seconds), not after a fixed number of calls.
- Batch 4 diverse double-bridge restarts using best route as their starting point.
- Give the 4 restarted agents protected search slots (2-opt/3-opt) for several epochs.
- Keep 12 elite slots and 48 exploratory slots to avoid turning the solver into a restart loop.
- Benchmark ablation mode 'v41_no_restart' uses identical engine minus restarts.
- Never claim improvement without recomputing full EUC_2D tour length.
"""
import time
import numpy as np
from drnas_v4 import prepare, tour_len, two_opt_candidate, three_opt_candidate, double_bridge

def run(n, seed, d, nn, budget=30.0, mode="v41", start=None,
        stall_seconds=1.6, restart_cooldown=1.4, restart_agents=4):
    if start is None: start=time.perf_counter()
    tours,pos,scores,initial_s,early8=prepare(n,seed,d,nn,start)
    champion=int(np.argmin(scores))
    best=float(scores[champion])
    best_tour=tours[champion].copy()
    clock=time.perf_counter()-start
    trace=[early8,(clock,best)]
    last_progress=clock
    last_wave=-1.0e10
    rng=np.random.default_rng(41000+seed)
    steps=two_moves=three_moves=best_updates=0
    restarts=restart_waves=perturbations=escape_best_updates=0
    route_copies=communication_s=0
    local_optimum_hits=0
    epoch=0
    # Agent 0..63 correspond to fixed worker identities.
    restart_until=np.zeros(64,dtype=np.int64)
    selected_restart=np.empty(0,dtype=np.int32)
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
            best=exact
            best_tour=tours[w].copy()
            t=time.perf_counter()-start
            trace.append((t,best))
            last_progress=t
            best_updates+=1
            if restart_until[w] > epoch: escape_best_updates+=1

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
        if (mode=="v41" and n>60 and now>=2.0 and
            now-last_progress>=stall_seconds and
            now-last_wave>=restart_cooldown and now<budget-0.2):
            started=time.perf_counter()
            # Preserve at least twelve non-restarted elite searchers, kick worst four.
            ranked=np.argsort(scores)[::-1]
            chosen=[int(w) for w in ranked[:restart_agents]]
            selected_restart=np.array(chosen,dtype=np.int32)
            for i,w in enumerate(chosen):
                tours[w,:]=best_tour
                pos[w,tours[w]]=np.arange(n,dtype=np.int32)
                route_copies+=1
                # 4-opt double bridge; its cost may increase temporarily, not the incumbent.
                # Keep cuts well inside tour to avoid degenerate near-zero partitions.
                minspace=max(5,n//40)
                if n>=7*minspace:
                    raw=np.sort(rng.choice(np.arange(minspace,n-minspace),size=3,replace=False))
                    cuts=[int(raw[0]),int(raw[1]),int(raw[2])]
                    for j in range(1,3):
                        if cuts[j]-cuts[j-1]<minspace:cuts[j]=cuts[j-1]+minspace
                    if cuts[2]>=n-minspace:
                        cuts=[n//5, n//2, 4*n//5]
                else:
                    cuts=[n//5,n//2,4*n//5]
                double_bridge(tours[w],pos[w],cuts[0],cuts[1],cuts[2])
                if i%2==1:
                    cuts2=[n//6,n//3,2*n//3]
                    double_bridge(tours[w],pos[w],cuts2[0],cuts2[1],cuts2[2])
                scores[w]=tour_len(tours[w],d)
                perturbations+=1 if i%2==0 else 2
                restart_until[w]=epoch+30
            restarts+=len(chosen);restart_waves+=1
            last_wave=time.perf_counter()-start
            communication_s+=time.perf_counter()-started

    final=tour_len(best_tour,d)
    if len(set(map(int,best_tour)))!=n or abs(final-best)>=0.1:
        raise ValueError("Invalid v4.1 incumbent permutation or length")
    return dict(events=trace,final=final,elapsed=time.perf_counter()-start,
                initialization_seconds=initial_s,steps=steps,two_opt_moves=two_moves,
                three_opt_moves=three_moves,best_updates=best_updates,
                restart_waves=restart_waves,restarted_agents=restarts,perturbations=perturbations,
                escape_best_updates=escape_best_updates,route_copies=route_copies,
                comm_seconds=float(communication_s),
                mode=mode)

def warmup():
    from drnas_v4 import warmup as baseline_warmup
    baseline_warmup()
