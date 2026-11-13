"""X4.9: freeze compact 30-feature zero-probe classifier, no held-out tuning."""
import numpy as np

NF=30

def fit(rows):
    rr=[r for r in rows if r['label'] is not None]
    if len(rr)<80:raise RuntimeError('insufficient complete training pairs')
    x=np.array([r['features'] for r in rr]);y=np.clip([r['label'] for r in rr],-4,4)
    center=x.mean(axis=0);scale=np.maximum(x.std(axis=0),.05)
    z=np.clip((x-center)/scale,-8,8)
    common=dict(centers=center.tolist(),scales=scale.tolist(),threshold=1e9,ood_limit=8.,training_pairs=len(rr),bias=0.)
    za=np.column_stack((z,np.ones(len(z))))
    rng=np.random.default_rng(471311);families=sorted(set(r['family'] for r in rr));weights=[]
    for member in range(9):
        chosen=families if member==0 else rng.choice(families,len(families),replace=True)
        ii=[i for f in chosen for i,r in enumerate(rr) if r['family']==f]
        a=za[ii];b=y[ii];reg=np.eye(NF+1)*8;reg[-1,-1]=.01
        weights.append(np.linalg.solve(a.T@a+reg,a.T@b).tolist())
    ridge={**common,'kind':'ridge','weights':weights}
    # Thirty-two fixed-depth trees. Split candidates and minimum leaf size fixed before validation.
    def split(ids,target):
        default=(0,1e12,ids,np.array([],dtype=int));best=float('inf');answer=default
        if len(ids)<16:return answer
        for j in range(NF):
            for t in np.unique(np.quantile(z[ids,j],[.15,.3,.5,.7,.85])):
                left=ids[z[ids,j]<=t];right=ids[z[ids,j]>t]
                if min(len(left),len(right))<8:continue
                loss=np.sum((target[left]-target[left].mean())**2)+np.sum((target[right]-target[right].mean())**2)
                if loss<best:best=loss;answer=(j,float(t),left,right)
        return answer
    bias=float(y.mean());pred=np.full(len(y),bias);trees=[];ids=np.arange(len(y))
    for _ in range(32):
        residual=y-pred;j,t,left,right=split(ids,residual)
        jl,tl,ll,lr=split(left,residual);jr,tr,rl,rrr=split(right,residual)
        leaves=[float(.08*residual[g].mean()) if len(g) else 0. for g in (ll,lr,rl,rrr)]
        for g,v in zip((ll,lr,rl,rrr),leaves):pred[g]+=v
        trees.append([j,t,jl,tl,jr,tr,*leaves])
    return {'ridge':ridge,'tree':{**common,'kind':'tree','bias':bias,'weights':trees}}

def predict(model,features):
    if features is None:return 0.,True
    z=(np.array(features)-model['centers'])/model['scales'];ood=bool(np.max(np.abs(z))>8);z=np.clip(z,-8,8)
    if model['kind']=='ridge':
        scores=np.array(model['weights'])@np.append(z,1);return float(scores.mean()-scores.std()),ood
    score=model['bias']
    for w in model['weights']:
        left=z[int(w[0])]<=w[1];off=2 if left else 4;inner=z[int(w[off])]<=w[off+1]
        score+=w[(6 if left else 8)+(0 if inner else 1)]
    return float(score),ood

def choose(model,features):
    if features is None:return False
    if len(features)!=NF:return False
    score,ood=predict(model,features)
    return not ood and score>model['threshold']

def select_threshold(model,validation):
    candidates=[]
    for t in (1e9,1.,.5,.25,.1,0.):
        m={**model,'threshold':t};choices=[choose(m,r['features']) for r in validation]
        cost=sum(r['flip' if flip else 'base']['work_cost'] for r,flip in zip(validation,choices))
        candidates.append(dict(threshold=t,work_cost=cost,flips=sum(choices)))
    best=min(candidates,key=lambda r:(r['work_cost'],-r['threshold']))
    return {**model,'threshold':best['threshold'],'validation_candidates':candidates,'validation_work_cost':best['work_cost']}

def write_model(path,m):
    lines=[f"X491 {NF} {len(m['weights'])} {m['threshold']:.17g} {m['ood_limit']} {m['kind']} {m['bias']:.17g} {m.get('min_conflicts',0)}"]
    for row in [m['centers'],m['scales'],*m['weights']]:lines.append(' '.join(format(x,'.17g') for x in row))
    path.write_text('\n'.join(lines)+'\n')
