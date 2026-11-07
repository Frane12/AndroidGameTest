#!/usr/bin/env python3
"""DRNAS New Horizon SAT: cheap source-only motif index and proof-gated routing.
UNKNOWN != MIXED. No benchmark outcome, file ID or family enters the selector.
"""
from __future__ import annotations
import collections, hashlib, json, pathlib, subprocess, tempfile, time
import r164_pure_exact_gf2 as pure
import r182_mixed_engine as certified

SCAN_LIMIT=2048
SCAN_MAX_S=0.025
FULL_MAX_CLAUSES=3200
FULL_MAX_BYTES=280000
MAX_CERT_ROWS=96

def need(v,msg):
    if not v: raise RuntimeError("NEW_HORIZON_FAIL_CLOSED: "+str(msg))

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def fingerprint(path):
    """Canonical XOR3 mask lookup: no enumeration of variable permutations.
    Source-only sample of <= 2048 original clauses. May miss late motifs.
    """
    st=time.perf_counter()
    n=m=None
    seen=0; pending=[]; sample=[]
    groups=collections.defaultdict(set)
    counts=collections.Counter()
    with pathlib.Path(path).open(encoding="ascii") as fd:
        for line in fd:
            line=line.strip()
            if not line or line.startswith(("c","%")):continue
            if line.startswith("p "):
                need(n is None,"duplicate header")
                a=line.split()
                need(len(a)==4 and a[1]=="cnf","bad header")
                n,m=int(a[2]),int(a[3])
                need(n>0 and m>=0,"bad dimensions")
                continue
            need(n is not None,"clause before header")
            for tok in line.split():
                lit=int(tok)
                if lit:
                    need(abs(lit)<=n,"literal beyond variable count")
                    pending.append(lit)
                else:
                    c=tuple(pending);pending=[]
                    seen+=1
                    counts["horn"]+=sum(z>0 for z in c)<=1
                    counts["binary"]+=len(c)==2
                    counts["ternary"]+=len(c)==3
                    counts["unit"]+=len(c)==1
                    if len(c)==3 and len({abs(z) for z in c})==3:
                        sorted_lits=sorted(c,key=abs)
                        vs=tuple(abs(x) for x in sorted_lits)
                        mask=sum(1<<j for j,x in enumerate(sorted_lits) if x<0)
                        groups[vs].add(mask)
                        sample.append((vs,mask))
                    else:
                        sample.append((None,tuple(abs(v) for v in c)))
                    if seen>=SCAN_LIMIT:break
            if seen>=SCAN_LIMIT:break
    need(n is not None,"missing source header")
    # A complete forbidden parity half (4 sign masks) implies an XOR3 equation.
    xor=[]
    matched=set()
    for vs,masks in groups.items():
        for parity in (0,1):
            quartet={k for k in range(8) if (k.bit_count()&1)==parity}
            if quartet.issubset(masks):
                xor.append((vs,1-parity))
                matched.update((vs,z) for z in quartet)
    xor.sort()
    covered=0; residual=collections.Counter()
    for vs,x in sample:
        if vs is not None and (vs,x) in matched:covered+=1
        elif vs is None and len(x)==1:covered+=1
        elif vs is None:residual.update(x)
        else:residual.update(vs)
    xor_vars={v for vs,_ in xor for v in vs}
    boundary=sum(residual[v] for v in xor_vars)
    residual_occ=sum(residual.values())
    if xor and covered==seen and seen==m and m<=512:
        classification="source_pure_xor_candidate"
    elif len(xor)>=2 and boundary>0:
        classification="certified_xor_residual_link"
    elif xor:
        classification="certified_xor_isolated_or_partial"
    elif seen and counts["binary"]/seen>=0.60:
        classification="binary_dominant_no_certified_xor"
    elif seen and counts["horn"]/seen>=0.80:
        classification="horn_dominant_no_certified_xor"
    else:
        classification="UNKNOWN"
    elapsed=time.perf_counter()-st
    # A key over relation shapes, not concrete variable IDs or source family.
    patterns=collections.Counter(f"XOR3:{rhs}" for _,rhs in xor)
    motif_key=hashlib.sha256(json.dumps(sorted(patterns.items())).encode()).hexdigest()[:16]
    return dict(n=n,m=m,scanned=seen,scan_s=elapsed,
                complete_xor3=len(xor),covered=covered,
                boundary_occurrences=boundary,residual_occurrences=residual_occ,
                boundary_fraction=boundary/max(1,residual_occ),
                bin_fraction=counts["binary"]/max(1,seen),
                horn_fraction=counts["horn"]/max(1,seen),
                classification=classification,motif_pointer=motif_key,
                analysis_within_budget=elapsed<=SCAN_MAX_S)

