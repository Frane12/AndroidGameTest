"""DRNAS v5.1 exact five-edge non-reversing exchange, numba JIT."""
from numba import njit

@njit
def five_opt_candidate(t,pos,d,nn,cursor=0,starts=10,width=12,
                       samples=9,third_width=10,fourth_width=10):
    """Cut five tour edges, permute four blocks as S3,S1,S4,S2.

    Original links (A,B),(C,D),(E,F),(G,H),(I,J).
    Replacement (A,F),(G,B),(C,H),(I,D),(E,J).
    Ordered cuts i<j<k<l<m guarantee one Hamiltonian tour.
    """
    n=len(t)
    if n<32:
        return 0.,-1
    best_delta=0.
    bi=bj=bk=bl=bm=-1
    a_width=min(width,nn.shape[1])
    c_width=min(third_width,nn.shape[1])
    e_width=min(fourth_width,nn.shape[1])
    for z in range(starts):
        i=(cursor+z*37)%(n-24)
        a=t[i];b=t[i+1]
        for q in range(a_width):
            f=nn[a,q]
            k=pos[f]-1
            if k<=i+7 or k>=n-6:
                continue
            e=t[k]
            span=k-i-3
            if span<=0:
                continue
            for p in range(samples):
                j=i+2+((z*29+p*17+q*11)%span)
                if j>=k-1:
                    continue
                c=t[j];d0=t[j+1]
                for qh in range(c_width):
                    h=nn[c,qh]
                    l=pos[h]-1
                    if l<=k+1 or l>=n-3:
                        continue
                    g=t[l]
                    for qm in range(e_width):
                        jj=nn[e,qm]
                        m=pos[jj]-1
                        if m<=l+1 or m>=n-1:
                            continue
                        ii=t[m]
                        old=(float(d[a,b])+float(d[c,d0])+float(d[e,f])+
                             float(d[g,h])+float(d[ii,jj]))
                        new=(float(d[a,f])+float(d[g,b])+float(d[c,h])+
                             float(d[ii,d0])+float(d[e,jj]))
                        delta=new-old
                        if delta<best_delta-0.001:
                            best_delta=delta
                            bi=i;bj=j;bk=k;bl=l;bm=m
    if bi<0:
        return 0.,-1
    old=t[bi+1:bm+1].copy()
    write=bi+1
    for x in range(bk-bi,bl-bi):
        v=old[x];t[write]=v;pos[v]=write;write+=1
    for x in range(0,bj-bi):
        v=old[x];t[write]=v;pos[v]=write;write+=1
    for x in range(bl-bi,bm-bi):
        v=old[x];t[write]=v;pos[v]=write;write+=1
    for x in range(bj-bi,bk-bi):
        v=old[x];t[write]=v;pos[v]=write;write+=1
    return best_delta,1
