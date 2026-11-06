#!/usr/bin/env python3
"""R171 short/easy: 12 public SATLIB uf20-91 original CNFs plus 8 explicitly
SYNTHETIC planted XOR+residual controls (not industrial/competition claims).
4 solver arms x 3 repeats x 20 cases = 240 paired runs; 4s cap.
Pinned upstream Git commit; all source SHA frozen BEFORE timing.
All SAT witnesses independently checked. Synthetic UNSAT enforced by parity
chain with contradictory terminal unit; not independent LRAT on other UNSATs.
"""
import argparse,hashlib,json,os,pathlib,random,statistics,subprocess,sys,time,urllib.request
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r165_component_benchmark as base
ROOT=pathlib.Path("r171")
base.ROOT=ROOT
base.FROZEN=ROOT/"frozen"
MODES=("clean","direct_full","direct_two_way_newonly","direct_two_way_shadow")
REPS=3
SHARDS=4
CAP=4.
SOURCE_COMMIT="fc0e735aff48989326f256121b5ed6fc585858c3"
PROTO="DRNAS-R171-SHORT-EASY-240-20261106-v1"
def need(ok,msg):
    if not ok:raise RuntimeError("R171_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,d):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
def clauses_cnf(n,cls):
    return ("p cnf %d %d\n"%(n,len(cls))+"".join(" ".join(map(str,c))+" 0\n" for c in cls)).encode()
def parity(vs,rhs):
    import itertools
    return [tuple(-v if b else v for v,b in zip(vs,bits))
       for bits in itertools.product((0,1),repeat=len(vs)) if sum(bits)%2!=rhs]
def make_control(n,unsat):
    bits={i:int(((i*7+n)%5)<3) for i in range(1,n+1)}
    cls=[]
    for i in range(1,n-1):
        vs=(i,i+1,i+2)
        cls+=parity(vs,bits[i]^bits[i+1]^bits[i+2])
    for i in range(1,n-2):
        # Contains a planted-true literal; genuine non-parity residual CNF.
        a=i if bits[i] else -i
        cls.append((a,(-(i+2) if bits[i+2] else i+2), (i+1 if bits[i+1] else -(i+1))))
    cls.extend(((1 if bits[1] else -1,), (2 if bits[2] else -2,)))
    last=n if bits[n] else -n
    cls.append((-last if unsat else last,))
    return clauses_cnf(n,cls)
def generate():
    (ROOT/"frozen").mkdir(parents=True,exist_ok=True)
    cases=[]
    names=["uf20-0%d.cnf"%i for i in range(1,13)]
    for filename in names:
        u=("https://raw.githubusercontent.com/mitchellh/go-sat/"+SOURCE_COMMIT+
           "/testdata/satlib/sat-uniform-20-91/"+filename)
        req=urllib.request.Request(u,headers={"User-Agent":"DRNAS-R171-SATLIB-test/1.0"})
        with urllib.request.urlopen(req,timeout=35) as r: data=r.read(200000)
        need(0<len(data)<200000,"SATLIB download corrupt "+filename)
        # Canonicalize optional historical DIMACS '%' trailer, if present.
        rawsha=hashlib.sha256(data).hexdigest()
        lines=data.decode("ascii").splitlines()
        # SATLIB "%" marks EOF; its following standalone 0 is not a clause.
        cutoff=next((j for j,x in enumerate(lines) if x.lstrip().startswith("%")),len(lines))
        normalized=("\n".join(lines[:cutoff]).rstrip()+"\n").encode()
        ident="satlib-"+filename[:-4]
        p=ROOT/"frozen"/(ident+".cnf");p.write_bytes(normalized)
        variables,clauses=base.dimacs(p)
        need(variables==20 and len(clauses)==91,"SATLIB original format unexpected")
        cases.append(dict(id=ident,sha256=sha(p),raw_sha256=rawsha,
            cohort="satlib_uf20_sat",family="SATLIB-public-random-3SAT",
            expected="SAT",origin_url=u,normalized_trailer=(data!=normalized)))
    for n in (12,16,20,24):
        for unsat in (False,True):
            ident="control-xor-%d-%s"%(n,"unsat" if unsat else "sat")
            p=ROOT/"frozen"/(ident+".cnf");p.write_bytes(make_control(n,unsat))
            variables,cls=base.dimacs(p)
            need(variables==n and bool(cls),"invalid controlled CNF")
            cases.append(dict(id=ident,sha256=sha(p),cohort="synthetic_xor_residual",
                family="planted-parity-chain-with-residual-CNF",
                expected="UNSAT" if unsat else "SAT",construction="mathematically constrained XOR chain"))
    need(len(cases)==20 and len({c["sha256"] for c in cases})==20,"expected 20 unique originals")
    save(ROOT/"frozen/manifest.json",dict(protocol=PROTO,cases=cases,
        public_originals=12,synthetic_controls=8,source_commit=SOURCE_COMMIT,
        SATLIB_not_fresh_holdout=True))
    print("R171_FROZEN_PASS",len(cases),"SATLIB",12,"controls",8,flush=True)
def sources():
    m=base.rd(ROOT/"frozen/manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==20,"wrong pre-frozen manifest")
    for c in m["cases"]:
        need(sha(ROOT/"frozen"/(c["id"]+".cnf"))==c["sha256"],"changed source "+c["id"])
    return m["cases"]
def trial(c,mode,rep,prep,binary):
    path=ROOT/"frozen"/(c["id"]+".cnf")
    tsv=ROOT/("full-"+c["id"]+".tsv")
    need(sha(path)==c["sha256"] and sha(tsv)==prep["full_tsv_sha"],"source/proof mutation")
    charge=0 if mode=="clean" else prep["preprocessing_s"]
    need(charge+1<CAP,"preprocessing too expensive")
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),mode,str(path.resolve()),str(tsv.resolve()),
            str(CAP-charge)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP+10)
    except subprocess.TimeoutExpired as e:raise RuntimeError("R171_NATIVE_HUNG "+c["id"]) from e
    elapsed=time.perf_counter()-start+charge
    need(p.returncode in (0,10,20),"native failed "+str(p.returncode)+" "+p.stderr[-350:].decode(errors="replace"))
    out,native,stats,rows,derived=base.parse_native(p.stdout,mode)
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    need(p.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],"inconsistent solver exit")
    need(rows==(0 if mode=="clean" else prep["full_rows"]),"GF2 rows not pinned")
    need(abs(float(native["solver_s"])-(elapsed-charge))<0.5,"wall/native timer disagreement")
    if status=="SAT":
        need(native["source_sat_witness_checked"]=="1","native witness missing")
        base.sat_check(path,out)
    # All 20 have expected known SAT/UNSAT. Fail closed on wrong answers.
    need(status==c["expected"],"KNOWN_STATUS_MISMATCH "+c["id"]+" "+mode+" "+status)
    used=int(native["two_way_used_reasons"])
    proposed=int(native["two_way_proposals"])
    if mode in ("clean","direct_full","direct_two_way_shadow"):
        need(used==0 and proposed==0,"inactive Gaussian mode unexpectedly propagated")
    need(used<=proposed,"used GF2 reason missing provenance")
    return dict(protocol=PROTO,id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
        mode=mode,repeat=rep,status=status,expected=c["expected"],
        elapsed_s=round(elapsed,6),native_solver_s=float(native["solver_s"]),
        cap_s=CAP,par2_s=round(min(CAP,elapsed),6),preprocess_s=charge,
        rows=rows,used_reasons=used,proposals=proposed,
        native_stats=stats,first_used_reason_ns=int(native["first_used_reason_ns"]))
