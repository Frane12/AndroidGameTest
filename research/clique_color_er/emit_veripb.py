#!/usr/bin/env python3
"""Source-backed CLIQUE-COLORING RED+RUP-hints+CP VeriPB 3.0 exporter.

This is an *extension* proof using fresh variables representing
Q_i,u,z = P_i,u AND C_u,z and Y_i,z = OR_u Q_i,u,z. Definitions are
introduced with checker-verified RED witnesses, all implications are
checked by RUP with explicit source/derived-clause hints, and a
cutting-planes pigeonhole contradiction ends the proof.

The original source schema is rechecked without filename or outcome labels.
Emitting proof is NOT sufficient for accepted UNSAT: external VeriPB 3.0.2
MUST print VERIFIED UNSATISFIABLE on unchanged original source.
No CDCL, no parallel solvers, no novel proof-complexity theorem claim.
"""
import argparse,collections,hashlib,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from source_check import recover,Unsupported

def need(ok,why):
    if not ok:raise Unsupported(why)

def compile_source(raw,max_steps=1000000,max_proof_bytes=128000000):
    t=time.perf_counter()
    src=recover(raw)
    nv,n,k,c=src["nv"],src["n"],src["k"],src["c"]
    P,C,edges,clauses=src["P"],src["C"],src["edges"],src["clauses"]
    estimated_pairs=k*(k-1)//2*c*n*n
    need(estimated_pairs<=max_steps,"bounded RUP-clause search/size policy")
    index={}
    for i,row in enumerate(clauses,1):
        index.setdefault(frozenset(row),i)
    proof=["pseudo-Boolean proof version 3.0",f"f {len(clauses)} ;"]
    last=len(clauses)
    counts=collections.Counter()

    def clause(lits):
        return " ".join("1 "+("~" if v<0 else "")+"x"+str(abs(v))
                        for v in lits)+" >= 1"

    def red(lits,var,setting):
        nonlocal last
        proof.append("red "+clause(lits)+f" : x{var} -> {setting} ;")
        last+=1;counts["red"]+=1
        return last

    def rup(lits,hints):
        nonlocal last
        proof.append("rup "+clause(lits)+
                     " : ~ "+" ".join(map(str,hints))+" ;")
        last+=1;counts["rup"]+=1
        return last

    def pol(parts):
        nonlocal last
        proof.append("pol "+" ".join(map(str,parts))+" ;")
        last+=1;counts["pol"]+=1
        return last

    Q={};Qid={};Y={};Yid={};next_var=nv+1
    for i in range(k):
        for u in range(n):
            for z in range(c):
                q=next_var;next_var+=1;Q[i,u,z]=q
                qp=red((-q,P[i][u]),q,0)
                qc=red((-q,C[u][z]),q,0)
                qpc=red((q,-P[i][u],-C[u][z]),q,1)
                Qid[i,u,z]=(qp,qc,qpc)
    for i in range(k):
        for z in range(c):
            y=next_var;next_var+=1;Y[i,z]=y
            forwards=[red((-Q[i,u,z],y),y,1) for u in range(n)]
            backward=red((-y,)+tuple(Q[i,u,z] for u in range(n)),y,0)
            Yid[i,z]=(forwards,backward)

    # Under P_i,u and all Y_i,* false, source-color ALO conflicts.
    # Under all Y_i,* false, these guarded ALOs force every P_i,u false,
    # contradicting the original position-ALO source clause.
    alo={}
    for i in range(k):
        colors=tuple(Y[i,z] for z in range(c))
        derived=[]
        for u in range(n):
            hints=[]
            for z in range(c):
                hints.extend((Yid[i,z][0][u],Qid[i,u,z][2]))
            hints.append(index[frozenset(C[u])])
            derived.append(rup((-P[i][u],)+colors,hints))
        derived.append(index[frozenset(P[i])])
        alo[i]=rup(colors,derived)

    # Under Q_i,u,z and Q_j,v,z: original injection (u==v) or
    # original clique-edge + original edge-color clauses (u!=v)
    # unit-propagate to contradiction. Eliminate v choices to get
    # ~Q_i,u,z OR ~Y_j,z, then eliminate u to get ~Y_i,z OR ~Y_j,z.
    forbidden={}
    for z in range(c):
        for i in range(k):
            for j in range(i+1,k):
                qy=[]
                for u in range(n):
                    disallow=[]
                    for v in range(n):
                        hints=list(Qid[i,u,z][:2])
                        hints.append(Qid[j,v,z][0])
                        if u==v:
                            hints.append(index[frozenset((-P[i][u],-P[j][u]))])
                        else:
                            hints.append(Qid[j,v,z][1])
                            edge=edges[tuple(sorted((u,v)))]
                            hints.append(index[frozenset((-P[i][u],-P[j][v],edge))])
                            hints.append(index[frozenset((-edge,-C[u][z],-C[v][z]))])
                        disallow.append(rup((-Q[i,u,z],-Q[j,v,z]),hints))
                    qy.append(rup((-Q[i,u,z],-Y[j,z]),
                                  disallow+[Yid[j,z][1]]))
                forbidden[i,j,z]=rup((-Y[i,z],-Y[j,z]),
                                     qy+[Yid[i,z][1]])

    # Cutting-planes clique inequalities: for each color z,
    # sum_{i=1}^k ~Y_i,z >= k-1, derived by weighted AMO induction.
    bounds=[]
    for z in range(c):
        previous=forbidden[0,1,z]
        for r in range(3,k+1):
            fresh=r-1;parts=[str(previous)]
            if r-2!=1:parts.extend([str(r-2),"*"])
            for prior in range(fresh):
                parts.extend([str(forbidden[prior,fresh,z]),"+"])
            parts.extend([str(r-1),"d"])
            previous=pol(parts)
        bounds.append(previous)

    # k position-ALOs plus c color-amo-clique bounds sum to
    # 0 >= k-c = 1 since k=c+1. Standard external checker decides.
    parts=[str(alo[0])]
    for i in range(1,k):parts.extend([str(alo[i]),"+"])
    for b in bounds:parts.extend([str(b),"+"])
    pol(parts)
    proof.extend(["output NONE ;","conclusion UNSAT ;",
                  "end pseudo-Boolean proof ;"])
    content="\n".join(proof)+"\n"
    need(len(content.encode())<=max_proof_bytes,"proof byte budget")
    return content,{"status":"EMITTED_EXTERNAL_VERIPB_REQUIRED",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "original_vars":nv,"original_clauses":len(clauses),
        "graph_vertices":n,"clique_size":k,"colors":c,
        "fresh_extension_vars":next_var-(nv+1),
        "steps":dict(counts),"RUP_hints":True,
        "proof_bytes":len(content.encode()),
        "emission_cpu_wall_s":round(time.perf_counter()-t,6),
        "mathematical_method":"extended-resolution-style RED plus source RUP and CP PHP",
        "not_CDCL":True,"external_checker_required":True,
        "not_claiming_polynomial_general_SAT":True}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cnf",required=True,type=pathlib.Path)
    ap.add_argument("--pbp",required=True,type=pathlib.Path)
    ap.add_argument("--meta",required=True,type=pathlib.Path)
    ap.add_argument("--max-steps",type=int,default=1000000)
    args=ap.parse_args()
    try:
        raw=args.cnf.read_bytes()
        proof,meta=compile_source(raw,max_steps=args.max_steps)
        args.pbp.parent.mkdir(parents=True,exist_ok=True)
        args.pbp.write_text(proof)
        args.meta.write_text(json.dumps(meta,sort_keys=True,indent=2)+"\n")
        print("CLIQUE_COLOR_ER_EMITTED "+json.dumps(meta,sort_keys=True),flush=True)
        return 0
    except (Unsupported,ValueError,TypeError,UnicodeError,OSError,
            OverflowError,IndexError,KeyError) as error:
        args.pbp.unlink(missing_ok=True)
        args.meta.unlink(missing_ok=True)
        print("CLIQUE_COLOR_ER_UNKNOWN "+str(error),flush=True)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
