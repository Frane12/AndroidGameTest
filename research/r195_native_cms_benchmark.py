#!/usr/bin/env python3
"""R195 first-stage LIVE CMS native GF(2) experiment; verified pre-SOLVE bridge.

A genuinely in-CDCL GF(2) engine is CryptoMiniSat's native Gaussian propagator:
we pass certified source XORs and (separately) DRNAS pair-derived XORs through
CMSat::SATSolver::add_xor_clause BEFORE solve; CMS's own Gaussian machinery then
propagates them DURING CDCL. This does NOT implement a separate DRNAS trail
callback or record per-reason adoption yet. Mode labels must not imply it does.
No source clauses are removed; all source XORs are truth-table-complete and
every derived XOR is replayed as the XOR of two source equations.

Cohorts: 8 reused SAT Competition 2026 originals from earlier Y005 benchmark,
16 reused Y005 synthetic controls, and 8 NEW fixed-seed mixed XOR/CNF probes.
No blind-real performance claims. Evaluate mechanism before new blind holdout.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, re
import shutil, subprocess, sys, time
from itertools import combinations

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as exact

ROOT=pathlib.Path("r195")
FROZEN=ROOT/"frozen"
PRIOR=pathlib.Path("drnas_yalsat_unseen/frozen")
PROTO="DRNAS-R195-CMS-EXACT-GF2-NATIVE-IN-CDCL-STAGE1-32SHA-4ARMS-2REP-30S-v1"
MODES=("cms_native","source_xor_import","derived_shadow","derived_active")
CAP=30.
REPS=2
SHARDS=8
MAX_WIDTH=6
MAX_SOURCE=180
MAX_DERIVED=48
SALT="R195-MIXED-CNF-XOR-FROZEN-20261108-V1"

def need(b,why):
    if not b:raise RuntimeError("R195_FAIL_CLOSED "+str(why))

def digest(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as fp:
        for chunk in iter(lambda:fp.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()

def sha_text(s):return hashlib.sha256(s.encode()).hexdigest()

def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")

def xor_cnf(vs,rhs):
    result=[]
    for bits in range(1<<len(vs)):
        if (bits.bit_count()%2)==rhs:continue
        result.append([(-v if bits&(1<<j) else v) for j,v in enumerate(vs)])
    return result

def mixed_case(i):
    seed=int(sha_text(SALT+"/"+str(i))[:15],16)
    rng=random.Random(seed)
    n=65+4*i
    plant={v:rng.randrange(2) for v in range(1,n+1)}
    clauses=[]
    for k in range(11):
        vs=[k+1,k+2,k+3] # neighboring equations give short derived XORs
        rhs=plant[vs[0]]^plant[vs[1]]^plant[vs[2]]
        clauses.extend(xor_cnf(vs,rhs))
        if i%2==1 and k==4:
            clauses.extend(xor_cnf(vs,1-rhs))  # provably UNSAT from original
    for j in range(n*3):
        vs=rng.sample(range(1,n+1),3)
        lits=[v if rng.randrange(2) else -v for v in vs]
        if not any(plant[abs(l)]==(l>0) for l in lits):
            idx=rng.randrange(3);v=vs[idx]
            lits[idx]=v if plant[v] else -v
        clauses.append(lits)
    expected="SAT" if i%2==0 else "UNSAT"
    content=f"c R195 frozen new mixed GF2/CNF seed={seed}\np cnf {n} {len(clauses)}\n"
    content+="".join(" ".join(map(str,c))+" 0\n" for c in clauses)
    return content,expected,seed

def freeze():
    old=json.loads((PRIOR/"manifest.json").read_text())
    need(len(old["cases"])==24 and old["official_count"]==8 and
         old["synthetic_count"]==16,"previous actual Y005 sources not present")
    FROZEN.mkdir(parents=True,exist_ok=True)
    rows=[]
    for c in old["cases"]:
        src=PRIOR/c["name"]
        need(digest(src)==c["sha256"] and src.stat().st_size==c["bytes"],
             "previous original SHA mismatch")
        dst=FROZEN/c["name"];shutil.copyfile(src,dst)
        rows.append(dict(name=dst.name,sha256=c["sha256"],bytes=c["bytes"],
            cohort="reused_official_2026" if c["cohort"]=="official_2026_new_to_tracked"
               else "reused_synthetic_controls",
            expected=c["expected"],source=c["source"]))
    for i in range(8):
        s,status,seed=mixed_case(i)
        dst=FROZEN/f"r195-new-mixed-{i}.cnf";dst.write_text(s)
        rows.append(dict(name=dst.name,sha256=digest(dst),bytes=dst.stat().st_size,
            cohort="new_mixed_xor_cnf",expected=status,seed=seed,
            source="fixed seed R195 synthetic mixed XOR/CNF generator"))
    need(len(rows)==32 and len({x["sha256"] for x in rows})==32,"32 unique sources required")
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=rows,
         caps_s=CAP,repetitions=REPS,cohorts={
         "reused_official_2026":8,"reused_synthetic_controls":16,
         "new_mixed_xor_cnf":8},
         prior_y005_manifest_sha256=digest(PRIOR/"manifest.json"),
         limitations=["2026 official cohort reused, NOT blind",
             "Synthetic 8 new fixed seeds exercise mechanism, not general SAT performance",
             "No DRNAS external live trail callback in R195 stage 1"]))
    print("R195_FREEZE_PASS",len(rows),flush=True)

def cases():
    m=json.loads((FROZEN/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==32,"manifest provenance changed")
    cs=m["cases"]
    for c in cs:
        p=FROZEN/c["name"]
        need(p.stat().st_size==c["bytes"] and digest(p)==c["sha256"],
             "source SHA mismatch "+c["name"])
    return cs

def certified_source_rows(clauses):
    """Independent truth-table check for each complete parity CNF block."""
    by_vars=collections.defaultdict(set)
    for c in clauses:
        if not 2<=len(c)<=MAX_WIDTH:continue
        ordered=sorted(c,key=abs)
        vs=tuple(abs(q) for q in ordered)
        if len(vs)!=len(set(vs)):continue
        mask=sum(1<<j for j,l in enumerate(ordered) if l<0)
        by_vars[vs].add(mask)
    rows=set()
    for vs,masks in by_vars.items():
        for forbidden_parity in (0,1):
            must={i for i in range(1<<len(vs))
                  if (i.bit_count()%2)==forbidden_parity}
            if must.issubset(masks):
                rhs=1-forbidden_parity
                # Replay the truth-table implication WITHOUT relying on
                # the extractor's original calculation.
                for assignment in range(1<<len(vs)):
                    if (assignment.bit_count()%2)==rhs:continue
                    need(assignment in masks,"XOR source evidence replay failed")
                rows.add((vs,rhs))
    return sorted(rows,key=lambda r:(len(r[0]),r[0],r[1]))

def xor_pair(a,b):
    aa,ar=a;bb,br=b
    vars_=tuple(sorted(set(aa)^set(bb)))
    return (vars_,ar^br)

def prep(source,src_out,derive_out,meta_out,derive):
    # This complete scan is charged INSIDE every non-native trial.
    n,clauses=exact.parse_dimacs(source)
    all_rows=certified_source_rows(clauses)
    # Favor short and repeated/residual-connected source rows.
    source_rows=all_rows[:MAX_SOURCE]
    derived=[]
    evidence=[]
    seen=set(source_rows)
    for ia,a in enumerate(source_rows):
        for ib in range(ia+1,len(source_rows)):
            b=source_rows[ib]
            vars_,rhs=xor_pair(a,b)
            if not 2<=len(vars_)<=MAX_WIDTH:continue
            row=(vars_,rhs)
            if row in seen:continue
            # Independent replay with full parity truth table for small widths.
            for bits in range(1<<len(set(a[0])|set(b[0]))):
                universe=sorted(set(a[0])|set(b[0]))
                assignment={v:(bits>>i)&1 for i,v in enumerate(universe)}
                av=sum(assignment[v] for v in a[0])%2
                bv=sum(assignment[v] for v in b[0])%2
                if av==a[1] and bv==b[1]:
                    need(sum(assignment[v] for v in vars_)%2==rhs,
                         "derived XOR proof invalid")
            seen.add(row)
            derived.append(row)
            evidence.append((ia,ib))
            if len(derived)>=MAX_DERIVED:break
        if len(derived)>=MAX_DERIVED:break
    if not derive:
        derived=[];evidence=[]
    for target,rows in ((src_out,source_rows),(derive_out,derived)):
        p=pathlib.Path(target);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text("".join(str(len(vs))+" "+str(rhs)+" "+
              " ".join(map(str,vs))+"\n" for vs,rhs in rows))
    meta=dict(source_sha256=digest(source),variables=n,
         source_rows_total=len(all_rows),
         source_rows_imported=len(source_rows),
         derived_rows_proven=len(derived),
         derived_source_index_pairs=[list(pair) for pair in evidence],
         proof_method="complete parity CNF truth table + verified GF2 XOR pair",
         source_rows_sha256=digest(src_out),derived_rows_sha256=digest(derive_out))
    save(meta_out,meta)
    return meta

def parsed_native(text):
    m=re.search(r"^R195_RESULT status=(SAT|UNSAT|TIMEOUT) conflicts=(\d+) decisions=(\d+) propagations=(\d+) source_rows=(\d+) derived_rows=(\d+)$",text,re.M)
    need(m is not None,"no exact R195 native stats")
    model={}
    for l in text.splitlines():
        if not l.startswith("v "):continue
        for v in map(int,l[2:].split()):
            if v:
                k=abs(v)
                need(k not in model or model[k]==(v>0),"inconsistent witness")
                model[k]=v>0
    return m[1],model,dict(conflicts=int(m[2]),decisions=int(m[3]),
                          propagations=int(m[4]),source_rows=int(m[5]),
                          derived_rows=int(m[6]))

def verify_model(source,model):
    n,clauses=exact.parse_dimacs(source)
    need(len(model)>=n,"SAT witness has no complete original model")
    for c in clauses:
        need(any(model.get(abs(x),False)==(x>0) for x in c),
             "SAT witness falsifies original clause")

def trial(c,rep,mode,binary):
    source=FROZEN/c["name"]
    need(digest(source)==c["sha256"],"source drift")
    started=time.perf_counter()
    seed=int(sha_text(PROTO+c["sha256"]+str(rep))[:8],16)
    source_file=ROOT/f"tmp-{os.getpid()}-source.tsv"
    derived_file=ROOT/f"tmp-{os.getpid()}-derived.tsv"
    meta_file=ROOT/f"tmp-{os.getpid()}-meta.json"
    for file in (source_file,derived_file,meta_file):
        pathlib.Path(file).parent.mkdir(parents=True,exist_ok=True)
    source_file.write_text("")
    derived_file.write_text("")
    info=dict(source_rows_imported=0,derived_rows_proven=0)
    elapsed_prep=0.
    if mode!="cms_native":
        # Native gets no prep; all added GF2 must pay its full source scan.
        info=prep(source,source_file,derived_file,meta_file,
                  derive=(mode in ("derived_shadow","derived_active")))
        elapsed_prep=time.perf_counter()-started
    result="TIMEOUT";model={};stats=dict(conflicts=0,decisions=0,propagations=0,
                                       source_rows=0,derived_rows=0)
    time_left=CAP-(time.perf_counter()-started)
    if time_left>0.05:
        try:
            p=subprocess.run([str(pathlib.Path(binary).resolve()),
                  str(source.resolve()),str(source_file.resolve()),
                  str(derived_file.resolve()),mode,str(seed)],
                  capture_output=True,text=True,errors="replace",
                  timeout=time_left,check=False)
        except subprocess.TimeoutExpired:
            p=None
        if p is not None:
            need(p.returncode==0,"CMS bridge exited %s: %s"%(
                 p.returncode,p.stderr[-2000:]))
            result,model,stats=parsed_native(p.stdout)
            if result=="SAT":
                verify_model(source,model)
    elapsed=time.perf_counter()-started
    if elapsed>=CAP:result="TIMEOUT"
    if result!="TIMEOUT":
        need(c["expected"]==result,"expected verdict disagreement")
    row=dict(protocol=PROTO,id=c["name"],source_sha256=c["sha256"],
       cohort=c["cohort"],rep=rep,mode=mode,status=result,
       elapsed_s=round(elapsed,6),par2_s=round(2*CAP if result=="TIMEOUT" else elapsed,6),
       prep_s=round(elapsed_prep,6),source_rows=stats["source_rows"],
       derived_rows=stats["derived_rows"],
       discovered_source_rows=info["source_rows_imported"],
       discovered_derived_rows=info["derived_rows_proven"],
       cms_conflicts=stats["conflicts"],
       cms_decisions=stats["decisions"],
       cms_propagations=stats["propagations"],
       proof="ORIGINAL_CNF_SAT_WITNESS_CHECKED" if result=="SAT"
          else "UNSAT_NO_INDEPENDENT_LRAT" if result=="UNSAT" else "CAP_TIMEOUT",
       run_id=os.environ.get("GITHUB_RUN_ID","local"),
       commit=os.environ.get("GITHUB_SHA","local"))
    for f in (source_file,derived_file,meta_file):
        if f.exists():f.unlink()
    return row

def shard(k,binary):
    need(0<=k<SHARDS,"invalid shard")
    rows=[];cs=cases()
    for c in cs[k::SHARDS]:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(arms)
            for mode in arms:
                row=trial(c,rep,mode,binary)
                rows.append(row)
                save(ROOT/f"shard-{k}.json",rows)
                print("R195_TRIAL",json.dumps({t:row[t] for t in (
                   "id","cohort","mode","rep","status","elapsed_s",
                   "par2_s","prep_s","source_rows","derived_rows",
                   "cms_conflicts","cms_decisions","cms_propagations")},sort_keys=True),
                   flush=True)
    need(len(rows)==len(cs[k::SHARDS])*REPS*len(MODES),"shard incomplete")
    print("R195_SHARD_PASS",k,len(rows),flush=True)

def audit():
    cs=cases();bysha={c["sha256"]:c for c in cs}
    rr=[]
    for i in range(SHARDS):
        a=json.loads((ROOT/f"shard-{i}.json").read_text())
        need(len(a)==len(cs[i::SHARDS])*REPS*len(MODES),"incomplete shard")
        rr+=a
    need(len(rr)==32*REPS*len(MODES)==256,"256 matched measurements required")
    pairs=collections.defaultdict(dict)
    for r in rr:
        need(r["source_sha256"] in bysha,"source SHA unfamiliar")
        need(r["id"]==bysha[r["source_sha256"]]["name"],"source label mismatch")
        key=(r["source_sha256"],r["rep"])
        need(r["mode"] not in pairs[key],"duplicate pairing")
        pairs[key][r["mode"]]=r
        need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"]))<1e-5,
             "PAR2 accounting mismatch")
        if r["status"]=="SAT":
            need(r["proof"]=="ORIGINAL_CNF_SAT_WITNESS_CHECKED","unverified SAT")
    need(len(pairs)==32*REPS,"missing source and repetition pair")
    for p in pairs.values():
        need(set(p)==set(MODES),"incomplete four-arm pair")
        need(len({v["status"] for v in p.values() if v["status"]!="TIMEOUT"})<=1,
             "contradictory SAT/UNSAT answers")
    totals={}
    for cohort in ("reused_official_2026","reused_synthetic_controls","new_mixed_xor_cnf","all"):
        vals=[r for r in rr if r["cohort"]==cohort or cohort=="all"]
        totals[cohort]={}
        for arm in MODES:
            x=[r for r in vals if r["mode"]==arm]
            totals[cohort][arm]=dict(attempts=len(x),
                solved=sum(v["status"]!="TIMEOUT" for v in x),
                sat=sum(v["status"]=="SAT" for v in x),
                unsat=sum(v["status"]=="UNSAT" for v in x),
                par2_s=round(sum(v["par2_s"] for v in x),6),
                prep_s=round(sum(v["prep_s"] for v in x),6),
                source_rows=sum(v["source_rows"] for v in x),
                derived_rows=sum(v["derived_rows"] for v in x),
                cms_conflicts=sum(v["cms_conflicts"] for v in x),
                cms_decisions=sum(v["cms_decisions"] for v in x),
                cms_propagations=sum(v["cms_propagations"] for v in x))
    report=dict(status="R195_STAGE1_AUDIT_PASS",protocol=PROTO,
       sources=32,attempts=256,cohorts=totals,
       full_wall_clock_includes_preparation=True,
       cms_runtime_native_api=True,
       active_gf2_propagation_inside_cms_existing_gauss=True,
       external_DRNAS_trail_callback=False,
       SAT_witness_original_verified=True,UNSAT_independent_LRAT=False,
       reused_official_originals_not_blind=True,
       original_manifest_sha256=digest(FROZEN/"manifest.json"))
    save(ROOT/"report.json",report);save(ROOT/"all-trials.json",rr)
    print("R195_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    cs=[]
    cs.extend(xor_cnf((1,2,3),1))
    cs.extend(xor_cnf((2,3,4),0))
    rows=certified_source_rows(cs)
    need(((1,2,3),1) in rows and ((2,3,4),0) in rows,"source detector")
    need(xor_pair(((1,2,3),1),((2,3,4),0))==((1,4),1),"GF2 XOR pair")
    for i in range(8):
        source,expected,_=mixed_case(i)
        need("p cnf" in source and expected in ("SAT","UNSAT"),"mixed generator")
    print("R195_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["selftest","freeze","verify","shard","audit"])
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r195/r195_native")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    if a.action=="freeze":freeze()
    if a.action=="verify":print("R195_VERIFY_PASS",len(cases()),flush=True)
    if a.action=="shard":shard(a.shard,a.binary)
    if a.action=="audit":audit()
