#!/usr/bin/env python3
"""Source-fixed, planted-SAT circuit/cardinality cohorts for ATLAS2.
Controls use naturally minimal encodings; treatment adds only logically
entailed *superset clauses*, never silently changes SAT semantics.
All source construction is independent of which solver performs best.
"""
import hashlib,json,pathlib,random
FAMILIES=("and_or","xor_parity","exactly_one","mixed_ite")
COHORTS=("minimal","entailed_redundancy")
VERSION="ATLAS2-STRUCTURED-v1-20261111"

def build(family,cohort):
    assert family in FAMILIES and cohort in COHORTS
    seed=int.from_bytes(hashlib.sha256((VERSION+"|"+family+"|"+cohort).encode()).digest()[:8],"big")
    rng=random.Random(seed)
    values={}
    clauses=[]
    next_var=0
    def newvar(value):
        nonlocal next_var
        next_var+=1
        values[next_var]=bool(value)
        return next_var
    def add(c):
        assert c and all(abs(l)<=next_var and l!=0 for l in c)
        assert len(set(map(abs,c)))==len(c)
        assert any(values[abs(l)]==(l>0) for l in c),(family,cohort,c)
        clauses.append(list(c))
    base=[newvar(rng.choice((0,1))) for _ in range(32)]
    pool=base[:]
    blocks=[]
    redundancy=cohort=="entailed_redundancy"

    def extra_clause(parent,used):
        # An entailed *proper* superset clause. Use a fresh/different variable
        # to test 4-input support and NPN mapping, not duplicated CNF copies.
        rest=[v for v in pool if v not in used and v not in set(map(abs,parent))]
        if not rest:return
        pick=rng.choice(rest)
        sup=list(parent)+[pick if rng.getrandbits(1) else -pick]
        assert len(sup)<=4
        add(sup)

    def gate(kind):
        if kind=="ite":
            sel,a,b=rng.sample(pool,3)
            out=newvar(values[a] if values[sel] else values[b])
            local=[
                [-sel,-a,out],[-sel,a,-out],
                [sel,-b,out],[sel,b,-out]
            ]
            used={sel,a,b,out}
        else:
            a,b=rng.sample(pool,2)
            if kind=="and":v=values[a] and values[b]
            elif kind=="or":v=values[a] or values[b]
            elif kind=="xor":v=values[a]^values[b]
            elif kind=="xnor":v=not(values[a]^values[b])
            else:raise ValueError(kind)
            out=newvar(v)
            used={a,b,out}
            if kind=="and":local=[[-a,-b,out],[a,-out],[b,-out]]
            elif kind=="or":local=[[a,b,-out],[-a,out],[-b,out]]
            else:
                local=[]
                for ai in (0,1):
                    for bi in (0,1):
                        wanted=(ai^bi)^(kind=="xnor")
                        for oi in (0,1):
                            if oi==wanted:continue
                            local.append([(-a if ai else a),(-b if bi else b),(-out if oi else out)])
        for c in local:add(c)
        if redundancy and rng.random()<0.83:
            # For gate clauses of width 2/3, add a locally entailed
            # 3/4 literal superset. This is realistic coding redundancy but
            # explicitly controlled, not an external competition benchmark.
            parent=rng.choice([c for c in local if len(c)<=3])
            extra_clause(parent,used)
        pool.append(out)
        blocks.append(dict(kind=kind,output=out,clauses=len(local),redundant=redundancy))
        return out

    def exactly_one(size):
        hot=rng.randrange(size)
        group=[newvar(j==hot) for j in range(size)]
        add(group)
        for i in range(size):
            for j in range(i+1,size):add([-group[i],-group[j]])
        if redundancy:
            # Entailed by any pairwise-negative clause: a wide no-triple.
            add([-v for v in group[:3]])
            if size==4: add([-group[1],-group[2],-group[3]])
        pool.extend(group)
        blocks.append(dict(kind="exactly_one",size=size,clauses=1+size*(size-1)//2,
                           redundant=redundancy))

    if family=="and_or":
        for i in range(74):gate(("and","or")[i%2])
    elif family=="xor_parity":
        for i in range(68):gate(("xor","xnor")[i%2])
    elif family=="exactly_one":
        for i in range(30):exactly_one(3 if i%2 else 4)
        for i in range(22):gate(("and","or","xor")[i%3])
    elif family=="mixed_ite":
        for i in range(70):
            gate(("and","xor","ite","or","xnor")[i%5])

    # Add planted output restrictions without inserting a globally known
    # model into the CNF. The benchmark checks actual returned models.
    outputs=[x["output"] for x in blocks if "output" in x]
    for out in outputs[-8::2]:
        add([out if values[out] else -out])
    # Independent global clauses preserve the same planted model, increasing
    # circuit coupling without making the original CNF equivalent to units.
    for i in range(35):
        a,b,c=rng.sample(pool,3)
        lits=[v if values[v] else -v for v in (a,b,c)]
        # One literal guaranteed true, other polarities vary.
        j=rng.randrange(3)
        for z in range(3):
            if z!=j and rng.randrange(2):lits[z]=-lits[z]
        add(lits)
    assert all(any(values[abs(l)]==(l>0) for l in c) for c in clauses)
    text="p cnf %d %d\n"%(next_var,len(clauses))
    text+="".join(" ".join(map(str,c))+" 0\n" for c in clauses)
    data=text.encode("ascii")
    return dict(family=family,cohort=cohort,version=VERSION,seed=seed,
        variables=next_var,clauses=len(clauses),blocks=len(blocks),
        source_sha256=hashlib.sha256(data).hexdigest(),raw=data,witness=values)

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="mre_atlas2/formula.cnf")
    ap.add_argument("--family",choices=FAMILIES,default="mixed_ite")
    ap.add_argument("--cohort",choices=COHORTS,default="entailed_redundancy")
    a=ap.parse_args()
    d=build(a.family,a.cohort)
    p=pathlib.Path(a.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(d["raw"])
    manifest={k:v for k,v in d.items() if k not in ("raw","witness")}
    p.with_suffix(".source.json").write_text(json.dumps(manifest,indent=2,sort_keys=True))
    print("ATLAS2_SOURCE "+json.dumps(manifest,sort_keys=True))
if __name__=="__main__":main()
