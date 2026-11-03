#!/usr/bin/env python3
"""R31 controlled study: certified binary implication SCC + full 2SAT solving.
9 x 8 new CNFs, 2 paired repeats, 6 modes. Other AND/OR/AMO structures are
observational only, no unproven intervention. Frozen R29 source and SHA binaries.
"""
import argparse,csv,hashlib,json,os,random,re,subprocess,time
from collections import Counter
from pathlib import Path
import r29_hidden_partial_benchmark as r29
import r28_exact_gf2_benchmark as prior
import r30_fresh_blind_benchmark as ext

PROTO="DRNAS-R31-CERTIFIED-IMPLICATION-GRAPH-20261103-V1"
SALT="R31-SEPARATE-PREDECLARED-FRESH-20261103-BINARY-GATE-LINKS"
FAMILIES=("implication_cycle_unsat","equivalence_ring_sat",
          "hidden_implication_unsat_mixed","independent_2sat_sat",
          "and_gate_residual","or_gate_residual","amo_pairwise_residual",
          "independent_3sat_control","hidden_xor_control")
N_PER=8; SHARDS=4; REPS=2; CAP=3.0
MODES=("Kissat_clean","R29_shadow","R31_shadow","R31_active",
       "CryptoMiniSat_Ubuntu","CaDiCaL_Ubuntu")
r29.CAP=CAP
r29.SALT=SALT
def check(ok,message):
    if not ok:raise RuntimeError("R31_AUDIT_FAIL "+message)
def sha(data):return hashlib.sha256(data).hexdigest()
def rng_for(family,i):
    return random.Random(int(sha((SALT+"/"+family+"/"+str(i)).encode()),16))
def rand_clause(rng,variables,truth,k=3):
    vs=rng.sample(variables,k)
    clause=[v if rng.getrandbits(1) else -v for v in vs]
    if not any((z>0)==bool(truth[abs(z)]) for z in clause):clause[0]*=-1
    return clause
def equivalence_chain(i,unsat,noise=False):
    rng=rng_for("eq_chain_unsat" if unsat else "eq_chain_sat",i)
    n=48+(i%4)*8
    clauses=[]
    for v in range(1,n):
        clauses += [[-v,v+1],[v,-(v+1)]]
    if unsat:
        # x_n = x_1 from the chain and x_n = ~x_1 from the final
        # signed edge: a genuine contradictory implication cycle.
        clauses += [[-n,-1],[n,1]]
    else:
        clauses += [[-n,1],[n,-1]]
    truth={v:1 for v in range(1,n+1)}
    if noise:
        for j in range(175):
            clauses.append(rand_clause(rng,list(truth),truth,3))
    rng.shuffle(clauses)
    return n,clauses,"UNSAT" if unsat else "SAT"
def planted2(i):
    rng=rng_for("planted_2sat",i)
    n=100+(i%4)*12
    truth={v:rng.getrandbits(1) for v in range(1,n+1)}
    clauses=[rand_clause(rng,list(truth),truth,2) for _ in range(400)]
    rng.shuffle(clauses)
    return n,clauses,"SAT"
def gate_case(family,i):
    rng=rng_for(family,i)
    gates=28+(i%4)*4
    n=3*gates
    truth={v:rng.getrandbits(1) for v in range(1,2*gates+1)}
    clauses=[]
    for g in range(gates):
        a,b,z=2*g+1,2*g+2,2*gates+g+1
        if family=="and_gate_residual":
            truth[z]=truth[a] & truth[b]
            clauses.extend([[-z,a],[-z,b],[z,-a,-b]])
        else:
            truth[z]=truth[a] | truth[b]
            clauses.extend([[z,-a],[z,-b],[-z,a,b]])
    for j in range(180):
        clauses.append(rand_clause(rng,list(truth),truth,3))
    rng.shuffle(clauses)
    return n,clauses,"SAT"
