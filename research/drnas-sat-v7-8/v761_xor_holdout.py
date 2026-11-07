#!/usr/bin/env python3
"""V7.6.1 immutable XOR parity holdout (40 UNSAT, 8 SAT), 2026-11-01.

8 cubic-graph sizes x 6 independently salted graphs, fixed before benchmarking.
Unsat labels follow from XORing all vertex equations of a connected cubic
graph: each edge cancels twice, while one inverted RHS makes sum 1.
SAT labels have an explicit constructed solution checked against CNF.
"""
import hashlib,random
import v134_constructive as prior
SALT="DRNAS-V761-XOR-48-LOCKED-INDEPENDENT-20261101-v1"
SIZES=(48,54,60,66,72,78,84,90)
COUNT=48
def make(i):
    assert 0<=i<COUNT
    size=SIZES[i//6]
    variant=i%6
    unsat=variant<5
    rng=random.Random(int(hashlib.sha256((SALT+"/"+str(i)).encode()).hexdigest(),16))
    edges=prior.graph(size,rng)
    inc=[[] for _ in range(size)]
    for j,(u,v) in enumerate(edges,1):
        inc[u].append(j);inc[v].append(j)
    witness={j:bool(rng.getrandbits(1)) for j in range(1,len(edges)+1)}
    rhs=[sum(witness[j] for j in incident)%2 for incident in inc]
    if unsat:rhs[0]^=1
    cs=[]
    for incident,parity in zip(inc,rhs):
        assert len(incident)==3
        for bits in range(8):
            values=[bool((bits>>j)&1) for j in range(3)]
            if sum(values)%2==parity:continue
            cs.append(tuple(-v if val else v for v,val in zip(incident,values)))
    label="UNSAT" if unsat else "SAT"
    if unsat:
        assert sum(rhs)%2==1
        assert len(edges)*2==size*3
        proof={"kind":"odd_global_parity","sum_rhs_mod2":1,"vertices":size,"edges":len(edges)}
    else:
        assert sum(rhs)%2==0 and prior.valid(cs,witness)
        proof={"kind":"explicit_sat_witness","vertices":size,"edges":len(edges)}
    data=prior.dimacs(len(edges),cs)
    entry={"id":f"v761/xor/{i:02d}","family":"cubic_xor_unsat" if unsat else "cubic_xor_sat",
           "source":"synthetic","index":i,"graph_vertices":size,"official_label":label,
           "variables":len(edges),"clauses":len(cs),"proof":proof,
           "sha256":hashlib.sha256(data).hexdigest()}
    return entry,data
def selftest(prior_sha=None):
    arr=[make(i)[0] for i in range(COUNT)]
    assert len({r["sha256"] for r in arr})==COUNT
    assert sum(x["official_label"]=="UNSAT" for x in arr)==40
    assert sum(x["official_label"]=="SAT" for x in arr)==8
    if prior_sha:
        assert not set(x["sha256"] for x in arr)&set(prior_sha)
    for i in [0,5,6,18,29,47]:
        assert make(i)==make(i)
    print("V761_XOR_48_GENERATOR_SELFTEST_PASS",flush=True)
if __name__=="__main__":selftest()
