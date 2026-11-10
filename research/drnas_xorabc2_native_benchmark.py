#!/usr/bin/env python3
"""XORABC2: natively derived and verified GF(2) short CNF consequences. No proof shortcut.
A untouched Kissat; B derived unit/binary GF(2); C derived <=3-literal GF(2);
P same C prepass but no clauses; CMS untouched reference.
40 previously frozen original SHA; original SAT checked; backend UNSAT not LRAT.
"""
from __future__ import annotations
import argparse,collections,itertools,json,os,pathlib,random,tempfile,time,subprocess
import drnas_mixab2_frozen40_20s as prev
import drnas_equiv9_prospective_seed_holdout as e9
ROOT=pathlib.Path("mre_xorabc2")
NATIVE=ROOT/"bin/xorabc2_native"
PROTO="DRNAS-XORABC2-40FROZEN-6ARM-NATIVE-GF2-CLAUSE-CAUSAL-1CPU-20S-v1"
ARMS=("A_kissat","B_xor_binary","PB_binary_placebo","C_xor_ternary","PC_ternary_placebo","cms_plain")
N=40;REPS=2;SHARDS=10;CAP=20.;NATIVE_TIMEOUT=.8;VERIFY_TIMEOUT=1.5
EXPECTED=N*REPS*len(ARMS)
def need(x,s):
    if not x:raise RuntimeError("XORABC2_FAIL_CLOSED "+s)
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def read(p):return json.loads(pathlib.Path(p).read_text())
def sha(p):return e9.digest(p)
def signature():
    return dict(script=sha(__file__),prior=sha("research/drnas_mixab2_frozen40_20s.py"),
       native_cpp=sha("research/drnas_xorabc2_native.cpp"),
       native_binary=sha(NATIVE),
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
       placebo_same_prepass_no_lemmas_for_B_and_C=True,
       no_GF2_UNSAT_shortcut=True,not_live_IPASIR_UP=True,
       no_auto_promotion=True)
    save(ROOT/"manifest.json",m);verify()
    print("XORABC2_FROZEN "+json.dumps(dict(sources=N,trials=EXPECTED,arms=len(ARMS),
            cap_s=CAP,one_cpu=True,not_blind=True)),flush=True)
def verify():
    m=read(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["cases"]==prev.roster() and m["signatures"]==signature() and
         m["cap_s"]==CAP and m["trials"]==EXPECTED,"protocol or original drift")
    for c in m["cases"]:prev.source(c)
    return m
def parity_clauses(vs,rhs):
    return [tuple(-v if mask>>i&1 else v for i,v in enumerate(vs))
            for mask in range(1<<len(vs)) if mask.bit_count()%2!=rhs]

def write_cnf(path,n,clauses):
    with pathlib.Path(path).open("w") as f:
        f.write("p cnf %d %d\n"%(n,len(clauses)))
        for c in clauses:f.write(" ".join(map(str,c))+" 0\n")

