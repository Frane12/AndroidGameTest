#!/usr/bin/env python3
"""DRNAS MRE4 P3 / Q1: certified equivalence quotient, R28 safe preserved.

Hypothesis: eliminate an independent Boolean decision by certified equivalence
rather than injecting potentially redundant watched clauses. Candidate source:
two ORIGINAL CNF binary clauses (-a v b) & (a v -b), or two proof-replayed
MRE1/CRR clauses. Transform CNF by b:=a and optionally transform source GF(2)
rows. SAT witnesses are lifted and checked against the ORIGINAL frozen CNF.

All comparisons use one pinned CMS5.11.15 instrumented MRE5 library, trace OFF,
OTF Gaussian OFF, same original input/seed per arm. Prep is charged to wall.
R28 safe is imported UNMODIFIED from MRE4 P1; no unsafe UNSAT shortcut.
No online promotion: source set reused development + new SYNTHETIC controls,
not a blind official-source holdout.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,sys,tempfile,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre4_safe_causal as p1
import mre4_p3_certified_quotient as quotient
import mre1_cross_representation as mre1
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

PROTO="DRNAS-MRE4-P3-CERTIFIED-QUOTIENT-Q1-40SHA-6ARMS-2REP-30S-v1"
ROOT=pathlib.Path("mre4_p3")
FROZEN=ROOT/"frozen"
MODES=("cms_native","r28_safe","xor_source","eq_shadow",
       "eq_quotient_no_xor","eq_quotient_with_xor")
CAP=30.0
REPS=2
SHARDS=8
MAX_GATE_CLAUSES=18000
MAX_GATE_BYTES=9000000
MAX_EQ_CANDIDATES=32
MAX_DERIVE_S=0.11
MAX_PREP_BUDGET=0.40
MAX_SOURCE_ROWS=32
MIN_REPLACED_OCCURRENCES=4
MIN_CLAUSES_SAVED=1
SYNTH_SEED="MRE4-P3-Q1-SOURCE-DISJOINT-SYNTHETIC-20261108-v1"

def need(x,msg):
    if not x:raise RuntimeError("MRE4_P3_FAIL_CLOSED "+str(msg))
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def normalize(c):return mre1.normalize(c)

def synthetic(i):
    """New SAT controls, not a substitute for blind original SAT2026 sources."""
    seed=int(sha(SYNTH_SEED+"|"+str(i))[:15],16)
    rng=random.Random(seed)
    n=165+3*i
    plant={v:bool(rng.getrandbits(1)) for v in range(1,n+1)}
    keep,drop=7+i,100+i
    plant[drop]=plant[keep]
    clauses=[(-keep,drop),(keep,-drop)]
    for j in range(500+25*i):
        vs=rng.sample(range(1,n+1),3)
        if j<220:vs[0]=drop
        vs=list(dict.fromkeys(vs))
        while len(vs)<3:
            x=rng.randrange(1,n+1)
            if x not in vs:vs.append(x)
        literals=[v if rng.getrandbits(1) else -v for v in vs]
        if not any(plant[abs(v)]==(v>0) for v in literals):
            q=rng.randrange(3);v=vs[q]
            literals[q]=v if plant[v] else -v
        clauses.append(tuple(literals))
    src=f"c MRE4 P3 synthetic positive equality witness, seed {seed}\n"
    src+=f"p cnf {n} {len(clauses)}\n"
    src+="".join(" ".join(str(l) for l in c)+" 0\n" for c in clauses)
    return src,seed,(keep,drop)

def freeze():
    original=r195.cases()
    need(len(original)==32,"original MRE4 development SHA count changed")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    import shutil
    for c in original:
        src=r195.FROZEN/c["name"]
        need(r195.digest(src)==c["sha256"],"old frozen SHA failed")
        dest=FROZEN/c["name"];shutil.copy2(src,dest)
        cases.append(dict(name=c["name"],sha256=c["sha256"],
            bytes=dest.stat().st_size,cohort=c["cohort"],
            expected=c["expected"],source="reused_MRE4_original_frozen_SHA"))
    for i in range(8):
        content,seed,pair=synthetic(i)
        dest=FROZEN/f"p3-synthetic-equivalence-{i:02}.cnf"
        dest.write_text(content)
        cases.append(dict(name=dest.name,sha256=r195.digest(dest),
            bytes=dest.stat().st_size,
            cohort="p3_new_synthetic_equivalence",
            expected="SAT",source="new_fixed_seed_synthetic_NOT_official_holdout",
            generator_seed=seed,planted_pair=list(pair)))
    need(len(cases)==40 and len({c["sha256"] for c in cases})==40,
         "not 40 unique development sources")
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
        original_mre4_manifest_sha256=r195.digest(r195.FROZEN/"manifest.json"),
        official_source_blind=False,synthetic_source_blind_to_previous=False,
        total_trials=40*REPS*len(MODES),cap_s=CAP))
    print("MRE4_P3_FREEZE_PASS",len(cases),flush=True)

def cases():
    m=json.loads((FROZEN/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==40,"manifest protocol/source count")
    for c in m["cases"]:
        f=FROZEN/c["name"]
        need(f.is_file() and f.stat().st_size==c["bytes"] and
             r195.digest(f)==c["sha256"],"frozen source changed: "+c["name"])
    return m["cases"]

def find_principle(original,source_rows,proofs):
    """Direct CNF clauses are already proofs; MRE1 lemmas need full replay."""
    existing={normalize(c) for c in original}
    choices=[]
    for c in original:
        if len(c)!=2:continue
        a,b=c
        if a>0 or b<0:continue
        # The opposite is checked with canonical literal normalization.
        low,high=-a,b
        if low==high or not (low<high):continue
        req1=normalize((-low,high))
        req2=normalize((low,-high))
        if req1 in existing and req2 in existing:
            choices.append((low,high,"direct_original_cnf_binary_pair"))
    if proofs:
        need(mre1.verify_proofs(original,source_rows,proofs),
             "MRE1 independent proof replay refused")
        derived={tuple(p["clause"]) for p in proofs}
        for c in derived:
            if len(c)!=2:continue
            x,y=c
            if (x>0)==(y>0):continue
            a,b=sorted((abs(x),abs(y)))
            req1=normalize((-a,b));req2=normalize((a,-b))
            if req1 in existing|derived and req2 in existing|derived:
                choices.append((a,b,"replayed_mre1_proof_pair"))
    occurrences=collections.Counter(abs(v) for c in original for v in c)
    candidates=[]
    for a,b,kind in sorted(set(choices)):
        # To remove work, prefer variable with more original occurrences.
        pr=dict(principle="certified_equality",keep=a,remove=b,
           proof_replayed=True,proof_kind=kind,
           proof_lemma_a=normalize((-a,b)),proof_lemma_b=normalize((a,-b)))
        cnf,unused_rows,stats=quotient.apply_quotient(original,[],pr)
        saved=len(original)-len(cnf)
        changed=stats["cnf"]["replaced_occurrences"]
        if changed<MIN_REPLACED_OCCURRENCES or saved<MIN_CLAUSES_SAVED:
            continue
        candidates.append((saved,changed,pr,cnf,stats))
    if not candidates:return None
    candidates.sort(key=lambda x:(x[0],x[1]),reverse=True)
    saved,changed,pr,cnf,stats=candidates[0]
    need(pr["proof_lemma_a"] in existing or
        any(tuple(p["clause"])==pr["proof_lemma_a"] for p in proofs),
        "first equality implication missing evidence")
    need(pr["proof_lemma_b"] in existing or
        any(tuple(p["clause"])==pr["proof_lemma_b"] for p in proofs),
        "second equality implication missing evidence")
    return pr,cnf,stats

def prepare(source,mode):
    begun=time.perf_counter()
    meta=dict(route="cms_native",reason=None,quotient=False,
        source_rows=0,proof_checked=False,merged_variables=0,
        source_clauses_saved=0,prep_seconds=None,
        proof_kind=None,active_var_reduction_proven=False,
        budget_s=MAX_PREP_BUDGET,
        source_xor_import_for_quotient=False)
    if mode=="cms_native":
        return None,[],None,meta,None
    if mode=="r28_safe":
        a,b,original_meta,status,proof=p1.prepare(source,"r28_safe")
        meta.update(route=original_meta["route"],reason=original_meta["prep_abstain"],
                    r28_original_proof=proof,quotient=False)
        return None,[],None,meta,status
    n,m=p1.header(source)
    f=pathlib.Path(source)
    if m>MAX_GATE_CLAUSES or f.stat().st_size>MAX_GATE_BYTES or m<2:
        meta.update(reason="cheap_size_budget_abstain")
        return None,[],None,meta,None
    if mode=="xor_source":
        _,original=exact.parse_dimacs(source)
        if time.perf_counter()-begun>MAX_PREP_BUDGET:
            meta["reason"]="source_parse_over_budget";return None,[],None,meta,None
        rows=r195.certified_source_rows(original)[:MAX_SOURCE_ROWS]
        if rows:
            mre1.replay_source_xors(original,rows)
        if time.perf_counter()-begun>MAX_PREP_BUDGET:
            meta["reason"]="source_GF2_over_budget";return None,[],None,meta,None
        meta.update(route="xor_source",source_rows=len(rows),
                    proof_checked=True)
        return None,rows,None,meta,None
    n2,original=exact.parse_dimacs(source)
    need(n2==n and len(original)==m,"source header mismatch")
    if time.perf_counter()-begun>MAX_PREP_BUDGET:
        meta["reason"]="full_source_parse_budget";return None,[],None,meta,None
    # Full-source XOR detection is proof-replayed, *only* where cheap; no
    # unconditional MRE1 reduce/BCP loop, only if a quotient prospect exists.
    original_set={normalize(c) for c in original}
    direct=sum(1 for c in original if len(c)==2 and len(set(c))==2 and
         ((a:=min(abs(c[0]),abs(c[1])))!=max(abs(c[0]),abs(c[1]))) and
         normalize((-a,max(abs(c[0]),abs(c[1])))) in original_set and
         normalize((a,-max(abs(c[0]),abs(c[1])))) in original_set)
    sig=p1.prefix_signal(source) if not direct else {"found_xor_rows":0}
    if not direct and sig.get("found_xor_rows",0)==0:
        meta["reason"]="no_original_equivalence_or_prefix_XOR"
        return None,[],None,meta,None
    rows=[]
    proofs=[]
    if not direct or mode=="eq_quotient_with_xor":
        rows=r195.certified_source_rows(original)[:MAX_SOURCE_ROWS]
        if rows:mre1.replay_source_xors(original,rows)
    if not direct and rows and time.perf_counter()-begun<MAX_PREP_BUDGET/2:
        saved=(mre1.MAX_SOURCE_ROWS,mre1.MAX_DERIVED,
               mre1.MAX_BINARY_POOL,mre1.MAX_CHECKS)
        try:
            mre1.MAX_SOURCE_ROWS=MAX_SOURCE_ROWS
            mre1.MAX_DERIVED=32
            mre1.MAX_BINARY_POOL=100
            mre1.MAX_CHECKS=600
            s,proofs,stats=mre1.derive(original,max_s=MAX_DERIVE_S)
            need(stats["proof_replayed"],"independent MRE1 proof replay missing")
            rows=s
        finally:
            (mre1.MAX_SOURCE_ROWS,mre1.MAX_DERIVED,
             mre1.MAX_BINARY_POOL,mre1.MAX_CHECKS)=saved
    if time.perf_counter()-begun>MAX_PREP_BUDGET:
        meta["reason"]="proof_prep_over_budget"
        return None,[],None,meta,None
    found=find_principle(original,rows,proofs)
    if not found:
        meta["reason"]="no_certificate_or_no_search_reduction"
        return None,[],None,meta,None
    pr,cnf,st=found
    if mode=="eq_quotient_with_xor":
        qcnf,qrows,qst=quotient.apply_quotient(original,rows,pr)
        cnf=qcnf;rows=qrows;st=qst
    else:rows=[]
    if time.perf_counter()-begun>MAX_PREP_BUDGET:
        meta["reason"]="post_quotient_budget"
        return None,[],None,meta,None
    meta.update(route=("eq_shadow_same_prep" if mode=="eq_shadow"
                  else "certified_equality_quotient"),
                proof_checked=True,quotient=(mode!="eq_shadow"),
                merged_variables=int(mode!="eq_shadow"),
                source_clauses_saved=len(original)-len(cnf),
                proof_kind=pr["proof_kind"],
                active_var_reduction_proven=True,
                source_xor_import_for_quotient=(mode=="eq_quotient_with_xor"),
                source_rows=len(rows))
    if mode=="eq_shadow":
        return None,[],pr,meta,None
    return cnf,rows,pr,meta,None

def one(c,mode,rep,binary):
    source=FROZEN/c["name"]
    start=time.perf_counter()
    need(r195.digest(source)==c["sha256"],"source hash mismatch")
    seed=int(sha(PROTO+"|"+c["sha256"]+"|"+str(rep))[:8],16)
    transformed,rows,pr,meta,fast=prepare(source,mode)
    prep_s=time.perf_counter()-start
    answer="TIMEOUT";stats={};proof="CAP_TIMEOUT"
    if fast=="SAT":
        need(mode=="r28_safe" and meta["r28_original_proof"]==
             "EXACT_CNFEQUIV_GAUSS_SAT_MODEL_CHECKED",
             "R28 requires checked full original SAT witness")
        answer="SAT";proof="EXACT_CNFEQUIV_GAUSS_SAT_MODEL_CHECKED"
    else:
        left=CAP-(time.perf_counter()-start)
        if left>0.1:
            with tempfile.TemporaryDirectory(prefix="mre4-p3-") as td:
                d=pathlib.Path(td)
                infile=source
                if transformed is not None:
                    nn,_=p1.header(source)
                    infile=d/"quotient.cnf"
                    mre1.write_cnf(infile,nn,transformed,[])
                sourcexor=d/"certified-xors.tsv"
                empty=d/"empty.tsv"
                empty.write_text("")
                mre1.write_xors(sourcexor,rows)
                env=os.environ.copy()
                env["DRNAS_TRACE_ENABLED"]="0"
                env["DRNAS_ORIG_COUNT"]=str(len(transformed) if transformed is not None
                    else p1.header(source)[1])
                env["DRNAS_TAG_0"]=""
                env["DRNAS_TAG_1"]=""
                try:
                    out=subprocess.run([str(pathlib.Path(binary).resolve()),
                        str(infile.resolve()),str(sourcexor.resolve()),
                        str(empty.resolve()),"source_xor_no_gauss",str(seed)],
                        env=env,capture_output=True,text=True,errors="replace",
                        timeout=max(0.001,CAP-(time.perf_counter()-start)),check=False)
                except subprocess.TimeoutExpired:out=None
                if out is not None:
                    need(out.returncode==0,"CMS source or transformed witness failure "+
                        out.stderr[-1300:])
                    answer,model,stats=r195.parsed_native(out.stdout)
                    if answer=="SAT":
                        if transformed is not None:
                            need(pr is not None and meta["active_var_reduction_proven"],
                                 "quotient missing certificate")
                            model=quotient.reconstruct(model,pr)
                        r195.verify_model(source,model)
                        proof="ORIGINAL_CNF_SAT_WITNESS_LIFTED_AND_CHECKED"
                    elif answer=="UNSAT":
                        proof="CMS_UNSAT_NO_INDEPENDENT_LRAT"
    wall=time.perf_counter()-start
    if wall>=CAP:
        answer="TIMEOUT";proof="CAP_TIMEOUT"
    if answer!="TIMEOUT":
        need(answer==c["expected"],"wrong original verdict")
    return dict(protocol=PROTO,case=c["name"],source_sha256=c["sha256"],
       cohort=c["cohort"],mode=mode,rep=rep,seed=seed,status=answer,proof=proof,
       par2_s=round(2*CAP if answer=="TIMEOUT" else wall,6),
       wall_s=round(wall,6),prep_s=round(prep_s,6),
       reduced_variables=meta["merged_variables"],
       saved_clauses=meta["source_clauses_saved"],
       quotient_proof=meta["proof_kind"],
       native_conflicts=stats.get("conflicts"),
       native_decisions=stats.get("decisions"),
       native_propagations=stats.get("propagations"),
       original_sat_witness_checked=(answer=="SAT"),
       source_blind=False,independent_unsat_lrat=False,
       native_otf_gauss=False,meta=meta,
       commit=os.environ.get("GITHUB_SHA","local"))

def shard(k,binary):
    need(0<=k<SHARDS,"shard index")
    cs=cases();out=[]
    for c in cs[k::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=one(c,mode,rep,binary)
                out.append(r);save(ROOT/f"shard-{k}.json",out)
                print("MRE4_P3_TRIAL",json.dumps({x:r[x] for x in
                  ("case","cohort","mode","rep","status","par2_s",
                   "prep_s","reduced_variables","saved_clauses",
                   "native_conflicts","native_decisions")},sort_keys=True),
                   flush=True)
    need(len(out)==len(cs[k::SHARDS])*REPS*len(MODES),"partial shard")
    print("MRE4_P3_SHARD_PASS",k,len(out),flush=True)

def audit():
    cs=cases();bysha={c["sha256"]:c for c in cs}
    pair=collections.defaultdict(dict);allrows=[]
    for k in range(SHARDS):
        rr=json.loads((ROOT/f"shard-{k}.json").read_text())
        need(len(rr)==len(cs[k::SHARDS])*REPS*len(MODES),
             "incomplete source shard")
        allrows+=rr
    need(len(allrows)==40*REPS*len(MODES)==480,"not 480 matched trials")
    for r in allrows:
        need(r["source_sha256"] in bysha and
             r["case"]==bysha[r["source_sha256"]]["name"],"source identity drift")
        need(r["protocol"]==PROTO and not r["native_otf_gauss"],
             "unsafe CMS configuration")
        if r["status"]=="SAT":
            need(r["original_sat_witness_checked"] and
                 r["proof"] in ("EXACT_CNFEQUIV_GAUSS_SAT_MODEL_CHECKED",
                   "ORIGINAL_CNF_SAT_WITNESS_LIFTED_AND_CHECKED"),"unchecked SAT")
        if r["reduced_variables"]:
            need(r["mode"].startswith("eq_quotient") and
                 r["quotient_proof"] in (
                   "direct_original_cnf_binary_pair","replayed_mre1_proof_pair") and
                 r["saved_clauses"]>=MIN_CLAUSES_SAVED,
                 "unproven search-space reduction")
        if r["mode"]=="eq_shadow":
            need(r["reduced_variables"]==0,"shadow changed search dimension")
        need(abs(r["par2_s"]-(CAP*2 if r["status"]=="TIMEOUT"
                               else r["wall_s"]))<1e-5,"bad PAR2 accounting")
        k=(r["source_sha256"],r["rep"])
        need(r["mode"] not in pair[k],"duplicated arm")
        pair[k][r["mode"]]=r
    need(len(pair)==40*REPS,"missing source/seed matches")
    for v in pair.values():
        need(set(v)==set(MODES),"missing arm")
        need(len({r["status"] for r in v.values()
                  if r["status"]!="TIMEOUT"})<=1,"SAT/UNSAT verdict mismatch")
    totals={}
    for cohort in ("reused_official_2026","reused_synthetic_controls",
                   "new_mixed_xor_cnf","p3_new_synthetic_equivalence","all"):
        x=[r for r in allrows if cohort=="all" or r["cohort"]==cohort]
        totals[cohort]={}
        for mode in MODES:
            a=[r for r in x if r["mode"]==mode]
            totals[cohort][mode]=dict(n=len(a),solved=sum(r["status"]!="TIMEOUT" for r in a),
                par2_s=round(sum(r["par2_s"] for r in a),6),
                prep_s=round(sum(r["prep_s"] for r in a),6),
                quotient_calls=sum(r["reduced_variables"]>0 for r in a),
                certified_eliminated_variables=sum(r["reduced_variables"] for r in a),
                clauses_saved=sum(r["saved_clauses"] for r in a))
    # Never promote without independent official-source blind holdout.
    report=dict(protocol=PROTO,status="MRE4_P3_Q1_DEVELOPMENT_AUDIT_PASS",
       original_sha_count=40,attempts=480,
       results=totals,all_sat_original_models_verified=True,
       unsat_independent_proof=False,otf_gauss_disabled=True,
       r28_safe_path_unmodified=True,source_blind=False,
       promotion_allowed=False,
       hypothesis="certified model-reconstructible quotient decreases independent search coordinates",
       reject_unprofitable_gate=True,
       mandatory_next="freeze gate then SAT2026 source-disjoint blind holdout")
    save(ROOT/"report.json",report);save(ROOT/"all-trials.json",allrows)
    print("MRE4_P3_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    quotient.selftest()
    need(MODES[1]=="r28_safe" and 40*REPS*len(MODES)==480,
         "R28 / trial protocol drift")
    s,seed,eq=synthetic(0)
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"synthetic.cnf";p.write_text(s)
        n,clauses=exact.parse_dimacs(p)
        need(n>100 and len(clauses)>400,"controlled positive case incorrect")
        pr=find_principle(clauses,[],[])
        need(pr and pr[0]["keep"]==eq[0] and
             pr[0]["remove"]==eq[1],"synthetic equality proof not detected")
        n0=len(set(abs(l) for c in clauses for l in c))
        n1=len(set(abs(l) for c in pr[1] for l in c))
        need(n1<n0,"equivalence did not eliminate search variable")
        print("MRE4_P3_SYNTHETIC_CERTIFIED_QUOTIENT_PASS",
              len(clauses),len(pr[1]),n0,n1,flush=True)
    print("MRE4_P3_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--binary",default="mre5/native")
    x=a.parse_args()
    if x.action=="selftest":selftest()
    elif x.action=="freeze":freeze()
    elif x.action=="verify":print("MRE4_P3_VERIFY_PASS",len(cases()),flush=True)
    elif x.action=="shard":shard(x.shard,x.binary)
    elif x.action=="audit":audit()
