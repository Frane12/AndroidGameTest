#!/usr/bin/env python3
"""R29 frozen first-principles hidden/partial XOR suite.

6 SHA-salted families × 12 formulas × 2 paired repeats × 4 strategies.
R29 is a *research prototype*. Claims are restricted to these distributions.
All UNSAT answers from algebra are independently verified by source-clause
resolution, full-parity group reconstruction and an XOR row certificate.
"""
import argparse,csv,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
from collections import Counter
import r28_exact_gf2_benchmark as prior

PROTO="DRNAS-R29-HIDDEN-PARTIAL-GF2-20261103-FROZEN-v1"
SALT="DRNAS-R29-UNSEEN-SALT-HIDDEN-RESOLVE-PARTIAL-20261103-LOCKED"
FAMILIES=("hidden_xor3","hidden_xor6","hidden_mixed","visible_partial",
          "split_near_xor_decoy","gauss_unit_partial")
N_PER,SHARDS,REPS,CAP=12,4,2,3.0
MODES=("Kissat_clean","R28_exact","R29_shadow","R29_active")
def check(ok,msg):
    if not ok:raise RuntimeError("R29_AUDIT_ERROR: "+msg)
def digest(data):return prior.digest(data)
def rng_for(family,i):
    return random.Random(int(digest(f"{SALT}/{family}/{i}".encode()),16))
