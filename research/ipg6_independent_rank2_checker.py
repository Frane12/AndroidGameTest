#!/usr/bin/env python3
"""Independent original-CNF integer PB checker for nine IPG6 rank2 mutexes.

Does not import the IPG6 producer, LP, RUP, or source graph converter.
Uses independently parsed original source bytes and ordinary integer
arithmetic to replay the exact source clause IDs and the three early
triangle cuts, then checks each claimed rank2 inequality.
The external VeriPB 3.0.2 separately checks the ENTIRE emitted proof.
"""
import argparse,hashlib,json,pathlib,itertools

SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def parse(path):
    content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=SHA:
        raise ValueError("source byte SHA mismatch")
    nv=count=None;clauses=[];pending=[]
    for line in content.decode("ascii").splitlines():
        f=line.split()
        if not f or f[0]=="c":continue
        if f[0]=="p":
            if nv is not None or len(f)!=4 or f[1]!="cnf":
                raise ValueError("bad source header")
            nv,count=int(f[2]),int(f[3])
            continue
        for word in f:
            x=int(word)
            if abs(x)>nv:raise ValueError("out-of-range original literal")
            if x:pending.append(x)
            else:clauses.append(tuple(pending));pending=[]
    if nv!=45 or count!=300 or len(clauses)!=300 or pending:
        raise ValueError("unexpected exact original source format")
    return clauses

def pb(clause):
    v=[0]*45;b=1
    for lit in clause:
        if lit<0:
            v[-lit-1]-=1;b-=1
        else:v[lit-1]+=1
    return tuple(v),b

def sum_divide(inequalities,divider):
    c=[0]*45
    b=0
    for aa,r in inequalities:
        for i,x in enumerate(aa):c[i]+=x
        b+=r
    if any(x%divider for x in c):
        raise ValueError("non-divisible source-PB coefficient")
    return tuple(x//divider for x in c),-((-b)//divider)

def check(source,metadata,proof):
    clauses=parse(source)
    d=json.loads(metadata.read_text())
    if d.get("source_sha256")!=SHA:
        raise ValueError("metadata source SHA not pinned")
    if d.get("source_rank1_triangle_cuts")!=3 or (
        d.get("source_rank2_new_petersen_mutexes")!=9):
        raise ValueError("wrong cut count")
    triangle=d["heavy_conflict_jobs_0based"]
    if triangle!=[9,12,14]:
        raise ValueError("source heavy job group not established")
    cid={frozenset(c):i for i,c in enumerate(clauses,1)}
    vec=lambda j,m:3*j+m+1
    tri=[]
    expected_lines=[]
    for m in range(3):
        parents=[cid[frozenset((-vec(i,m),-vec(j,m)))]
                 for i,j in itertools.combinations(triangle,2)]
        new=sum_divide([pb(clauses[p-1]) for p in parents],2)
        want=[0]*45
        for j in triangle:want[vec(j,m)-1]=-1
        if new!=(tuple(want),-1):
            raise ValueError("rank1 triangle algebra invalid")
        tri.append(new)
        expected_lines.append(f"pol {parents[0]} {parents[1]} + {parents[2]} + 2 d ;")
    proved=set()
    for record in d["cut_records"]:
        lits=record["source_derived_mutex"]
        if len(lits)!=2 or any(x>=0 for x in lits):
            raise ValueError("invalid derived mutex format")
        u,v=map(lambda l:-l,lits)
        if (u-1)%3!=(v-1)%3 or u==v:
            raise ValueError("not same-machine independent selectors")
        if frozenset((-u,-v)) in cid:
            raise ValueError("trivial source clause mislabelled as newly derived")
        if (u,v) in proved:
            raise ValueError("duplicate rank2 target")
        proved.add((u,v))
        m=(u-1)%3
        source_ids=record["source_CNF_clause_ids"]
        derived_ids=record["source_triangle_cut_ids"]
        if len(source_ids)!=6 or derived_ids!=[
            301+k for k in range(3) if k!=m]:
            raise ValueError("wrong source rank2 support")
        expected_source_alo=[
            cid[frozenset((vec(j,0),vec(j,1),vec(j,2)))]
            for j in triangle
        ]
        expected_source_no_goods=[
            cid[frozenset((-u,-v,-vec(j,m)))]
            for j in triangle
        ]
        if source_ids!=expected_source_alo+expected_source_no_goods:
            raise ValueError("source job/packing clauses do not support target")
        eight=[pb(clauses[p-1]) for p in source_ids]+[
            tri[k] for k in range(3) if k!=m]
        actual=sum_divide(eight,3)
        expect=[0]*45;expect[u-1]=expect[v-1]=-1
        if actual!=(tuple(expect),-1):
            raise ValueError("invalid claimed rank2 source-PB inequality")
        expr=str(source_ids[0])
        for p in source_ids[1:]+derived_ids:expr+=" "+str(p)+" +"
        expected_lines.append("pol "+expr+" 3 d ;")
    if len(proved)!=9 or len(expected_lines)!=12:
        raise ValueError("missing original rank2 support")
    lines=proof.read_text().splitlines()
    if lines[:2]!=["pseudo-Boolean proof version 3.0","f 300 ;"]:
        raise ValueError("not original source proof")
    if lines[2:14]!=expected_lines:
        raise ValueError("first 12 source-only CG instructions do not match independent audit")
    if len([line for line in lines if line.startswith("pol ")])!=112 or (
       any(line.startswith(("rup ","pbc ")) for line in lines)):
        raise ValueError("unexpected POL-only full proof format")
    return {"status":"INDEPENDENT_ORIGINAL_SOURCE_RANK2_CG_VERIFIED",
            "source_sha256":SHA,
            "original_clauses":300,
            "new_source_rank1_cuts":3,
            "new_source_rank2_mutexes":9,
            "source_only_PB_lines":12,
            "full_original_PB_lines":112,
            "requires_external_VerIPB_to_certify_UNSAT":True,
            "proof_includes_older_DPLL_discovered_suffix":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",type=pathlib.Path,required=True)
    p.add_argument("--meta",type=pathlib.Path,required=True)
    p.add_argument("--proof",type=pathlib.Path,required=True)
    a=p.parse_args()
    try:
        r=check(a.cnf,a.meta,a.proof)
        print("IPG6_SOURCE_CG_ACCEPT "+json.dumps(r,sort_keys=True),flush=True)
        return 0
    except (KeyError,TypeError,ValueError,OSError,IndexError) as err:
        print("IPG6_SOURCE_CG_REJECT "+str(err),flush=True)
        return 1
if __name__=="__main__":raise SystemExit(main())
