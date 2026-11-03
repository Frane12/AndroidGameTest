#!/usr/bin/env python3
"""DRNAS TSP v3.1: paired local/wide/collective/explorer virtual-agent search."""
import random, time
import numpy as np
from scipy.spatial import cKDTree
from numba import njit

def initial_tours(n,d,nn,seed,workers=64):
    r=random.Random(seed); tours=[]
    for w in range(workers):
        used=bytearray(n);cur=r.randrange(n);t=[cur];used[cur]=1
        while len(t)<n:
            opts=[int(c) for c in nn[cur,:min(4+(w%4)*8,32)] if not used[int(c)]]
            if opts:nxt=opts[r.randrange(min(1+(w%4)*2,len(opts)))]
            else:
                row=d[cur]
                nxt=int(np.argmin(np.where(np.frombuffer(used,dtype=np.uint8),np.inf,row)))
            t.append(nxt);used[nxt]=1;cur=nxt
        tours.append(t)
    return tours

def tour_len(t,d):
    a=np.asarray(t,dtype=np.int32)
    return float(d[a,np.roll(a,-1)].sum(dtype=np.float64))

@njit
def move(t,pos,d,nn,votes,role,reverse_scan,use_advice,cursor):
    n=len(t)
    kmax=(8 if role==0 else (32 if role==1 else (24 if role==2 else 32)))
    chosen_i=-1;chosen_j=-1;chosen_delta=0.;chosen_score=-1.e10
    picked_advice=0
    for z in range(48):
        i=(cursor+(n-z-1 if reverse_scan else z)*37)%n
        a=t[(i-1)%n];b=t[i]
        for q in range(kmax):
            nq=(kmax-1-q if role==3 else q)
            c=nn[a,nq];j=pos[c]
            if j<=i or (i==0 and j==n-1):continue
            e=t[(j+1)%n]
            delta=float(d[a,c]+d[b,e]-d[a,b]-d[c,e])
            if delta>=-0.00001:continue
            edge_signal=(votes[a,c]+votes[b,e]-votes[a,b]-votes[c,e]) if role==2 and use_advice else 0.
            priority=(-delta)+(min(25.,max(-25.,edge_signal))*0.18 if role==2 else 0.)
            if priority>chosen_score:
                chosen_score=priority;chosen_delta=delta;chosen_i=i;chosen_j=j
                picked_advice=1 if edge_signal>0 else 0
    if chosen_i<0:return 0.,-1,-1,-1,-1,0
    i=chosen_i;j=chosen_j;a=t[(i-1)%n];b=t[i];c=t[j];e=t[(j+1)%n]
    while i<j:
        x=t[i];y=t[j];t[i]=y;t[j]=x;pos[x]=j;pos[y]=i;i+=1;j-=1
    if i==j:pos[t[i]]=i
    return chosen_delta,a,b,c,e,picked_advice

def run(d,nn,bases,mode,seconds):
    n=len(d); agents=len(bases)
    tours=np.array(bases,dtype=np.int32)
    pos=np.empty_like(tours)
    for w in range(agents):pos[w,tours[w]]=np.arange(n,dtype=np.int32)
    lengths=np.array([tour_len(t,d) for t in tours])
    bestidx=int(np.argmin(lengths)); best=float(lengths[bestidx]);best_tour=tours[bestidx].copy()
    votes=np.zeros((n,n),np.float32)
    inbox=[];steps=accepted=best_updates=packets=events=advice_moves=route_copies=0
    comm=0.; deadline=time.perf_counter()+seconds;start=time.perf_counter();w=0;epoch=0
    while time.perf_counter()<deadline:
        role=w//16;direction=(w%2)==1;cursor=(epoch*157+w*193)%n
        delta,a,b,c,e,advised=move(tours[w],pos[w],d,nn,votes,role,direction,mode=='batched_lookup',cursor)
        steps+=1
        if a>=0:
            accepted+=1;lengths[w]+=delta
            if mode=='batched_lookup' and (-delta)>1.0:
                inbox.append((a,b,c,e,min(100.,-float(delta))))
            advice_moves+=advised
            if lengths[w]<best-1e-4:
                best=float(lengths[w]);best_tour=tours[w].copy();best_updates+=1
        w+=1
        if w==agents:
            w=0;epoch+=1
            if mode=='batched_lookup' and epoch%2==0 and inbox:
                t0=time.perf_counter()
                top=sorted(inbox,key=lambda x:x[4],reverse=True)[:16]
                for a,b,c,e,g in top:
                    v=np.float32(g/20.)
                    for x,y,s in ((a,c,1),(b,e,1),(a,b,-1),(c,e,-1)):
                        votes[x,y]+=s*v;votes[y,x]+=s*v
                inbox.clear();packets+=1;events+=len(top)
                comm+=time.perf_counter()-t0
            if mode in ('route_share','batched_lookup') and epoch%4==0:
                t0=time.perf_counter();lag=int(np.argmax(lengths))
                if lengths[lag]>best*1.05:
                    tours[lag,:]=best_tour
                    pos[lag,tours[lag]]=np.arange(n,dtype=np.int32)
                    lengths[lag]=best;route_copies+=1
                comm+=time.perf_counter()-t0
    return dict(length=round(best,3), seconds=round(time.perf_counter()-start,4), steps=steps, packets=packets,edge_events=events,advice_moves=advice_moves,route_copies=route_copies,comm_seconds=round(comm,5))

def warmup():
    xy=np.random.default_rng(99).uniform(0,1000,(40,2))
    d=np.sqrt(((xy[:,None]-xy[None,:])**2).sum(axis=2)).astype(np.float32)
    nn=cKDTree(xy).query(xy,k=33)[1][:,1:].astype(np.int32)
    t=np.arange(40,dtype=np.int32);p=t.copy()
    move(t,p,d,nn,np.zeros((40,40),np.float32),0,False,False,0)
