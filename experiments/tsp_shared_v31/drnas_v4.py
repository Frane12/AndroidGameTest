#!/usr/bin/env python3
"""DRNAS TSP v4: 64 virtual agent states, early feasible route,
candidate 2-opt + limited 3-opt and sparse shared-best communication.
Independent of LKH, which is only a benchmark competitor.
Objective: TSPLIB EUC_2D (rounded integer edge weights).
"""
import time, random
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist
from numba import njit

def fast_make(n,seed):
    """Exactly the same coordinates and EUC_2D edge costs as compare_lkh.make."""
    xy=np.random.default_rng(88001+seed).uniform(0,1000,(n,2))
    coords=np.rint(xy*1000).astype(np.int32)
    d=np.floor(cdist(coords,coords)+0.5).astype(np.float32)
    nn=cKDTree(coords).query(coords,k=33)[1][:,1:].astype(np.int32)
    return coords,d,nn

def tour_len(t,d):
    a=np.asarray(t,dtype=np.int32)
    return float(d[a,np.roll(a,-1)].sum(dtype=np.float64))

@njit
def two_opt_candidate(t,pos,d,nn,cursor=0,width=20,checks=500):
    n=len(t);best_delta=0.;best_i=-1;best_j=-1
    for z in range(min(checks,n)):
        i=(cursor+z*37)%n
        a=t[i];b=t[(i+1)%n]
        for q in range(min(width,nn.shape[1])):
            c=nn[a,q];j=pos[c]
            if j<=i+1 or (i==0 and j==n-1):continue
            e=t[(j+1)%n]
            delta=float(d[a,c])+float(d[b,e])-float(d[a,b])-float(d[c,e])
            if delta<best_delta-1e-7:
                best_delta=delta;best_i=i;best_j=j
    if best_i<0:return 0.,-1
    i=best_i+1;j=best_j
    while i<j:
        x=t[i];y=t[j];t[i]=y;t[j]=x;pos[x]=j;pos[y]=i
        i+=1;j-=1
    if i==j:pos[t[i]]=i
    return best_delta,best_j-best_i

@njit
def three_opt_candidate(t,pos,d,nn,cursor=0,checks=120,width=13):
    n=len(t);best_delta=0.;bi=bj=bk=-1;which=0
    for z in range(min(checks,n)):
        i=(cursor+z*29)%n
        if i+5>=n:continue
        a=t[i];b=t[i+1]
        for x in range(min(width,nn.shape[1])):
            cand_d=nn[a,x];j=pos[cand_d]-1
            if j<i+2 or j>=n-3:continue
            c=t[j];dd=t[j+1]
            for y in range(min(width,nn.shape[1])):
                f=nn[c,y] if y%2==0 else nn[b,y]
                k=pos[f]-1
                if k<=j+1 or k>=n-1:continue
                e=t[k];ff=t[k+1]
                old=float(d[a,b])+float(d[c,dd])+float(d[e,ff])
                delta0=float(d[a,dd])+float(d[e,b])+float(d[c,ff])-old
                delta1=float(d[a,e])+float(d[dd,b])+float(d[c,ff])-old
                delta2=float(d[a,dd])+float(d[e,c])+float(d[b,ff])-old
                delta3=float(d[a,e])+float(d[dd,c])+float(d[b,ff])-old
                for m,delta in enumerate((delta0,delta1,delta2,delta3)):
                    if delta<best_delta-1e-7:
                        best_delta=delta;bi=i;bj=j;bk=k;which=m
    if bi<0:return 0.,-1
    i=bi;j=bj;k=bk
    temp=np.empty(k-i,dtype=np.int32);w=0
    if which==1 or which==3:
        for idx in range(k,j,-1):temp[w]=t[idx];w+=1
    else:
        for idx in range(j+1,k+1):temp[w]=t[idx];w+=1
    if which==2 or which==3:
        for idx in range(j,i,-1):temp[w]=t[idx];w+=1
    else:
        for idx in range(i+1,j+1):temp[w]=t[idx];w+=1
    for idx in range(k-i):
        v=temp[idx];t[i+1+idx]=v;pos[v]=i+1+idx
    return best_delta,which

@njit
def double_bridge(t,pos,s1,s2,s3):
    n=len(t);tmp=t.copy();j=0
    for i in range(s1):t[j]=tmp[i];j+=1
    for i in range(s2,s3):t[j]=tmp[i];j+=1
    for i in range(s1,s2):t[j]=tmp[i];j+=1
    for i in range(s3,n):t[j]=tmp[i];j+=1
    for i in range(n):pos[t[i]]=i

