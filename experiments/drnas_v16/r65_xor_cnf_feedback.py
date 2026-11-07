#!/usr/bin/env python3
"""DRNAS R65: bounded, sound bidirectional XOR<->CNF propagation experiment.

Reuse R64's SHA-locked, structurally stratified SATCompetition2026 originals.
R65 detects *complete* XOR clause encodings only, combines them with ordinary
CNF Boolean constraint propagation (BCP), performs bounded conditional probes,
and adds only clauses logically entailed by the ORIGINAL CNF.
No structural guess from incomplete XOR sign patterns is allowed.
This is a replay on previously seen inputs, not a blind holdout or official score.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, random, subprocess, tempfile, time
from pathlib import Path
import r28_exact_gf2_benchmark as r28
import r32p_real_satcomp26_benchmark as r32p
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64

PROTO="DRNAS-R65-XOR-CNF-BIDIRECTIONAL-20261103-v1"
SHARDS=8
REPS=2
CAP=40.0
MODES=("clean_kissat","r28_exact_gf2_fallback","r65_xor_cnf_feedback")
MAX_PREP_S=2.0
MAX_PROBES=12
MAX_DERIVED=64
MAX_WORK=750000

def ck(v,msg):
    if not v:raise RuntimeError("R65_FAIL_CLOSED "+str(msg))
def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class ProbeBudget(Exception):pass

def build_network(n,cnf,equations):
    occurrences=collections.defaultdict(list)
    xrefs=collections.defaultdict(list)
    # Index occurrences by literal that is falsified by a variable assignment.
    nonxor=collections.Counter()
    recognized_supports={vs for vs,_ in equations}
    for i,clause in enumerate(cnf):
        if not clause:return None
        for lit in set(clause):
            occurrences[lit].append(i)
        support=tuple(sorted({abs(x) for x in clause}))
        if support not in recognized_supports:
            nonxor.update(set(abs(x) for x in clause))
    for i,(vs,_) in enumerate(equations):
        for v in vs:xrefs[v].append(i)
    return occurrences,xrefs,nonxor

def propagate(cnf,equations,occ,xrefs,base=None,assumption=None,deadline=None):
    """BCP<->XOR fixed point. Every assignment is entailed by base+assumption.

    No SAT/UNSAT answer is emitted here; the augmented input is still solved
    by clean Kissat, and any SAT witness is checked against original DIMACS.
    """
    assigned=dict(base or {})
    pending=collections.deque()
    if base is None:
        for clause in cnf:
            if not clause:return True,assigned
            if len(clause)==1:
                lit=clause[0];v=abs(lit);val=lit>0
                old=assigned.get(v)
                if old is not None and old!=val:return True,assigned
                if old is None:
                    assigned[v]=val;pending.append(v)
    if assumption is not None:
        v=abs(assumption);val=assumption>0
        old=assigned.get(v)
        if old is not None and old!=val:return True,assigned
        if old is None:
            assigned[v]=val;pending.append(v)
    work=0
    while pending:
        v=pending.popleft()
        negative=-v if assigned[v] else v
        for idx in occ.get(negative,()):
            work+=1
            if work&4095==0 and (work>MAX_WORK or
                (deadline is not None and time.monotonic()>deadline)):
                raise ProbeBudget("bounded CNF propagation")
            free=0;candidate=0;satisfied=False
            for lit in cnf[idx]:
                x=assigned.get(abs(lit))
                if x is None:
                    free+=1;candidate=lit
                elif x==(lit>0):
                    satisfied=True;break
            if satisfied:continue
            if free==0:return True,assigned
            if free==1:
                w=abs(candidate);value=candidate>0
                prior=assigned.get(w)
                if prior is not None:
                    if prior!=value:return True,assigned
                else:
                    assigned[w]=value;pending.append(w)
        for idx in xrefs.get(v,()):
            work+=1
            if work&4095==0 and (work>MAX_WORK or
                (deadline is not None and time.monotonic()>deadline)):
                raise ProbeBudget("bounded XOR propagation")
            vs,rhs=equations[idx]
            remainder=rhs;missing=0;free=0
            for w in vs:
                x=assigned.get(w)
                if x is None:
                    missing=w;free+=1
                else:remainder^=int(x)
            if free==0:
                if remainder:return True,assigned
            elif free==1:
                prior=assigned.get(missing)
                val=bool(remainder)
                if prior is not None:
                    if prior!=val:return True,assigned
                else:
                    assigned[missing]=val;pending.append(missing)
    return False,assigned

def propose_clauses(n,cnf,equations,deadline):
    """Derive sound root units + binary implication clauses by assumption probes.

    If F & assumption -> literal, F -> (-assumption OR literal).
    If F & assumption -> conflict, F -> -assumption.
    """
    if not equations:return [],{"route":"no_complete_xor","probes":0}
    network=build_network(n,cnf,equations)
    if network is None:return [],{"route":"empty_original","probes":0}
    occurrences,xrefs,nonxor=network
    conflict,root=propagate(cnf,equations,occurrences,xrefs,deadline=deadline)
    if conflict:
        # No UNSAT output or empty clause is generated. Delegate to Kissat.
        return [],{"route":"root_conflict_fallback","probes":0}
    implied=set()
    for v,val in root.items():
        implied.add((v if val else -v,))
    # Probe the XOR variables most connected to non-XOR clauses first.
    candidates=[v for v in xrefs if v not in root]
    candidates.sort(key=lambda v:(-int(nonxor[v]>0),
       -(len(xrefs[v])*nonxor[v]),-len(xrefs[v]),v))
    probes=0;conflicts=0
    for v in candidates[:MAX_PROBES]:
        for assumption in (v,-v):
            if time.monotonic()>deadline:raise ProbeBudget("preprocessing deadline")
            conflict,model=propagate(cnf,equations,occurrences,xrefs,
                  base=root,assumption=assumption,deadline=deadline)
            probes+=1
            if conflict:
                conflicts+=1
                implied.add((-assumption,))
                continue
            for target,value in model.items():
                if target==v or target in root:continue
                literal=target if value else -target
                pair=tuple(sorted((-assumption,literal)))
                # Ignore tautological clauses, which impose no restriction.
                if -assumption!=-literal:
                    implied.add(pair)
    existing={tuple(sorted(c)) for c in cnf if len(c)<=2}
    fresh=sorted(implied-existing,key=lambda x:(len(x),x))
    return fresh[:MAX_DERIVED],{
       "route":"probe_derived" if fresh else "probe_no_new_clauses",
       "probes":probes,"conflicting_probes":conflicts,
       "root_units":len(root),"new_clauses":len(fresh)}

def derive_for_source(source,case,deadline):
    if not case["supported"] or case["complete_blocks"]==0:
        return [],{"route":"not_eligible_or_no_exact","probes":0}
    # R64 independent parity scanner rejects any incomplete pattern as proof.
    equations,_=r64.extract_equations(source,case["variables"],
                            case["clauses"],time.monotonic())
    ck(len(equations)==case["complete_blocks"],"R63 vs R65 exact XOR scan drift")
    n,cnf=r28.load_clauses(source)
    ck(n==case["variables"] and len(cnf)==case["clauses"],"source CNF count drift")
    return propose_clauses(n,cnf,equations,deadline)

def r65_one(source,case,kissat,gf2):
    start=time.monotonic()
    if case["pure_exact_xor"]:
        row=r63.one(source,case,kissat,gf2,"r28_exact_gf2_fallback")
        row.update(native_route="pure_control_"+row["native_route"],
            added_clauses=0,probes=0,preprocess_s=0.0)
        return row
    clauses=[];info={"route":"skip","probes":0}
    try:
        clauses,info=derive_for_source(source,case,start+MAX_PREP_S)
    except (ProbeBudget,TimeoutError):
        clauses=[]
        info={"route":"budget_fallback","probes":0}
    preprocess_s=time.monotonic()-start
    if preprocess_s>MAX_PREP_S:
        clauses=[];info={"route":"budget_fallback","probes":0}
    target=Path(source)
    answer="TIMEOUT";proof="none"
    with tempfile.TemporaryDirectory(prefix="drnas-r65-") as work:
        if clauses:
            target=Path(work)/"augmented.cnf"
            r64.augment(source,target,case["variables"],case["clauses"],clauses)
        left=CAP-(time.monotonic()-start)
        if left>0:
            try:
                p=subprocess.run([str(kissat),str(target)],stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE,text=True,errors="replace",
                      timeout=left,preexec_fn=r63.child)
                ck(p.returncode in (10,20),"Kissat invalid exit "+str(p.returncode))
                answer="SAT" if p.returncode==10 else "UNSAT"
                ck(answer==case["official_status"],"official status contradiction")
                if answer=="SAT":
                    r32p.verify_sat_witness(source,p.stdout)
                    proof="SAT_original_model_verified"
                else:proof="UNSAT_Kissat_official_status_only"
            except subprocess.TimeoutExpired:
                answer="TIMEOUT"
    elapsed=time.monotonic()-start
    if elapsed>CAP:
        answer="TIMEOUT"
        info["route"]="censored_after_verification"
    wall=min(CAP,elapsed)
    return dict(answer=answer,wall_s=round(wall,6),
       par2_s=round(wall if answer!="TIMEOUT" else CAP*2,6),
       native_route=info["route"],proof=proof,
       added_clauses=len(clauses),probes=info["probes"],
       preprocess_s=round(preprocess_s,6))

def selftest():
    import itertools
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/"selftest.cnf"
        def encode(vs,rhs):
            return [tuple(-v if (mask>>i)&1 else v for i,v in enumerate(vs))
                    for mask in range(1<<len(vs)) if mask.bit_count()%2!=rhs]
        def check_equivalence(clauses,add,n):
            for values in itertools.product((False,True),repeat=n):
                values=(False,)+values
                def sat(rows):
                    return all(any(values[abs(lit)]==(lit>0) for lit in row)
                               for row in rows)
                ck(sat(clauses)==sat(clauses+add),
                   "unsound added clause for assignment")
        def run(cs,n):
            path.write_text("p cnf "+str(n)+" "+str(len(cs))+"\n"+
                "".join(" ".join(map(str,row))+" 0\n" for row in cs))
            eq,_=r64.extract_equations(path,n,len(cs),time.monotonic())
            derived,info=propose_clauses(n,cs,eq,time.monotonic()+2)
            check_equivalence(cs,derived,n)
            return eq,derived,info
        # Chain CNF(1->4->2) & XOR(1,2,3)=0 proves conditional 1->!3.
        xor=encode((1,2,3),0)
        eq,derived,info=run(xor+[(-1,4),(-4,2)],4)
        ck(len(eq)==1 and derived and info["probes"]>0,
           "bidirectional test did not extract implications")
        # XOR with root-level CNF units gives guaranteed new top-level values.
        eq2,add2,info2=run(xor+[(1,),(-2,)],4)
        ck(len(eq2)==1 and (3,) in add2,
           "CNF->XOR root propagation missing")
        # Partial parity-looking clauses must not be mistaken for XOR.
        eq3,add3,info3=run(xor[:-1]+[(-1,4),(-4,2)],4)
        ck(not eq3 and not add3,"unsound partial XOR gate")
        # Negative controls: exact XOR plus unrelated CNF should remain sound.
        for p in range(4):
            extras=[(4 if p&1 else -4,),(2 if p&2 else -2,)]
            run(xor+extras,4)
    print("R65_FEEDBACK_SELFTEST_PASS",json.dumps(
        {"conditional_clauses":derived,"root_clauses":add2,
         "incomplete_xor_added":len(add3)}),flush=True)

def freeze(args):
    original=Path(args.sources)
    old=json.loads((Path(args.r64spec)/"manifest.json").read_text())
    ck(old["protocol"]==r64.PROTO and len(old["cases"])==18,
       "R64 prior frozen stratum protocol/count drift")
    ck(old["source_manifest_sha"]==digest(original/"manifest.json"),
       "R63 original manifest changed")
    for c in old["cases"]:
        ck(digest(original/c["filename"])==c["sha256"],
           "original CNF SHA changed")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    spec=dict(protocol=PROTO,old_spec_sha=digest(Path(args.r64spec)/"manifest.json"),
        original_manifest_sha=digest(original/"manifest.json"),
        cases=old["cases"],modes=list(MODES),shards=SHARDS,reps=REPS,
        cap_s=CAP,max_preprocess_s=MAX_PREP_S,max_probes=MAX_PROBES,
        max_derived=MAX_DERIVED,source_run_id=41707669490,
        caveats=["Not independent holdout: same 18 source inputs as R64",
          "Only verified complete XOR sign-mask groups become equations",
          "Root and conditional BCP/XOR deductions are entailed by original",
          "Truncation falls back to unchanged Kissat",
          "R65 never claims native UNSAT without pinned Kissat",
          "SAT witness always checked against original",
          "Wall cap includes preprocessing, Kissat and verification",
          "Frozen SHA source, pinned binaries and paired two-run validation"])
    (out/"manifest.json").write_text(json.dumps(spec,indent=2)+"\n")
    print("R65_FROZEN",json.dumps({"sources":len(spec["cases"]),
         "original_manifest_sha":spec["original_manifest_sha"],
         "r64_spec_sha":spec["old_spec_sha"]}),flush=True)

def measure(args):
    roots=Path(args.sources);specroot=Path(args.spec)
    spec=json.loads((specroot/"manifest.json").read_text())
    ck(spec["protocol"]==PROTO and spec["original_manifest_sha"]==
       digest(roots/"manifest.json"),"manifest drift")
    ck(0<=args.shard<SHARDS,"invalid shard")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    kissat=Path(args.kissat).resolve();gf2=Path(args.gf2).resolve()
    ck(kissat.is_file() and gf2.is_file(),"binary missing")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    meta=dict(shard=args.shard,protocol=PROTO,
        spec_sha=digest(specroot/"manifest.json"),
        original_manifest_sha=spec["original_manifest_sha"],
        kissat_sha=digest(kissat),gf2_sha=digest(gf2),
        n_cases=len(spec["cases"][args.shard::SHARDS]))
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for case in spec["cases"][args.shard::SHARDS]:
        source=(roots/case["filename"]).resolve()
        ck(digest(source)==case["sha256"],"source SHA mismatch")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(hashlib.sha256(
                f"r65/{case['sha256']}/{rep}".encode()).hexdigest(),16)).shuffle(modes)
            for mode in modes:
                row=r65_one(source,case,kissat,gf2) if mode=="r65_xor_cnf_feedback" \
                    else r63.one(source,case,kissat,gf2,mode)
                data=dict(gbd=case["gbd"],sha=case["sha256"],
                      group=case["group"],rep=rep,mode=mode,**row)
                rows.append(data)
                (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                print("R65_TRIAL",case["gbd"],case["group"],rep,mode,
                      row["answer"],row["wall_s"],"PAR2",row["par2_s"],
                      "added",row.get("added_clauses",0),
                      "route",row["native_route"],flush=True)
    print("R65_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    specroot=Path(args.spec)
    spec=json.loads((specroot/"manifest.json").read_text())
    ck(spec["protocol"]==PROTO,"R65 protocol mismatch")
    pins=set();allrows=[]
    for i in range(SHARDS):
        folder=Path(args.combined)/f"r65-shard-{i}"/"results"
        meta=json.loads((folder/"metadata.json").read_text())
        ck(meta["shard"]==i and meta["spec_sha"]==
            digest(specroot/"manifest.json"),"mixed source SHA")
        pins.add((meta["kissat_sha"],meta["gf2_sha"],
                  meta["original_manifest_sha"]))
        rows=json.loads((folder/"rows.json").read_text())
        ck(len(rows)==meta["n_cases"]*REPS*len(MODES),"incomplete shard")
        allrows+=rows
    ck(len(pins)==1 and len(allrows)==len(spec["cases"])*REPS*len(MODES),
        "binary drift or partial matched evidence")
    bygroup={}
    rows_per_case={}
    for c in spec["cases"]:
        rr=[r for r in allrows if r["gbd"]==c["gbd"]]
        ck(len(rr)==REPS*len(MODES) and all(r["sha"]==c["sha256"] for r in rr),
           "case SHA or replicate missing")
        for rep in range(REPS):
            ck({x["mode"] for x in rr if x["rep"]==rep}==set(MODES),
               "incomplete matched triplet")
        vals={mode:round(sum(x["par2_s"] for x in rr if x["mode"]==mode),6)
              for mode in MODES}
        rows_per_case[c["gbd"]]=dict(group=c["group"],par2=vals,
           max_added_clauses=max(x.get("added_clauses",0) for x in rr),
           routes=dict(collections.Counter(x["native_route"] for x in rr
                              if x["mode"]=="r65_xor_cnf_feedback")))
    for group in ("ALL",)+r64.GROUPS:
        subset=[x for x in allrows if group=="ALL" or x["group"]==group]
        bygroup[group]={}
        for mode in MODES:
            rr=[x for x in subset if x["mode"]==mode]
            bygroup[group][mode]=dict(trials=len(rr),solved=sum(
                x["answer"]!="TIMEOUT" for x in rr),
                timeouts=sum(x["answer"]=="TIMEOUT" for x in rr),
                par2_s=round(sum(x["par2_s"] for x in rr),6))
        clean=bygroup[group]["clean_kissat"]["par2_s"]
        new=bygroup[group]["r65_xor_cnf_feedback"]["par2_s"]
        bygroup[group]["gain_pct"]=round(100*(1-new/clean),4) if clean else None
    regressions=sum(v["par2"]["r65_xor_cnf_feedback"]-
        v["par2"]["clean_kissat"]>0.5 for v in rows_per_case.values())
    derived=sum(x.get("added_clauses",0) for x in allrows
                if x["mode"]=="r65_xor_cnf_feedback")
    result=dict(protocol=PROTO,status="PASS",sources=len(spec["cases"]),
         trials=len(allrows),summary=bygroup,per_case=rows_per_case,
         added_clauses_over_all_reps=derived,regressions_gt_0_5s=regressions,
         binaries=list(pins)[0],limitations=spec["caveats"])
    Path(args.json).write_text(json.dumps(result,indent=2)+"\n")
    lines=["# DRNAS R65 — Bidirectional CNF↔XOR feedback", "",
      "**Exploratory replay, NOT a previously unseen SAT2026 holdout.**",
      "Official originals from R63, structural strata from R64.",
      "2 repetitions; 40s per method including all preprocessing and original SAT check.",
      "PAR2=80s for timeout; lower is better.", "",
      "| Stratum | Kissat PAR2 | R28 PAR2 | R65 PAR2 | R65 gain |",
      "|---|---:|---:|---:|---:|"]
    for g,item in bygroup.items():
        vals=[item[z]["par2_s"] for z in MODES]
        lines.append(f"| {g} | {vals[0]:.3f} | {vals[1]:.3f} | "+
             f"{vals[2]:.3f} | {item['gain_pct']:+.3f}% |")
    lines+=["",f"Derived clauses across R65 runs: {derived}",
       f"Regressions >0.5s per formula (both reps): {regressions}",
       "","## Per original","| Formula ID | Group | Kissat | R28 | R65 | Added | Routes |",
       "|---|---|---:|---:|---:|---:|---|"]
    for name,data in rows_per_case.items():
        v=data["par2"]
        lines.append(f"| {name[:12]} | {data['group']} | "+
             f"{v[MODES[0]]:.3f} | {v[MODES[1]]:.3f} | {v[MODES[2]]:.3f} | "+
             f"{data['max_added_clauses']} | {','.join(data['routes'])} |")
    lines+=["","## Limitations"]+["- "+x for x in spec["caveats"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R65_FINAL_AUDIT_PASS",json.dumps({"sources":len(spec["cases"]),
        "trials":len(allrows),"derived":derived,
        "regressions":regressions,"summary":bygroup},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sp=p.add_subparsers(dest="cmd",required=True)
    sp.add_parser("selftest")
    f=sp.add_parser("freeze")
    for name in ("sources","r64spec","out"):f.add_argument("--"+name,required=True)
    m=sp.add_parser("measure")
    for name in ("sources","spec","kissat","gf2","out"):
        m.add_argument("--"+name,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sp.add_parser("audit")
    for name in ("spec","combined","json","md"):a.add_argument("--"+name,required=True)
    args=p.parse_args()
    if args.cmd=="selftest":selftest()
    elif args.cmd=="freeze":freeze(args)
    elif args.cmd=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":main()
