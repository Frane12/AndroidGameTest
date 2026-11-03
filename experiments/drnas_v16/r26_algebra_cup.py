#!/usr/bin/env python3
"""R26: 53-case fixed algebra cup against R25, V15.3.1, V7.8, CaDiCaL and Kissat.
Inputs include earlier 32 frozen R25 CNFs, plus 16 fresh 4-/6-XOR GF(2)
instances, 4 original GBD polynomial CNFs, and one original 2025 algebra CNF.
No tuning occurs within measured group. Contest-style, not official competition.
"""
import argparse,hashlib,importlib.util,json,os,random,statistics,subprocess,sys,time
from pathlib import Path
from collections import Counter,defaultdict
import r25_xor_algebra_cup as old

PROTO="DRNAS-R26-NATIVE-XOR-ALGEBRA-CUP-20261103-v1"
MODES=("R26_native","R25_previous","DRNAS_V1531","DRNAS_V78_guided","CaDiCaL301","Kissat404")
CAP=10.0
REPS=2
SHARDS=5
SALT="DRNAS-R26-XOR4-XOR6-SALTED-20261103-BEFORE-TEST-v1"
ADDED_POLY=(4,5,7,8)  # Predeclared previously published authentic, SAT
ADDED_CONTROL="3ef7fa06-grs-fp-comm.cnf"
def configure():
    old.PROTO=PROTO;old.MODES=MODES;old.CAP=CAP;old.REPS=REPS;old.SHARDS=SHARDS

