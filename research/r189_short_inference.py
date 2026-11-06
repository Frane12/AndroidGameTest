#!/usr/bin/env python3
"""R189 source-certified useful-information ablation on frozen original SAT CNFs.

This DOES NOT send continuous IPASIR-UP propagator callbacks. Compare the existing
R188 source-only Selective Gate with one-time, proof-traced short XOR consequences
and XOR-to-CNF local resolvents, plus a matched preprocessing-only shadow.

25 original GBD formulas already seen in R154/R155/R187/R188, 13 R179 generated
reference-calibrated controls; exact unchanged R187 SHA manifest. This is
development evidence, NOT unseen/blind or general SAT competitiveness.
CaDiCaL SAT models independently checked on ORIGINAL CNF. Source GF2 traces are
verified, and every bridge clause has replayed parity+CNF resolution parents.
CaDiCaL UNSAT without an XOR source contradiction is not LRAT verified.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, pathlib, random, statistics, time
import r188_feedback_benchmark as old

ROOT=pathlib.Path("r189")
FROZEN=ROOT/"frozen"
SOURCE_SHA="3f0f67bea5547daa1ba07d9a1dba31d8d33f7d734db8eb6e8cae358a46c91ef3"
SOURCE_PROTO="DRNAS-R187-REAL25-SELECTIVE-LIVE-GF2-20261106-v1"
PROTO="DRNAS-R189-SOURCE-TRACED-XOR-CNF-ONE-SHOT-v1"
CAP=15.0
SHARDS=8
REPS=2
MODES=("clean","selective_gate","short4","bridge4","hybrid4","hybrid_shadow")
MAX_PAIR_INPUT_ROWS=100
MAX_PAIR_EXAM=4500
MAX_SHORT_EQ=24
MAX_ADDED=96
MAX_BRIDGE_CANDIDATES=4000
MAX_RESIDUAL_SCAN=12000

def need(ok,msg):
    if not ok:raise RuntimeError("R189_FAIL_CLOSED "+str(msg))
def sha(p):return old.sha(p)
def get(p):return old.read(p)
def save(p,obj):old.save(p,obj)

def verify():
    need(sha(FROZEN/"manifest.json")==SOURCE_SHA,
         "R187 original frozen suite SHA drift")
    m=get(FROZEN/"manifest.json")
    need(m["protocol"]==SOURCE_PROTO and len(m["cases"])==38 and
         m["originals"]==25 and m["synthetic_controls"]==13,
         "R187 original identity/count mismatch")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"original formula SHA drift")
    return m["cases"]

def norm(c):
    return tuple(sorted(c,key=lambda v:(abs(v),v<0)))

def masks_to_clauses(vs,rhs):
    """CNF clauses precisely exclude the violating assignments of XOR."""
    k=len(vs)
    need(2<=k<=4 and rhs in (0,1),"unsupported generated parity")
    for bits in range(1<<k):
        if bits.bit_count()%2==rhs:continue
        clause=norm(tuple(-v if bits>>i&1 else v for i,v in enumerate(vs)))
        # Check the positive XOR source row logically entails this nogood:
        for assignment in range(1<<k):
            if assignment.bit_count()%2!=rhs:continue
            need(any(((assignment>>i&1)!=int(lit<0))
                     for i,lit in enumerate(clause)), "XOR-derived clause false under parity")
        yield clause

def shortlist(clauses,rows,covered):
    """Deterministic bounded 2-row XOR elimination with original source traces."""
    residual=[(i,c) for i,c in enumerate(clauses)
              if i not in covered and len(c)<=4]
    boundary=collections.Counter(abs(x) for _,c in residual for x in c)
    bases=sorted(range(len(rows)),key=lambda i:(
        -sum(boundary[v] for v in rows[i][0]),
        len(rows[i][0]),rows[i][0],rows[i][1]))[:MAX_PAIR_INPUT_ROWS]
    derived={}
    exam=0
    for ii,i in enumerate(bases):
        ai,pi,_=rows[i];aset=set(ai)
        for j in bases[ii+1:]:
            exam+=1
            if exam>MAX_PAIR_EXAM:break
            bj,pj,_=rows[j]
            if not (aset&set(bj)):continue
            vs=tuple(sorted(aset.symmetric_difference(bj)))
            if not 2<=len(vs)<=4:continue
            if not any(boundary[v] for v in vs):continue
            rhs=pi^pj
            trace=(1<<i)^(1<<j)
            old.gf.check_trace(rows,sum(1<<(v-1) for v in vs),rhs,trace)
            key=(vs,rhs)
            score=(sum(boundary[v] for v in vs),-len(vs))
            if key not in derived or score>derived[key][0]:
                derived[key]=(score,(i,j))
        if exam>MAX_PAIR_EXAM:break
    order=sorted(derived.items(),key=lambda item:(
        -item[1][0][0],len(item[0][0]),item[0][0],item[0][1]))
    selected=[(vs,rhs,indices) for (vs,rhs),(score,indices) in order[:MAX_SHORT_EQ]]
    return selected,residual,boundary,exam

def prepare(clauses,rows,covered,mode):
    """Return extra original-CNF-entailed clauses and replayable derivations.
    This is a local, capped one-shot preprocessor, NEVER a live CDCL callback.
    """
    need(mode in ("short4","bridge4","hybrid4","hybrid_shadow"),"bad derive mode")
    start=time.perf_counter()
    existing={norm(c) for c in clauses}
    chosen=[]
    derived_rows,residual,boundary,pairs=shortlist(clauses,rows,covered)
    stats={"xor_pair_examined":pairs,"short_equations":len(derived_rows),
           "bridge_candidates":0,"bridge_resolutions":0,
           "short_clauses":0,"new_clauses":0,"preprocessing_s":0.0}
    proof=[]
    def admit(clause,why):
        if len(chosen)>=MAX_ADDED or clause in existing:return False
        if not clause or len(clause)>4:return False
        if len(set(map(abs,clause)))!=len(clause):return False
        existing.add(clause)
        chosen.append(clause)
        proof.append(why)
        return True

    if mode in ("short4","hybrid4","hybrid_shadow"):
        for vs,rhs,indices in derived_rows:
            traced=(1<<indices[0])^(1<<indices[1])
            old.gf.check_trace(rows,sum(1<<(v-1) for v in vs),rhs,traced)
            # Avoid adding partially encoded XOR if the budget is exhausted:
            complete=list(masks_to_clauses(vs,rhs))
            missing=[c for c in complete if c not in existing]
            if len(chosen)+len(missing)>MAX_ADDED:continue
            for clause in missing:
                if admit(clause,{"kind":"xor2_source_trace","source_row_indices":indices,
                                 "vars":vs,"rhs":rhs,"clause":clause}):
                    stats["short_clauses"]+=1

    if mode in ("bridge4","hybrid4","hybrid_shadow"):
        # Only actual ORIGINAL residual CNF clauses are resolution parents.
        residual_by_lit=collections.defaultdict(list)
        for i,c in residual[:MAX_RESIDUAL_SCAN]:
            for lit in c:residual_by_lit[lit].append((i,c))
        # Source-certified equations (including bounded two-row XOR consequences).
        eqs=[(vs,rhs,(i,)) for i,(vs,rhs,_) in enumerate(rows) if 2<=len(vs)<=4]
        eqs.extend(derived_rows)
        eqs=sorted(eqs,key=lambda e:(
            -sum(boundary[v] for v in e[0]),len(e[0]),e[0],e[1]))[:100]
        for vs,rhs,parents in eqs:
            if len(chosen)>=MAX_ADDED:break
            trace=0
            for idx in parents:trace^=1<<idx
            old.gf.check_trace(rows,sum(1<<(v-1) for v in vs),rhs,trace)
            for source_parent in masks_to_clauses(vs,rhs):
                if len(chosen)>=MAX_ADDED:break
                for pivot_lit in source_parent:
                    if len(chosen)>=MAX_ADDED:break
                    for residual_idx,residual_clause in residual_by_lit.get(-pivot_lit,())[:50]:
                        stats["bridge_candidates"]+=1
                        if stats["bridge_candidates"]>MAX_BRIDGE_CANDIDATES:break
                        resolvent=norm(tuple(l for l in source_parent if l!=pivot_lit)+
                            tuple(l for l in residual_clause if l!=-pivot_lit))
                        if len(resolvent)>4 or not resolvent:continue
                        if any(-x in resolvent for x in resolvent):continue
                        if admit(resolvent,{
                            "kind":"parity_source_plus_original_cnf_resolution",
                            "source_rows":parents,
                            "parity_rhs":rhs,"parity_vars":vs,
                            "source_parity_parent":source_parent,
                            "residual_parent_index":residual_idx,
                            "pivot_lit":pivot_lit,
                            "clause":resolvent}):
                            stats["bridge_resolutions"]+=1
                    if stats["bridge_candidates"]>MAX_BRIDGE_CANDIDATES:break
                if stats["bridge_candidates"]>MAX_BRIDGE_CANDIDATES:break
            if stats["bridge_candidates"]>MAX_BRIDGE_CANDIDATES:break
    # Independent source-local proof replay, for every admitted implication:
    for note in proof:
        clause=tuple(note["clause"])
        if note["kind"]=="xor2_source_trace":
            vs=tuple(note["vars"]);rhs=note["rhs"]
            parents=note["source_row_indices"]
            check=(1<<parents[0])^(1<<parents[1])
            old.gf.check_trace(rows,sum(1<<(v-1) for v in vs),rhs,check)
            need(clause in set(masks_to_clauses(vs,rhs)),
                 "short derived clause not from traced XOR")
        else:
            parents=note["source_rows"];trace=0
            for idx in parents:trace^=1<<idx
            vs=tuple(note["parity_vars"]);rhs=note["parity_rhs"]
            old.gf.check_trace(rows,sum(1<<(v-1) for v in vs),rhs,trace)
            parity_parent=tuple(note["source_parity_parent"])
            residual_parent=tuple(clauses[note["residual_parent_index"]])
            need(parity_parent in set(masks_to_clauses(vs,rhs)),
                 "bridge parity parent not entailed by certified source equations")
            lit=note["pivot_lit"]
            need(lit in parity_parent and -lit in residual_parent,
                 "bridge resolution pivot mismatched")
            expected=norm(tuple(x for x in parity_parent if x!=lit)+
                          tuple(x for x in residual_parent if x!=-lit))
            need(expected==clause,"bridge resolution logical replay mismatch")
    stats["new_clauses"]=len(chosen)
    stats["preprocessing_s"]=round(time.perf_counter()-start,6)
    return chosen,stats,proof

def write_augmented(target,n,clauses,units,extra):
    """Original CNF remains complete; add only verified consequences."""
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w") as f:
        f.write(f"p cnf {n} {len(clauses)+len(units)+len(extra)}\n")
        for cl in clauses:f.write(" ".join(map(str,cl))+" 0\n")
        for u in units:f.write(f"{u} 0\n")
        for cl in extra:f.write(" ".join(map(str,cl))+" 0\n")

def trial(c,mode,rep,binary):
    source=FROZEN/(c["id"]+".cnf")
    need(sha(source)==c["sha256"],"source SHA mismatched in trial")
    start=time.perf_counter()
    status="TIMEOUT";model={}
    proof_type="NO_INDEPENDENT_UNSAT_LRAT"
    prep={"xor_pair_examined":0,"short_equations":0,"bridge_candidates":0,
          "bridge_resolutions":0,"short_clauses":0,"new_clauses":0,"preprocessing_s":0.0}
    enabled=False;reason="clean";xor_rows=0;units=0;injected=0
    n=None;original=None
    stats={"conflicts":-1,"decisions":-1,"propagations":-1,"learned":-1}
    input_path=source
    if mode!="clean":
        enabled,reason,screen=old.route(source)
        if enabled:
            n,original=old.gf.dimacs(source)
            rows,covered=old.ext.xor_source(original)
            xor_rows=len(rows)
            gauss=old.gf.gaussian(rows)
            if gauss["conflict"]:
                old.gf.check_trace(rows,0,1,gauss["conflict_trace"])
                status="UNSAT";proof_type="SOURCE_GF2_CONTRADICTION_REPLAYED"
            else:
                unitlist=[]
                for var,(rhs,trace) in sorted(gauss["units"].items()):
                    old.gf.check_trace(rows,1<<(var-1),rhs,trace)
                    unitlist.append(var if rhs else -var)
                units=len(unitlist)
                extra=[]
                if mode in ("short4","bridge4","hybrid4","hybrid_shadow") and rows:
                    extra,prep,metadata=prepare(original,rows,covered,mode)
                    if rep==0:
                        save(ROOT/"proofs"/(c["id"]+"-"+mode+".json"),{
                            "source_sha256":c["sha256"],"preprocessor":mode,
                            "source_rows":len(rows),"certified_clauses":metadata})
                    if mode=="hybrid_shadow":extra=[]
                injected=len(extra)
                if unitlist or extra:
                    input_path=ROOT/"scratch"/mode/(c["id"]+"-"+str(rep)+".cnf")
                    write_augmented(input_path,n,original,unitlist,extra)
    if status!="UNSAT":
        left=CAP-(time.perf_counter()-start)
        if left>0.12:
            status,_,model,stats,_=old.native(binary,[input_path,left],left,False)
    elapsed=time.perf_counter()-start
    if elapsed>=CAP:status="TIMEOUT";proof_type="CAP"
    if status=="SAT":
        if original is None:_,original=old.gf.dimacs(source)
        old.gf.sat_check(original,model)
        proof_type="SAT_WITNESS_ORIGINAL_CNF_VERIFIED"
    if c["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==c["expected"],"expected source truth mismatch")
    return {"id":c["id"],"sha256":c["sha256"],"suite":c["suite"],
        "family":c["family"],"mode":mode,"rep":rep,"status":status,
        "elapsed_s":round(elapsed,6),
        "par2_s":round(2*CAP if status=="TIMEOUT" else elapsed,6),
        "proof":proof_type,"selected":enabled,"route":reason,
        "xor_rows":xor_rows,"units":units,"injected_clauses":injected,
        **prep,**stats}

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and binary.is_file(),"bad shard/binary")
    trials=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                x=trial(c,mode,rep,binary)
                trials.append(x)
                save(ROOT/f"shard-{index}.json",trials)
                print("R189_TRIAL",json.dumps({k:x[k] for k in (
                    "id","suite","mode","rep","status","elapsed_s",
                    "injected_clauses","short_clauses","bridge_resolutions",
                    "preprocessing_s","conflicts")},sort_keys=True),flush=True)
    need(len(trials)==len(cases[index::SHARDS])*REPS*len(MODES),
         "partial same-source shard")
    print("R189_SHARD_PASS",index,len(trials),flush=True)

def audit():
    cases=verify();rows=[]
    for idx in range(SHARDS):
        part=get(ROOT/f"shard-{idx}.json")
        need(len(part)==len(cases[idx::SHARDS])*REPS*len(MODES),"partial audit shard")
        rows.extend(part)
    need(len(rows)==38*REPS*len(MODES)==456,"expected exactly 456 trials")
    by=collections.defaultdict(list)
    frozen={c["sha256"]:c for c in cases}
    for r in rows:
        need(r["sha256"] in frozen and r["id"]==frozen[r["sha256"]]["id"],
             "source SHA mismatch")
        need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"]))<1e-5,
             "PAR2 drift")
        by[(r["sha256"],r["mode"])].append(r)
    for c in cases:
        for mode in MODES:
            rec=by[c["sha256"],mode]
            need(len(rec)==2 and {x["rep"] for x in rec}=={0,1},"missing repeat")
        for rep in range(REPS):
            solved={r["status"] for m in MODES for r in by[c["sha256"],m]
                    if r["rep"]==rep and r["status"]!="TIMEOUT"}
            need(len(solved)<=1,"SAT/UNSAT contradictory results")
    cohorts={"all":cases,
      "external_original_25":[c for c in cases if c["real"]],
      "synthetic_control_13":[c for c in cases if not c["real"]]}
    for fam in sorted(set(c["family"] for c in cases if c["real"])):
        cohorts["external:"+fam]=[c for c in cases if c["real"] and c["family"]==fam]
    result={}
    for name,subset in cohorts.items():
        s={}
        for mode in MODES:
            rr=[r for c in subset for r in by[c["sha256"],mode]]
            s[mode]={"attempts":len(rr),
               "solved":sum(r["status"]!="TIMEOUT" for r in rr),
               "SAT":sum(r["status"]=="SAT" for r in rr),
               "UNSAT":sum(r["status"]=="UNSAT" for r in rr),
               "par2_s":round(sum(r["par2_s"] for r in rr),6),
               "injected_clauses":sum(r["injected_clauses"] for r in rr),
               "short_clauses":sum(r["short_clauses"] for r in rr),
               "bridge_resolutions":sum(r["bridge_resolutions"] for r in rr),
               "preprocessing_s":round(sum(r["preprocessing_s"] for r in rr),6),
               "selected":sum(r["selected"] for r in rr),
               "source_GF2_proofs":sum(r["proof"]=="SOURCE_GF2_CONTRADICTION_REPLAYED" for r in rr),
               "CDCL_conflicts_known":sum(max(0,r["conflicts"]) for r in rr)}
        clean=s["clean"]["par2_s"]
        result[name]={"formulas":len(subset),"modes":s,
           "clean_over_mode_x":{m:round(clean/s[m]["par2_s"],6)
                                 for m in MODES if m!="clean"}}
    report={"protocol":PROTO,"status":"R189_PAIRED_AUDIT_PASS",
       "source_manifest_sha256":SOURCE_SHA,"formulas":38,"attempts":len(rows),
       "repetitions":2,"cap_s":CAP,"external_reused_not_blind":True,
       "not_general_world_competition_claim":True,
       "SAT_models_checked_against_original":True,
       "GF2_source_and_resolution_proofs_replayed":True,
       "CaDiCaL_UNSAT_without_source_GF2_not_LRAT_verified":True,
       "groups":result,
       "proof_counts":dict(collections.Counter(r["proof"] for r in rows))}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R189 — short source-certified XOR → CNF communication\n\n")
        f.write("25 GBD original CNFs previously seen in R154/R155/R187/R188, "
                "13 known synthetic controls. Same source SHA and exact CaDiCaL reference "
                "binary as R187. Not blind. 15s wall limit including source screening/"
                "parity extraction/derivation/file write, 2 paired repetitions.\n\n")
        f.write("| Cohort | Mode | Solved attempts | PAR-2 s | Clean / mode | New clauses | Preprocess s |\n"
                "|---|---|---:|---:|---:|---:|---:|\n")
        for group in ("external_original_25","synthetic_control_13","all"):
            for mode,s in result[group]["modes"].items():
                f.write(f"| {group} | {mode} | {s['solved']}/{s['attempts']} | "
                        f"{s['par2_s']} | {result[group]['clean_over_mode_x'].get(mode,'—')} | "
                        f"{s['injected_clauses']} | {s['preprocessing_s']} |\n")
        f.write("\n**Interpretation:** compare hybrid4 vs hybrid_shadow for the "
                "causal information value, and hybrid_shadow vs selective_gate "
                "for preprocessing overhead. No automatic promotion.\n")
    print("R189_FINAL",json.dumps({"groups":{k:result[k] for k in
            ("external_original_25","synthetic_control_13","all")},
            "proof_counts":report["proof_counts"]},sort_keys=True),flush=True)

def selftest():
    # XOR3 source-equations sharing two variables yield XOR2 (1,4);
    # residual (1 or 5) enables one-hop short resolution.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        source=[]
        for vs in ((1,2,3),(2,3,4)):
            source.extend(masks_to_clauses(vs,0))
        source.append((1,5))
        n=5;source=[tuple(c) for c in source]
        p=pathlib.Path(td)/"test.cnf"
        p.write_text(f"p cnf {n} {len(source)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in source))
        nc,clauses=old.gf.dimacs(p)
        rows,covered=old.ext.xor_source(clauses)
        need(len(rows)==2,"source XOR3 extraction failed")
        combo,res,b,exam=shortlist(clauses,rows,covered)
        need(any(vs==(1,4) and rhs==0 for vs,rhs,_ in combo),
             "XOR-XOR shared-variable shortening failed")
        for mode in ("short4","bridge4","hybrid4","hybrid_shadow"):
            extra,stats,proof=prepare(clauses,rows,covered,mode)
            need(extra and len(extra)==stats["new_clauses"] and
                 len(proof)==len(extra),"source certified consequences missing")
            if mode=="bridge4":need(stats["bridge_resolutions"]>0,
                "XOR-to-original-CNF resolution missing")
            for bits in range(1<<n):
                def satisfies(c):return any(
                    bool(bits>>(abs(l)-1)&1)==(l>0) for l in c)
                if all(satisfies(c) for c in clauses):
                    need(all(satisfies(c) for c in extra),
                         "generated clause not entailed by original CNF")
    print("R189_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r189/r189-driver")
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="verify":print("R189_VERIFY_PASS",len(verify()),flush=True)
    elif args.action=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()