def native_prepass(src,mode,folder):
    """The generator AND original-CNF certificate checker are native C++.
    Python only launches/watches children and reads their results.
    """
    begin=time.perf_counter()
    target=pathlib.Path(folder)/("native_"+mode+".cnf")
    proof=pathlib.Path(folder)/("native_"+mode+".proof")
    try:
        raw=subprocess.run([str(NATIVE.resolve()),"derive",mode,
            str(src.resolve()),str(target.resolve()),str(proof.resolve())],
            capture_output=True,text=True,timeout=NATIVE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return dict(path=src,gate="native_timeout",eq=0,rank=0,rows=0,
                    lemmas=0,candidates=0,contradiction=False,
                    verified=False,time=time.perf_counter()-begin)
    need(raw.returncode==0,"native C++ derivation: "+raw.stderr[-1200:])
    lines=[x[len("XORABC2_NATIVE "):] for x in raw.stdout.splitlines()
           if x.startswith("XORABC2_NATIVE ")]
    need(len(lines)==1,"native result record missing")
    metrics=json.loads(lines[0])
    try:
        chk=subprocess.run([str(NATIVE.resolve()),"verify",
            str(src.resolve()),str(target.resolve()),str(proof.resolve())],
            capture_output=True,text=True,timeout=VERIFY_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError("XORABC2_FAIL_CLOSED native proof verification timeout")
    need(chk.returncode==0,"independent C++ verification: "+chk.stderr[-1200:])
    checks=[x[len("XORABC2_CHECK_PASS "):] for x in chk.stdout.splitlines()
            if x.startswith("XORABC2_CHECK_PASS ")]
    need(len(checks)==1,"checker PASS missing")
    r=json.loads(checks[0])
    need(r["rows"]==metrics["derived_rows"] and
         r["added_clauses"]==metrics["lemmas_added"],
         "native proof and emitted clause count mismatch")
    return dict(path=target,gate=metrics["gate"],eq=metrics["xor_equations"],
         rank=metrics["GF2_rank"],rows=metrics["derived_rows"],
         lemmas=metrics["lemmas_added"],candidates=metrics["candidate_rows"],
         contradiction=metrics["contradiction_seen"],verified=True,
         time=time.perf_counter()-begin)

def selftest():
    need(NATIVE.is_file(),"native C++ binary absent")
    ROOT.mkdir(parents=True,exist_ok=True)
    toys=[("unit",[((1,3),0),((1,2,3),1)],1,"b"),
          ("binary",[((1,2,4),0),((2,3,4),0)],2,"b"),
          ("ternary",[((1,2,3,5),0),((3,4,5),0)],3,"c")]
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        path=pathlib.Path(td)/"test.cnf"
        for label,eqs,width,mode in toys:
            n=max(v for vs,_ in eqs for v in vs)
            clauses=[c for vs,rhs in eqs for c in parity_clauses(vs,rhs)]
            write_cnf(path,n,clauses)
            x=native_prepass(path,mode,td)
            need(x["verified"] and x["lemmas"]>0,"native "+label+" proof absent")
            nn,aug=e9.x22.read_cnf(x["path"])
            added=aug[len(clauses):]
            need(nn==n and len(aug)>len(clauses) and
                 any(len(c)==width for c in added),"missing "+label+" clause")
            for bits in range(1<<n):
                model={i+1:bool(bits>>i&1) for i in range(n)}
                if e9.x22.holds(clauses,model):
                    need(e9.x22.holds(added,model),
                         "native lemma excludes an original SAT model")
        clauses=[c for vs,r in [((1,2),0),((1,2),1)]
                 for c in parity_clauses(vs,r)]
        write_cnf(path,2,clauses)
        c=native_prepass(path,"c",td)
        need(c["contradiction"] and not c["lemmas"],"no-shortcut rule violated")
        write_cnf(path,2,clauses[:-1])
        c=native_prepass(path,"c",td)
        need(not c["contradiction"],"partial XOR false positive")
    print("XORABC2_SELFTEST_PASS "+json.dumps(dict(
      native_unit_binary_ternary=True,native_independent_original_proof=True,
      original_SAT_truth_tables=True,no_GF2_unsat_shortcut=True,
      partial_pattern_negative=True)),flush=True)

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
    result=dict(path=src,gate="unmodified",eq=0,rank=0,rows=0,lemmas=0,
                candidates=0,contradiction=False,verified=False,time=0.)
    status="TIMEOUT";verified=False;called=False
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        if arm not in ("A_kissat","cms_plain"):
            mode="b" if arm in ("B_xor_binary","PB_binary_placebo") else "c"
            result=native_prepass(src,mode,td)
        use_clauses=arm in ("B_xor_binary","C_xor_ternary") and result["lemmas"]>0
        target=result["path"] if use_clauses else src
        left=CAP-(time.perf_counter()-t)
        if left>.08:
            called=True
            status,verified=backend(target,original,
                         "cms" if arm=="cms_plain" else "kissat",cpu,left,td)
    wall=time.perf_counter()-t
    if wall>=CAP:status="TIMEOUT";verified=False
    need(status!="SAT" or verified,"SAT model did not satisfy original")
    need(sha(src)==c["sha256"],"original source SHA changed")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],arm=arm,rep=rep,
       cap_s=CAP,one_cpu=cpu,original_SHA_verified=True,
       status=status,SAT_original_witness_verified=verified if status=="SAT" else False,
       UNSAT_GF2_proved_this_trial=False,UNSAT_independent_LRAT=False,
       GF2_contradiction_seen_no_shortcut=result["contradiction"],
       GF2_native_certificate_checked=result["verified"],
       backend_called=called,GF2_equations=result["eq"],GF2_rank=result["rank"],
       GF2_derived_rows=result["rows"],
       GF2_lemmas_added=result["lemmas"] if use_clauses else 0,
       GF2_lemmas_found=result["lemmas"],GF2_candidates=result["candidates"],
       GF2_gate=result["gate"],GF2_prepass_s=round(result["time"],6),
       wall_E2E_s=round(wall,6),
       child_CPU_s=round(e9.x22.child_cpu()-cc,6),
       parent_CPU_s=round(time.process_time()-pc,6))
