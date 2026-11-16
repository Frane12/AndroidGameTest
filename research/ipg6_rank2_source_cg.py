#!/usr/bin/env python3
"""IPG6 original-source two-round PB derivation: nine nontrivial graph mutexes.

On the EXACT SHA-pinned 45v/300c weighted Petersen source, recognize the
three heavy-job source AMO triangles and derive each by source-ID POL
integer division by two. For nine distinct non-source binary conflicts,
combine THREE original onehot job ALO clauses, THREE original ternary
overweight clauses, and TWO just-derived source triangle bounds.
Divide by THREE and obtain a new graph mutex: ~u+~v >= 1.

These 12 new derivations are NOT discovered by DPLL or CDCL.
However the separate 100-line pure-POL suffix proving global UNSAT
WAS found by structural DPLL; do not mislabel the combined proof as
search-free UNSAT. External VeriPB validates all 112 POL steps
on the unchanged original source. No general polynomial SAT claim.
"""
import argparse,hashlib,itertools,json,pathlib
from ipg4_rup_drat_to_veripb import dimacs

SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def row(c):
    aa=[0]*45;neg=0
    for v in c:
        aa[abs(v)-1]+=1 if v>0 else -1
        neg+=v<0
    return tuple(aa),1-neg

def divide(items,d):
    aa=[sum(v[0][i] for v in items) for i in range(45)]
    b=sum(v[1] for v in items)
    if any(v%d for v in aa):
        raise ValueError("PB source coefficients not divisible by cut divisor")
    return tuple(v//d for v in aa),-((-b)//d)

def source_cuts(clauses):
    ix={}
    for i,c in enumerate(clauses,1):ix.setdefault(frozenset(c),i)
    val=lambda j,m:3*j+m+1
    job_alo={}
    for j in range(15):
        job_alo[j]=ix.get(frozenset(val(j,m) for m in range(3)))
        if job_alo[j] is None:raise ValueError("original ALO group absent")
    triangles=[t for t in itertools.combinations(range(15),3)
        if all(frozenset((-val(a,m),-val(b,m))) in ix
               for a,b in itertools.combinations(t,2) for m in range(3))]
    if len(triangles)!=1:raise ValueError("ambiguous source AMO triangle")
    t=triangles[0]
    orig=[row(c) for c in clauses]
    derived=[];commands=[];records=[];triangle_ids=[]
    for m in range(3):
        parents=[ix[frozenset((-val(a,m),-val(b,m)))]
                 for a,b in itertools.combinations(t,2)]
        actual=divide([orig[cid-1] for cid in parents],2)
        expect=[0]*45
        for j in t:expect[val(j,m)-1]=-1
        if actual!=(tuple(expect),-1):
            raise ValueError("source triangle integer algebra mismatch")
        cmds=[str(parents[0])]
        for cid in parents[1:]:cmds.extend((str(cid),"+"))
        cmds.extend(("2","d"))
        commands.append("pol "+" ".join(cmds)+" ;")
        derived.append(actual);triangle_ids.append(len(clauses)+len(commands))
    for a,b in itertools.combinations(range(15),2):
        if a in t or b in t:continue
        for m in range(3):
            u,v=val(a,m),val(b,m)
            if frozenset((-u,-v)) in ix:continue
            ternary=[ix.get(frozenset((-u,-v,-val(j,m)))) for j in t]
            if any(cid is None for cid in ternary):continue
            parents=[job_alo[j] for j in t]+ternary+[
                     triangle_ids[k] for k in range(3) if k!=m]
            lookup=lambda id_:orig[id_-1] if id_<=len(clauses) else derived[id_-len(clauses)-1]
            actual=divide([lookup(cid) for cid in parents],3)
            expect=[0]*45;expect[u-1]=expect[v-1]=-1
            if actual!=(tuple(expect),-1):
                raise ValueError("rank2 exact PB arithmetic does not derive required mutex")
            cmds=[str(parents[0])]
            for cid in parents[1:]:cmds.extend((str(cid),"+"))
            cmds.extend(("3","d"))
            commands.append("pol "+" ".join(cmds)+" ;")
            derived.append(actual)
            records.append({"source_derived_mutex":[-u,-v],
                            "source_CNF_clause_ids":parents[:6],
                            "source_triangle_cut_ids":parents[6:],
                            "new_veripb_clause_id":len(clauses)+len(commands)})
    if len(commands)!=12 or len(records)!=9:
        raise ValueError("unsupported original source CG2 derivation count")
    return triangles[0],commands,records

def shift_old(lines,initial,shift):
    new=[]
    for line in lines:
        if not line.startswith("pol ") or not line.endswith(" ;"):
            raise ValueError("old proof not POL-only")
        words=line.split()
        for i,v in enumerate(words):
            if v.isdigit() and int(v)>initial and not (
                i+1<len(words) and words[i+1] in ("d","*")):
                words[i]=str(int(v)+shift)
        new.append(" ".join(words))
    return new

def generate(source,older,out,metadata):
    raw,nv,clauses=dimacs(source)
    if hashlib.sha256(raw).hexdigest()!=SHA or nv!=45 or len(clauses)!=300:
        raise ValueError("source not frozen original weighted Petersen")
    triangle,lines,records=source_cuts(clauses)
    old=older.read_text().splitlines()
    if old[:2]!=["pseudo-Boolean proof version 3.0","f 300 ;"] or (
       old[-3:]!=["output NONE ;","conclusion UNSAT ;",
                  "end pseudo-Boolean proof ;"]):
        raise ValueError("unsupported prior standard VeriPB structure")
    old_body=old[2:-3]
    shifted=shift_old(old_body,300,len(lines))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text("\n".join(old[:2]+lines+shifted+old[-3:])+"\n")
    result={"status":"IPG6_SOURCE_RANK2_CUTS_EMITTED_NEEDS_VERIPB",
            "source_sha256":SHA,"source_original_clauses":300,
            "heavy_conflict_jobs_0based":list(triangle),
            "source_rank1_triangle_cuts":3,
            "source_rank2_new_petersen_mutexes":len(records),
            "source_only_cut_lines":len(lines),
            "cut_records":records,
            "total_POL_lines":len(lines)+len(shifted),
            "total_RUP_lines":0,
            "final_UNSAT_suffix_discovered_by_DPLL":True,
            "source_algebra_all_cut_rows_exactly_checked":True,
            "proof_bytes":out.stat().st_size}
    metadata.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--old-pol",required=True,type=pathlib.Path)
    p.add_argument("--proof",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    a=p.parse_args()
    try:
        report=generate(a.cnf,a.old_pol,a.proof,a.meta)
        print("IPG6_RANK2_SOURCE "+json.dumps({
            k:v for k,v in report.items() if k!="cut_records"
        },sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError) as exc:
        a.proof.unlink(missing_ok=True)
        print("IPG6_RANK2_REJECT "+str(exc),flush=True)
        return 1
if __name__=="__main__":raise SystemExit(main())