def write_dimacs(n,clauses):
    return (f"p cnf {n} {len(clauses)}\n" +
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
def parity_clause(row,parity):
    out=[]
    for mask in range(1<<len(row)):
        if (mask.bit_count()&1)!=parity:
            out.append([-v if (mask>>j)&1 else v for j,v in enumerate(row)])
    return out
def xor_graph(k,vertices,rng,unsat):
    inc,n=prior.graph_xor(k,vertices,rng)
    witness={v:rng.getrandbits(1) for v in range(1,n+1)}
    rhs=[sum(witness[x] for x in row)%2 for row in inc]
    if unsat:
        rhs[0]^=1
        check(sum(rhs)%2==1,"Missing GF2 parity contradiction")
    clauses=[cl for row,p in zip(inc,rhs) for cl in parity_clause(row,p)]
    if not unsat:
        check(all(any((v>0)==bool(witness[abs(v)]) for v in cl)
                  for cl in clauses),"Invalid planted XOR SAT witness")
    return n,clauses,witness
def planted_clause(rng,variables,witness):
    vs=rng.sample(variables,3)
    out=[-v if rng.getrandbits(1) else v for v in vs]
    if not any((lit>0)==bool(witness[abs(lit)]) for lit in out):
        out[0]=-out[0]
    check(any((v>0)==bool(witness[abs(v)]) for v in out),"Invalid planted clause")
    return out
def split_all(n,clauses,rng):
    out=[]
    for cl in clauses:
        check(len(cl) in (3,6),"Unexpected XOR size in splitting")
        xs=list(cl);rng.shuffle(xs)
        n+=1
        out.append([xs[0],n])
        out.append([-n]+xs[1:])
    rng.shuffle(out)
    return n,out
def regular_case(family,i):
    rng=rng_for(family,i)
    k=6 if family=="hidden_xor6" else 3
    vertices=(24+(i%3)*4) if k==6 else (56+(i%3)*8)
    unsat=i%2==0 and family!="split_near_xor_decoy"
    n,clauses,witness=xor_graph(k,vertices,rng,unsat)
    if family=="split_near_xor_decoy":
        # Remove one of the four forbidden assignments from every width-3
        # block. *Three out of four is not a proven XOR equation*.
        check(k==3 and len(clauses)%4==0,"Wrong parity block")
        clauses=[c for j,c in enumerate(clauses) if j%4!=i%4]
        check(all(any((v>0)==bool(witness[abs(v)]) for v in cl)
                  for cl in clauses),"Decoy SAT witness must still work")
    if family in ("hidden_mixed","visible_partial","split_near_xor_decoy"):
        for j in range(30):
            clauses.append(planted_clause(rng,list(range(1,n+1)),witness))
        # For odd i when the XOR subsystem is consistent the planted model
        # certifies SAT; for even i UNSAT follows from XOR alone.
    if family in ("hidden_xor3","hidden_xor6","hidden_mixed","split_near_xor_decoy"):
        # In the decoy branch only the shortened 3/4 parity set is split;
        # missing forbidden clauses are NEVER added back.
        n,clauses=split_all(n,clauses[:len(clauses)-(30 if family in ("hidden_mixed","split_near_xor_decoy") else 0)],rng) if family!="split_near_xor_decoy" else split_all(n,clauses[:-30],rng)
        if family in ("hidden_mixed","split_near_xor_decoy"):
            # Rematerialize the identical planted noise deterministically
            # from a stable separate seed (no hidden solver feedback).
            noise_rng=rng_for(family+"_noise",i)
            clauses += [planted_clause(noise_rng,list(range(1,len(witness)+1)),witness)
                        for j in range(30)]
            rng.shuffle(clauses)
    expected=("UNSAT" if unsat else "SAT") if family!="split_near_xor_decoy" else "SAT"
    return n,clauses,expected
def gaussian_unit_case(i):
    rng=rng_for("gauss_unit_partial",i)
    chain=20+(i%3)*4
    # Variables: x_0..x_chain, s_0..s_(chain-1), t_0..t_(chain-1)
    x=list(range(1,chain+2))
    s=list(range(chain+2,2*chain+2))
    t=list(range(2*chain+2,3*chain+2))
    n=3*chain+1
    truth={v:0 for v in x}
    for v in s+t:truth[v]=rng.getrandbits(1)
    clauses=[]
    for j in range(chain):
        p=truth[s[j]]^truth[t[j]]
        clauses+=parity_clause([x[j],s[j],t[j]],p)
        clauses+=parity_clause([x[j+1],s[j],t[j]],p)
    clauses.append([-x[0]])  # implies all chain x_i == 0 via GF(2)
    extra=list(range(n+1,n+141))
    for v in extra:truth[v]=rng.getrandbits(1)
    n+=len(extra)
    # Residual CNF is intentionally not fully algebraic. Some clauses use
    # the implied x's; R29 may inject units but cannot claim SAT/UNSAT from
    # the consistent XOR subsystem alone.
    choices=extra+x
    for j in range(500):
        if j%3==0:
            vs=[rng.choice(x)]+rng.sample(extra,2)
            lits=[v if rng.getrandbits(1) else -v for v in vs]
            if not any((z>0)==bool(truth[abs(z)]) for z in lits):lits[1]*=-1
            clauses.append(lits)
        else:
            clauses.append(planted_clause(rng,choices,truth))
    rng.shuffle(clauses)
    check(all(any((v>0)==bool(truth[abs(v)]) for v in cl)
              for cl in clauses),"Unit-chain SAT witness invalid")
    return n,clauses,"SAT"
def prepare(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in FAMILIES:
        for i in range(N_PER):
            if family=="gauss_unit_partial":
                n,clauses,expected=gaussian_unit_case(i)
            else:
                n,clauses,expected=regular_case(family,i)
            raw=write_dimacs(n,clauses)
            name=f"{family}_{i:02}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              n=n,m=len(clauses),sha256=digest(raw)))
    check(len(cases)==72 and len({c["sha256"] for c in cases})==72,
          "Expected 72 distinct CNFs")
    manifest=dict(protocol=PROTO,salt=SALT,cases=cases,cap_s=CAP,repeats=REPS,
                  modes=MODES,shards=SHARDS,notes=[
                    "All 72 R29 inputs SHA-frozen before timings",
                    "Synthetic, not an official SAT Competition sample",
                    "R29 uses bounded single-positive/single-negative auxiliary resolution",
                    "Incomplete parity blocks do not imply any GF2 equation",
                    "Correct XOR subset contradiction proves original mixed CNF UNSAT",
                    "Consistent mixed GF2 subsystem cannot by itself prove SAT",
                    "At least four new certified units and 32 covered clauses required for active injection",
                    "Same pinned Kissat binary used for every fallback",
                    "Independent UNSAT parity/resolution certificate verifier",
                    "Two paired repeats per SHA-pinned formula and native CPU affinity",
                    "Timeout scored 2*cap with PAR-2"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(f"{c['sha256']}  {c['name']}\n" for c in cases))
    print("R29_FROZEN",len(cases),digest(out/"manifest.json"),flush=True)

def parse_resolution_logs(output,original):
    derived=[]
    seen=set()
    for line in output.splitlines():
        if not line.startswith("c R29_RESOLVE "):continue
        m=re.fullmatch(r"c R29_RESOLVE var=(\d+) pos=(\d+) neg=(\d+) literals=([-0-9,]+)",line)
        check(m is not None,"Malformed resolution certificate")
        v,p,n=map(int,m.group(1,2,3))
        check(0<=p<len(original) and 0<=n<len(original) and p!=n,
              "Resolution parents out of bounds")
        left,right=original[p],original[n]
        check(v in left and -v in right,"Resolution parent polarity")
        litset=set(x for x in left+right if abs(x)!=v)
        check(all(-x not in litset for x in litset),"Tautological resolution row")
        result=tuple(sorted(litset))
        printed=tuple(int(x) for x in m.group(4).split(","))
        check(printed==result,"Resolution resolvent mismatch")
        check((v,p,n) not in seen,"Repeated resolution")
        seen.add((v,p,n))
        derived.append(result)
    return original+derived

def proof_equations(output,clauses):
    # Check the equations supplied by the native solver independently by
    # looking up every required forbidden-sign clause in original+derived.
    equations={}
    canon={tuple(sorted(c,key=lambda t:(abs(t),t<0))) for c in clauses}
    for line in output.splitlines():
        if not line.startswith("c R28_EQ "):continue
        m=re.fullmatch(r"c R28_EQ id=(\d+) rhs=([01]) vars=([0-9,]+)",line)
        check(m is not None,"Malformed GF2 equation")
        eid=int(m.group(1));rhs=int(m.group(2))
        vs=tuple(map(int,m.group(3).split(",")))
        check(1<=len(vs)<=6 and vs==tuple(sorted(set(vs))) and eid not in equations,
              "Bad GF2 equation variables")
        if len(vs)==1:
            check((vs[0] if rhs else -vs[0],) in canon,"Missing unit clause")
        else:
            for mask in range(1<<len(vs)):
                if (mask.bit_count()&1)==rhs:continue
                clause=tuple(-x if (mask>>j)&1 else x for j,x in enumerate(vs))
                check(clause in canon,"Incomplete or false XOR block")
        equations[eid]=(vs,rhs)
    check(set(equations)==set(range(len(equations))),"GF2 equation IDs not contiguous")
    return equations
def certify(output,original,status,route):
    if route not in ("certified_xor_contradiction","certified_derived_units"):
        return "not_applicable",0
    augmented=parse_resolution_logs(output,original)
    eqs=proof_equations(output,augmented)
    check(bool(eqs),"Empty proof equation set")
    if route=="certified_xor_contradiction":
        cert=[line for line in output.splitlines() if line.startswith("c R28_UNSAT_CERT ids=")]
        check(len(cert)==1 and status=="UNSAT","Contradiction cert or result missing")
        selected=list(map(int,cert[0].split("ids=",1)[1].split(",")))
        check(len(set(selected))==len(selected),"Duplicate XOR proof IDs")
        bitset=set();rhs=0
        for eid in selected:
            check(eid in eqs,"Unknown XOR row in contradiction")
            vs,p=eqs[eid];rhs^=p
            for x in vs:
                if x in bitset:bitset.remove(x)
                else:bitset.add(x)
        check(not bitset and rhs==1,"XOR contradiction proof does not yield 0=1")
        return "xor_unsat_resolve_verified",len(selected)
    check(route=="certified_derived_units","Unexpected route")
    allunits=[l for l in output.splitlines() if l.startswith("c R29_UNIT ")]
    check(bool(allunits),"No injected unit certificates")
    for line in allunits:
        m=re.fullmatch(r"c R29_UNIT value=(-?\d+) ids=([0-9,]+)",line)
        check(m is not None,"Malformed derived unit")
        unit=int(m.group(1));ids=list(map(int,m.group(2).split(",")))
        check(unit and len(set(ids))==len(ids),"Bad unit proof")
        bits=set();rhs=0
        for eid in ids:
            check(eid in eqs,"Unknown unit proof equation")
            vs,p=eqs[eid];rhs^=p
            for x in vs:
                if x in bits:bits.remove(x)
                else:bits.add(x)
        check(bits=={abs(unit)} and rhs==int(unit>0),
              "Derived unit is NOT entailed by original CNF")
    return "gf2_derived_units_verified",len(allunits)

def run_one(mode,binaries,path,original,case):
    if mode=="Kissat_clean":cmd=[str(binaries["kissat"]),str(path)]
    elif mode=="R28_exact":cmd=[str(binaries["r28"]),str(path),str(binaries["kissat"])]
    else:cmd=[str(binaries["r29"]),str(path),str(binaries["kissat"])]
    env=os.environ.copy()
    env["R29_MODE"]="shadow" if mode=="R29_shadow" else "active"
    t0=time.monotonic()
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                            env=env,timeout=CAP)
        sec=time.monotonic()-t0
        check(proc.returncode in (10,20),"Solver failure "+str(proc.returncode)+" "+proc.stderr[-350:])
        status="SAT" if proc.returncode==10 else "UNSAT"
        check(status==case["expected"],"Wrong SAT/UNSAT status")
        output=proc.stdout
        mark=next((x for x in output.splitlines() if x.startswith("c R29_ROUTE ")),"")
        route=mark.split()[2] if mark else ("kissat" if mode=="Kissat_clean" else
             "r28_"+next((x.split()[2] for x in output.splitlines()
                    if x.startswith("c R28_ROUTE ")),"unknown"))
        if status=="SAT":
            check(prior.check_sat_model(output,case["n"],original),
                  "Original CNF SAT model invalid")
            sat_cert="SAT_witness_checked"
        else:sat_cert="UNSAT_by_solver"
        gf2_cert,k=certify(output,original,status,route)
        if gf2_cert!="not_applicable":sat_cert=gf2_cert
    except subprocess.TimeoutExpired:
        sec=time.monotonic()-t0
        status="TIMEOUT";route="timeout";sat_cert="not_applicable";k=0
    return dict(status=status,seconds=round(sec,6),
                par2=6.0 if status=="TIMEOUT" else round(sec,6),
                route=route,certificate=sat_cert,cert_size=k)

def measure(a):
    root=Path(a.inputs);manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and manifest["modes"]==list(MODES)
          and manifest["cap_s"]==CAP and manifest["repeats"]==REPS,
          "Frozen manifest mismatch")
    check(0<=a.shard<SHARDS,"Shard range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    bins={k:Path(getattr(a,k)).resolve() for k in ("kissat","r28","r29")}
    check(all(p.is_file() for p in bins.values()),"Missing binary")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    meta=dict(shard=a.shard,manifest_sha256=digest(root/"manifest.json"),
              binary_sha256={k:digest(p) for k,p in bins.items()})
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for case in manifest["cases"][a.shard::SHARDS]:
        path=(root/case["name"]).resolve()
        check(digest(path)==case["sha256"],"Input SHA mismatch")
        n,clauses=prior.load_clauses(path)
        check(n==case["n"] and len(clauses)==case["m"],"DIMACS mismatch")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(digest(("r29-order/"+case["sha256"]+"/"+str(rep)).encode()),16)).shuffle(order)
            for mode in order:
                result=run_one(mode,bins,path,clauses,case)
                rows.append(dict(formula=case["name"],family=case["family"],
                                 repeat=rep,mode=mode,**result))
                (out/"rows.json").write_text(json.dumps(rows,indent=1)+"\n")
                print("R29_TRIAL",a.shard,case["name"],rep,mode,
                      result["status"],result["seconds"],result["route"],
                      result["certificate"],flush=True)
        actual={x["status"] for x in rows if x["formula"]==case["name"]} - {"TIMEOUT"}
        check(len(actual)<=1,"Contradictory outcomes")
    print("R29_SHARD_DONE",a.shard,len(rows),flush=True)
def aggregate(a):
    root=Path(a.inputs);manifest=json.loads((root/"manifest.json").read_text())
    sha=digest(root/"manifest.json")
    rows=[];bins=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r29-shard-{shard}"/"results"
        md=json.loads((folder/"metadata.json").read_text())
        check(md["shard"]==shard and md["manifest_sha256"]==sha,"Shard manifest provenance")
        bins.add(json.dumps(md["binary_sha256"],sort_keys=True))
        z=json.loads((folder/"rows.json").read_text())
        check(len(z)==len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),
              "Incomplete shard "+str(shard))
        rows.extend(z)
    check(len(rows)==72*REPS*len(MODES) and len(bins)==1,"Incomplete 576/72 or binary drift")
    summary={}
    for family in ("ALL",)+FAMILIES:
        group={}
        for mode in MODES:
            subset=[x for x in rows if x["mode"]==mode and
                    (family=="ALL" or x["family"]==family)]
            solved=sum(all(x["status"]!="TIMEOUT" for x in rows
                           if x["formula"]==c["name"] and x["mode"]==mode)
                       for c in manifest["cases"] if family=="ALL" or c["family"]==family)
            group[mode]=dict(sum_PAR2=round(sum(x["par2"] for x in subset),6),
                             solved=solved,timeouts=sum(x["status"]=="TIMEOUT" for x in subset),
                             routes=dict(Counter(x["route"] for x in subset)),
                             independent_proofs=sum(x["certificate"] in
                                    ("xor_unsat_resolve_verified","gf2_derived_units_verified")
                                    for x in subset))
        total=group["Kissat_clean"]["sum_PAR2"]
        group["R29_gain_pct"]=round(100*(total-group["R29_active"]["sum_PAR2"])/total,3)
        summary[family]=group
        print("R29_SUMMARY",family,json.dumps(group,sort_keys=True),flush=True)
    result=dict(protocol=PROTO,manifest_sha256=sha,binaries=json.loads(next(iter(bins))),
                summary=summary,rows=rows,
                caveats=["72 seeded synthetic formulas, not proof of universality",
                         "No official external SAT Competition CNFs",
                         "Independent certificates for GF2 contradictions and injected units",
                         "Fallback Kissat UNSAT results not independently proof-checked",
                         "Native R29 startup / preprocessing included in wall-clock measurements"])
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    md=["# DRNAS R29 — hidden and partial XOR experimental holdout",
        "72 SHA-frozen synthetic CNFs, 2 repeats x 4 modes = 576 trials.",
        "3 s cap, PAR-2 timeout penalty 6 s; lower is better.",
        "The R29 admission gate uses only proven parity blocks or resolution.",
        "Not an official SAT Competition ranking or evidence for P=NP.","",
        "| Family | Kissat PAR2 (s) | R28 PAR2 (s) | R29 shadow (s) | R29 active (s) | R29 gain | independent proofs (attempts) |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for fam,d in summary.items():
        md.append("| "+fam+" | "+" | ".join(f"{d[m]['sum_PAR2']:.3f}" for m in MODES)+
                  f" | {d['R29_gain_pct']:+.2f}% | {d['R29_active']['independent_proofs']} |")
    Path(a.report).write_text("\n".join(md)+"\n")
    with Path(a.csv).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    print("R29_AUDIT_PASS",len(rows),"attempts",len(manifest["cases"]),"formulas",flush=True)
def preflight(a):
    root=Path(a.inputs);spec=json.loads((root/"manifest.json").read_text())
    bins={k:Path(getattr(a,k)).resolve() for k in ("kissat","r28","r29")}
    for name in ("hidden_xor3_00.cnf","hidden_xor3_01.cnf",
                 "hidden_xor6_00.cnf","hidden_mixed_00.cnf",
                 "split_near_xor_decoy_00.cnf","gauss_unit_partial_00.cnf"):
        case=next(x for x in spec["cases"] if x["name"]==name)
        path=(root/name).resolve();n,clauses=prior.load_clauses(path)
        for mode in MODES:
            result=run_one(mode,bins,path,clauses,case)
            print("R29_PREFLIGHT",name,mode,json.dumps(result,sort_keys=True),flush=True)
            if mode=="R29_active" and name in ("hidden_xor3_00.cnf","hidden_xor6_00.cnf",
                                              "hidden_mixed_00.cnf"):
                check(result["status"]=="UNSAT" and
                      result["certificate"]=="xor_unsat_resolve_verified",
                      "Hidden XOR contradiction independent proof failed")
            if mode=="R29_active" and name=="hidden_xor3_01.cnf":
                check(result["status"]=="SAT" and
                      result["route"]=="certified_recovered_pure_xor_sat",
                      "Hidden XOR SAT recovery failed")
            if mode=="R29_active" and name=="split_near_xor_decoy_00.cnf":
                check(result["route"] not in
                    ("certified_xor_contradiction","certified_recovered_pure_xor_sat"),
                    "Incomplete XOR decoy was unsoundly promoted")
    print("R29_PREFLIGHT_PASS",flush=True)
def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    v=sub.add_parser("prepare");v.add_argument("--outdir",required=True)
    v=sub.add_parser("preflight")
    for s in ("inputs","kissat","r28","r29"):v.add_argument("--"+s,required=True)
    v=sub.add_parser("measure")
    for s in ("inputs","kissat","r28","r29","outdir"):v.add_argument("--"+s,required=True)
    v.add_argument("--shard",type=int,required=True)
    v=sub.add_parser("aggregate")
    for s in ("inputs","combined","output","report","csv"):v.add_argument("--"+s,required=True)
    a=p.parse_args()
    if a.cmd=="prepare":prepare(a.outdir)
    elif a.cmd=="preflight":preflight(a)
    elif a.cmd=="measure":measure(a)
    else:aggregate(a)
if __name__=="__main__":main()