def shard(idx):
    m=verify();need(idx in range(SHARDS),"bad shard")
    cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx];allrows=[]
    for c in cs:
        for rep in range(REPS):
            arms=list(ARMS);random.Random(c["sha256"]+str(rep)+"xorabc2").shuffle(arms)
            for arm in arms:
                row=trial(c,rep,arm);row["shard"]=idx
                need(row["wall_E2E_s"]<=CAP+.2,"budget exceeded")
                allrows.append(row);save(ROOT/("shard-%d.json"%idx),allrows)
                print("XORABC2_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(allrows)==len(cs)*REPS*len(ARMS),"shard incomplete")
    print("XORABC2_SHARD_PASS %d %d"%(idx,len(allrows)),flush=True)
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
          GF2_candidates=sum(r["GF2_candidates"] for r in rows),
          GF2_native_certificate_checked=sum(r["GF2_native_certificate_checked"] for r in rows),
          GF2_lemmas_found=sum(r["GF2_lemmas_found"] for r in rows),
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
      B_vs_PB=paired("B_xor_binary","PB_binary_placebo"),
      C_vs_A=paired("C_xor_ternary","A_kissat"),
      C_vs_B=paired("C_xor_ternary","B_xor_binary"),
      C_vs_PC=paired("C_xor_ternary","PC_ternary_placebo"),
      C_vs_CMS=paired("C_xor_ternary","cms_plain"))
    report=dict(protocol=PROTO,sources=N,trials=EXPECTED,
       original_sources_previously_seen_not_blind=True,one_CPU=True,
       static_CNF_bridge_not_live_CDCL=True,no_independent_backend_LRAT=True,
       no_GF2_UNSAT_shortcut=True,native_C_plus_plus_verifier=True,
       independently_verified_Gf2_implied_lemmas=True,
       algebraic_UNSAT_SHA=sorted(math),backend_UNSAT_original_agreement=sorted(consensus),
       scores=scores,comparisons=comp,
       per_shard={str(i):{a:score([r for r in allrows if r["shard"]==i
                        and r["arm"]==a]) for a in ARMS} for i in range(SHARDS)})
    save(ROOT/"report.json",report)
    print("XORABC2_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["selftest","freeze","verify","shard","audit"])
    p.add_argument("--shard",type=int,default=-1)
    args=p.parse_args()
    if args.command=="selftest":selftest()
    elif args.command=="freeze":freeze()
    elif args.command=="verify":verify();print("XORABC2_VERIFY_PASS",flush=True)
    elif args.command=="shard":shard(args.shard)
    else:audit()
