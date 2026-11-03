#!/usr/bin/env python3
"""R30 Phase A: proof-safe passive correlation between structure and CDCL.

Read-only native snapshots from pinned Kissat at conflict-free propagation
boundaries. Compare unit propagation and certified GF(2) implications from
the same externally exported trail *projection*. No decision is ever sent
back to the monitored solver. Explicit guard exclusions and instrumentation
overhead are recorded. Learned clauses are counted, not falsely asserted to
be identified parity equations.
"""
import argparse, collections, csv, hashlib, json, os, random, re, statistics
import subprocess, sys, time
from pathlib import Path

PROTO="DRNAS-R30-PASSIVE-CDCL-GF2-20261103-v1"
SALT="DRNAS-R30-NEW-UNSEEN-INPUT-SALT-NOV03-2026-v1"
UPSTREAM="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
REPS=2
CAP=5.0
SHARDS=4
MAX_VARS=1024
MAX_CLAUSES=10000
MAX_SIZE=8*1024*1024
MODES=("Kissat_clean","Kissat_R30_passive")
FAMILIES=("xor3_visible","xor3_hidden","xor3_mixed","parity_bridge",
          "random3_critical","xor_decoy")
PER_FAMILY=4
OFFICIAL_SAMPLE_ROLES=("previously_measured_development","r28_additional_original_holdout")

def check(x,reason):
    if not x:raise RuntimeError("R30_AUDIT_ERROR "+reason)
def digest(s):
    h=hashlib.sha256()
    if isinstance(s,Path):
        with s.open("rb") as f:
            for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    else:h.update(s)
    return h.hexdigest()
def seed(family,idx):
    return random.Random(int(digest((SALT+"/"+family+"/"+str(idx)).encode()),16))
def xor_clauses(vs,rhs):
    clauses=[]
    for mask in range(1<<len(vs)):
        if (mask.bit_count()&1)!=rhs:
            clauses.append([-v if mask>>j&1 else v for j,v in enumerate(vs)])
    return clauses
