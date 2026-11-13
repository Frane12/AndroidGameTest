"""X4.12 frozen two-stage linear policy.

Stage 1: context probability estimated from matched completed counterfactuals.
Stage 2: predicted net search-work gain in propagation units / baseline work,
after a fixed overhead proxy. No family names or target labels are used at inference.
"""
import numpy as np

NF=30
SEED=4121311
PROXY=300


def features_and_targets(rows):
    rr=[r for r in rows if r.get('label') is not None and
        r.get('features') is not None and len(r['features'])==NF]
    if len(rr)<80:raise RuntimeError('not enough complete training pairs')
    x=np.array([r['features'] for r in rr],dtype=float)
    gain=np.array([r['base']['remaining_propagations']-
                   r['flip']['remaining_propagations']-PROXY for r in rr],dtype=float)
    baseline=np.array([max(1000.,r['base']['remaining_propagations']) for r in rr],dtype=float)
    targets=np.clip(gain/baseline,-2.0,2.0)
    label=(gain>0).astype(float)
    return rr,x,label,targets


def fit(rows):
    rr,x,label,target=features_and_targets(rows)
    center=x.mean(axis=0)
    scale=np.maximum(x.std(axis=0),.05)
    z=np.clip((x-center)/scale,-8,8)
    design=np.column_stack((z,np.ones(len(z))))
    # Give each training family equal weight; no holdout or validation statistics.
    family=np.array([r['family'] for r in rr])
    weights=np.array([1.0/max(1,np.count_nonzero(family==f)) for f in family])
    weights*=len(weights)/weights.sum()
    # Weighted, regularized logistic regression for stage-1 sign.
    beta=np.zeros(NF+1,dtype=float)
    beta[-1]=float(np.log((label.sum()+.5)/(len(label)-label.sum()+.5)))
    reg=np.eye(NF+1)*12.0
    reg[-1,-1]=1.0
    for _ in range(16):
        score=np.clip(design@beta,-25,25)
        prob=1/(1+np.exp(-score))
        gradient=design.T@(weights*(label-prob))-reg@beta
        curvature=np.maximum(prob*(1-prob),1e-5)
        hessian=design.T@((weights*curvature)[:,None]*design)+reg
        beta+=np.linalg.solve(hessian,gradient)
    # The gain is a signed, capped net-benefit estimate, not SAT distance.
    rreg=np.eye(NF+1)*22
    rreg[-1,-1]=2
    gamma=np.linalg.solve(design.T@(weights[:,None]*design)+rreg,
                          design.T@(weights*target))
    return dict(centers=center.tolist(),scales=scale.tolist(),
                gate_weights=beta.tolist(),gain_weights=gamma.tolist(),
                gate_threshold=.5,gain_threshold=0.,ood_limit=8.,
                min_conflicts=0,min_propagations=0,
                train_pairs=len(rr),positive_train=int(label.sum()),
                train_families=sorted(set(family)))


def scores(model,features):
    if features is None or len(features)!=NF:return dict(gate=0.,gain=0.,ood=True)
    z=(np.asarray(features,dtype=float)-model['centers'])/model['scales']
    ood=bool(np.max(np.abs(z))>model['ood_limit'])
    z=np.clip(z,-model['ood_limit'],model['ood_limit'])
    # Logistic is a model score, not calibrated certainty on unseen families.
    logit=float(np.append(z,1.)@np.asarray(model['gate_weights']))
    gate=float(1./(1.+np.exp(-np.clip(logit,-50,50))))
    gain=float(np.append(z,1.)@np.asarray(model['gain_weights']))
    return dict(gate=gate,gain=gain,ood=ood)


def choose(model,features,prefix_conflicts=0,prefix_propagations=0):
    if prefix_conflicts<model['min_conflicts'] or prefix_propagations<model['min_propagations']:
        return False
    s=scores(model,features)
    return bool(not s['ood'] and s['gate']>=model['gate_threshold']
                and s['gain']>model['gain_threshold'])


def write_model(path,model):
    header=(f"X4121 {NF} {model['gate_threshold']:.17g} "
            f"{model['gain_threshold']:.17g} {model['ood_limit']:.17g} "
            f"{model['min_conflicts']} {model['min_propagations']}")
    lines=[header]
    for key in ('centers','scales','gate_weights','gain_weights'):
        values=model[key]
        if len(values)!=(NF+1 if key.endswith('_weights') else NF):
            raise ValueError('invalid model length '+key)
        if not np.isfinite(values).all():raise ValueError('nonfinite '+key)
        lines.append(' '.join(f'{float(n):.17g}' for n in values))
    path.write_text('\n'.join(lines)+'\n')
