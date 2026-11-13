"""Warm-start bounded tree memory with validation-only periodic retirement."""
import copy
import numpy as np

def matrix(model, rows):
    return np.clip((np.array([r['features'] for r in rows])-model['centers'])/model['scales'],-8,8)

def tree_values(w,z):
    left=z[:,int(w[0])]<=w[1]
    return np.where(left,np.where(z[:,int(w[2])]<=w[3],w[6],w[7]),np.where(z[:,int(w[4])]<=w[5],w[8],w[9]))

def scores(model,z):
    result=np.full(len(z),model['bias'],dtype=float)
    for w in model['weights']:result+=tree_values(w,z)
    return result

def decisions(model,rows,threshold=None):
    valid=[i for i,r in enumerate(rows) if r['features'] is not None]
    out=np.zeros(len(rows),bool)
    if not valid:return out
    f=np.array([rows[i]['features'] for i in valid]);raw=(f-model['centers'])/model['scales'];z=np.clip(raw,-8,8)
    pred=(scores(model,z)>(model['threshold'] if threshold is None else threshold)) & (np.max(np.abs(raw),axis=1)<=8)
    forced=f[:,15]!=f[:,16];pred[forced]=f[forced,15]>f[forced,16];out[valid]=pred
    return out

def cost(model,rows,threshold=None):
    chosen=decisions(model,rows,threshold)
    return int(sum(r['flip' if flip else 'base']['work_cost'] for r,flip in zip(rows,chosen)))

def calibrate(model,validation):
    results=[dict(threshold=t,work_cost=cost(model,validation,t)) for t in (1e9,1.,.5,.25,.1,0.)]
    best=min(results,key=lambda r:(r['work_cost'],-r['threshold']))
    return {**model,'threshold':best['threshold'],'tune_cost':best['work_cost'],'threshold_candidates':results}

def grow(previous,rows,active,add_trees=8):
    rr=[r for r in rows if r['label'] is not None]
    if len(rr)<32:raise RuntimeError('insufficient labeled training sources')
    x=np.array([r['features'] for r in rr]);y=np.clip([r['label'] for r in rr],-4,4)
    if previous is None:
        model=dict(kind='tree',bias=float(y.mean()),centers=x.mean(0).tolist(),scales=np.maximum(x.std(0),.05).tolist(),weights=[],threshold=1e9,ood_limit=8.)
    else:model=copy.deepcopy(previous)
    z=matrix(model,rr);pred=scores(model,z);ids=np.arange(len(rr))
    def split(group,target):
        best=(0,1e12,group,np.array([],dtype=int));loss_best=float('inf')
        if len(group)<24:return best
        for j in sorted(active):
            for t in np.unique(np.quantile(z[group,j],[.2,.4,.6,.8])):
                a=group[z[group,j]<=t];b=group[z[group,j]>t]
                if min(len(a),len(b))<12:continue
                loss=np.sum((target[a]-target[a].mean())**2)+np.sum((target[b]-target[b].mean())**2)
                if loss<loss_best:best=(j,float(t),a,b);loss_best=loss
        return best
    for _ in range(add_trees):
        residual=y-pred;j,t,a,b=split(ids,residual);ja,ta,aa,ab=split(a,residual);jb,tb,ba,bb=split(b,residual)
        leaves=[float(.06*residual[g].mean()) if len(g) else 0. for g in (aa,ab,ba,bb)]
        w=[j,t,ja,ta,jb,tb,*leaves];model['weights'].append(w);pred+=tree_values(w,z)
    model['training_pairs']=len(rr)
    return model

def prune(model,tune,periodic):
    m=copy.deepcopy(model);events=[]
    # Keep inference compatible with the unchanged X4.7 native parser (2..64 trees).
    while len(m['weights'])>64:
        options=[]
        for i in range(len(m['weights'])):
            trial={**m,'weights':m['weights'][:i]+m['weights'][i+1:]};options.append(cost(trial,tune))
        i=int(np.argmin(options));events.append(dict(reason='capacity',tree=i,tune_cost=options[i]));del m['weights'][i]
    if periodic:
        for _ in range(8):
            if len(m['weights'])<=2:break
            baseline=cost(m,tune);options=[]
            for i in range(len(m['weights'])):
                options.append(cost({**m,'weights':m['weights'][:i]+m['weights'][i+1:]},tune))
            i=int(np.argmin(options))
            if options[i]>baseline:break
            events.append(dict(reason='no_validation_work_loss',tree=i,before=baseline,after=options[i]));del m['weights'][i]
    used={int(w[j]) for w in m['weights'] for j in (0,2,4)}
    return m,events,used
