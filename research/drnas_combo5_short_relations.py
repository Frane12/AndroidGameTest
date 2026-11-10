#!/usr/bin/env python3
"""COMBO5: short 2/3-variable XOR relations with original-DIMACS certificates.
29 SHA (17 GF2-S1 + 12 SEARCH6), 6 arms x 2 reps = 348 oneCPU E2E attempts.
Previously observed and diagnostic, NOT global blind holdout. Never infer
an original UNSAT from transformed-CNF backend UNSAT without original proof.
Source-complete 2..6 XOR roots, pair/triple derived rows; independent separate
source parity reconstruction AND GF2 parent-XOR replay before injection.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,os,pathlib,random,shutil,subprocess,tempfile,time
import drnas_gf2_screen6 as screen
import drnas_gf2_proof_first_s1 as s1
import drnas_binary_scc2_e2e as s2
import drnas_equiv9_prospective_seed_holdout as e9

ROOT=pathlib.Path("mre_combo5")
ORIGINAL=e9.SOURCE
SEARCH6=pathlib.Path("mre_search6")
CMS=pathlib.Path("mre_equiv12/bin/cryptominisat5")
PROOFSET=pathlib.Path("prior_combo2proof/report.json")
PROTO="DRNAS-COMBO5-29SHA-XOR2-3-PAIR-TRIPLE-GF2PROOF-6ARM-2REP-10S-v1"
ARMS=("cms_plain","cms_placebo","cms_prooffirst",
      "cms_pair2","cms_pair23","kissat_plain")
N=29
REPS=2
SHARDS=6
CAP=10.0
SCAN_LIMIT=1.1
MAX_RELS=8
MAX_EXTRA_CLAUSES=32
EXPECTED=N*len(ARMS)*REPS

def need(ok,why):
    if not ok:raise RuntimeError("COMBO5_FAIL_CLOSED "+str(why))
def sha(p):return e9.digest(p)
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,val):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(val,sort_keys=True,indent=2)+"\n")

def sources():
    a=[dict(x,source_cohort="gf2s1") for x in s2.cases()]
    b=[dict(x,source_cohort="search6") for x in
       read(SEARCH6/"manifest.json")["original_SHA_sources"]]
    cases=a+b
    need(len(a)==17 and len(b)==12 and len(cases)==N and
         len({c["sha256"] for c in cases})==N and
         len({c["gbd"] for c in cases})==N,
         "frozen original-SHA cohort overlap or count mismatch")
    return sorted(cases,key=lambda c:c["sha256"])

def src(c):
    p=ORIGINAL/c["filename"]
    need(p.is_file() and sha(p)==c["sha256"],"original CNF SHA drift")
    return p

def certified_SHA():
    evidence=read(PROOFSET)
    need(evidence["protocol"]==
      "DRNAS-COMBO2-2ORIGINAL-SHA-PINNED-CMS17-CAKEML-BINARY-XLRUP-v1"
      and evidence["independent_XLRUP_CakeML_verified_count"]==2,
      "original externally certified UNSAT evidence absent")
    proofs={k for k,v in evidence["certificates"].items()
        if v["independent_verified"] and v["certification_status"]==
              "CERTIFIED_ORIGINAL_UNSAT_BY_CMS_XLRUP_CAKEML"}
    need(len(proofs)==2,"expected exactly two CakeML source certificates")
    return proofs

def signature():
    return dict(py=sha(__file__),
       screen6=sha("research/drnas_gf2_screen6.py"),
       gf2_source=sha("research/drnas_gf2_proof_first_s1.cpp"),
       gf2_native=sha(s1.BIN),cms_native=sha(CMS),
       kissat_native=sha(e9.KISSAT),
       gf2s1_manifest=sha("mre_gf2_s1/manifest.json"),
       scc2_manifest=sha("mre_binary_scc2/manifest.json"),
       search6_manifest=sha(SEARCH6/"manifest.json"),
       original_certs=sha(PROOFSET))

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    ORIGINAL.mkdir(parents=True,exist_ok=True)
    need(s1.BIN.is_file() and CMS.is_file() and e9.KISSAT.is_file(),
         "pinned binaries missing")
    cs=sources()
    for c in cs:
        if c["source_cohort"]=="search6":
            original=SEARCH6/"cases"/c["filename"]
            need(original.is_file() and sha(original)==c["sha256"],
                 "SEARCH6 source SHA mismatch")
            dst=ORIGINAL/c["filename"]
            if dst.exists():need(sha(dst)==c["sha256"],"existing original SHA drift")
            else:shutil.copyfile(original,dst)
        src(c)
    verified=certified_SHA()
    need(verified<={c["sha256"] for c in cs},
         "XLRUP source not in original cohort")
    m=dict(protocol=PROTO,cases=cs,source_count=N,arms=list(ARMS),
       cap_s=CAP,reps=REPS,shards=SHARDS,expected_trials=EXPECTED,
       scanner_limit_s=SCAN_LIMIT,max_new_relations=MAX_RELS,
       max_derived_clauses=MAX_EXTRA_CLAUSES,
       original_SHA_unchanged=True,one_logical_CPU=True,
       no_parallel_solver_children=True,
       source_XOR_root_complete_blocks_only=True,
       every_derived_relation_original_CNF_replayed=True,
       SAT_original_witness_verified=True,
       independent_LRAT_for_backend_UNSAT=False,
       external_CakeML_XLRUP_original_source_proofs=sorted(verified),
       previously_observed_NOT_BLIND=True,
       no_automatic_promotion=True,sha256_pins=signature())
    save(ROOT/"manifest.json",m);verify()
    print("COMBO5_FROZEN "+json.dumps(dict(original_sha=N,
       arms=len(ARMS),trials=EXPECTED,GF2_S1=17,SEARCH6=12,
       globally_blind=False),sort_keys=True),flush=True)

def verify():
    m=read(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["source_count"]==N and
         m["cases"]==sources() and m["arms"]==list(ARMS) and
         m["cap_s"]==CAP and m["shards"]==SHARDS and
         m["reps"]==REPS and m["expected_trials"]==EXPECTED and
         m["scanner_limit_s"]==SCAN_LIMIT and
         m["sha256_pins"]==signature(),"code/binary/source freeze drift")
    need(set(m["external_CakeML_XLRUP_original_source_proofs"])==certified_SHA(),
         "external proof evidence changed")
    for c in m["cases"]:src(c)
    return m

def independent_roots(clauses):
    """Separate original-clause parity reconstruction; never trust SCREEN6 roots."""
    complete=collections.defaultdict(set)
    units={}
    for clause in clauses:
        if len(clause)==1:
            v=abs(clause[0]);bit=int(clause[0]>0)
            if v in units:need(units[v]==bit,"contradictory source units: abstain")
            units[v]=bit
        if not 2<=len(clause)<=6:continue
        ids=tuple(sorted(abs(l) for l in clause))
        if len(ids)!=len(set(ids)):continue
        signed=set(clause)
        sign=tuple(int(-v in signed) for v in ids)
        complete[ids].add(sign)
    result=set()
    for vs,patterns in complete.items():
        for rhs in (0,1):
            forbidden=1-rhs
            required={bits for bits in itertools.product((0,1),repeat=len(vs))
                      if sum(bits)%2==forbidden}
            if not required.issubset(patterns):continue
            remaining=tuple(v for v in vs if v not in units)
            adjusted=rhs
            for v in vs:
                if v in units:adjusted^=units[v]
            if len(remaining)>=2:result.add((remaining,adjusted))
    return result

def root_proof_check(clauses,raw):
    again=independent_roots(clauses)
    need(set(raw)==again and len(raw)==len(again),
         "independent original-CNF parity reconstruction disagrees")

def relation_candidates(original,method):
    """Pure-source diagnostic: run from its OWN subprocess with strict timeout."""
    n,clauses=e9.x22.read_cnf(original)
    raw,meta=screen.full_source_scan(clauses)
    if meta["contradictory_original_units"] or meta["source_root_empty_contradictions"]:
        return dict(roots=0,selected=[],reason="source_unit_conflict_abstain")
    pair,tri=screen.pair_trip_screen(raw)
    allproofs=list(pair["proofs"])
    if method=="pair23":allproofs+=tri["proofs"]
    # Importance for residual CDCL clauses, never from benchmark outcomes.
    freq=collections.Counter(abs(lit) for clause in clauses
             if 2<=len(clause)<=8 for lit in clause)
    scored={}
    original=set(raw)
    for p in allproofs:
        vs=tuple(p["vars"]);rhs=p["rhs"]
        if not 2<=len(vs)<=3 or (vs,rhs) in original:continue
        if len(p["parents"])<2:continue
        if not p["strict_shorter_than_every_parent"]:continue
        score=sum(min(200,freq[v]) for v in vs)/(len(vs)**2)
        if score<=0:continue
        key=(vs,rhs)
        old=scored.get(key)
        if old is None or len(p["parents"])<len(old["parents"]):
            scored[key]=dict(p,impact=round(score,3))
    sorted_proofs=sorted(scored.values(),key=lambda p:(
       -p["impact"],len(p["vars"]),len(p["parents"]),
       p["vars"],p["rhs"],p["parents"]))
    selected=[];extra=0
    for p in sorted_proofs:
        cost=1<<(len(p["vars"])-1)
        if len(selected)>=MAX_RELS:break
        if extra+cost>MAX_EXTRA_CLAUSES:continue
        selected.append(p);extra+=cost
    return dict(roots=len(raw),selected=selected,all_pair_unique=pair["unique_short_novel"],
       all_triple_unique=tri["unique_short_novel"],
       novel_binary_pairs=pair["new_binary_xor"],
       strict_pair=pair["strict_shorter"],triple_capped=tri["triple_enumeration_capped"],
       pair_capped=pair["pair_enumeration_capped"],
       augmented_clauses=extra,reason="source_structural_proof_screen")

def scan_cli(original,method):
    try:
        d=relation_candidates(original,method)
        print("COMBO5_RELATION_RESULT "+json.dumps(d,sort_keys=True),flush=True)
    except Exception as error:
        print("COMBO5_SCAN_ERROR "+repr(error),flush=True)
        raise

def verify_candidates(original,selected):
    need(len(selected)<=MAX_RELS,"too many derived parity rows")
    n,clauses=e9.x22.read_cnf(original)
    raw,meta=screen.full_source_scan(clauses)
    need(not meta["contradictory_original_units"],"original contradictory units")
    root_proof_check(clauses,raw)
    seen=set();verified=[]
    for p in selected:
        vs=tuple(p["vars"]);rhs=p["rhs"];parents=p["parents"]
        need(len(vs) in (2,3) and len(vs)==len(set(vs))
             and rhs in (0,1) and max(vs)<=n
             and len(parents)==len(set(parents))
             and 2<=len(parents)<=screen.MAX_GAUSS_ROOTS and
             all(type(i) is int and 0<=i<len(raw) for i in parents),
             "untrusted short XOR relation")
        accum=set();bit=0
        for i in parents:
            source_vars,source_rhs=raw[i]
            accum.symmetric_difference_update(source_vars)
            bit^=source_rhs
        need(accum==set(vs) and bit==rhs and
             (vs,rhs) not in set(raw) and (vs,rhs) not in seen,
             "independent GF2 relation proof failed")
        # Strictly more concise than EVERY contributing root.
        need(len(vs)<min(len(raw[i][0]) for i in parents),
             "candidate is not strictly shorter than source parents")
        seen.add((vs,rhs));verified.append((vs,rhs))
    need(sum(1<<(len(vs)-1) for vs,_ in verified)<=MAX_EXTRA_CLAUSES,
         "derived CNF addition exceeds cap")
    return verified

def scan(original,method):
    start=time.perf_counter()
    try:
        cmd=["python3",str(pathlib.Path(__file__).resolve()),
             "scan",str(original.resolve()),method]
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,timeout=SCAN_LIMIT)
    except subprocess.TimeoutExpired:
        return dict(proofs=[],scan_s=round(time.perf_counter()-start,6),
                    roots=0,reason="scanner_time_bound",candidates=0,strict_pairs=0)
    if p.returncode!=0:
        return dict(proofs=[],scan_s=round(time.perf_counter()-start,6),
                    roots=0,reason="scanner_fail_closed",candidates=0,strict_pairs=0)
    lines=[l[len("COMBO5_RELATION_RESULT "):] for l in p.stdout.splitlines()
           if l.startswith("COMBO5_RELATION_RESULT ")]
    need(len(lines)==1,"invalid scanner JSON output")
    record=json.loads(lines[0]);raw=record["selected"]
    verified=verify_candidates(original,raw) if raw else []
    return dict(proofs=verified,scan_s=round(time.perf_counter()-start,6),
       roots=record["roots"],reason=record["reason"],
       candidates=len(raw),strict_pairs=record.get("strict_pair",0),
       all_pair_unique=record.get("all_pair_unique",0),
       novel_binary_pairs=record.get("novel_binary_pairs",0),
       extra_clauses=record.get("augmented_clauses",0))

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="combo5-toy-") as d:
        path=pathlib.Path(d)/"original.cnf"
        def eq(vs,rhs):
            return [tuple(-v if (mask>>i)&1 else v for i,v in enumerate(vs))
                    for mask in range(1<<len(vs))
                    if mask.bit_count()%2 != rhs]
        def make(clauses,n):
            path.write_text("p cnf %d %d\n"%(n,len(clauses))+
                "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses))
        # Two different complete width-3 roots, sharing 2 vars,
        # entail short x4 XOR x3 = 1 without a source unit.
        cls=eq((1,2,3),0)+eq((1,2,4),1)
        make(cls,4)
        checked=scan(path,"pair")
        need(any(set(vs)=={3,4} and rhs==1 for vs,rhs in checked["proofs"]),
             "missing independently verified binary XOR shortening")
        make(cls[:-1],4)
        invalid=scan(path,"pair")
        need(not any(set(vs)=={3,4} for vs,rhs in invalid["proofs"]),
             "unsafe incomplete XOR source clause pattern")
        # Genuine three-root-only short relation: all root widths 3,
        # first and second partially cancel, third completes two-variable XOR.
        c=eq((1,2,3),0)+eq((1,2,4),0)+eq((3,4,5),1)
        make(c,5)
        proof=scan(path,"pair23")
        need(any(set(vs)=={5} for vs,rhs in proof["proofs"]) is False,
             "derived unit should not masquerade as binary/ternary relation")
        # Independent original 0=1 source proof, not short-relational evidence.
        source=next(c for c in s2.cases()
                    if c["sha256"]==s1.KNOWN_CERT_SHA)
        # Only actual freeze loads original; selftest is called after source restore.
        full=s1.scan(s1.original_path(source))
        need(full["proved"] and full["proof"]["terms"]==196,
             "old 196-term original GF2 contradiction not independently replayed")
    print("COMBO5_SELFTEST_PASS "+json.dumps(dict(
      complete_XOR_pair_binary_derived_and_verified=True,
      incomplete_XOR_negative_control=True,
      original_196_equation_GF2_certificate_verified=True,
      original_SHA_only=True),sort_keys=True),flush=True)

def augmented_cnf(original,target,relations):
    n,clauses=e9.x22.read_cnf(original)
    cost=sum(1<<(len(vs)-1) for vs,_ in relations)
    need(cost<=MAX_EXTRA_CLAUSES,"bound on strengthened source CNF")
    with open(target,"w") as f:
        f.write("p cnf %d %d\n"%(n,len(clauses)+cost))
        for cl in clauses:f.write(" ".join(map(str,cl))+" 0\n")
        for vs,rhs in relations:
            for mask in range(1<<len(vs)):
                if mask.bit_count()%2==rhs:continue
                cl=[-v if mask&(1<<i) else v for i,v in enumerate(vs)]
                f.write(" ".join(map(str,cl))+" 0\n")

def cms(original,altered,cap):
    n,orig=e9.x22.read_cnf(original)
    need(n>0 and len(orig)>0,"DIMACS original invalid")
    cpu=min(os.sched_getaffinity(0))
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        child=e9.x22.launch("cms",
              [str(CMS),"--verb","0","-t","1",str(altered)],cpu,tmp)
        status="TIMEOUT";witness=False
        try:
            while child["p"].poll() is None and time.perf_counter()-start<cap-.018:
                time.sleep(.004)
            if child["p"].poll() is not None:
                output,err=e9.x22.read_output(child)
                status,witness=e9.x22.solver_result("cms",
                     child["p"].returncode,output,orig,{})
        finally:e9.x22.cleanup([child])
    if time.perf_counter()-start>=cap:status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"reported model invalid on ORIGINAL CNF")
    return status,bool(witness)

def one(c,rep,arm):
    need(rep in range(REPS) and arm in ARMS,"invalid paired test")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    start=time.perf_counter();parent_cpu=time.process_time();child_cpu=e9.x22.child_cpu()
    original=src(c)
    state=None;shortcut=False;relations=[];backend=False
    if arm in ("cms_placebo","cms_prooffirst","cms_pair2","cms_pair23"):
        proof=s1.scan(original)
        shortcut=bool(proof["proved"] and arm!="cms_placebo")
    else:proof=None
    if arm in ("cms_placebo","cms_pair2","cms_pair23") and not shortcut:
        method="pair23" if arm in ("cms_placebo","cms_pair23") else "pair"
        state=scan(original,method)
        if arm!="cms_placebo":relations=state["proofs"]
    status="UNSAT" if shortcut else "TIMEOUT";witness=False
    if not shortcut:
        left=CAP-(time.perf_counter()-start)
        if left>.09:
            backend=True
            if arm=="kissat_plain":
                s2.ROOT.mkdir(parents=True,exist_ok=True)
                b=s2.trial(dict(c,cohort="holdout"),rep,"kissat_orig",cap=left)
                status=b["status"];witness=b["SAT_original_witness_verified"]
            elif relations:
                with tempfile.TemporaryDirectory(dir=ROOT) as folder:
                    stronger=pathlib.Path(folder)/"strengthened.cnf"
                    augmented_cnf(original,stronger,relations)
                    left=CAP-(time.perf_counter()-start)
                    if left>.09:status,witness=cms(original,stronger,left)
            else:
                status,witness=cms(original,original,left)
    wall=time.perf_counter()-start
    if wall>=CAP:status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"SAT original model missing")
    need(sha(original)==c["sha256"],"original changed during trial")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
      cohort=c["source_cohort"],arm=arm,rep=rep,cap_s=CAP,
      one_logical_CPU=cpu,one_backend_child_max=True,
      original_SHA_verified=True,
      status=status,SAT_original_witness_verified=bool(witness if status=="SAT" else False),
      UNSAT_original_GF2_certified=shortcut,
      UNSAT_standard_LRAT_from_backend=False,
      gf2_cert_terms=proof["proof"]["terms"] if shortcut else 0,
      GF2_original_equations=proof["equations"] if proof else None,
      source_complete_XOR_roots=state["roots"] if state else None,
      candidate_rels=state["candidates"] if state else 0,
      independent_original_GF2_derived_rels=len(state["proofs"]) if state else 0,
      appended_short_rels=len(relations),
      appended_entailed_clauses=sum(1<<(len(vs)-1) for vs,rhs in relations),
      strict_pair_candidates=state.get("strict_pairs",0) if state else 0,
      novel_binary_pair_count=state.get("novel_binary_pairs",0) if state else 0,
      scan_reason=state["reason"] if state else "no_pair_scan",
      original_proof_scan_s=proof["probe_wall_s"] if proof else 0,
      short_relation_scan_s=state["scan_s"] if state else 0,
      backend_called=backend,wall_E2E_s=round(wall,6),
      actual_parent_CPU_s=round(time.process_time()-parent_cpu,6),
      actual_child_CPU_s=round(e9.x22.child_cpu()-child_cpu,6))

def shard(index):
    need(index in range(SHARDS),"invalid shard index")
    m=verify();cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==index]
    out=[]
    for c in cs:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(c["sha256"]+str(rep)+"COMBO5").shuffle(order)
            for arm in order:
                row=one(c,rep,arm);row["shard"]=index
                need(row["wall_E2E_s"]<=CAP+.2,"E2E cap violation")
                out.append(row);save(ROOT/f"shard-{index}.json",out)
                print("COMBO5_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(out)==len(cs)*REPS*len(ARMS),"incomplete shard")
    print("COMBO5_SHARD_PASS %d %d"%(index,len(out)),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        rr=read(ROOT/f"shard-{i}.json")
        need(len(rr)==len([c for j,c in enumerate(m["cases"]) if j%SHARDS==i])*REPS*len(ARMS),
             "incomplete paired shard")
        rows+=rr
    expected={(c["sha256"],rep,arm) for c in m["cases"]
              for rep in range(REPS) for arm in ARMS}
    got={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(got)==len(rows)==EXPECTED and got==expected,
         "original SHA pair count or arm mismatch")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["original_SHA_verified"]
             and r["one_backend_child_max"] and r["cap_s"]==CAP
             and r["status"] in ("SAT","UNSAT","TIMEOUT")
             and (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "invalid SAT witness, original proof or source metadata")
        bysha[r["sha256"]].append(r)
    independent=certified_SHA()|{sha for sha,rr in bysha.items() if
          any(r["UNSAT_original_GF2_certified"] for r in rr)}
    refagree={sha for sha,rr in bysha.items()
           if any(r["arm"]=="cms_plain" and r["status"]=="UNSAT" for r in rr)
           and any(r["arm"]=="kissat_plain" and r["status"]=="UNSAT" for r in rr)}
    for sha,rr in bysha.items():
        need(len({r["status"] for r in rr if r["status"]!="TIMEOUT"})<=1,
             "SAT and UNSAT on same original SHA")
    def accepted(r):
        return r["status"]=="SAT" and r["SAT_original_witness_verified"] or (
               r["status"]=="UNSAT" and r["sha256"] in (independent|refagree))
    def penalty(r):return r["wall_E2E_s"] if accepted(r) else 2*CAP
    def stats(rr):
        return dict(trials=len(rr),solved=sum(accepted(r) for r in rr),
          SAT_original_verified=sum(r["status"]=="SAT" and accepted(r) for r in rr),
          UNSAT_independent_original=sum(r["status"]=="UNSAT" and r["sha256"] in independent for r in rr),
          UNSAT_reference_agreed_no_independent_proof=sum(r["status"]=="UNSAT" and
                              r["sha256"] in refagree-independent for r in rr),
          raw_UNSAT_unverified=sum(r["status"]=="UNSAT" and not accepted(r) for r in rr),
          timeouts=sum(r["status"]=="TIMEOUT" for r in rr),
          PAR2_s=round(sum(penalty(r) for r in rr),6),
          total_actual_CPU_s=round(sum(r["actual_parent_CPU_s"]+r["actual_child_CPU_s"] for r in rr),6),
          total_wall_s=round(sum(r["wall_E2E_s"] for r in rr),6),
          original_GF2_math_shortcuts=sum(r["UNSAT_original_GF2_certified"] for r in rr),
          original_GF2_complete_XOR_rows=sum(r["GF2_original_equations"] or 0 for r in rr),
          independently_derived_short_relation_trials=sum(r["independent_original_GF2_derived_rels"]>0 for r in rr),
          appended_derived_relation_trials=sum(r["appended_short_rels"]>0 for r in rr),
          total_relations_appended=sum(r["appended_short_rels"] for r in rr),
          total_entailed_clauses_appended=sum(r["appended_entailed_clauses"] for r in rr),
          total_scan_wall_s=round(sum(r["short_relation_scan_s"]+
                    r["original_proof_scan_s"] for r in rr),6))
    scores={arm:stats([r for r in rows if r["arm"]==arm]) for arm in ARMS}
    for arm in ARMS:
        scores[arm]["speedup_vs_CMS_x"]=round(scores["cms_plain"]["PAR2_s"]/
                             scores[arm]["PAR2_s"],6)
    paired={}
    for arm in ARMS:
        if arm=="cms_plain":continue
        diff=[]
        for sha,rr in bysha.items():
            for rep in range(REPS):
                a=next(r for r in rr if r["arm"]==arm and r["rep"]==rep)
                b=next(r for r in rr if r["arm"]=="cms_plain" and r["rep"]==rep)
                diff.append(penalty(a)-penalty(b))
        paired[arm]=dict(wins=sum(d<-.02 for d in diff),losses=sum(d>.02 for d in diff),
          ties=sum(abs(d)<=.02 for d in diff),
          net_PAR2_gain_s=round(-sum(diff),6),
          max_gain_s=round(-min(diff),6),
          max_regression_s=round(max(diff),6))
    report=dict(protocol=PROTO,original_sources=N,total_trials=EXPECTED,
       one_logical_CPU=True,globally_blind=False,
       independent_original_GF2_replay=True,
       novel_short_parity_proofs_not_LRAT=True,
       independent_XLRUP_original_SHA=sorted(certified_SHA()),
       independently_certified_GF2_original_SHA=sorted(independent-certified_SHA()),
       reference_agreement_no_standard_proof_SHA=sorted(refagree-independent),
       backend_UNSAT_without_original_proof_not_accepted=True,
       no_automatic_promotion=True,
       scores=scores,paired=paired,
       per_shard={str(i):{a:stats([r for r in rows if r["shard"]==i and r["arm"]==a])
                      for a in ARMS} for i in range(SHARDS)},
       per_SHA={sha:{a:[dict(rep=r["rep"],status=r["status"],E2E_s=r["wall_E2E_s"],
              source_roots=r["source_complete_XOR_roots"],
              strict_pairs=r["strict_pair_candidates"],
              verified_new_relations=r["independent_original_GF2_derived_rels"],
              appended=r["appended_short_rels"],clauses=r["appended_entailed_clauses"],
              math_unsat=r["UNSAT_original_GF2_certified"],
              scan_s=r["short_relation_scan_s"],
              reason=r["scan_reason"])
              for r in rr if r["arm"]==a] for a in ARMS} for sha,rr in bysha.items()})
    save(ROOT/"report.json",report)
    print("COMBO5_FINAL "+json.dumps(report,sort_keys=True),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","verify","shard","audit","scan"))
    parser.add_argument("source",nargs="?")
    parser.add_argument("method",nargs="?")
    parser.add_argument("--shard",type=int,default=0)
    a=parser.parse_args()
    if a.action=="scan":
        need(a.source is not None and a.method in ("pair","pair23"),
             "invalid scanner subcommand")
        scan_cli(pathlib.Path(a.source),a.method)
    elif a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard)
    elif a.action=="verify":verify();print("COMBO5_VERIFY_PASS",flush=True)
    else:globals()[a.action]()

if __name__=="__main__":main()
