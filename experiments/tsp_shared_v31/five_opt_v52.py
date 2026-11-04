"""DRNAS v5.2: pre-ranked long/regret second cuts for exact five-edge exchange.

Candidate-policy-only experiment: same five-opt scheduling as v5.1, same
other kernel versions, and same strict exact-gain acceptance. This module
uses 20 deterministic second-cut samples, prefers high edge regret,
retains an exploratory unranked candidate, and evaluates a wider
five-opt candidate neighborhood for the chosen cuts.
"""
import numpy as np
from numba import njit

@njit
def five_opt_candidate(t,pos,d,nn,cursor=0,starts=14,width=14,
                       samples=20,third_width=12,fourth_width=12):
    """Connected exchange: cut five edges; reorder blocks S3 S1 S4 S2.

    Tour cut positions satisfy i < j < k < l < m. Only an actual
    negative delta is committed; sum of the five replacement edges
    is evaluated with the original TSPLIB EUC_2D integer costs.
    """
    n=len(t)
    if n<32:return 0.,-1
    best_delta=0.
    bi=bj=bk=bl=bm=-1
    a_width=min(width,nn.shape[1])
    c_width=min(third_width,nn.shape[1])
    e_width=min(fourth_width,nn.shape[1])
    for z in range(starts):
        i=(cursor+z*37)%(n-24)
        a=t[i];b=t[i+1]
        ab=float(d[a,b])
        for q in range(a_width):
            f=nn[a,q]
            k=pos[f]-1
            if k<=i+7 or k>=n-6:continue
            e=t[k]
            ef=float(d[e,f])
            span=k-i-3
            if span<=0:continue
            # Keep the four highest-regret second cuts, plus one unbiased
            # deterministic candidate. Neither variant gets information
            # from any prior holdout formula or performance result.
            chosen=np.full(5,-1,dtype=np.int32)
            regret=np.full(4,-1.0e30,dtype=np.float64)
            for p in range(samples):
                j=i+2+((z*29+p*17+q*11)%span)
                if j>=k-1:continue
                c=t[j];d0=t[j+1]
                # An expensive current edge is a plausible profitable cut,
                # especially if each endpoint has much cheaper nearest links.
                penalty=float(d[c,d0])-0.5*(float(d[c,nn[c,0]])+
                                               float(d[d0,nn[d0,0]]))
                for slot in range(4):
                    if penalty>regret[slot]:
                        for down in range(3,slot,-1):
                            regret[down]=regret[down-1]
                            chosen[down]=chosen[down-1]
                        regret[slot]=penalty
                        chosen[slot]=j
                        break
                if p==samples//2:chosen[4]=j
            for slot in range(5):
                j=chosen[slot]
                if j<0:continue
                # Duplicate scan suppression when sample spacings alias.
                duplicate=False
                for earlier in range(slot):
                    if chosen[earlier]==j:duplicate=True
                if duplicate:continue
                c=t[j];d0=t[j+1]
                cd=float(d[c,d0])
                for qh in range(c_width):
                    h=nn[c,qh];l=pos[h]-1
                    if l<=k+1 or l>=n-3:continue
                    g=t[l]
                    gh=float(d[g,h])
                    for qm in range(e_width):
                        jj=nn[e,qm];m=pos[jj]-1
                        if m<=l+1 or m>=n-1:continue
                        ii=t[m]
                        old=ab+cd+ef+gh+float(d[ii,jj])
                        new=(float(d[a,f])+float(d[g,b])+float(d[c,h])+
                             float(d[ii,d0])+float(d[e,jj]))
                        delta=new-old
                        if delta<best_delta-0.001:
                            best_delta=delta
                            bi=i;bj=j;bk=k;bl=l;bm=m
    if bi<0:return 0.,-1
    old=t[bi+1:bm+1].copy()
    write=bi+1
    # S3
    for x in range(bk-bi,bl-bi):
        v=old[x];t[write]=v;pos[v]=write;write+=1
    # S1
    for x in range(0,bj-bi):
        v=old[x];t[write]=v;pos[v]=write;write+=1
    # S4
    for x in range(bl-bi,bm-bi):
        v=old[x];t[write]=v;pos[v]=write;write+=1
    # S2
    for x in range(bj-bi,bk-bi):
        v=old[x];t[write]=v;pos[v]=write;write+=1
    return best_delta,1
