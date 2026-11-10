#!/usr/bin/env python3
"""Independent source-only QA of DRNAS's OWN R1 and R2 CDCL C++ code.
No existing SAT solver binaries/libraries are used or invoked.
Original SAT witnesses are checked against ORIGINAL SHA CNF, UNSAT on
larger CNF remains raw until independent LRAT/DRAT is implemented.
"""
import argparse,collections,hashlib,json,os,pathlib,random,re,subprocess,tempfile,time
ROOT=pathlib.Path("mre_drnas_native_core_r2")
R1=ROOT/"bin/drnas_native_core_r1"
R2=ROOT/"bin/drnas_native_core_r2"
def require(ok,msg):
    if not ok:raise RuntimeError("DRNAS_NATIVE_R2_QA_FAIL_CLOSED "+str(msg))
def source_sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def dump(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def content(n,clauses):
    return ("c DRNAS R2 independent source-CNF test\n"+
            f"p cnf {n} {len(clauses)}\n"+
            "".join(" ".join(map(str,row))+(" " if row else "")+"0\n" for row in clauses))
def parse_dimacs(path):
    n=k=None;clauses=[];buffer=[]
    for line in pathlib.Path(path).read_text().splitlines():
        line=line.strip()
        if not line or line.startswith("c"):continue
        if line.startswith("p "):
            tokens=line.split()
            require(len(tokens)==4 and tokens[1]=="cnf","invalid original DIMACS header")
            n=int(tokens[2]);k=int(tokens[3]);continue
        for l in map(int,line.split()):
            if l==0:clauses.append(buffer);buffer=[]
            else:
                require(n is not None and 1<=abs(l)<=n,"original literal invalid")
                buffer.append(l)
    require(n is not None and not buffer and k==len(clauses),"original CNF invalid")
    return n,clauses
def satisfied(clauses,assignment):
    return all(any(assignment.get(abs(l))==(l>0) for l in row) for row in clauses)
def independent_truth(n,clauses):
    require(n<=12,"exhaustive ground truth restricted to <=12 variables")
    for mask in range(1<<n):
        ass={v:bool(mask&(1<<(v-1))) for v in range(1,n+1)}
        if satisfied(clauses,ass):return "SAT"
    return "UNSAT"
def xor_cnf(vars,rhs):
    rows=[];width=len(vars)
    for mask in range(1<<width):
        if(mask.bit_count()&1)==rhs:continue
        rows.append([-v if mask&(1<<i) else v for i,v in enumerate(vars)])
    return rows
def trial(path,arm,cap):
    require(arm in ("r1","r2_plain","r2_gf2"),"unknown mode")
    start=time.perf_counter()
    cpus=os.sched_getaffinity(0)
    require(bool(cpus),"missing logical CPU")
    cpu=min(cpus);os.sched_setaffinity(0,{cpu})
    cmd=([str(R1.resolve()),str(pathlib.Path(path).resolve()),"--time",str(cap)]
         if arm=="r1" else
         [str(R2.resolve()),str(pathlib.Path(path).resolve()),
          "--mode","plain" if arm=="r2_plain" else "gf2","--time",str(cap)])
    run=subprocess.run(cmd,text=True,capture_output=True,timeout=cap+2.0)
    elapsed=time.perf_counter()-start
    require(run.returncode in (0,10,20),
        "native C++ crash "+arm+" "+str(run.returncode)+": "+run.stderr[-700:])
    prefix="DRNAS_NATIVE_R1_RESULT" if arm=="r1" else "DRNAS_NATIVE_R2_RESULT"
    line=re.search(r"^c "+prefix+r" (.+)$",run.stdout,re.M)
    require(line is not None,"native telemetry missing "+arm+": "+run.stdout[-400:])
    metrics={}
    for token in line.group(1).split():
        if "=" in token:
            k,v=token.split("=",1);metrics[k]=v
    status=metrics["status"]
    require(run.returncode=={"SAT":10,"UNSAT":20,"UNKNOWN":0}[status],
            "native exit and status diverged")
    require(metrics.get("third_party_solver_calls")=="0",
            "foreign solver invoked")
    n,clauses=parse_dimacs(path)
    witness={}
    if status=="SAT":
        for l in run.stdout.splitlines():
            if l.startswith("v "):
                for lit in map(int,l[2:].split()):
                    if lit:
                        require(abs(lit) not in witness,"duplicate SAT witness variable")
                        witness[abs(lit)]=(lit>0)
        require(len(witness)==n and satisfied(clauses,witness),
                "SAT witness invalid on original SHA")
    require(elapsed<=cap+1.0,"time-cap violated")
    return dict(arm=arm,solver_s=float(metrics["solver_s"]),
        e2e_s=round(elapsed,6),native_E2E_s=float(metrics["e2e_s"]),
        status=status,verified_SAT=status=="SAT",
        raw_UNSAT_no_independent_LRAT=status=="UNSAT",
        decisions=int(metrics["decisions"]),conflicts=int(metrics["conflicts"]),
        learned=int(metrics["learned"]),restarts=int(metrics["restarts"]),
        xor_source_rows=int(metrics.get("xor_source_rows",0)),
        xor_derived_rows=int(metrics.get("xor_derived_rows",0)),
        xor_implications=int(metrics.get("xor_implications",0)),
        xor_derived_implications=int(metrics.get("xor_derived_implications",0)),
        xor_conflicts=int(metrics.get("xor_conflicts",0)),
        xor_reasons=int(metrics.get("xor_reasons",0)),
        xor_budget_off=int(metrics.get("xor_budget_off",0)),
        single_CPU=cpu,third_party_solver_calls=0)
def fuzz():
    ROOT.mkdir(exist_ok=True)
    for arm,binpath,expected in [
        ("r1",R1,"DRNAS_NATIVE_R1_SELFTEST_PASS"),
        ("r2",R2,"DRNAS_NATIVE_R2_SELFTEST_PASS")]:
        p=subprocess.run([str(binpath.resolve()),"--selftest"],
                     text=True,capture_output=True,timeout=60)
        require(p.returncode==0 and expected in p.stdout,
                arm+" selftest failed "+p.stderr[-900:])
        print(p.stdout.strip(),flush=True)
    rng=random.Random(0xD2A52026)
    summaries=collections.Counter();verified_conflicts=0;gf2_activated=0
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        filename=pathlib.Path(td)/"original.cnf"
        for i in range(420):
            n=rng.randint(1,10);k=rng.randrange(0,5*n+12)
            clauses=[]
            for j in range(k):
                width=rng.randrange(0,min(8,n+4))
                clauses.append([rng.choice((-1,1))*rng.randint(1,n)
                              for _ in range(width)])
            filename.write_text(content(n,clauses))
            truth=independent_truth(n,clauses)
            for arm in ("r1","r2_plain","r2_gf2"):
                result=trial(filename,arm,1.5)
                require(result["status"]==truth,
                     "independent exhaustive disagreement case "+str(i)+
                     " mode "+arm+" expected "+truth+" got "+result["status"])
                summaries[arm+"_"+truth]+=1
                verified_conflicts+=result["conflicts"]>0
        # Deliberate source-proved GF(2) cancellation, with shuffled variables,
        # random equation parities and assigned literal. Root conflict variants
        # are checked against the original CNF *by independent enumeration*.
        for i in range(120):
            variables=list(range(1,5));rng.shuffle(variables)
            a,b,c,d=variables
            r1,r2=rng.randrange(2),rng.randrange(2)
            assigned=rng.randrange(2)
            clauses=xor_cnf((a,b,c),r1)+xor_cnf((a,b,d),r2)
            clauses.append([c if assigned else -c])
            if i%2==1:
                implied=r1^r2^assigned
                clauses.append([-d if implied else d]) # contradiction with derived
            filename.write_text(content(4,clauses))
            truth=independent_truth(4,clauses)
            for arm in ("r1","r2_plain","r2_gf2"):
                result=trial(filename,arm,1.5)
                require(result["status"]==truth,
                        "derived XOR proof mismatch "+str(i)+" "+arm)
                summaries[arm+"_"+truth]+=1
                if arm=="r2_gf2":
                    require(result["xor_source_rows"]>=2 and
                            result["xor_derived_rows"]>=1,
                            "missing source-derived GF2 closure")
                    require(result["xor_derived_implications"]+
                            result["xor_conflicts"]>0,
                            "mathematically novel GF2 never entered native CDCL")
                    gf2_activated+=1
        require(gf2_activated==120,"GF2 native derived novelty insufficient")
    report=dict(total_original_small_CNF=540,
        independent_truth_table_CNF=540,
        matched_solver_modes=3,verified_trials=1620,
        summaries=dict(summaries),
        cases_with_CDCL_conflicts=verified_conflicts,
        synthetic_mathematically_derived_GF2_activation=gf2_activated,
        external_solver_calls=0)
    dump(ROOT/"fuzz-report.json",report)
    print("DRNAS_NATIVE_R2_FUZZ_PASS "+json.dumps(report,sort_keys=True),flush=True)
def original():
    ROOT.mkdir(exist_ok=True)
    m=json.loads(pathlib.Path("mre_mixab4/manifest.json").read_text())
    cases=m["original_cases"]
    require(len(cases)==6,"MIXAB4 frozen original source roster not six")
    seen={};records=[]
    for c in sorted(cases,key=lambda x:x["sha256"]):
        src=pathlib.Path("mre_mixab4/cases")/c["filename"]
        require(src.is_file() and source_sha(src)==c["sha256"],
                "frozen original SHA mismatch")
        for rep in range(2):
            arms=["r1","r2_plain","r2_gf2"]
            random.Random(c["sha256"]+str(rep)+"NATIVE_R2").shuffle(arms)
            for arm in arms:
                row=trial(src,arm,3.0)
                row.update(source_sha=c["sha256"],rep=rep,cap_s=3.,
                           source_frozen_reference_easy=True)
                records.append(row)
                dump(ROOT/"original-trials.json",records)
                print("DRNAS_NATIVE_R2_ORIGINAL_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    require(len(records)==36,"36 original matched attempts expected")
    outputs={}
    for arm in ("r1","r2_plain","r2_gf2"):
        rows=[z for z in records if z["arm"]==arm]
        require(len(rows)==12,"missing arm")
        outputs[arm]=dict(attempts=12,SAT_original_verified=sum(z["verified_SAT"] for z in rows),
                          raw_UNSAT_without_LRAT=sum(z["raw_UNSAT_no_independent_LRAT"] for z in rows),
                          timeout=sum(z["status"]=="UNKNOWN" for z in rows),
                          strict_PAR2_s=round(sum(z["e2e_s"] if z["verified_SAT"]
                              else 6 for z in rows),4),
                          full_E2E_s=round(sum(z["e2e_s"] for z in rows),4),
                          xor_derived_implications=sum(z["xor_derived_implications"] for z in rows),
                          xor_reason_clauses=sum(z["xor_reasons"] for z in rows))
    report=dict(protocol="DRNAS-NATIVE-R2-SAME-ORIGINAL-6SHA-3ARMS-2REPS",
                paired_original_sha=6,attempts=36,
                same_single_CPU=True,source_frozen_not_blind=True,
                UNSAT_independent_LRAT=False,arms=outputs)
    dump(ROOT/"original-audit.json",report)
    print("DRNAS_NATIVE_R2_ORIGINAL_PASS "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("cmd",choices=("fuzz","original"))
    a=parser.parse_args()
    if a.cmd=="fuzz":fuzz()
    else:original()
