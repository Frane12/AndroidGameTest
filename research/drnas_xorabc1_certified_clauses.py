#!/usr/bin/env python3
"""XORABC1: proven parity-to-CNF clauses for pinned Kissat. Static lemmas, NOT live UP.
A untouched Kissat; B derived unit/binary GF(2); C derived <=3-literal GF(2);
P same C prepass but no clauses; CMS untouched reference.
40 previously frozen original SHA; original SAT checked; backend UNSAT not LRAT.
"""
from __future__ import annotations
import argparse,collections,itertools,json,os,pathlib,random,tempfile,time
import drnas_mixab2_frozen40_20s as prev
import drnas_gf2_proof_first_s1 as gf
import drnas_equiv9_prospective_seed_holdout as e9
ROOT=pathlib.Path("mre_xorabc1")
PROTO="DRNAS-XORABC1-40SHA-CERTIFIED-3VAR-CLAUSE-BRIDGE-1CPU-20S-v1"
ARMS=("A_kissat","B_xor_binary","C_xor_ternary","P_ternary_placebo","cms_plain")
N=40;REPS=2;SHARDS=10;CAP=20.;LIMIT=.8;MAX_EQUATIONS=3500;MAX_LEMMAS=384
EXPECTED=N*REPS*len(ARMS)
def need(x,s):
    if not x:raise RuntimeError("XORABC1_FAIL_CLOSED "+s)
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def read(p):return json.loads(pathlib.Path(p).read_text())
def sha(p):return e9.digest(p)
def signature():
    return dict(script=sha(__file__),prior=sha("research/drnas_mixab2_frozen40_20s.py"),
       verifier=sha("research/drnas_gf2_proof_first_s1.py"),
       kissat=sha(e9.KISSAT),cms=sha(prev.CMS),
       search5=sha(prev.SEARCH5/"manifest.json"),
       search6=sha(prev.SEARCH6/"manifest.json"),
       equiv9=sha(e9.ROOT/"manifest.json"))
def freeze():
    prev.freeze();cs=prev.roster()
    need(len(cs)==N,"roster wrong")
    m=dict(protocol=PROTO,arms=list(ARMS),source_count=N,cap_s=CAP,
       reps=REPS,shards=SHARDS,trials=EXPECTED,cases=cs,
       signatures=signature(),one_logical_CPU=True,not_blind=True,
       SHA_frozen=True,independent_original_GF2_certificates=True,
       SAT_original_witness_required=True,backend_UNSAT_no_independent_LRAT=True,
       placebo_same_prepass_no_lemmas=True,not_live_IPASIR_UP=True,
       no_auto_promotion=True)
    save(ROOT/"manifest.json",m);verify()
    print("XORABC1_FROZEN "+json.dumps(dict(sources=N,trials=EXPECTED,arms=len(ARMS),
            cap_s=CAP,one_cpu=True,not_blind=True)),flush=True)
def verify():
    m=read(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["cases"]==prev.roster() and m["signatures"]==signature() and
         m["cap_s"]==CAP and m["trials"]==EXPECTED,"protocol or original drift")
    for c in m["cases"]:prev.source(c)
    return m
def parity_clauses(vars_,rhs):
    return [tuple(-v if (mask>>i)&1 else v for i,v in enumerate(vars_))
            for mask in range(1<<len(vars_)) if mask.bit_count()%2!=rhs]
def basis_rows(eqs,maxwidth,deadline):
    basis={};contradiction=None;steps=0
    for i,(vs,rhs) in enumerate(eqs):
        v=set(vs);r=rhs;cert=1<<i
        while v:
            pivot=max(v)
            if pivot not in basis:
                basis[pivot]=(v,r,cert);break
            bv,br,bc=basis[pivot]
            v.symmetric_difference_update(bv);r^=br;cert^=bc;steps+=1
            if (steps&127)==0 and time.perf_counter()>deadline:
                return [],None,len(basis),True
        else:
            if r:contradiction=cert;break
        if i%64==0 and time.perf_counter()>deadline:
            return [],None,len(basis),True
    if contradiction is not None:
        return [],contradiction,len(basis),False
    reduced={}
    for i,p in enumerate(sorted(basis)):
        vs,r,cert=basis[p];vs=set(vs)
        while True:
            qs=[q for q in vs if q!=p and q in reduced]
            if not qs:break
            q=max(qs);bv,br,bc=reduced[q]
            vs.symmetric_difference_update(bv);r^=br;cert^=bc;steps+=1
            if (steps&127)==0 and time.perf_counter()>deadline:
                return [],None,len(basis),True
        reduced[p]=(vs,r,cert)
        if i%64==0 and time.perf_counter()>deadline:
            return [],None,len(basis),True
    candidates={}
    for vs,r,cert in itertools.chain(basis.values(),reduced.values()):
        if not (1<=len(vs)<=maxwidth and cert.bit_count()>=2):continue
        key=(tuple(sorted(vs)),r)
        if key not in candidates or cert.bit_count()<candidates[key].bit_count():
            candidates[key]=cert
    ordered=sorted(candidates.items(),key=lambda x:(len(x[0][0]),x[1].bit_count(),x[0]))
    return [(v,r,c) for (v,r),c in ordered[:96]],None,len(basis),False