def decide(info, source):
    if not info["analysis_within_budget"]:return "clean","scan_budget_exceeded"
    if info["classification"]=="source_pure_xor_candidate":
        return "pure_exact","full_source_equivalence_required"
    size=pathlib.Path(source).stat().st_size
    if (info["classification"]=="certified_xor_residual_link"
            and info["m"]<=FULL_MAX_CLAUSES and size<=FULL_MAX_BYTES
            and info["complete_xor3"]<=MAX_CERT_ROWS):
        return "certified_bridge","measured_linked_xor_source"
    return "clean","unknown_or_unprofitable_fallback"

def certified_preprocess(source, target, *, forced=False):
    """Reconstruct source-certified XOR rows and only add proven GF2 unit facts."""
    n,clauses=certified.dimacs(source)
    rows,_=certified.xor3_extract(clauses)
    if not rows:return dict(kind="none",rows=0,units=0,reason="no_full_source_motifs")
    if len(rows)>MAX_CERT_ROWS:
        return dict(kind="none",rows=len(rows),units=0,reason="row_budget")
    result=certified.gaussian(rows)
    if result["conflict"]:
        certified.check_trace(rows,0,1,result["conflict_trace"])
        return dict(kind="unsat",rows=len(rows),units=0,
                    proof="SOURCE_XOR3_GF2_CONTRADICTION_REPLAYED_NO_LRAT")
    units={}
    for v,(rhs,trace) in result["units"].items():
        certified.check_trace(rows,1<<(v-1),rhs,trace)
        units[v]=rhs
    if not units:return dict(kind="none",rows=len(rows),units=0,reason="no_derived_units")
    orig={abs(c[0]):int(c[0]>0) for c in clauses if len(c)==1}
    for v,rhs in units.items():
        if v in orig:
            need(orig[v]==rhs,"source unit conflict should be handled in native CDCL")
    fresh={v:rhs for v,rhs in units.items() if v not in orig}
    if not fresh:return dict(kind="none",rows=len(rows),units=0,reason="units_already_present")
    out=pathlib.Path(target);out.parent.mkdir(parents=True,exist_ok=True)
    # No deletion or alteration of original constraints: only entailed units.
    with out.open("w") as f:
        f.write(f"p cnf {n} {len(clauses)+len(fresh)}\n")
        for c in clauses:f.write(" ".join(map(str,c))+" 0\n")
        for v,rhs in sorted(fresh.items()):f.write(f"{v if rhs else -v} 0\n")
    return dict(kind="strengthened",rows=len(rows),units=len(fresh),
                proof="SOURCE_XOR3_GF2_UNITS_REPLAYED",file=str(out))

def native(binary,source,seconds,profile="default"):
    need(seconds>=0.1,"insufficient time budget")
    p=subprocess.run([str(pathlib.Path(binary).resolve()),str(pathlib.Path(source).resolve()),
                      str(max(0.1,seconds)),profile],
                     capture_output=True,text=True,timeout=max(3,seconds+3))
    need(p.returncode==0,"CaDiCaL driver failed "+p.stderr[-800:])
    lines=p.stdout.splitlines()
    status=next((line.split("status=",1)[1].split()[0] for line in lines
                 if line.startswith("R182_STATUS status=")),None)
    need(status in ("SAT","UNSAT","TIMEOUT"),"invalid native outcome")
    model={}
    if status=="SAT":
        for line in lines:
            if line.startswith("v "):
                for lit in map(int,line[2:].split()):
                    if lit: model[abs(lit)]=lit>0
    return status,model

def verify_model(source,model):
    n,clauses=certified.dimacs(source)
    need(all(any(model.get(abs(v),False)==(v>0) for v in c) for c in clauses),
         "SAT witness fails ORIGINAL source CNF")
    return n

