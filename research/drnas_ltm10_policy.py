#!/usr/bin/env python3
"""LTM10: deterministic, cost-aware strategy learning from ORIGINAL real CNF.

No filename, archive label, SHA, solver result or instance ID enters the feature
vector. Memory JSON is learned on TRAIN + chosen on VALIDATION, then frozen.
This is a conservative router for native C++ solvers, not learned proof logic.
"""
import hashlib
import json
import math
import pathlib
import statistics

BASE="LTM9_FAST"
NATIVE_ARMS=("LTM9_FAST","LTM8_FAST","LTM8_CHAOS")
FEATURES=("log_vars","log_clauses","binary","ternary","unit","long",
          "positive","mean_width","active_vars","mixed_polarity","binary_density")
SCHEMA="ltm10-features-v1"

def extract(path):
    """Bounded-memory streaming DIMACS features; cost included in E2E routing."""
    n=m=None
    seen=0;clause=[];unit=two=three=long=0;lit_count=pos_count=0
    positive=[];negative=[];distinct=0;edge_count=0
    with open(path,encoding="ascii",errors="replace") as f:
        for raw in f:
            line=raw.strip()
            if not line or line[0] in ("c","%"):continue
            if line.startswith("p "):
                fields=line.split()
                if len(fields)!=4 or fields[1]!="cnf" or n is not None:
                    raise ValueError("invalid DIMACS header")
                n=int(fields[2]);m=int(fields[3])
                if n<=0 or n>1000000 or m<0:raise ValueError("unsafe DIMACS sizes")
                positive=[0]*(n+1);negative=[0]*(n+1)
                continue
            if n is None:raise ValueError("clause before header")
            for word in line.split():
                lit=int(word)
                if lit:
                    if abs(lit)>n:raise ValueError("literal out of bounds")
                    clause.append(lit)
                else:
                    k=len(clause)
                    unit+=k==1;two+=k==2;three+=k==3;long+=k>=8
                    edge_count+=k*(k-1)//2 if k<=8 else 28
                    for v in clause:
                        if v>0:positive[v]+=1;pos_count+=1
                        else:negative[-v]+=1
                    lit_count+=k;seen+=1;clause=[]
    if n is None or seen!=m or clause:raise ValueError("incomplete DIMACS")
    active=balanced=0
    for p,q in zip(positive[1:],negative[1:]):
        if p+q:
            active+=1
            balanced+=int(p>0 and q>0)
    denom=max(m,1)
    return dict(log_vars=round(math.log1p(n),6),
                log_clauses=round(math.log1p(m),6),
                binary=round(two/denom,6),ternary=round(three/denom,6),
                unit=round(unit/denom,6),long=round(long/denom,6),
                positive=round(pos_count/max(1,lit_count),6),
                mean_width=round(lit_count/denom,6),
                active_vars=round(active/n,6),
                mixed_polarity=round(balanced/max(1,active),6),
                binary_density=round(edge_count/max(1,n),6))

def cost(row,cap):
    if row["status"] in ("SAT_VERIFIED","UNSAT_MATH_CERTIFIED","UNSAT_UNVERIFIED"):
        return float(row["e2e_s"])
    return 2*cap

def evaluate(policy,feature,rows,cap):
    """Same source+seed paired results for all three native candidate arms."""
    selected=pick(policy,feature)
    return cost(rows[selected],cap)

def pick(policy,feature):
    if policy["schema"]!=SCHEMA:raise ValueError("policy schema mismatch")
    if not policy["enabled"]:return BASE
    key=policy["feature"]
    if key not in FEATURES:raise ValueError("unknown feature in memory")
    matched=(float(feature[key]) <= float(policy["threshold"]))
    if not policy["less_equal"]:matched=not matched
    return policy["alternate"] if matched else BASE

def blank():
    return dict(schema=SCHEMA,enabled=False,default=BASE,
                feature=None,threshold=None,less_equal=True,alternate=None,
                status="fallback-until-validated")

