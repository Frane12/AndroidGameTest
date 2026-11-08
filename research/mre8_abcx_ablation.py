#!/usr/bin/env python3
"""DRNAS MRE8: A/B/C/X causal ablation on 16 already-development SAT originals.

Not a blind holdout: the cohort and two interesting cases were examined in MRE7e.
A = equality substitution without cleanup; B = plain syntactic CNF cleanup;
C = A+B; D = clause-order control; Xs/Xc = cheaper exact streaming rewrites;
Xr = predeclared sparse/dense decision from *original input only*.
All equations are positive direct binary equivalences certified in original CNF.
Every SAT model is lifted and replayed against the exact original SHA. No LRAT
is available for UNSAT; existing original CaDiCaL/CMS consensus is disclosed.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,statistics,subprocess,tempfile,time
import mre7_extended_easy_freeze as frozen
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195

PROTO="DRNAS-MRE8-ABCX-16ORIGINAL-8ARMS-4REPS-8S-20261108-v1"
ROOT=pathlib.Path("mre8")
MODES=("N_native","A_rename","B_clean","C_joint","D_length_order",
       "Xs_stream_rename","Xc_stream_joint","Xr_route")
REPS=4
SHARDS=8
CAP=8.0
FOCUS=("fdfcd52a21824b7181d66672f283ba04",
       "037d21e060a2e3eab8b080aa84ceee75")
def need(ok,msg):
    if not ok:raise RuntimeError("MRE8_FAIL_CLOSED "+str(msg))
def digest(data):return hashlib.sha256(data).hexdigest()
def save(path,object_):
    pathlib.Path(path).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(path).write_text(json.dumps(object_,sort_keys=True,indent=2)+"\n")
def seed_for(case,rep):
    # Across variants, a single (source_SHA, repetition) has the same CMS seed.
    return int(digest(("DRNAS-MRE8-SOURCE-SEED|"+case["sha256"]+"|"+str(rep)).encode())[:8],16)

def positive_equivalences(binary):
    # Each equality u=v has BOTH (-u OR v) and (u OR -v) in ORIGINAL CNF.
    pairs=set()
    for clause in binary:
        if len(clause)!=2:continue
        x,y=tuple(clause)
        if x*y<0 and abs(x)!=abs(y) and frozenset((-x,-y)) in binary:
            pairs.add(tuple(sorted((abs(x),abs(y)))))
    parent={}
    def find(v):
        parent.setdefault(v,v)
        while parent[v]!=v:
            parent[v]=parent[parent[v]]
            v=parent[v]
        return v
    for a,b in sorted(pairs):
        need(frozenset((-a,b)) in binary and frozenset((a,-b)) in binary,
             "certificate missing original binary side")
        u,v=find(a),find(b)
        if u!=v:parent[max(u,v)]=min(u,v)
    mapping={v:find(v) for v in list(parent) if find(v)!=v}
    return mapping,len(pairs)

def mapping_for_original(original):
    return positive_equivalences({frozenset(c) for c in original if len(c)==2})

def rewrite_rename(original,mapping):
    if not mapping:return list(original)
    return [tuple((1 if v>0 else -1)*mapping.get(abs(v),abs(v))
                  for v in clause) for clause in original]

def cleanup(clauses):
    kept=[];seen=set();taut=dup=0
    for c in clauses:
        litset=frozenset(c)
        if any(-lit in litset for lit in litset):
            taut+=1;continue
        if litset in seen:
            dup+=1;continue
        seen.add(litset);kept.append(tuple(dict.fromkeys(c)))
    return kept,dict(tautologies_removed=taut,duplicate_clauses_removed=dup)

def write_cnf(path,n,clauses):
    with pathlib.Path(path).open("w") as handle:
        handle.write("p cnf %d %d\n"%(n,len(clauses)))
        for clause in clauses:
            handle.write(" ".join(map(str,clause))+" 0\n")

def stream_equivalences(source):
    """Fail-closed fast path for one-complete-clause-per-line original DIMACS.
    If DIMACS has multi-line/multi-clause rows, fall back to unmodified native.
    A detected equality is always independently present in two original clauses.
    """
    original=source.read_bytes()
    n=m=None;count=0;binary=set();lines=[]
    for row in original.splitlines():
        s=row.strip()
        if not s or s[:1] in (b"c",b"%"):continue
        if s.startswith(b"p "):
            need(n is None,"multiple original DIMACS headers")
            f=s.split()
            need(len(f)==4 and f[:2]==[b"p",b"cnf"],"bad original header")
            n,m=int(f[2]),int(f[3])
            continue
        need(n is not None,"clauses before original header")
        t=s.split()
        if not t or t[-1]!=b"0" or t.count(b"0")!=1:
            return None
        count+=1
        lines.append(t[:-1])
        if len(t)==3:
            x,y=int(t[0]),int(t[1])
            need(0<abs(x)<=n and 0<abs(y)<=n,"binary outside var declaration")
            binary.add(frozenset((x,y)))
    need(n is not None and count==m,"stream header/clauses mismatch")
    mapping,pairs=positive_equivalences(binary)
    return n,lines,mapping,pairs

def stream_transform(stream,mode):
    n,lines,mapping,pairs=stream
    need(mode in MODES,"bad stream variant")
    # A cheap structural router. It NEVER sees incumbent solver performance.
    decision="APPLY"
    if mode=="Xr_route":
        if len(mapping)>=64: decision="DENSE"
        elif len(mapping)>=2: decision="SPARSE"
        else: decision="SKIP"
    elif mode=="Xs_stream_rename":decision="SPARSE"
    elif mode=="Xc_stream_joint":decision="DENSE"
    if decision=="SKIP":return None,{},dict(route=decision,pairs=pairs,merges=len(mapping))
    clean=(decision=="DENSE")
    if not mapping and not clean:
        return None,{},dict(route="NO_CERTIFIED_EQUALITIES",pairs=pairs,merges=0)
    clauses=[];seen=set();removed=0
    for row in lines:
        c=tuple((1 if v>0 else -1)*mapping.get(abs(v),abs(v))
                 for v in map(int,row))
        if clean:
            litset=frozenset(c)
            if any(-lit in litset for lit in litset):removed+=1;continue
            if litset in seen:removed+=1;continue
            seen.add(litset)
            c=tuple(dict.fromkeys(c))
        clauses.append(c)
    return clauses,mapping,dict(route=decision,pairs=pairs,
        merges=len(mapping),removed=removed,clauses_out=len(clauses))

def transform(source,mode,outfile):
    """Outputs (solver input, model-lifting mapping, source preprocessor audit).
    N and D are structural controls, and A/B/C isolate the two transformations.
    """
    if mode=="N_native":
        return source,{},dict(arm=mode,changed=False,method="none")
    if mode.startswith("X"):
        s=stream_equivalences(source)
        if s is None:
            return source,{},dict(arm=mode,changed=False,
                                 method="safe_fallback_multiline_DIMACS")
        n=s[0]
        cnf,mapping,meta=stream_transform(s,mode)
        if cnf is None:
            return source,{},dict(arm=mode,changed=False,method="fast_stream",**meta)
        write_cnf(outfile,n,cnf)
        return outfile,mapping,dict(arm=mode,changed=True,method="fast_stream",**meta)
    n,original=exact.parse_dimacs(source)
    mapping,pairs=mapping_for_original(original)
    stats=dict(arm=mode,pairs=pairs,merges=len(mapping),method="fully_parsed")
    if mode=="A_rename":
        cnf=rewrite_rename(original,mapping)
    elif mode=="B_clean":
        cnf,cleanstat=cleanup(original)
        stats.update(cleanstat)
        mapping={}
    elif mode=="C_joint":
        cnf,cleanstat=cleanup(rewrite_rename(original,mapping))
        stats.update(cleanstat)
    elif mode=="D_length_order":
        cnf=sorted(original,key=len)
        mapping={}
    else:
        raise RuntimeError("unimplemented MRE8 arm "+mode)
    if cnf==original:
        stats["changed"]=False
        return source,{},stats
    write_cnf(outfile,n,cnf)
    stats.update(changed=True,clauses_out=len(cnf))
    return outfile,mapping,stats

def trial(case,rep,mode,binary):
    original=frozen.ROOT/case["filename"]
    need(digest(original.read_bytes())==case["sha256"],"original SHA mismatch")
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="drnas-mre8-") as tmp:
        d=pathlib.Path(tmp)
        runinput,mapping,prepmeta=transform(original,mode,d/"reduced.cnf")
        transform_s=time.perf_counter()-start
        runsha=digest(runinput.read_bytes())
        status="TIMEOUT";stats=None;checked_model=False;native_wall=None
        remaining=CAP-(time.perf_counter()-start)
        if remaining>=.05:
            empty=d/"none.tsv";empty.write_text("")
            cmd=[str(pathlib.Path(binary).resolve()),
                 str(runinput.resolve()),str(empty.resolve()),
                 str(empty.resolve()),"cms_native",str(seed_for(case,rep))]
            begin=time.perf_counter()
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                                 timeout=remaining,check=False)
            except subprocess.TimeoutExpired:
                p=None
            native_wall=time.perf_counter()-begin
            if p is not None:
                need(p.returncode==0,"CMS native error "+p.stderr[-350:])
                status,model,stats=r195.parsed_native(p.stdout)
                if status=="SAT":
                    if mapping:
                        model={**model,**{v:model[root] for v,root in mapping.items()}}
                    r195.verify_model(original,model)
                    checked_model=True
                need(status not in ("SAT","UNSAT") or
                     status==case["reference_screen_status"],
                     "transformed verdict differs from cross-checked original")
        full=time.perf_counter()-start
        if full>CAP and status in ("SAT","UNSAT"):
            status="TIMEOUT";checked_model=False
        need(status!="SAT" or checked_model,"SAT without checked original witness")
        return dict(protocol=PROTO,gbd=case["gbd"],year=case["year"],
            source_sha256=case["sha256"],input_sha256=runsha,
            mode=mode,rep=rep,seed=seed_for(case,rep),status=status,
            original_sat_model_verified=checked_model,
            unsat_original_cadical_crosscheck=(case["reference_screen_status"]=="UNSAT"),
            unsat_independent_LRAT=False,
            transform_s=round(transform_s,6),
            native_s=round(native_wall,6) if native_wall is not None else None,
            full_wall_s=round(full,6),
            par2_s=round(full if status in ("SAT","UNSAT") else 2*CAP,6),
            counters=stats,meta=prepmeta,
            dataset="posthoc_MRE7E_PILOT16_development_not_blind",
            original_witness_required=True)

def frozen_cases():
    manifest=json.loads((frozen.ROOT/"manifest.json").read_text())
    need(manifest["protocol"]==frozen.PROTO and
         manifest["selected"]==16 and
         manifest["parent_six_SHA_untouched"] and
         manifest["source_selection_before_mre7e_gate"],
         "wrong frozen 16-original development cohort")
    cases=manifest["selected_cases"]
    need(len(cases)==16 and len({x["sha256"] for x in cases})==16,"case registry drift")
    for case in cases:
        need(digest((frozen.ROOT/case["filename"]).read_bytes())==case["sha256"],
             "original source SHA drift")
    return cases

def selftest():
    # Check A/B/C/X exact original satisfiability equivalence by exhaustion.
    rng=random.Random(8808)
    total=0
    for k in range(32):
        n=5
        cnf=[tuple(rng.choice((-1,1))*rng.randint(1,n)
                   for _ in range(rng.randrange(1,5))) for j in range(12)]
        if k%3==0:cnf.extend([(-1,2),(1,-2),(-2,3),(2,-3)])
        if k%3==1:cnf.extend([(-4,5),(4,-5)])
        with tempfile.TemporaryDirectory() as tmp:
            src=pathlib.Path(tmp)/"orig.cnf"
            write_cnf(src,n,cnf)
            data=stream_equivalences(src)
            need(data is not None,"selftest standalone DIMACS")
            m,pairs=mapping_for_original(cnf)
            need(m==data[2],"fast/slow certified mapping mismatch")
            sols=[]
            for mode in MODES:
                fout=pathlib.Path(tmp)/("x-"+mode+".cnf")
                fpath,map_,_=transform(src,mode,fout)
                _,transformed=exact.parse_dimacs(fpath)
                satvals=[]
                for bits in range(1<<n):
                    model={v:bool(bits&(1<<(v-1))) for v in range(1,n+1)}
                    lifted=dict(model)
                    lifted.update({v:lifted[root] for v,root in map_.items()})
                    transformed_sat=all(any(model[abs(l)]==(l>0) for l in c)
                                        for c in transformed)
                    original_sat=all(any(lifted[abs(l)]==(l>0) for l in c)
                                     for c in cnf)
                    if transformed_sat:
                        need(original_sat,"SAT witness does not lift to original")
                    satvals.append(transformed_sat)
                sols.append(any(satvals))
                total+=1
            need(len(set(sols))==1,"equisatisfiability ablation violated")
            # Canonical joint reduction must be byte-for-byte identical to
            # its optimized streaming implementation, independent of speed.
            pc,_,_=transform(src,"C_joint",pathlib.Path(tmp)/"baseline.cnf")
            px,_,_=transform(src,"Xc_stream_joint",pathlib.Path(tmp)/"stream.cnf")
            need(exact.parse_dimacs(pc)==exact.parse_dimacs(px),
                 "fast joint transformation differs from slow joint")
            pa,_,_=transform(src,"A_rename",pathlib.Path(tmp)/"rename.cnf")
            ps,_,_=transform(src,"Xs_stream_rename",pathlib.Path(tmp)/"streamrename.cnf")
            need(exact.parse_dimacs(pa)==exact.parse_dimacs(ps),
                 "fast substitution differs from slow substitution")
    need(REPS==4 and SHARDS==8 and CAP==8.0 and len(MODES)==8,"protocol drift")
    print("MRE8_ABCX_EXHAUSTIVE_SELFTEST_PASS",total,flush=True)

def shard(i,binary):
    need(0<=i<SHARDS,"invalid shard")
    cc=frozen_cases()
    cases=[c for j,c in enumerate(cc) if j%SHARDS==i]
    need(len(cases)==2,"not exactly two SHA originals on shard")
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for case in cases:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+case["sha256"]+"/"+str(rep)).shuffle(arms)
            for mode in arms:
                x=trial(case,rep,mode,binary)
                rows.append(x)
                save(ROOT/("shard-%d.json"%i),rows)
                print("MRE8_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==len(cases)*REPS*len(MODES),"missing trial")
    print("MRE8_SHARD_PASS",i,len(cases),len(rows),flush=True)

def audit():
    cc=frozen_cases()
    rows=[]
    for i in range(SHARDS):
        path=ROOT/("shard-%d.json"%i)
        need(path.is_file(),"missing source shard")
        rows.extend(json.loads(path.read_text()))
    n=len(cc)
    need(n==16 and len(rows)==n*REPS*len(MODES),"incomplete development benchmark")
    lookup={c["sha256"]:c for c in cc}
    groups=collections.defaultdict(dict)
    for r in rows:
        c=lookup.get(r["source_sha256"])
        need(c is not None and c["gbd"]==r["gbd"],"wrong source SHA/ID")
        need(r["protocol"]==PROTO and 0<=r["rep"]<REPS and r["mode"] in MODES,
             "unexpected arm/protocol")
        if r["status"]=="SAT":
            need(r["original_sat_model_verified"],"SAT not independently verified")
        if r["status"]=="UNSAT":
            need(c["reference_screen_status"]=="UNSAT","UNSAT originally unverified")
        p=(c["sha256"],r["rep"])
        need(r["mode"] not in groups[p],"duplicate paired mode")
        groups[p][r["mode"]]=r
    need(len(groups)==n*REPS,"missing paired seed")
    for pair in groups.values():
        need(set(pair)==set(MODES),"missing one factorial arm")
        need(len({r["seed"] for r in pair.values()})==1,"unequal seeds")
        need(pair["C_joint"]["input_sha256"]==
             pair["Xc_stream_joint"]["input_sha256"],
             "C and Xc emitted different exact CNF; causal parity broken")
        need(pair["A_rename"]["input_sha256"]==
             pair["Xs_stream_rename"]["input_sha256"],
             "A and Xs emitted different exact CNF")
    score={}
    base_par2=sum(x["N_native"]["par2_s"] for x in groups.values())
    for mode in MODES:
        selected=[r for r in rows if r["mode"]==mode]
        this_par2=sum(r["par2_s"] for r in selected)
        score[mode]=dict(trials=len(selected),
            sat=sum(r["status"]=="SAT" for r in selected),
            unsat_crosscheck_no_LRAT=sum(r["status"]=="UNSAT" for r in selected),
            timeout=sum(r["status"]=="TIMEOUT" for r in selected),
            solved=sum(r["status"] in ("SAT","UNSAT") for r in selected),
            par2_s=round(this_par2,6),
            speedup_par2_vs_native_x=round(base_par2/this_par2,6),
            full_wall_s=round(sum(r["full_wall_s"] for r in selected),6),
            preprocess_s=round(sum(r["transform_s"] for r in selected),6),
            applied=sum(r["meta"].get("changed",False) for r in selected),
            route_dense=sum(r["meta"].get("route")=="DENSE" for r in selected),
            route_sparse=sum(r["meta"].get("route")=="SPARSE" for r in selected),
            route_skip=sum(r["meta"].get("route")=="SKIP" for r in selected))
    focus=[]
    for (sha,rep),p in groups.items():
        if p["N_native"]["gbd"] not in FOCUS:continue
        focus.append(dict(gbd=p["N_native"]["gbd"],rep=rep,
            native_conflicts=p["N_native"]["counters"]["conflicts"] if p["N_native"]["counters"] else None,
            native_propagations=p["N_native"]["counters"]["propagations"] if p["N_native"]["counters"] else None,
            variants={m:dict(par2_s=p[m]["par2_s"],status=p[m]["status"],
                prep_s=p[m]["transform_s"],
                native_s=p[m]["native_s"],
                conflicts=p[m]["counters"]["conflicts"] if p[m]["counters"] else None,
                propagations=p[m]["counters"]["propagations"] if p[m]["counters"] else None)
                for m in MODES}))
    report=dict(protocol=PROTO,original_cohort=16,repetitions=REPS,
        total_trials=len(rows),valid_sat_witness_original=True,
        unsat_cross_solver_not_independent_lrat=True,
        data_is_dev_posthoc=True,holdout=False,promotion_allowed=False,
        all_pair_shas_frozen=True,paired_seeds=True,source_sha_integrity=True,
        transformation_equivalence_verified=True,
        cap_wall_including_prep_s=CAP,gate_threshold_precommitted="mapping≥64 dense; mapping≥2 sparse; otherwise native",
        score=score,focus=focus)
    save(ROOT/"report.json",report)
    print("MRE8_FINAL",json.dumps({k:v for k,v in report.items() if k!="focus"},
        sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--cms",default="mre7_easy/bin/native")
    a=ap.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard,a.cms)
    else:audit()