def shard(i,binary):
    need(0<=i<SHARDS and binary.is_file(),"invalid shard or missing binary")
    pin=base.rd(ROOT/"r170-build-pin.json")
    need(sha(binary)==pin["binary_sha256"],"R170 binary provenance mismatch")
    if hasattr(os,"sched_getaffinity"):
        mask=os.sched_getaffinity(0)
        if mask:os.sched_setaffinity(0,{min(mask)})
    cases=sources();arr=[]
    for j,c in enumerate(cases):
        if j%SHARDS!=i:continue
        prep=base.prepare(c)
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,mode,rep,prep,binary)
                arr.append(r)
                save(ROOT/("shard-%d.json"%i),arr)
                print("R171_TRIAL",json.dumps({k:r[k] for k in
                    ("id","mode","repeat","status","native_solver_s","elapsed_s","used_reasons")},sort_keys=True),flush=True)
    need(len(arr)==5*REPS*len(MODES),"incomplete shard")
    print("R171_SHARD_PASS",i,len(arr),flush=True)
def audit():
    cases=sources();d={c["sha256"]:c for c in cases}
    rows=[]
    for i in range(SHARDS):
        file=ROOT/("shard-%d.json"%i)
        need(file.is_file(),"missing shard")
        arr=base.rd(file);need(len(arr)==60,"incomplete shard data")
        rows+=arr
    need(len(rows)==240,"expected 240 attempts")
    need(len({(r["sha256"],r["mode"],r["repeat"]) for r in rows})==240,"duplicate trials")
    for c in cases:
        need(len([r for r in rows if r["sha256"]==c["sha256"]])==12,"unpaired CNF")
        ev=base.rd(ROOT/("cert-"+c["id"]+".json"))
        base.independent_cert(c,ev)
    for r in rows:
        need(r["sha256"] in d and r["status"]==d[r["sha256"]]["expected"],"wrong answer")
    result={}
    for cohort in ("all","satlib_uf20_sat","synthetic_xor_residual"):
        vals=[r for r in rows if cohort=="all" or cohort==r["cohort"]]
        result[cohort]={}
        for mode in MODES:
            arr=[r for r in vals if r["mode"]==mode]
            times=sorted(r["native_solver_s"] for r in arr)
            walls=sorted(r["elapsed_s"] for r in arr)
            result[cohort][mode]=dict(trials=len(arr),solved=len(arr),
                median_native_s=round(statistics.median(times),6),
                median_process_s=round(statistics.median(walls),6),
                total_process_s=round(sum(walls),6),
                median_preprocessing_s=round(statistics.median(r["preprocess_s"] for r in arr),6),
                par2_s=round(sum(r["par2_s"] for r in arr),6),
                used_GF2_reasons=sum(r["used_reasons"] for r in arr))
    paired=[]
    for c in cases:
        for rep in range(REPS):
            a={r["mode"]:r for r in rows if r["sha256"]==c["sha256"] and r["repeat"]==rep}
            need(set(a)==set(MODES),"mode missing")
            paired.append(dict(id=c["id"],cohort=c["cohort"],repeat=rep,
                clean_s=a["clean"]["elapsed_s"],
                newonly_s=a["direct_two_way_newonly"]["elapsed_s"],
                shadow_s=a["direct_two_way_shadow"]["elapsed_s"],
                gain_pct=round(100*(a["clean"]["elapsed_s"]-a["direct_two_way_newonly"]["elapsed_s"])/
                    a["clean"]["elapsed_s"],3)))
    final=dict(status="R171_EASY_AUDIT_PASS",protocol=PROTO,attempts=240,
        source_SHA_verified=True,SAT_witnesses_checked=True,independent_source_XOR_certificates=True,
        cohorts={"satlib_uf20_sat":12,"synthetic_xor_residual":8},
        original_formulas_in_results=12,artificial_formulas_in_results=8,
        binary_provenance=base.rd(ROOT/"r170-build-pin.json"),summary=result,
        paired=paired,records=rows,caveats=["SATLIB 20-variable instances are public historical SAT benchmarks, not fresh blind holdout.",
        "Eight XOR residual cases are deliberately constructed controlled examples, NOT real application CNFs.",
        "All tasks are easy and native times may be near timer resolution; compare end-to-end wall and medians.",
        "A successful easy microbenchmark is not evidence of improved performance on the hard R170 formulas.",
        "UNSAT synthetic cases guaranteed contradictory from parity chain and terminal unit.",
        "No Kissat comparison in this short causal test."])
    save(ROOT/"report.json",final)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R171 easy short 240 paired attempts\n\n")
        for cohort,group in result.items():
            f.write("## "+cohort+"\n\n")
            f.write("| Mode | solved | Median native ms | Median process ms | GF2 reasons used |\n|---|---:|---:|---:|---:|\n")
            for mode,v in group.items():
                f.write(f'| {mode} | {v["solved"]}/{v["trials"]} | {v["median_native_s"]*1000:.3f} | {v["median_process_s"]*1000:.3f} | {v["used_GF2_reasons"]} |\n')
            f.write("\n")
    print("R171_FINAL",json.dumps({"status":final["status"],"attempts":240,"summary":result},sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("generate","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r171/r170-native")
    a=p.parse_args()
    if a.action=="generate":generate()
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