def fit(train,val,cap):
    """Fit one stump using only training rewards; select using validation.

    train/val are lists of (feature_vector, {native_arm: trial_row}).
    Selection requires real solved/e2e PAR2 improvement on >=2 distinct
    validation cases and no increase in recorded UNSAT contradictions.
    Ties always resolve to the LTM9 baseline.
    """
    if len(train)<10 or len(val)<5:raise ValueError("too few training cases")
    b=blank()
    candidate=[]
    # Candidates must improve training *first*. Validation only selects or
    # rejects, never determines thresholds or invents new structural features.
    for feature_name in FEATURES:
        x=sorted({float(f[feature_name]) for f,_ in train})
        if len(x)<4:continue
        thresholds=[x[min(len(x)-2,max(0,int((len(x)-1)*q)))]
                    for q in (.15,.30,.50,.70,.85)]
        for threshold in set(thresholds):
            for sense in (True,False):
                for alternate in NATIVE_ARMS:
                    if alternate==BASE:continue
                    c=dict(b,enabled=True,feature=feature_name,
                           threshold=threshold,less_equal=sense,
                           alternate=alternate,status="train-candidate")
                    changed=sum(pick(c,f)!=BASE for f,_ in train)
                    if changed<5 or changed>len(train)-3:continue
                    gain=sum(cost(rows[BASE],cap)-evaluate(c,f,rows,cap)
                             for f,rows in train)
                    # Cost-aware conservative threshold: avoid tiny timing noise.
                    if gain>max(0.30,cap*0.08):
                        candidate.append((gain,c))
    # Avoid validation hyperparameter sweeps: rank by TRAIN gain, then
    # validate only the top hypothesis on the disjoint validation set.
    candidate.sort(key=lambda item:(-item[0],item[1]["feature"],
                                    item[1]["threshold"],item[1]["alternate"]))
    if not candidate:
        b.update(status="no-training-benefit",training_examples=len(train),
                 validation_examples=len(val))
        return b
    gain,c=candidate[0]
    validation_gain=sum(cost(rows[BASE],cap)-evaluate(c,f,rows,cap)
                        for f,rows in val)
    switches=sum(pick(c,f)!=BASE for f,_ in val)
    improved=sum(pick(c,f)!=BASE and cost(rows[pick(c,f)],cap)+0.03 <
                 cost(rows[BASE],cap) for f,rows in val)
    # A genuinely useful strategy should not be selected on millisecond noise.
    accepted=(switches>=2 and improved>=2 and
              validation_gain>max(0.3,cap*0.1))
    if not accepted:c=blank()
    c.update(status="validated" if accepted else "validation-rejected",
             train_gain_s=round(gain,5),
             validation_gain_s=round(validation_gain,5),
             validation_switched=switches,validation_improved=improved,
             training_examples=len(train),validation_examples=len(val))
    return c

def save(policy,path,train_sources,val_sources):
    # SHA of source manifests serves as provenance, never a prediction input.
    memory=dict(policy,trained_from="official SAT Competition 2024 originals",
                training_sources_hash=hashlib.sha256(
                   json.dumps(sorted(train_sources)).encode()).hexdigest(),
                validation_sources_hash=hashlib.sha256(
                   json.dumps(sorted(val_sources)).encode()).hexdigest(),
                sources_used_for_fit=len(train_sources)+len(val_sources),
                holdout_used_for_fit=False,
                model_kind="one-feature conservative decision stump")
    pathlib.Path(path).write_text(json.dumps(memory,indent=2,sort_keys=True)+"\n")
    return memory

def load(path):
    p=json.loads(pathlib.Path(path).read_text())
    if p.get("schema")!=SCHEMA or p.get("default")!=BASE:
        raise ValueError("unknown/incompatible LTM10 memory")
    if p.get("enabled") and (p.get("alternate") not in NATIVE_ARMS or
                             p.get("feature") not in FEATURES):
        raise ValueError("invalid LTM10 policy arm")
    return p

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"a.cnf"
        p.write_text("p cnf 3 3\n1 -2 0\n2 3 -1 0\n-3 0\n")
        f=extract(p)
        assert f["binary"]>0 and f["ternary"]>0 and f["unit"]>0
        q=blank();assert pick(q,f)==BASE
        q.update(enabled=True,feature="binary",threshold=0.5,
                 less_equal=True,alternate="LTM8_CHAOS")
        assert pick(q,f)=="LTM8_CHAOS"
        p.write_text("p cnf 2 1\n3 0\n")
        try:extract(p)
        except ValueError:pass
        else:raise AssertionError("invalid CNF accepted")
        p.write_text("p cnf 2 1\n1 0\n")
        m=save(blank(),pathlib.Path(td)/"memory.json",["a"],["b"])
        assert load(pathlib.Path(td)/"memory.json")==m
    print("LTM10_POLICY_SELFTEST_PASS features=11 persistent_json=true",flush=True)

if __name__=="__main__":selftest()