def amo_case(i):
    rng=rng_for("amo",i)
    groups=5; size=10+(i%3)*2;n=groups*size
    truth={v:0 for v in range(1,n+1)}
    clauses=[]
    for g in range(groups):
        vars=list(range(g*size+1,(g+1)*size+1))
        truth[rng.choice(vars)]=1
        clauses.append(vars)
        for a in range(len(vars)):
            for b in range(a+1,len(vars)):
                clauses.append([-vars[a],-vars[b]])
    for j in range(150):
        clauses.append(rand_clause(rng,list(truth),truth,3))
    rng.shuffle(clauses)
    return n,clauses,"SAT"
def independent3(i):
    rng=rng_for("independent3",i)
    n=88+(i%4)*8
    truth={v:rng.getrandbits(1) for v in range(1,n+1)}
    clauses=[rand_clause(rng,list(truth),truth,3) for _ in range(370)]
    rng.shuffle(clauses)
    return n,clauses,"SAT"
def generate(family,i):
    if family=="implication_cycle_unsat":return equivalence_chain(i,True,False)
    if family=="equivalence_ring_sat":return equivalence_chain(i,False,True)
    if family=="hidden_implication_unsat_mixed":return equivalence_chain(i+100,True,True)
    if family=="independent_2sat_sat":return planted2(i)
    if family in ("and_gate_residual","or_gate_residual"):return gate_case(family,i)
    if family=="amo_pairwise_residual":return amo_case(i)
    if family=="independent_3sat_control":return independent3(i)
    if family=="hidden_xor_control":return r29.regular_case("hidden_xor3",i+17001)
    raise ValueError(family)