def prepare(n,seed,d,nn,start):
    began=time.perf_counter()
    r=random.Random(72001+seed);bases=[];early8=None
    for w in range(64):
        used=bytearray(n);cur=r.randrange(n);t=[cur];used[cur]=1
        while len(t)<n:
            opts=[int(c) for c in nn[cur,:min(4+(w%4)*8,32)] if not used[int(c)]]
            if opts:nxt=opts[r.randrange(min(1+(w%4)*2,len(opts)))]
            else:
                nxt=int(np.argmin(np.where(np.frombuffer(used,dtype=np.uint8),np.inf,d[cur])))
            t.append(nxt);used[nxt]=1;cur=nxt
        bases.append(t)
        if w==7:
            early8=(time.perf_counter()-start,min(tour_len(x,d) for x in bases))
    tours=np.asarray(bases,dtype=np.int32)
    pos=np.empty_like(tours)
    for w in range(64):pos[w,tours[w]]=np.arange(n,dtype=np.int32)
    scores=np.asarray([tour_len(t,d) for t in tours],dtype=np.float64)
    return tours,pos,scores,time.perf_counter()-began,early8

def run(n,seed,d,nn,budget=10.0,mode='v4',start=None):
    if start is None:start=time.perf_counter()
    tours,pos,scores,init_s,early8=prepare(n,seed,d,nn,start)
    best_idx=int(np.argmin(scores));best_tour=tours[best_idx].copy()
    best=float(scores[best_idx])
    trace=[early8,(time.perf_counter()-start,best)]
    steps=two_moves=three_moves=route_copies=kicks=checks=0
    comm_s=0.;rng=np.random.default_rng(31000+seed)
    epoch=0;order=np.argsort(scores)
    elite=order[:16];explore=order[16:]
    while time.perf_counter()-start<budget:
        for w in elite:
            w=int(w)
            if epoch%6==5:
                delta,move_code=three_opt_candidate(tours[w],pos[w],d,nn,(epoch*239+w*31)%n,90,12)
                if move_code>=0:three_moves+=1
            else:
                delta,move_code=two_opt_candidate(tours[w],pos[w],d,nn,(epoch*239+w*31)%n,24,240)
                if move_code>=0:two_moves+=1
            steps+=1
            if move_code>=0:
                scores[w]+=delta
                if scores[w]<best-0.0001:
                    actual=tour_len(tours[w],d);scores[w]=actual;checks+=1
                    if actual<best-0.0001:
                        best=actual;best_tour=tours[w].copy()
                        trace.append((time.perf_counter()-start,best))
            if time.perf_counter()-start>=budget:break
        if epoch%2==0 and time.perf_counter()-start<budget:
            for w in explore:
                w=int(w)
                delta,move_code=two_opt_candidate(tours[w],pos[w],d,nn,(epoch*67+w*61)%n,20,130)
                steps+=1
                if move_code>=0:
                    two_moves+=1;scores[w]+=delta
                    if scores[w]<best-0.0001:
                        actual=tour_len(tours[w],d);scores[w]=actual;checks+=1
                        if actual<best-0.0001:
                            best=actual;best_tour=tours[w].copy()
                            trace.append((time.perf_counter()-start,best))
                if time.perf_counter()-start>=budget:break
        epoch+=1
        if epoch%5==0 and time.perf_counter()-start<budget:
            ts=time.perf_counter()
            order=np.argsort(scores);elite=order[:16];explore=order[16:]
            worst=int(order[-1])
            if mode=='v4' and scores[worst]>best*1.02:
                tours[worst,:]=best_tour
                pos[worst,tours[worst]]=np.arange(n,dtype=np.int32)
                scores[worst]=best;route_copies+=1
                if epoch%25==0 and n>60:
                    cuts=sorted(rng.choice(np.arange(5,n-5),size=3,replace=False).tolist())
                    double_bridge(tours[worst],pos[worst],cuts[0],cuts[1],cuts[2])
                    scores[worst]=tour_len(tours[worst],d);kicks+=1
            comm_s+=time.perf_counter()-ts
    actual=tour_len(best_tour,d)
    if len(set(map(int,best_tour)))!=n or abs(best-actual)>=0.1:
        raise ValueError('Invalid v4 permutation or route cost drift')
    return {'events':trace,'final':actual,'elapsed':time.perf_counter()-start,
            'steps':steps,'two_opt_moves':two_moves,'three_opt_moves':three_moves,
            'route_copies':route_copies,'kicks':kicks,'validated_updates':checks,
            'comm_seconds':comm_s,'initialization_seconds':init_s}

def warmup():
    n=40
    xy=np.random.default_rng(0).uniform(0,100,(n,2))
    d=np.sqrt(((xy[:,None]-xy[None,:])**2).sum(axis=2)).astype(np.float32)
    nn=cKDTree(xy).query(xy,k=33)[1][:,1:].astype(np.int32)
    t=np.arange(n,dtype=np.int32);pos=t.copy()
    two_opt_candidate(t,pos,d,nn,0,8,30)
    three_opt_candidate(t,pos,d,nn,0,25,8)
    double_bridge(t,pos,6,12,21)