def gencase(i,gen):
    k=4 if i<8 else 6
    family=f"xor{k}_new"
    pos=i%8
    n=(24,28,32,36)[pos%4]
    # Connected simple k-regular circulant graph, every edge occurs twice.
    edges=sorted({tuple(sorted((v,(v+shift)%n)))
                  for v in range(n) for shift in range(1,k//2+1)})
    assert len(edges)==n*k//2
    incidence=[[] for _ in range(n)]
    for j,(u,v) in enumerate(edges,1):
        incidence[u].append(j);incidence[v].append(j)
    assert all(len(inc)==k for inc in incidence)
    rng=random.Random(int(old.digest((SALT+"/"+str(i)).encode()),16))
    witness={j:bool(rng.getrandbits(1)) for j in range(1,len(edges)+1)}
    rhs=[sum(witness[j] for j in inc)%2 for inc in incidence]
    unsat=pos%2==0
    if unsat:
        rhs[0]^=1
        assert sum(rhs)%2==1
    clauses=[]
    for inc,parity in zip(incidence,rhs):
        for mask in range(1<<k):
            flags=[bool(mask>>j&1) for j in range(k)]
            if sum(flags)%2==parity:continue
            clause=[-v if flag else v for v,flag in zip(inc,flags)]
            rng.shuffle(clause)
            clauses.append(tuple(clause))
    rng.shuffle(clauses)
    if not unsat:assert gen.valid(clauses,witness)
    raw=gen.dimacs(len(edges),clauses)
    return raw,"UNSAT" if unsat else "SAT",family,n

def extend(a):
    root=Path(a.inputs);prev=json.loads((root/"manifest.json").read_text())
    old.check(prev["protocol"]=="DRNAS-R25-XOR-ALGEBRA-FROZEN-CUP-20261103-v1",
              "Original R25 manifest must be bytewise retained")
    for x in prev["cases"]:
        old.check(old.digest(root/x["path"])==x["sha256"],"R25 sample SHA mismatch")
    cases=list(prev["cases"])
    sys.path.insert(0,str(Path("research/drnas-sat-v7-8").resolve()))
    import v134_constructive as gen
    for i in range(16):
        raw,status,family,n=gencase(i,gen)
        name=f"r26_xor_{i:02d}.cnf"
        (root/name).write_bytes(raw)
        cases.append(dict(id=name,path=name,sha256=old.digest(raw),
                          status=status,family=family,source="R26-salted-mathematical-gf2",
                          vertices=n,previously_measured=False,bytes=len(raw)))
    pinned=Path(a.pinned)
    manifest=json.loads((pinned/"frozen_verified_gbd_family.json").read_text())
    fetch=old.module("r26_source_verifier",pinned/"preflight.py")
    for idx in ADDED_POLY:
        item=manifest["samples"][idx]
        old.check(item["group"]=="holdout" and
                  item["source_validation"]["validation"]=="sha256_verified",
                  "GBD pin invalid")
        raw,_=fetch.download(item,manifest)
        pin=item["source_validation"]
        old.check(old.digest(raw)==pin["sha256"] and len(raw)==pin["bytes"],
                  "Original GBD data changed")
        name=f"r26_poly_{idx:02d}.cnf"
        (root/name).write_bytes(raw)
        cases.append(dict(id=item["name"],path=name,sha256=old.digest(raw),
                          status=item["status"],family="polynomial_gbd_original",
                          source=item["url"],previously_measured=True,bytes=len(raw)))
    competition=json.loads((pinned/"frozen_competition_v78.json").read_text())
    ctrl=next(x for x in competition["pilot"]+competition["holdout"]
              if x["name"]==ADDED_CONTROL)
    request=dict(hash=ADDED_CONTROL.split("-")[0],name=ADDED_CONTROL,
                 group="competition_control",author="SATCompetition2025",
                 status=ctrl["status"],url=ctrl["url"])
    raw,_=fetch.download(request,dict(max_compressed_bytes=25000000,
                                     max_plain_bytes=100000000))
    old.check(old.digest(raw)==ctrl["sha256"] and len(raw)==ctrl["bytes"],
              "Competition control SHA mismatch")
    name="r26_control_"+ADDED_CONTROL
    (root/name).write_bytes(raw)
    cases.append(dict(id=ADDED_CONTROL,path=name,sha256=old.digest(raw),
                      status=ctrl["status"],family="official_2025_algebra_control",
                      source=ctrl["url"],previously_measured=True,bytes=len(raw)))
    old.check(len(cases)==53 and len({x["sha256"] for x in cases})==53,
              "Missing/duplicate R26 samples")
    spec=dict(protocol=PROTO,cases=cases,cutoff_s=CAP,repeats=REPS,shards=SHARDS,
              modes=MODES,r25_manifest_sha256=old.digest(root/"manifest.json"),
              xor_salt=SALT,added_poly_indices=ADDED_POLY,
              caveats=["No new general SAT complexity claim",
                       "Existing 24 R25 XOR3 are previously tested",
                       "16 freshly salted XOR4/6 are algebraic constructed benchmarks",
                       "All GBD and official controls are historical, NOT unseen",
                       "Native R26 checks complete parity blocks in prefix, then native proof or unchanged Kissat",
                       "No solver output is inferred from family names or input labels"])
    old.save(root/"r26_manifest.json",spec)
    (root/"r25_manifest.json").write_bytes((root/"manifest.json").read_bytes())
    (root/"manifest.json").write_bytes((root/"r26_manifest.json").read_bytes())
    print("R26_FROZEN",len(cases),old.digest(root/"manifest.json"),flush=True)
    for x in cases:print("R26_SOURCE",x["family"],x["id"],x["status"],x["sha256"],flush=True)

ORIGINAL_ATTEMPT=old.attempt
def attempt(mode,case,a,seed,cap):
    if mode=="R25_previous":
        return ORIGINAL_ATTEMPT("R25_adaptive",case,a,seed,cap)
    if mode!="R26_native":
        return ORIGINAL_ATTEMPT(mode,case,a,seed,cap)
    src=Path(a.inputs).resolve()/case["path"]
    b=Path(a.bin).resolve()
    cmd=[str(b/"r26_native"),str(src),str(b/"kissat_solver"),
         str(b/"v1531_nohang"),str(seed)]
    started=time.monotonic()
    try:
        proc=subprocess.run(cmd,timeout=cap,capture_output=True,
                            text=True,errors="replace")
        elapsed=time.monotonic()-started
        status,route,payload=old.parse(proc.stdout,proc.returncode)
        for line in proc.stdout.splitlines():
            if line.startswith("DRNAS_R26_ROUTE\t"):
                route=line.split("\t")[1]
                break
        verified=status==case["status"]
        cert=None
        if payload and status=="UNSAT":
            sys.path.insert(0,str(Path("research/tseitin-replay").resolve()))
            from v153_proof_checker import verify_certificate
            cert=bool(verify_certificate(payload,old.clauses_for_proof(src)))
            verified=verified and cert
        if payload and status=="SAT" and isinstance(payload.get("model"),list):
            values={abs(v):v>0 for v in payload["model"]}
            cert=all(any(values.get(abs(v))==(v>0) for v in clause)
                     for clause in old.clauses_for_proof(src))
            verified=verified and cert
        return dict(status=status,seconds=round(elapsed,6),route=route,
                    correct=verified,proof_valid=cert,exit=proc.returncode,
                    stderr=proc.stderr[-180:])
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",seconds=cap,route="timeout",
                    correct=False,proof_valid=None,exit=-1,stderr="")

def run(a):
    configure()
    old.attempt=attempt
    old.benchmark(a)

def aggregate(a):
    inp=Path(a.inputs)
    spec=json.loads((inp/"manifest.json").read_text())
    rows=[];models=set();bins=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r26-shard-{shard}"
        md=json.loads((folder/"metadata.json").read_text())
        assert md["protocol"]==PROTO and md["shard"]==shard
        assert md["manifest_sha256"]==old.digest(inp/"manifest.json")
        models.add(md["cpu_model"]);bins.add(json.dumps(md["binaries"],sort_keys=True))
        part=json.loads((folder/"rows.json").read_text())
        assert [r["case"]["sha256"] for r in part]==[
            x["sha256"] for x in spec["cases"][shard::SHARDS]]
        rows.extend(part)
    # Parallel GitHub runners may have different CPU models. Paired trials\n    # within each shard share one CPU; record all observed CPU models.\n    assert len(rows)==53, f"Missing rows: {len(rows)} / 53"\n    assert len(models)>=1, "Missing hardware metadata"\n    assert len(bins)==1, f"Binary drift among shards: {len(bins)} SHA sets"
    report={}
    categories=["ALL","xor_gf2_new","xor4_new","xor6_new",
                "polynomial_gbd_original","official_2025_algebra_control"]
    for family in categories:
        subset=[x for x in rows if family=="ALL" or x["case"]["family"]==family]
        stats={}
        for mode in MODES:
            par2=[];medians=[];solved=0;timeouts=0;routes=Counter()
            for item in subset:
                rr=[x for x in item["trials"] if x["mode"]==mode]
                assert len(rr)==REPS
                assert all(x["status"]=="TIMEOUT" or x["correct"] for x in rr)
                costs=[2*CAP if x["status"]=="TIMEOUT" else x["seconds"] for x in rr]
                medians.append(statistics.median(costs));par2+=costs
                solved+=int(all(x["correct"] for x in rr))
                timeouts+=sum(x["status"]=="TIMEOUT" for x in rr)
                routes.update(x["route"] for x in rr)
            stats[mode]=dict(solved=solved,total=len(subset),
                             sum_median_PAR2_s=round(sum(medians),6),
                             median_PAR2_s=round(statistics.median(medians),6) if medians else None,
                             timeout_attempts=timeouts,routes=dict(routes))
        stats["ratio_kissat_over_r26"]=round(
           stats["Kissat404"]["sum_median_PAR2_s"]/
           max(stats["R26_native"]["sum_median_PAR2_s"],1e-9),5)
        report[family]=stats
    best=[]
    for item in rows:
        d={}
        for mode in MODES:
            rr=[x for x in item["trials"] if x["mode"]==mode]
            d[mode]=statistics.median(2*CAP if x["status"]=="TIMEOUT"
                                     else x["seconds"] for x in rr)
        best.append(dict(family=item["case"]["family"],case=item["case"]["id"],
                         R26_PAR2=d["R26_native"],Kissat_PAR2=d["Kissat404"],
                         ratio=round(d["Kissat404"]/max(d["R26_native"],1e-9),4)))
    best.sort(key=lambda x:x["ratio"],reverse=True)
    data=dict(protocol=PROTO,manifest_sha256=old.digest(inp/"manifest.json"),
              hardware=sorted(models),binary_sha256=json.loads(next(iter(bins))),
              summary=report,top_speedups=best[:12],worst_regressions=best[-12:],
              all_rows=rows)
    old.save(a.out,data)
    lines=["# DRNAS R26 Native XOR/Algebra Cup","53 fixed CNFs, 2 paired repeats, 10s cutoff, PAR2 timeout=20s, native selector startup included.",
           "**Local competition-style simulation; not official SAT Competition ranking**.",""]
    for family,v in report.items():
        lines+=["## "+family,
                "| Solver | Solved | Sum median PAR2 (s) | Timeouts |",
                "|---|---:|---:|---:|"]
        for m in MODES:
            x=v[m]
            lines.append(f'| {m} | {x["solved"]}/{x["total"]} | {x["sum_median_PAR2_s"]:.6f} | {x["timeout_attempts"]} |')
        lines+=[f'**Kissat / R26 native: {v["ratio_kissat_over_r26"]}x**',""]
    lines+=["## Strongest R26 gains",
            "| Case | Category | R26 PAR2 | Kissat PAR2 | ratio |",
            "|---|---|---:|---:|---:|"]
    for x in best[:10]:
        lines.append(f'| {x["case"]} | {x["family"]} | {x["R26_PAR2"]:.4f} | {x["Kissat_PAR2"]:.4f} | {x["ratio"]:.2f}x |')
    lines+=["","## Worst R26 regressions","| Case | Category | R26 PAR2 | Kissat PAR2 | ratio |","|---|---|---:|---:|---:|"]
    for x in reversed(best[-10:]):
        lines.append(f'| {x["case"]} | {x["family"]} | {x["R26_PAR2"]:.4f} | {x["Kissat_PAR2"]:.4f} | {x["ratio"]:.2f}x |')
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)

def main():
    p=argparse.ArgumentParser()
    sp=p.add_subparsers(dest="cmd",required=True)
    c=sp.add_parser("extend")
    c.add_argument("--inputs",required=True);c.add_argument("--pinned",required=True)
    c=sp.add_parser("run")
    for s in ("inputs","bin","outdir"):c.add_argument("--"+s,required=True)
    c.add_argument("--shard",type=int,required=True)
    c.add_argument("--timeout",type=float,default=CAP)
    c.add_argument("--repeats",type=int,default=REPS)
    c=sp.add_parser("aggregate")
    for s in ("inputs","combined","out","md"):c.add_argument("--"+s,required=True)
    a=p.parse_args()
    if a.cmd=="extend":extend(a)
    elif a.cmd=="run":run(a)
    else:aggregate(a)
if __name__=="__main__":main()