def prepare(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in FAMILIES:
        for i in range(N_PER):
            n,clauses,expected=generate(family,i)
            data=r29.write_dimacs(n,clauses)
            name=family+"_"+f"{i:02d}"+".cnf"
            (out/name).write_bytes(data)
            cases.append(dict(name=name,family=family,n=n,m=len(clauses),
                              expected=expected,sha256=sha(data)))
    check(len(cases)==72 and len({c["sha256"] for c in cases})==72,"Duplicate CNF")
    manifest=dict(protocol=PROTO,salt=SALT,cases=cases,modes=MODES,
                  cap_s=CAP,repeats=REPS,shards=SHARDS,
                  safeguards=["All formulas frozen before testing",
                              "R29 source and native binary unchanged",
                              "Binary implication UNSAT proven by two clause-id paths",
                              "Pure 2-SAT SAT checked against original full CNF",
                              "3-clause AND/OR signatures logged but not used to change answers",
                              "Predefined study is synthetic, NOT official SAT Competition",
                              "3s timeout and 6s PAR-2 penalty"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(c["sha256"]+"  "+c["name"]+"\n" for c in cases))
    print("R31_FROZEN",len(cases),sha((out/"manifest.json").read_bytes()),flush=True)
def verify_binary_certificate(output,original,status):
    x=re.findall(r"^c R31_ROUTE certified_binary_unsat var=(\d+)$",output,re.M)
    check(len(x)==1 and status=="UNSAT","Missing 2SAT UNSAT announcement")
    v=int(x[0]);paths={1:[],2:[]}
    for line in output.splitlines():
        if not line.startswith("c R31_EDGE "):continue
        m=re.fullmatch(r"c R31_EDGE path=([12]) from=(-?\d+) to=(-?\d+) clause=(\d+)",line)
        check(m is not None,"Malformed binary edge")
        pid,a,b,cid=map(int,m.groups())
        check(0<=cid<len(original),"Original source clause id out of range")
        cl=original[cid]
        check((len(cl)==1 and a==-cl[0] and b==cl[0]) or
              (len(cl)==2 and ((a==-cl[0] and b==cl[1]) or
                               (a==-cl[1] and b==cl[0]))),
              "Invalid binary entailment edge: "+str(cid))
        paths[pid].append((a,b))
    for pid,begin,end in ((1,v,-v),(2,-v,v)):
        edges=paths[pid]
        check(bool(edges) and edges[0][0]==begin and edges[-1][1]==end,
              "Missing correct start or end in contradiction path")
        check(all(a[1]==b[0] for a,b in zip(edges,edges[1:])),
              "Non-contiguous contradiction chain")
    return "independent_binary_scc_proof",sum(map(len,paths.values()))
def run_r31(mode,bins,path,original,case):
    cmd=[str(bins["r31"]),str(path),str(bins["r29"]),str(bins["kissat"])]
    env=os.environ.copy()
    env["R31_MODE"]="active" if mode=="R31_active" else "shadow"
    env["R29_MODE"]="shadow"
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                         env=env,timeout=CAP)
        sec=time.monotonic()-start
        check(p.returncode in (10,20),"Bad R31 subprocess exit "+str(p.returncode)+": "+p.stderr[-400:])
        status="SAT" if p.returncode==10 else "UNSAT"
        check(status==case["expected"],"Incorrect SAT status "+case["name"])
        output=p.stdout
        features=next((line for line in output.splitlines() if line.startswith("c R31_FEATURES ")),"")
        feat={k:int(v) for k,v in re.findall(r"([a-z0-9_]+)=(\d+)",features)}
        check("binary" in feat and "scc" in feat,"Missing telemetry")
        route=next((line.split()[2] for line in output.splitlines()
                    if line.startswith("c R31_ROUTE ")),"unknown")
        if route=="certified_binary_unsat":
            certificate,size=verify_binary_certificate(output,original,status)
        elif route=="certified_entire_2sat_sat":
            check(status=="SAT" and prior.check_sat_model(output,case["n"],original),
                  "2SAT model not valid on original CNF")
            certificate,size="independent_complete_2sat_witness",1
        else:
            rm=next((line.split()[2] for line in output.splitlines()
                     if line.startswith("c R29_ROUTE ")),"")
            if status=="SAT":
                check(prior.check_sat_model(output,case["n"],original),
                      "Inherited R29 SAT model invalid")
                certificate,size="SAT_witness_checked",0
            elif rm=="certified_xor_contradiction":
                certificate,size=r29.certify(output,original,status,rm)
            else:certificate,size="UNSAT_solver_only",0
    except subprocess.TimeoutExpired:
        sec=time.monotonic()-start
        status="TIMEOUT";route="timeout";certificate="not_applicable";size=0;feat={}
    return dict(status=status,seconds=round(sec,6),par2=6.0 if status=="TIMEOUT" else round(sec,6),
                route=route,certificate=certificate,cert_size=size,features=feat)
def measure(a):
    root=Path(a.inputs);j=json.loads((root/"manifest.json").read_text())
    check(j["protocol"]==PROTO and j["modes"]==list(MODES),"Wrong frozen manifest")
    check(0<=a.shard<SHARDS,"Bad shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    bins={k:Path(getattr(a,k)).resolve() for k in ("kissat","r29","r31","cms","cadical")}
    check(all(p.is_file() for p in bins.values()),"Missing executable")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    metadata=dict(shard=a.shard,manifest_sha256=sha((root/"manifest.json").read_bytes()),
                  binary_sha256={k:sha(v.read_bytes()) for k,v in bins.items()})
    (out/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    rows=[]
    for case in j["cases"][a.shard::SHARDS]:
        path=(root/case["name"]).resolve()
        check(sha(path.read_bytes())==case["sha256"],"Formula SHA drift")
        n,clauses=prior.load_clauses(path)
        check(n==case["n"] and len(clauses)==case["m"],"Bad DIMACS")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(sha(("R31/ORDER/"+case["sha256"]+"/"+str(rep)).encode()),16)).shuffle(order)
            for mode in order:
                if mode in ("R31_active","R31_shadow"):
                    result=run_r31(mode,bins,path,clauses,case)
                elif mode in ("Kissat_clean","R29_shadow"):
                    result=r29.run_one(mode,bins,path,clauses,case)
                else:result=ext.external_run(mode,bins,path,clauses,case)
                if "features" not in result:result["features"]={}
                rows.append(dict(formula=case["name"],family=case["family"],
                                 repeat=rep,mode=mode,**result))
                (out/"rows.json").write_text(json.dumps(rows,indent=1)+"\n")
                print("R31_TRIAL",a.shard,case["name"],rep,mode,result["status"],
                      result["seconds"],result["route"],flush=True)
        statuses={x["status"] for x in rows if x["formula"]==case["name"]}-{"TIMEOUT"}
        check(len(statuses)<=1,"Contradictory solver decisions")
    print("R31_SHARD_DONE",a.shard,len(rows),flush=True)
def aggregate(a):
    root=Path(a.inputs);j=json.loads((root/"manifest.json").read_text())
    digest=sha((root/"manifest.json").read_bytes())
    rows=[];binaries=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r31-shard-{shard}"/"results"
        meta=json.loads((folder/"metadata.json").read_text())
        check(meta["shard"]==shard and meta["manifest_sha256"]==digest,"Shard drift")
        binaries.add(json.dumps(meta["binary_sha256"],sort_keys=True))
        x=json.loads((folder/"rows.json").read_text())
        check(len(x)==len(j["cases"][shard::SHARDS])*REPS*len(MODES),"Missing shard attempts")
        rows+=x
    check(len(rows)==864 and len(binaries)==1,"Incomplete audit or inconsistent builds")
    summary={}
    for family in ("ALL",)+FAMILIES:
        group={}
        for mode in MODES:
            trials=[x for x in rows if x["mode"]==mode and
                    (family=="ALL" or x["family"]==family)]
            cands=[c for c in j["cases"] if family=="ALL" or c["family"]==family]
            group[mode]=dict(par2=round(sum(x["par2"] for x in trials),6),
                solved=sum(all(x["status"]!="TIMEOUT" for x in trials
                               if x["formula"]==c["name"]) for c in cands),
                total=len(cands),timeouts=sum(x["status"]=="TIMEOUT" for x in trials),
                bin_proofs=sum(x["certificate"]=="independent_binary_scc_proof" for x in trials),
                two_sat_sat=sum(x["certificate"]=="independent_complete_2sat_witness" for x in trials))
        active=[x for x in rows if x["mode"]=="R31_active" and
                (family=="ALL" or x["family"]==family)]
        feat=next((x["features"] for x in active if x["features"]),{})
        group["example_structural_features"]=feat
        summary[family]=group
        print("R31_SUMMARY",family,json.dumps(group,sort_keys=True),flush=True)
    result=dict(protocol=PROTO,summary=summary,rows=rows,
        sha256_manifest=digest,sha256_binaries=json.loads(next(iter(binaries))),
        limitations=["Synthetic controls, NOT an external SAT Competition sample",
                     "Gate motifs are observational; only exact 2SAT paths acted upon",
                     "R29 unchanged; fallback unchanged",
                     "Subprocess wall clock including preprocessing and startup",
                     "R31 proof checked against original source CNF"])
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    md=["# DRNAS R31 certified binary implications and gate motif study",
        "9 families × 8 unseen CNFs, two repeats, six solver modes, 3s cap.",
        "PAR-2 timeout penalty=6s, lower is better; solver restarts not modified.",
        "Certified 2-SAT implication paths are independently replayed against source binary clauses.","",
        "| Family | Kissat | R29 | R31 shadow | R31 active | CMS | CaDiCaL | Binary proof attempts |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for fam,g in summary.items():
        md.append("| "+fam+" | "+" | ".join(f"{g[m]['par2']:.4f}" for m in MODES)+
                  f" | {g['R31_active']['bin_proofs']} |")
    md.extend(["","Pure 2SAT models verified on original CNF. Certificate snippets in raw artifact.",
               "No universality, P=NP, or official leaderboard claim."])
    Path(a.report).write_text("\n".join(md)+"\n")
    with Path(a.csv).open("w",newline="") as f:
        fieldnames=[k for k in rows[0] if k!="features"]
        w=csv.DictWriter(f,fieldnames=fieldnames,extrasaction="ignore")
        w.writeheader();w.writerows(rows)
    print("R31_AUDIT_PASS",len(rows),len(j["cases"]),flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    x=sub.add_parser("prepare");x.add_argument("--outdir",required=True)
    x=sub.add_parser("measure")
    for name in ("inputs","kissat","r29","r31","cms","cadical","outdir"):
        x.add_argument("--"+name,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sub.add_parser("aggregate")
    for name in ("inputs","combined","output","report","csv"):x.add_argument("--"+name,required=True)
    a=p.parse_args()
    if a.cmd=="prepare":prepare(a.outdir)
    elif a.cmd=="measure":measure(a)
    else:aggregate(a)
if __name__=="__main__":main()