def replay(src,count,vs,rhs,cert):
    _,_,eqs=gf.xor_equations_from_original(src)
    need(len(eqs)==count and cert>0 and cert>>len(eqs)==0,
         "original equation list mismatch")
    acc=set();r=0
    while cert:
        bit=cert&-cert;idx=bit.bit_length()-1;cert^=bit
        variables,parity=eqs[idx];acc.symmetric_difference_update(variables);r^=parity
    need(acc==set(vs) and r==rhs,"new CNF lemma not proved by original parity blocks")
def prep(src,original,width):
    t=time.perf_counter();deadline=t+LIMIT
    zero=dict(eq=0,rank=0,rows=0,lemmas=[],contradiction=False,
              gate="abstained",time=0)
    if src.stat().st_size>6*1024*1024:return dict(zero,time=time.perf_counter()-t,gate="oversize")
    n,k,eqs=gf.xor_equations_from_original(src)
    need(k==len(original),"original DIMACS parse disagreement")
    if len(eqs)>MAX_EQUATIONS or time.perf_counter()>deadline:
        return dict(zero,eq=len(eqs),time=time.perf_counter()-t)
    rows,proof,rank,timeout=basis_rows(eqs,width,deadline)
    if timeout:return dict(zero,eq=len(eqs),rank=rank,time=time.perf_counter()-t)
    if proof is not None:
        replay(src,len(eqs),(),1,proof)
        return dict(zero,eq=len(eqs),rank=rank,contradiction=True,gate="GF2_UNSAT",
                    time=time.perf_counter()-t)
    seen={tuple(sorted(c)) for c in original};new=[];verified=0
    for vs,rhs,cert in rows:
        if time.perf_counter()>deadline:
            return dict(zero,eq=len(eqs),rank=rank,time=time.perf_counter()-t)
        proposed=[c for c in parity_clauses(vs,rhs)
                  if tuple(sorted(c)) not in seen]
        if not proposed:continue
        if len(new)+len(proposed)>MAX_LEMMAS:break
        replay(src,len(eqs),vs,rhs,cert)
        verified+=1
        for c in proposed:
            seen.add(tuple(sorted(c)));new.append(c)
    return dict(eq=len(eqs),rank=rank,rows=verified,lemmas=new,
                contradiction=False,gate="verified" if new else "no_new_lemmas",
                time=time.perf_counter()-t)
def write_cnf(dst,n,clauses,lemmas):
    with pathlib.Path(dst).open("w") as f:
        f.write("p cnf %d %d\n"%(n,len(clauses)+len(lemmas)))
        for c in itertools.chain(clauses,lemmas):
            f.write(" ".join(map(str,c))+" 0\n")
def selftest():
    def encoded(rows):
        n=max(v for vs,_ in rows for v in vs);cls=[]
        for vs,r in rows:cls+=parity_clauses(vs,r)
        return n,cls
    tests=[("unit",[((1,3),0),((1,2,3),1)],1),
           ("binary",[((1,2,4),0),((2,3,4),0)],2),
           ("ternary",[((1,2,3,5),0),((3,4,5),0)],3)]
    with tempfile.TemporaryDirectory() as td:
        src=pathlib.Path(td)/"toy.cnf"
        for title,rows,k in tests:
            n,clauses=encoded(rows);write_cnf(src,n,clauses,[])
            r=prep(src,clauses,3)
            need(not r["contradiction"] and any(len(c)==k for c in r["lemmas"]),
                 "missing certified "+title)
            for bits in range(1<<n):
                model={i+1:bool(bits>>i&1) for i in range(n)}
                if e9.x22.holds(clauses,model):
                    need(e9.x22.holds(r["lemmas"],model),"source SAT assignment excluded")
        n,c=encoded([((1,2),0),((1,2),1)])
        write_cnf(src,n,c,[]);r=prep(src,c,3)
        need(r["contradiction"],"contradictory parity not certified")
        write_cnf(src,n,c[:-1],[]);r=prep(src,c[:-1],3)
        need(not r["contradiction"],"partial parity spuriously certified")
    print("XORABC1_SELFTEST_PASS "+json.dumps(dict(
        units=True,binary=True,ternary=True,exhaustive=True,
        contradictory_GF2=True,partial_negative=True)),flush=True)