def run_one(source,binary,cap,mode, scratch):
    need(mode in ("clean","shadow","new_horizon","forced"),
         "bad strategy")
    st=time.perf_counter()
    info=None;route="clean";reason="baseline";cert=None;inp=pathlib.Path(source)
    proof="TIMEOUT";status="TIMEOUT";model={}
    if mode!="clean":
        info=fingerprint(source)
        if mode=="forced":
            route="certified_bridge";reason="forced_certified_ablation"
        else:
            route,reason=decide(info,source)
        if mode=="shadow":
            route="clean";reason="analyzer_shadow_no_change"
        elif route=="pure_exact":
            # Full, independently verified exact source equivalence (not sample-based).
            if cap-(time.perf_counter()-st)>.10:
                ans=pure.solve(source)
                if ans["status"] in ("SAT","UNSAT"):
                    status=ans["status"]
                    proof=ans["proof"]
                    elapsed=time.perf_counter()-st
                    if elapsed>=cap:status="TIMEOUT";proof="CAP"
                    return dict(status=status,elapsed=elapsed,proof=proof,route="pure_exact",
                                reason=reason,screen=info,preprocess=ans)
                route="clean";reason="not_source_pure"
        if route=="certified_bridge" and mode!="shadow":
            # Expensive full reconstruction allowed only under strict size cap.
            if (info["m"]<=FULL_MAX_CLAUSES and
                pathlib.Path(source).stat().st_size<=FULL_MAX_BYTES and
                cap-(time.perf_counter()-st)>.20):
                t=time.perf_counter()
                cert=certified_preprocess(source,pathlib.Path(scratch)/"strengthened.cnf")
                cert["full_s"]=time.perf_counter()-t
                if cert["kind"]=="unsat":
                    elapsed=time.perf_counter()-st
                    status="UNSAT" if elapsed<cap else "TIMEOUT"
                    return dict(status=status,elapsed=elapsed,
                                proof=cert["proof"] if status=="UNSAT" else "CAP",
                                route="certified_bridge",reason=reason,
                                screen=info,preprocess=cert)
                if cert["kind"]=="strengthened":inp=pathlib.Path(cert["file"])
                else:route="clean";reason="certified_no_useful_consequence"
            else:route="clean";reason="full_source_budget_abstain"
    remaining=cap-(time.perf_counter()-st)
    if remaining>0.12:
        try:status,model=native(binary,inp,remaining)
        except subprocess.TimeoutExpired:status="TIMEOUT"
    elapsed=time.perf_counter()-st
    if elapsed>=cap:status="TIMEOUT"
    if status=="SAT":
        verify_model(source,model)
        proof="SAT_WITNESS_CHECKED_ORIGINAL_SHA"
    elif status=="UNSAT":
        proof="CDCL_UNSAT_NOT_INDEPENDENTLY_LRAT_CERTIFIED"
    else:proof="CAP"
    return dict(status=status,elapsed=elapsed,proof=proof,
                route=route,reason=reason,screen=info,preprocess=cert)

def selftest():
    with tempfile.TemporaryDirectory() as td:
        t=pathlib.Path(td)
        # Same relation across variable renaming and reordered original clause order.
        def xor(vs,rhs):
            return [tuple(-v if (mask>>j)&1 else v for j,v in enumerate(vs))
                    for mask in range(8) if (mask.bit_count()&1)==1-rhs]
        a=xor((1,2,3),1)
        b=xor((9,4,7),1)
        def write(name,n,cs):
            f=t/name
            f.write_text(f"p cnf {n} {len(cs)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in cs))
            return f
        p=write("a.cnf",3,a)
        q=write("b.cnf",9,b[::-1])
        x,y=fingerprint(p),fingerprint(q)
        need(x["complete_xor3"]==y["complete_xor3"]==1,"canonical xor3")
        need(x["motif_pointer"]==y["motif_pointer"],"renaming invariant")
        need(decide(x,p)[0]=="pure_exact","pure routing")
        need(pure.solve(p)["status"]=="SAT","verified original pure source")
        wrong=write("wrong.cnf",3,[a[0],a[1],a[2],(-1,2,3)])
        need(fingerprint(wrong)["complete_xor3"]==0,"non-parity quartet false positive")
        conflict=write("conflict.cnf",3,a+xor((1,2,3),0))
        z=fingerprint(conflict)
        need(z["complete_xor3"]==2,"xor contradiction")
        assert certified_preprocess(conflict,t/"never.cnf")["kind"]=="unsat"
        mixed=write("mixed.cnf",5,a+[(1,4,5)])
        need(fingerprint(mixed)["classification"].startswith("certified_xor"),"mixed no guessed structure")
    print("NEW_HORIZON_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    selftest()