def connected_parity(family,idx,rng):
    size=48+8*(idx%2)
    ring={tuple(sorted((v,(v+1)%size))) for v in range(size)}
    for _ in range(200):
        perm=list(range(size));rng.shuffle(perm)
        match={tuple(sorted((perm[j],perm[j+size//2]))) for j in range(size//2)}
        if not ring.intersection(match) and len(match)==size//2:break
    else:raise RuntimeError("No cubic matching")
    edges=sorted(ring|match)
    incident=[[] for _ in range(size)]
    for k,(a,b) in enumerate(edges,1):
        incident[a].append(k);incident[b].append(k)
    check(all(len(v)==3 for v in incident),"Invalid cubic graph")
    witness={v:rng.getrandbits(1) for v in range(1,len(edges)+1)}
    rhs=[sum(witness[v] for v in row)&1 for row in incident]
    unsat=(idx%2==0 and family!="xor_decoy")
    if unsat:rhs[0]^=1
    original=[cl for vs,p in zip(incident,rhs) for cl in xor_clauses(vs,p)]
    n=len(edges)
    if family=="xor_decoy":
        # Drop one of four required parity CNF clauses per vertex.
        original=[cl for k,cl in enumerate(original) if k%4!=0]
        check(all(any((x>0)==bool(witness[abs(x)]) for x in c) for c in original),
              "Decoy witness invalid")
    if family in ("xor3_hidden","xor3_mixed"):
        # Split each parity clause by an auxiliary variable; (a v t)
        # AND (!t v b v c) resolves exactly to (a v b v c).
        hidden=[]
        for cl in original:
            c=cl[:]
            rng.shuffle(c)
            n+=1
            hidden.extend([[c[0],n],[-n]+c[1:]])
        original=hidden
    if family=="xor3_mixed":
        for j in range(20):
            vs=rng.sample(range(1,len(edges)+1),3)
            cl=[v if rng.getrandbits(1) else -v for v in vs]
            if not unsat and not any((lit>0)==bool(witness[abs(lit)]) for lit in cl):
                cl[0]*=-1
            original.append(cl)
    rng.shuffle(original)
    return n,original,"UNSAT" if unsat else "SAT"
def parity_bridge(idx,rng):
    groups=4+(idx%3)
    clauses=[]
    for g in range(groups):
        x,y,z,w=(4*g+1,4*g+2,4*g+3,4*g+4)
        clauses+=xor_clauses([x,y,z],0)
        clauses+=xor_clauses([x,y,w],1)
        clauses.append([-z])
    rng.shuffle(clauses)
    return 4*groups,clauses,"SAT"
def generate(fam,idx):
    rng=seed(fam,idx)
    if fam=="parity_bridge":return parity_bridge(idx,rng)
    if fam=="random3_critical":
        n=220+20*(idx%2)
        clauses=[]
        for j in range(round(n*4.23)):
            vs=rng.sample(range(1,n+1),3)
            clauses.append([v if rng.getrandbits(1) else -v for v in vs])
        return n,clauses,None
    return connected_parity(fam,idx,rng)
def freeze(out, official):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for fam in FAMILIES:
        for idx in range(PER_FAMILY):
            n,clauses,expected=generate(fam,idx)
            name=f"{fam}_{idx:02d}.cnf"
            raw=(f"p cnf {n} {len(clauses)}\n"+
                 "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
            (out/name).write_bytes(raw)
            cases.append(dict(file=name,family=fam,expected=expected,
                              vars=n,clauses=len(clauses),
                              bytes=len(raw),sha256=digest(raw),source="R30_new_SHA_salt"))
    if official:
        src=Path(official)
        archive=json.loads((src/"manifest.json").read_text())
        check(archive.get("protocol")=="DRNAS-R28-AND-XOR-PHASE-AB-AUDIT-20261103-v1",
              "Incorrect original official archive")
        selected=( [x for x in archive["cases"] if x["role"]=="previously_measured_development"][:2]
                  +[x for x in archive["cases"] if x["role"]=="r28_additional_original_holdout"][:2] )
        check(len(selected)==4 and len({x["sha256"] for x in selected})==4,
              "Expected two development plus two previously-held-out original GBD cases")
        for idx,c in enumerate(selected):
            p=src/c["path"]
            check(digest(p)==c["sha256"],"Official original source SHA mismatch")
            data=p.read_bytes()
            if data.startswith(b"\xfd7zXZ\x00"):
                import lzma
                data=lzma.decompress(data)
            elif data.startswith(b"\x1f\x8b"):
                import gzip
                data=gzip.decompress(data)
            check(data.lstrip().startswith((b"c ",b"p cnf ",b"c\n")),
                  "Unexpected official DIMACS bytes")
            name=f"official_{idx:02d}.cnf"
            (out/name).write_bytes(data)
            cases.append(dict(file=name,family="official_gbd_2026",expected=c["status"],
                              vars=None,clauses=None,bytes=len(data),sha256=digest(data),
                              original_sha256=c["sha256"],source=c["source"]))
    check(len(cases)==24+(4 if official else 0),"Frozen case count")
    check(len({v["sha256"] for v in cases})==len(cases),"Formula SHA duplicate")
    manifest=dict(protocol=PROTO,salt=SALT,upstream=UPSTREAM,
                  cap_s=CAP,repeats=REPS,shards=SHARDS,modes=MODES,
                  guard=dict(max_vars=MAX_VARS,max_clauses=MAX_CLAUSES,
                             max_bytes=MAX_SIZE,max_trail=1024),
                  cases=cases,notes=[
                    "Original official 2026 GBD case hashes were previously examined and are diagnostic",
                    "New synthetic R30 examples are SHA-separated from prior R29 generated inputs",
                    "Read-only instrumented Kissat - no native policy or clause modification",
                    "R30 trail is exported internal CDCL trail after a conflict-free propagation",
                    "BCP uses original CNF with exported trail projection, not the solver's preprocessed clause DB",
                    "No complete trail => no gap claim",
                    "GF2 inferences only from syntactically complete parity CNF or sound local resolvents",
                    "Learned clauses counted; dynamic learned-XOR motifs not certified/instrumented yet",
                    "Timeout PAR2 = 2*cap, UNSAT fallback lacks independent proof certificate"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(f'{x["sha256"]}  {x["file"]}\n' for x in cases))
    print("R30_FROZEN",len(cases),digest(out/"manifest.json"),flush=True)

def parse_dimacs(path):
    if path.stat().st_size>MAX_SIZE:
        return None,dict(guard="bytes_exceeded",bytes=path.stat().st_size)
    clauses=[];vars_count=0;declared=None
    try:
        for line in path.read_text(errors="strict").splitlines():
            s=line.strip()
            if not s or s.startswith(("c","%")):continue
            if s.startswith("p "):
                t=s.split()
                check(len(t)==4 and t[1]=="cnf","Bad DIMACS header")
                vars_count=int(t[2]);declared=int(t[3])
                if vars_count>MAX_VARS:return None,dict(guard="variables_exceeded",vars=vars_count,declared=declared)
                if declared>MAX_CLAUSES:return None,dict(guard="clauses_exceeded",vars=vars_count,declared=declared)
                continue
            vals=[int(x) for x in s.split()]
            check(vals and vals[-1]==0,"Expected one clause per line")
            clauses.append(vals[:-1])
    except UnicodeDecodeError:
        return None,dict(guard="non_ascii",bytes=path.stat().st_size)
    check(declared==len(clauses) and vars_count>0,"CNF declaration mismatch")
    return (vars_count,clauses),dict(guard="full_parse",vars=vars_count,clauses=len(clauses),
                                   widths=dict(collections.Counter(len(c) for c in clauses)))
def eliminate_hidden(clauses,n):
    # Each auxiliary variable can be projected exactly if it occurs in one
    # positive and one negative clause and neither original parent is reused.
    occurs=[( [], [] ) for _ in range(n+1)]
    for i,cl in enumerate(clauses):
        for lit in cl:
            occurs[abs(lit)][0 if lit>0 else 1].append(i)
    used=set();derived=[]
    for v in range(1,n+1):
        pos,neg=occurs[v]
        if len(pos)!=1 or len(neg)!=1:continue
        p,q=pos[0],neg[0]
        if p in used or q in used:continue
        a,b=clauses[p],clauses[q]
        if not ((len(a)==2 and 2<=len(b)<=6) or (len(b)==2 and 2<=len(a)<=6)):continue
        lits=set(x for cl in (a,b) for x in cl if abs(x)!=v)
        if len(lits)<2 or len(lits)>6 or any(-x in lits for x in lits):continue
        used.update((p,q))
        derived.append(sorted(lits,key=lambda z:(abs(z),z<0)))
    transformed=[cl for i,cl in enumerate(clauses) if i not in used]+derived
    return transformed,len(derived)
def extract_equations(clauses):
    patterns={}
    for cl in clauses:
        if not 2<=len(cl)<=6:continue
        ls=sorted(cl,key=lambda x:abs(x))
        vs=tuple(abs(x) for x in ls)
        if len(set(vs))!=len(vs):continue
        m=sum((1<<i) for i,x in enumerate(ls) if x<0)
        patterns.setdefault(vs,set()).add(m)
    eq=[]
    for vs,masks in patterns.items():
        for rhs in (0,1):
            forbidden={m for m in range(1<<len(vs)) if m.bit_count()%2!=rhs}
            if forbidden <= masks:
                bits=sum(1<<(v-1) for v in vs)
                eq.append((bits,rhs,vs))
    for cl in clauses:
        if len(cl)==1:
            x=cl[0]
            eq.append((1<<(abs(x)-1),int(x>0),(abs(x),)))
    return eq

def rank_units(equations, assignment):
    basis={}
    mask_known=sum(1<<(v-1) for v in assignment)
    ones=sum(1<<(v-1) for v,x in assignment.items() if x)
    contradiction=False
    for bits,rhs,*_ in equations:
        row=bits&~mask_known
        val=rhs^((bits & ones).bit_count()&1)
        while row:
            pivot=(row & -row).bit_length()-1
            if pivot in basis:
                br,bv=basis[pivot];row^=br;val^=bv
            else:
                basis[pivot]=(row,val);break
        if not row and val:contradiction=True
    # Reduced row echelon form over GF2 to discover forced individual vars.
    for p in sorted(basis,reverse=True):
        br,bv=basis[p]
        for q in list(basis):
            if q!=p and (basis[q][0] & (1<<p)):
                qr,qv=basis[q];basis[q]=(qr^br,qv^bv)
    units={}
    for row,val in basis.values():
        if row.bit_count()==1:
            v=row.bit_length()
            if v not in assignment:units[v]=val
    return dict(rank=len(basis),extra_units=units,contradiction=contradiction)

def bcp(clauses,initial):
    vals=dict(initial)
    for _ in range(1025):
        updated=False
        for cl in clauses:
            unknown=0;one=0;true=False
            for lit in cl:
                v=abs(lit)
                if v in vals:
                    if vals[v]==int(lit>0):true=True;break
                else:unknown+=1;one=lit
            if true:continue
            if unknown==0:return vals,True
            if unknown==1:
                v=abs(one);val=int(one>0)
                if v in vals and vals[v]!=val:return vals,True
                if v not in vals:vals[v]=val;updated=True
        if not updated:return vals,False
    raise RuntimeError("BCP_NOT_CONVERGED")
def inspect_formula(path):
    parsed,meta=parse_dimacs(path)
    if parsed is None:
        return None,meta
    n,clauses=parsed
    transformed,resolved=eliminate_hidden(clauses,n)
    eq=extract_equations(transformed)
    raw=rank_units(eq,{})
    root,root_conflict=bcp(clauses,{})
    algebra=rank_units(eq,root)
    gap={v:val for v,val in algebra["extra_units"].items() if v not in root}
    features=dict(**meta,resolution_derived=resolved,equations=len(eq),
                  rank=raw["rank"],rank_deficiency=len(eq)-raw["rank"],
                  full_xor_coverage=sum(1 for cl in transformed if 2<=len(cl)<=6),
                  root_BCP_units=len(root),root_BCP_conflict=root_conflict,
                  root_GF2_extra_units=len(gap),
                  root_GF2_contradiction=algebra["contradiction"],
                  original_clause_count=len(clauses))
    return dict(n=n,clauses=clauses,equations=eq),features

def parse_traces(output):
    traces=[];data={}
    for line in output.splitlines():
        if line.startswith("c R30_TRACE "):
            m=dict(re.findall(r"(\w+)=(\d+)",line))
            if "mark" not in m:continue
            mark=int(m.pop("mark"))
            check(mark not in data,"Duplicate native snapshot")
            data[mark]={k:int(v) for k,v in m.items()}
        elif line.startswith("c R30_TRAIL "):
            m=re.fullmatch(r"c R30_TRAIL mark=(\d+) literals=(.*)",line)
            check(m is not None,"Bad trail line")
            mark=int(m.group(1))
            parts=m.group(2).split(",") if m.group(2) else []
            pairs=[]
            for part in parts:
                if not part:continue
                t=part.split(":")
                check(len(t)==3,"Malformed trail entry")
                pairs.append([int(x) for x in t])
            if mark not in data:
                # Unexpected ordering is a protocol error, not a guessed value.
                raise RuntimeError("R30_TRAIL_BEFORE_TRACE")
            data[mark]["trail"]=pairs
    for mark in sorted(data):
        row=data[mark]
        check(row["conflict"]>=mark,"Checkpoint came early")
        if row["complete"]:
            check(len(row.get("trail",[]))==row["trail_total"],
                  "Complete snapshot missing or truncated")
            check(row["unmapped"]==0,"Unmapped declared complete")
        else:
            check(not row.get("trail"),"Partial snapshot claimed useful")
        traces.append(dict(mark=mark,**row))
    return traces

def trace_gaps(snapshot,analysis):
    if not snapshot["complete"]:
        return dict(status="missing_or_unmapped_trail")
    if analysis is None:
        return dict(status="static_input_guard")
    assignments={}
    for ext,level,kind in snapshot["trail"]:
        v=abs(ext);val=int(ext>0)
        if v in assignments and assignments[v]!=val:
            raise RuntimeError("Inconsistent exported trail snapshot")
        assignments[v]=val
    # A trail snapshot is an external *projection* of a solver using its
    # internal preprocessed formula; BCP below operates on ORIGINAL clauses.
    base,conflict=bcp(analysis["clauses"],assignments)
    result=rank_units(analysis["equations"],base)
    extra={v:x for v,x in result["extra_units"].items() if v not in base}
    return dict(status="projection_analyzed",exported_assignments=len(assignments),
                original_BCP_closure=len(base),original_BCP_conflict=conflict,
                verified_GF2_extra_units=len(extra),
                verified_GF2_conflict=result["contradiction"],
                gf2_rank_conditioned=result["rank"])
def model_valid(output,clauses,n):
    model={}
    for line in output.splitlines():
        if line.startswith("v "):
            for s in line.split()[1:]:
                t=int(s)
                if t:model[abs(t)]=int(t>0)
    if len(model)<n:return False
    return all(any(model[abs(l)]==int(l>0) for l in cl) for cl in clauses)
def run_one(mode,original,passive,path,analysis,expected):
    cmd=[str(original if mode=="Kissat_clean" else passive),str(path)]
    started=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",timeout=CAP)
        elapsed=time.monotonic()-started
        check(p.returncode in (10,20),"Native Kissat failure "+mode+" "+p.stderr[-350:])
        status="SAT" if p.returncode==10 else "UNSAT"
        check(expected is None or status==expected.upper(),"Expected SAT label disagreement")
        if analysis is not None and status=="SAT":
            check(model_valid(p.stdout,analysis["clauses"],analysis["n"]),"Original CNF SAT model invalid")
        verification=("SAT_model_checked" if analysis is not None and status=="SAT"
                      else "source_label_or_solver_only")
        output=p.stdout
    except subprocess.TimeoutExpired as e:
        elapsed=time.monotonic()-started;status="TIMEOUT"
        output=e.stdout or b""
        if isinstance(output,bytes):output=output.decode(errors="replace")
        verification="not_applicable"
    traces=parse_traces(output) if mode=="Kissat_R30_passive" else []
    if mode=="Kissat_R30_passive":
        for t in traces:t["algebra"]=trace_gaps(t,analysis)
    return dict(status=status,seconds=round(elapsed,6),
                par2=round(elapsed,6) if status!="TIMEOUT" else 2*CAP,
                verification=verification,snapshots=traces)
def measure(a):
    root=Path(a.inputs)
    spec=json.loads((root/"manifest.json").read_text())
    check(spec["protocol"]==PROTO and spec["modes"]==list(MODES)
          and spec["cap_s"]==CAP and spec["repeats"]==REPS,"Frozen manifest changed")
    check(0<=a.shard<SHARDS,"Bad shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    original=Path(a.kissat).resolve();passive=Path(a.passive).resolve()
    check(original.is_file() and passive.is_file(),"Missing pinned native solvers")
    output=Path(a.outdir);output.mkdir(parents=True,exist_ok=True)
    meta=dict(shard=a.shard,manifest_sha256=digest(root/"manifest.json"),
              clean_binary_sha256=digest(original),passive_binary_sha256=digest(passive))
    (output/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[];features=[]
    for case in spec["cases"][a.shard::SHARDS]:
        p=(root/case["file"]).resolve()
        check(digest(p)==case["sha256"],"Source CNF SHA changed")
        analysis,f=inspect_formula(p)
        features.append(dict(file=case["file"],family=case["family"],sha256=case["sha256"],**f))
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(digest((case["sha256"]+"/R30/"+str(rep)).encode()),16)).shuffle(order)
            for mode in order:
                res=run_one(mode,original,passive,p,analysis,case["expected"])
                row=dict(file=case["file"],family=case["family"],repeat=rep,
                         mode=mode,**res)
                rows.append(row)
                (output/"rows.json").write_text(json.dumps(rows,indent=1)+"\n")
                print("R30_TRIAL",a.shard,case["file"],rep,mode,
                      res["status"],res["seconds"],"snapshots",len(res["snapshots"]),
                      flush=True)
        labels={r["status"] for r in rows if r["file"]==case["file"]}-{"TIMEOUT"}
        check(len(labels)<=1,"Solver SAT/UNSAT mismatch")
    (output/"structure.json").write_text(json.dumps(features,indent=2)+"\n")
    print("R30_SHARD_DONE",a.shard,len(rows),flush=True)
def aggregate(a):
    root=Path(a.inputs)
    spec=json.loads((root/"manifest.json").read_text())
    results=[];structure=[];identity=set()
    for shard in range(SHARDS):
        out=Path(a.combined)/f"r30-shard-{shard}"/"results"
        info=json.loads((out/"metadata.json").read_text())
        check(info["shard"]==shard and info["manifest_sha256"]==digest(root/"manifest.json"),
              "Shard manifests mismatch")
        identity.add(info["clean_binary_sha256"]+"/"+info["passive_binary_sha256"])
        rr=json.loads((out/"rows.json").read_text())
        check(len(rr)==len(spec["cases"][shard::SHARDS])*REPS*len(MODES),
              "Incomplete trial shard")
        results+=rr
        structure+=json.loads((out/"structure.json").read_text())
    check(len(identity)==1 and len(results)==len(spec["cases"])*REPS*2,
          "Missing attempts or mismatched binaries")
    fams=["ALL"]+list(FAMILIES)+(["official_gbd_2026"] if len(spec["cases"])>24 else [])
    table={}
    by_formula={f:[] for f in (c["file"] for c in spec["cases"])}
    for r in results:by_formula[r["file"]].append(r)
    regressions=[]
    for name,rr in by_formula.items():
        b=statistics.median(x["par2"] for x in rr if x["mode"]=="Kissat_clean")
        p=statistics.median(x["par2"] for x in rr if x["mode"]=="Kissat_R30_passive")
        regressions.append(dict(file=name,ratio=round(p/max(b,1e-6),5),
                                baseline=round(b,6),passive=round(p,6)))
    for fam in fams:
        ss=[c for c in spec["cases"] if fam=="ALL" or c["family"]==fam]
        dat={}
        for mode in MODES:
            group=[r for r in results if r["mode"]==mode and
                   (fam=="ALL" or r["family"]==fam)]
            check(len(group)==len(ss)*REPS,"Incomplete family")
            dat[mode]=dict(sum_PAR2=round(sum(r["par2"] for r in group),6),
                           solved_cases=sum(all(r["status"]!="TIMEOUT" for r in by_formula[c["file"]]
                                                if r["mode"]==mode) for c in ss),
                           timeouts=sum(r["status"]=="TIMEOUT" for r in group))
        b=dat["Kissat_clean"]["sum_PAR2"];p=dat["Kissat_R30_passive"]["sum_PAR2"]
        cps=[t for r in results if r["mode"]=="Kissat_R30_passive" and
             (fam=="ALL" or r["family"]==fam) for t in r["snapshots"]]
        gaps=[t["algebra"] for t in cps if t["algebra"]["status"]=="projection_analyzed"]
        dat["passive_overhead_pct"]=round(100*(p-b)/max(b,1e-9),3)
        dat["checkpoints"]=len(cps)
        dat["analyzable_snapshots"]=len(gaps)
        dat["extra_gap_snapshots"]=sum(x["verified_GF2_extra_units"]>0 for x in gaps)
        dat["gf2_conflict_snapshots"]=sum(x["verified_GF2_conflict"] for x in gaps)
        table[fam]=dat
        print("R30_SUMMARY",fam,json.dumps(dat,sort_keys=True),flush=True)
    report=dict(protocol=PROTO,manifest_sha256=digest(root/"manifest.json"),
                binary_identity=next(iter(identity)),summary=table,
                regressions=regressions,structure=structure,rows=results,
                limitations=["Analysis is passive, no intervention executed",
                             "BCP and GF2 applied to externally projected trail on ORIGINAL CNF, not exact solver internal propagated DB",
                             "Only complete externally mapped <=1024-literal trail snapshots support a gap metric",
                             "Newly learned XOR structures are NOT independently recovered yet",
                             "Synthetic controls and previously used GBD official inputs are separate cohorts",
                             "No causal runtime predictor or universal speedup claim"])
    Path(a.outjson).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# DRNAS R30 — passive algebra-vs-CDCL checkpoint experiment",
           f"{len(spec['cases'])} frozen formulas × 2 repeats × 2 modes = {len(results)} attempts.",
           "Same pinned upstream Kissat, with and without one read-only source patch.",
           "**No strategy intervention. No runtime causality claim.**",
           "BCP vs GF2 conditions use external solver trail projected on original CNF.",
           "", "| Family | Clean PAR2 s | Passive PAR2 s | Overhead | Snapshots | GF2-extra snapshots |",
           "|---|---:|---:|---:|---:|---:|"]
    for family,d in table.items():
        b,p=d["Kissat_clean"],d["Kissat_R30_passive"]
        lines.append(f"| {family} | {b['sum_PAR2']:.4f} | {p['sum_PAR2']:.4f} | "
                     f"{d['passive_overhead_pct']:+.2f}% | {d['checkpoints']} | {d['extra_gap_snapshots']} |")
    lines+=["","## Largest timing regressions (per-formula median PAR2)"]
    for z in sorted(regressions,key=lambda x:-x["ratio"])[:8]:
        lines.append(f"- {z['file']}: {z['ratio']:.2f}×, baseline {z['baseline']:.4f}s, passive {z['passive']:.4f}s")
    Path(a.report).write_text("\n".join(lines)+"\n")
    with Path(a.csv).open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["formula","family","repeat","mode","status","seconds",
                                   "par2","snapshot_count","gap_snapshots"])
        for x in results:
            w.writerow([x["file"],x["family"],x["repeat"],x["mode"],x["status"],
                        x["seconds"],x["par2"],len(x["snapshots"]),
                        sum(t["algebra"].get("verified_GF2_extra_units",0)>0
                            for t in x["snapshots"])])
    print("R30_AUDIT_PASS",len(results),"attempts",len(spec["cases"]),"formulas",flush=True)

def main():
    a=argparse.ArgumentParser()
    sub=a.add_subparsers(dest="command",required=True)
    x=sub.add_parser("freeze");x.add_argument("--out",required=True);x.add_argument("--official")
    x=sub.add_parser("measure")
    for k in ("inputs","kissat","passive","outdir"):x.add_argument("--"+k,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sub.add_parser("aggregate")
    for k in ("inputs","combined","outjson","report","csv"):x.add_argument("--"+k,required=True)
    x=a.parse_args()
    if x.command=="freeze":freeze(x.out,x.official)
    elif x.command=="measure":measure(x)
    else:aggregate(x)

if __name__=="__main__":main()