def backend(target,original,kind,cpu,seconds,folder):
    if seconds<.08:return "TIMEOUT",False
    command=[str(e9.KISSAT),str(target)] if kind=="kissat" else [
        str(prev.CMS),"--verb","0","-t","1",str(target)]
    child=e9.x22.launch(kind,command,cpu,folder);t=time.perf_counter()
    status="TIMEOUT";witness=False
    try:
        while child["p"].poll() is None and time.perf_counter()-t<seconds-.018:
            time.sleep(.004)
        if child["p"].poll() is not None:
            out,_=e9.x22.read_output(child)
            status,witness=e9.x22.solver_result(kind,child["p"].returncode,out,original,{})
    finally:e9.x22.cleanup([child])
    if time.perf_counter()-t>=seconds:return "TIMEOUT",False
    return status,witness
def trial(c,rep,arm):
    need(arm in ARMS and rep in (0,1),"bad arm/rep")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    t=time.perf_counter();pc=time.process_time();cc=e9.x22.child_cpu()
    src=prev.source(c);n,original=e9.x22.read_cnf(src)
    need(n>0 and len(original)>0 and sha(src)==c["sha256"],"source modified")
    result=dict(eq=0,rank=0,rows=0,lemmas=[],contradiction=False,
                gate="unmodified",time=0.)
    if arm not in ("A_kissat","cms_plain"):
        result=prep(src,original,2 if arm=="B_xor_binary" else 3)
    enabled=arm in ("B_xor_binary","C_xor_ternary")
    cert=bool(result["contradiction"] and enabled)
    clauses=result["lemmas"] if enabled else []
    status="UNSAT" if cert else "TIMEOUT";verified=False;called=False
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        target=src
        if clauses:
            target=pathlib.Path(td)/"original_verified_lemmas.cnf"
            write_cnf(target,n,original,clauses)
        left=CAP-(time.perf_counter()-t)
        if not cert and left>.08:
            called=True
            status,verified=backend(target,original,
                                   "cms" if arm=="cms_plain" else "kissat",
                                   cpu,left,td)
    wall=time.perf_counter()-t
    if wall>=CAP:status="TIMEOUT";verified=False
    need(status!="SAT" or verified,"SAT model did not satisfy original")
    need(sha(src)==c["sha256"],"original source SHA changed")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],arm=arm,rep=rep,
       cap_s=CAP,one_cpu=cpu,original_SHA_verified=True,
       status=status,SAT_original_witness_verified=verified if status=="SAT" else False,
       UNSAT_GF2_proved_this_trial=cert,UNSAT_independent_LRAT=False,
       backend_called=called,GF2_equations=result["eq"],GF2_rank=result["rank"],
       GF2_derived_rows=result["rows"],GF2_lemmas_added=len(clauses),
       GF2_gate=result["gate"],GF2_prepass_s=round(result["time"],6),
       wall_E2E_s=round(wall,6),
       child_CPU_s=round(e9.x22.child_cpu()-cc,6),
       parent_CPU_s=round(time.process_time()-pc,6))
