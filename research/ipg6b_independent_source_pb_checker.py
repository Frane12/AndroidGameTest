#!/usr/bin/env python3
"""Independent generic integer PB parser for IPG6B source cuts.

Does NOT import the IPG6B producer. Reparse exact original 300 CNF
clauses; interpret first 21 VeriPB POL operations as integer sums plus
division, calculating every resulting canonical linear inequality with
arbitrary precision. The expected source-only statements are 6
three-job at-most-one triangle inequalities and 15 previously absent
binary mutex inequalities, all same-machine and source-novel.

VeriPB 3.0.2 must independently accept the 121-line complete
source proof. No assumptions of SAT/UNSAT label are accepted as proof.
"""
import argparse,hashlib,json,pathlib

SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def source(path):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:
        raise ValueError("source byte checksum mismatch")
    nv=nc=None;clauses=[];c=[]
    for l in raw.decode("ascii").splitlines():
        xs=l.split()
        if not xs or xs[0]=="c":continue
        if xs[0]=="p":
            if nv is not None or len(xs)!=4:raise ValueError("DIMACS header invalid")
            nv=int(xs[2]);nc=int(xs[3]);continue
        for tok in xs:
            v=int(tok)
            if v:c.append(v)
            else:clauses.append(tuple(c));c=[]
    if nv!=45 or nc!=300 or len(clauses)!=300 or c:
        raise ValueError("original source format wrong")
    return clauses

def canonical(c):
    coeff=[0]*45;rhs=1
    for v in c:
        if v<0:coeff[-v-1]-=1;rhs-=1
        else:coeff[v-1]+=1
    return tuple(coeff),rhs

def check(cnf,proof,meta):
    cs=source(cnf)
    data=json.loads(meta.read_text())
    if data.get("source_sha256")!=SHA or data.get("new_source_mutexes")!=15:
        raise ValueError("claimed source proof not from frozen original")
    ls=proof.read_text().splitlines()
    if ls[:2]!=["pseudo-Boolean proof version 3.0","f 300 ;"]:
        raise ValueError("bad source-PB proof header")
    early=ls[2:23]
    if len(early)!=21 or any(not line.startswith("pol ") for line in early):
        raise ValueError("cut prefix is not exactly 21 pure POL steps")
    nodes={i+1:canonical(c) for i,c in enumerate(cs)}
    source_index={frozenset(c) for c in cs}
    proved_binary=set();triangle_count=0;pair_count=0
    for ix,line in enumerate(early,1):
        words=line.split()
        if words[0]!="pol" or words[-1]!=";" or words[-2]!="d":
            raise ValueError("unsupported source CG POL instruction")
        divisor=int(words[-3])
        if divisor not in (2,3):
            raise ValueError("unexpected CG divisor")
        body=words[1:-3]
        if len(body)%2!=1 or any(x!="+" for x in body[2::2]):
            raise ValueError("not a simple original-source addition proof")
        antecedents=[int(body[0])]+[int(x) for x in body[1::2]]
        if len(antecedents)!=(3 if divisor==2 else 8):
            raise ValueError("wrong number source PB antecedents")
        if any(cid not in nodes for cid in antecedents):
            raise ValueError("forward or invalid source-PB antecedent")
        summed=[0]*45;b=0
        for cid in antecedents:
            aa,c=nodes[cid]
            b+=c
            for i,v in enumerate(aa):summed[i]+=v
        if any(x%divisor for x in summed):
            raise ValueError("PB source coefficient not divisible")
        output=tuple(x//divisor for x in summed),-((-b)//divisor)
        neg=[i+1 for i,x in enumerate(output[0]) if x==-1]
        if (output[1]!=-1 or any(x not in (-1,0) for x in output[0]) or
            any((v-1)%3!=(neg[0]-1)%3 for v in neg)):
            raise ValueError("source algebra not a same-machine conflict")
        if divisor==2:
            if len(neg)!=3:raise ValueError("not a proper 3-job triangle bound")
            triangle_count+=1
        else:
            if len(neg)!=2:raise ValueError("not a proper 2-job derived mutex")
            if frozenset((-neg[0],-neg[1])) in source_index:
                raise ValueError("supposed new source mutex already input")
            key=tuple(sorted(neg))
            if key in proved_binary:raise ValueError("duplicate new source-derived graph mutex")
            proved_binary.add(key);pair_count+=1
        nodes[300+ix]=output
    if pair_count!=15 or triangle_count!=6 or len(proved_binary)!=15:
        raise ValueError("incomplete 15-mutex/6-triangle PB source closure")
    if len([l for l in ls if l.startswith("pol ")])!=121 or any(
        l.startswith(("rup ","pbc ")) for l in ls):
        raise ValueError("full original proof not 121 pure POL lines")
    return {"status":"INDEPENDENT_INTEGER_SOURCE_CG_RANK4_VERIFIED",
            "source_sha256":SHA,"source_clauses":300,
            "source_only_POL_lines":21,"rank2_and_rank4_new_graph_mutexes":15,
            "triangle_capacity_bounds":6,"full_POL_lines":121,
            "RUP_lines":0,"global_UNSAT_requires_old_DPLL_discovered_suffix":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",type=pathlib.Path,required=True)
    p.add_argument("--proof",type=pathlib.Path,required=True)
    p.add_argument("--meta",type=pathlib.Path,required=True)
    a=p.parse_args()
    try:
        data=check(a.cnf,a.proof,a.meta)
        print("IPG6B_SOURCE_CG_ACCEPT "+json.dumps(data,sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,KeyError,TypeError,IndexError) as err:
        print("IPG6B_REJECT "+str(err),flush=True)
        return 1
if __name__=="__main__":raise SystemExit(main())