def shard(idx):
    m=verify();need(idx in range(SHARDS),"bad shard")
    cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx];allrows=[]
    for c in cs:
        for rep in range(REPS):
            arms=list(ARMS);random.Random(c["sha256"]+str(rep)+"xorabc1").shuffle(arms)
            for arm in arms:
                row=trial(c,rep,arm);row["shard"]=idx
                need(row["wall_E2E_s"]<=CAP+.2,"budget exceeded")
                allrows.append(row);save(ROOT/("shard-%d.json"%idx),allrows)
                print("XORABC1_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(allrows)==len(cs)*REPS*len(ARMS),"shard incomplete")
    print("XORABC1_SHARD_PASS %d %d"%(idx,len(allrows)),flush=True)
def audit():
    m=verify();allrows=[]
    for idx in range(SHARDS):
        rs=read(ROOT/("shard-%d.json"%idx))
        need(len(rs)==len([c for i,c in enumerate(m["cases"]) if i%SHARDS==idx])
             *REPS*len(ARMS),"incomplete shard JSON")
        allrows+=rs
    expected={(c["sha256"],rep,arm) for c in m["cases"]
              for rep in range(REPS) for arm in ARMS}
    keys={(r["sha256"],r["rep"],r["arm"]) for r in allrows}
    need(len(allrows)==len(keys)==EXPECTED and keys==expected,
         "paired trial omission or duplicate")
    bysha=collections.defaultdict(list)
    for r in allrows:
        need(r["protocol"]==PROTO and r["original_SHA_verified"]
          and r["wall_E2E_s"]<=CAP+.2 and r["status"] in ("SAT","UNSAT","TIMEOUT")
          and (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
          "trial correctness failure")
        bysha[r["sha256"]].append(r)
    math={s for s,rs in bysha.items() if any(r["UNSAT_GF2_proved_this_trial"] for r in rs)}
    consensus={s for s,rs in bysha.items()
       if any(r["arm"]=="A_kissat" and r["status"]=="UNSAT" for r in rs)
       and any(r["arm"]=="cms_plain" and r["status"]=="UNSAT" for r in rs)}
    for s,rs in bysha.items():
        need(len({r["status"] for r in rs if r["status"]!="TIMEOUT"})<=1,
             "SAT UNSAT inconsistency")
    def valid(r):
        return (r["status"]=="SAT" and r["SAT_original_witness_verified"]) or (
            r["status"]=="UNSAT" and r["sha256"] in (math|consensus))
    def par(r):return r["wall_E2E_s"] if valid(r) else 2*CAP
    def score(rows):
        return dict(attempts=len(rows),solved=sum(valid(r) for r in rows),
          SAT_original_verified=sum(valid(r) and r["status"]=="SAT" for r in rows),
          UNSAT_math_this_arm=sum(r["UNSAT_GF2_proved_this_trial"] for r in rows),
          UNSAT_reference_consensus_no_LRAT=sum(valid(r) and r["status"]=="UNSAT"
              and r["sha256"] in consensus-math for r in rows),
          UNSAT_unverified=sum(r["status"]=="UNSAT" and not valid(r) for r in rows),
          timeouts=sum(r["status"]=="TIMEOUT" for r in rows),
          PAR2_s=round(sum(par(r) for r in rows),6),
          actual_wall_s=round(sum(r["wall_E2E_s"] for r in rows),6),
          total_CPU_s=round(sum(r["child_CPU_s"]+r["parent_CPU_s"] for r in rows),6),
          GF2_certified_lemma_clauses=sum(r["GF2_lemmas_added"] for r in rows),
          GF2_derived_rows=sum(r["GF2_derived_rows"] for r in rows),
          GF2_probed_equations=sum(r["GF2_equations"] for r in rows),
          GF2_prepass_s=round(sum(r["GF2_prepass_s"] for r in rows),6),
          abstentions=sum(r["GF2_gate"]=="abstained" for r in rows))
    scores={arm:score([r for r in allrows if r["arm"]==arm]) for arm in ARMS}
    for a in ARMS:scores[a]["PAR2_speedup_vs_A_x"]=round(
         scores["A_kissat"]["PAR2_s"]/scores[a]["PAR2_s"],6)
    def paired(a,b):
        diff=[par(next(r for r in rs if r["arm"]==a and r["rep"]==rep))-
              par(next(r for r in rs if r["arm"]==b and r["rep"]==rep))
              for s,rs in bysha.items() for rep in range(REPS)]
        return dict(wins=sum(d<-.02 for d in diff),
          losses=sum(d>.02 for d in diff),ties=sum(abs(d)<=.02 for d in diff),
          gain_PAR2_s=round(-sum(diff),6),best_gain_s=round(min(diff),6),
          worst_regression_s=round(max(diff),6))
    comp=dict(B_vs_A=paired("B_xor_binary","A_kissat"),
      C_vs_A=paired("C_xor_ternary","A_kissat"),
      C_vs_B=paired("C_xor_ternary","B_xor_binary"),
      C_vs_placebo=paired("C_xor_ternary","P_ternary_placebo"),
      C_vs_CMS=paired("C_xor_ternary","cms_plain"))
    report=dict(protocol=PROTO,sources=N,trials=EXPECTED,
       original_sources_previously_seen_not_blind=True,one_CPU=True,
       static_CNF_bridge_not_live_CDCL=True,no_independent_backend_LRAT=True,
       independently_verified_Gf2_implied_lemmas=True,
       algebraic_UNSAT_SHA=sorted(math),backend_UNSAT_original_agreement=sorted(consensus),
       scores=scores,comparisons=comp,
       per_shard={str(i):{a:score([r for r in allrows if r["shard"]==i
                        and r["arm"]==a]) for a in ARMS} for i in range(SHARDS)})
    save(ROOT/"report.json",report)
    print("XORABC1_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["selftest","freeze","verify","shard","audit"])
    p.add_argument("--shard",type=int,default=-1)
    args=p.parse_args()
    if args.command=="selftest":selftest()
    elif args.command=="freeze":freeze()
    elif args.command=="verify":verify();print("XORABC1_VERIFY_PASS",flush=True)
    elif args.command=="shard":shard(args.shard)
    else:audit()
