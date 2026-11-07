#!/usr/bin/env python3
"""DRNAS New Horizon R4c: density-veto stress benchmark.

72 fresh seed formulas, 4 repeats, 4 methods, 1152 SHA-paired runs.
All generator families are known, NOT blind external industrial holdout.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random,statistics
import new_horizon_r4c as r4c
import new_horizon_r4b as r4b
import new_horizon_benchmark as gxor
import new_horizon_r2_benchmark as gtwo
import new_horizon_r3_benchmark as ggeneral
import new_horizon_r4_benchmark as glarge

ROOT=pathlib.Path("new_horizon_r4c")
FROZEN=ROOT/"frozen"
PROTO="DRNAS_NH_R4C_DENSITY_VETO_72x4x4_v1"
POLICIES=("clean","pure_only","r4b","r4c")
REPS=4
SHARDS=4
SIZES={"pure_xor":12,"dense_2sat":12,"sparse_2sat":12,
       "sparse_late":12,"dense_late":8,"large_2sat":8,"general_3cnf":8}
TOTAL=sum(SIZES.values())

def need(x,msg):
    if not x:raise AssertionError("NH_R4C_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def cnf(n,clauses):
    return f"p cnf {n} {len(clauses)}\n"+"".join(
      " ".join(map(str,c))+" 0\n" for c in clauses)

def new_example(family,i):
    if family=="pure_xor":
        return gxor.generated_pure(2600+i)
    if family=="dense_2sat":
        return gtwo.generated_two(2600+i)
    if family=="large_2sat":
        return glarge.large_2sat(2600+i)
    if family=="general_3cnf":
        return ggeneral.generate_unknown(260+i)
    if family in ("sparse_2sat","sparse_late","dense_late"):
        n=(96+(i%4)*8 if family!="sparse_late" else 128+(i%4)*8)
        clauses=[(1,)]+[(-j,j+1) for j in range(1,n)]
        if family=="sparse_2sat":
            clauses += [(-1,j) for j in range(2,10)] + [(1,10+i)]
            # Unique source per seed; SAT under all-true, sparse m/n~1.09.
        elif family=="sparse_late":
            clauses += [(1,2,3),(10+i,11+i,12+i)]
            # First n clauses 2CNF, ending disqualifies source-wide family.
        else:
            clauses = clauses*3 + [(1,2,3),(10+i,11+i,12+i)]
            # Dense source with a deceptive final clause still incurs scan.
        return n,clauses,"SAT"
    raise ValueError(family)

def selftest():
    r4c.selftest()
    r4b.selftest()
    with __import__("tempfile").TemporaryDirectory() as tmp:
        root=pathlib.Path(tmp)
        for family,size in SIZES.items():
            for i in range(size):
                n,cs,expected=new_example(family,i)
                need(n>0 and len(cs)>0,"empty source")
                p=root/f"{family}-{i}.cnf"
                p.write_text(cnf(n,cs))
                baseline=r4b.source_evidence(p)
                proposal=r4c.source_evidence(p)
                if family=="pure_xor":
                    need(proposal["route"]=="pure" and baseline["route"]=="pure",
                         "GF2 recognition regression")
                if family=="dense_2sat":
                    need(proposal["route"]=="two_sat" and baseline["route"]=="two_sat",
                         "dense valid 2SAT regression")
                if family=="sparse_2sat":
                    need(baseline["route"]=="two_sat" and proposal["route"]=="clean" and
                         proposal["scanned"]==0,"density veto missed sparse 2SAT")
                if family=="sparse_late":
                    need(proposal["route"]=="clean" and proposal["scanned"]==0,
                         "density veto missed sparse false prefix")
                if family=="dense_late":
                    need(proposal["route"]=="clean" and
                         proposal["scanned"]>=len(cs)-1,
                         "dense false prefix escaped exact disproof")
                if family=="large_2sat":
                    need(baseline["route"]=="clean" and proposal["route"]=="clean",
                         "oversize envelope regression")
                if family in ("dense_2sat","sparse_2sat","large_2sat"):
                    need(r4c.r2.is_2cnf(cs) and
                         r4c.r2.solve_2sat(n,cs)["status"]==expected,
                         "invalid 2SAT expectation")
                if family in ("sparse_late","dense_late"):
                    need(not r4c.r2.is_2cnf(cs),
                         "late clause still in 2SAT")
                if family=="pure_xor":
                    exact,rows,_=r4c.pure.detect_exact(cs)
                    need(exact and r4c.pure.gaussian(rows)["status"]==expected,
                         "incorrect XOR expected")
    print("NH_R4C_SELFTEST_PASS",TOTAL,flush=True)

def freeze():
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family,size in SIZES.items():
        for i in range(size):
            n,cs,expected=new_example(family,i)
            name=f"r4c-{family}-{i}"
            p=FROZEN/(name+".cnf")
            p.write_text(cnf(n,cs))
            cases.append(dict(id=name,family=family,expected=expected,
                 cap_s=(2.0 if family=="general_3cnf" else 3.0),
                 sha256=sha(p)))
    need(len(cases)==TOTAL and len({x["sha256"] for x in cases})==TOTAL,
         "missing cases or duplicate sources")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
        source_content_pinned=True,not_external_blind=True,
        cost_threshold_precommitted_before_trial=True,
        family_not_exposed_to_route=True,
        policies=POLICIES,reps=REPS,shards=SHARDS))
    verify()
    print("NH_R4C_FREEZE_PASS",json.dumps(
         dict(formulas=len(cases),manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    m=read(FROZEN/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==TOTAL,"manifest mismatch")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "source hash mismatch "+c["id"])
    return m["cases"]

def trial(c,policy,rep,binary):
    src=FROZEN/(c["id"]+".cnf")
    need(sha(src)==c["sha256"],"source changed")
    x=r4c.run_one(src,binary,c["cap_s"],policy,
      ROOT/"scratch"/(c["sha256"][:16]+f"-{policy}-{rep}"))
    status=x["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"bad status")
    if status!="TIMEOUT":
        need(status==c["expected"],"SAT answer contradicts exact source expected")
    cost=x.get("r4c_evidence") or x.get("r4b_evidence") or {}
    elapsed=round(x["elapsed"],6)
    return dict(id=c["id"],source_sha256=c["sha256"],
       family=c["family"],policy=policy,rep=rep,
       status=status,elapsed_s=elapsed,
       par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
       cap_s=c["cap_s"],route=x["route"],reason=x["reason"],proof=x["proof"],
       scan_s=round(cost.get("scan_s",0),6),sampled=cost.get("scanned"))

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),
         "bad shard or binary")
    data=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            arms=list(POLICIES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(arms)
            for policy in arms:
                z=trial(c,policy,rep,binary)
                data.append(z)
                save(ROOT/f"shard-{index}.json",data)
                print("NH_R4C_TRIAL",json.dumps({k:z[k] for k in
                    ("id","policy","status","elapsed_s","route","sampled")}),flush=True)
    need(len(data)==len(cases[index::SHARDS])*REPS*len(POLICIES),
         "shard incomplete")
    print("NH_R4C_SHARD_PASS",index,len(data),flush=True)

def audit():
    cases=verify()
    bysha={c["sha256"]:c for c in cases}
    data=[]
    for k in range(SHARDS):
        part=read(ROOT/f"shard-{k}.json")
        need(len(part)==len(cases[k::SHARDS])*REPS*len(POLICIES),
             "missing/incomplete shard "+str(k))
        data.extend(part)
    need(len(data)==TOTAL*REPS*len(POLICIES),
         "wrong number of trials")
    pairs=collections.defaultdict(list)
    for r in data:
        c=bysha.get(r["source_sha256"])
        need(c is not None and r["id"]==c["id"],"source SHA mismatch in row")
        need(abs(r["par2_s"]-(2*r["cap_s"] if r["status"]=="TIMEOUT"
                  else r["elapsed_s"]))<=0.00001,"PAR2 mismatch")
        pairs[r["source_sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            z=pairs[c["sha256"],rep]
            need(len(z)==len(POLICIES) and
                 set(r["policy"] for r in z)==set(POLICIES),"broken arm pairing")
            need(len(set(r["status"] for r in z if r["status"]!="TIMEOUT"))<=1,
                 "opposing successful solver answers")
    groups={"all":cases}
    for name in SIZES:groups[name]=[c for c in cases if c["family"]==name]
    report={}
    for name,subset in groups.items():
        shas={c["sha256"] for c in subset}
        report[name]={}
        for policy in POLICIES:
            z=[r for r in data if r["policy"]==policy and r["source_sha256"] in shas]
            report[name][policy]=dict(n=len(z),
              solved=sum(r["status"]!="TIMEOUT" for r in z),
              par2_s=round(sum(r["par2_s"] for r in z),6),
              elapsed_s=round(sum(r["elapsed_s"] for r in z),6),
              median_elapsed_s=(round(statistics.median(r["elapsed_s"] for r in z),6)
                                if z else None),
              sample_sum=sum(r["sampled"] or 0 for r in z),
              routes=dict(collections.Counter(r["route"] for r in z)))
    outcome=dict(protocol=PROTO,
        status="NH_R4C_AUDIT_SUCCESS_NOT_EXTERNAL_BLIND",
        formulas=TOTAL,trials=len(data),reps=REPS,
        original_sha_pinned=True,all_four_arms_source_paired=True,
        source_verification_exact=True,
        native_UNSAT_no_independent_LRAT=True,
        known_generator_families=True,
        thresholds_chosen_using_prior_development=True,
        summary=report)
    save(ROOT/"report.json",outcome)
    save(ROOT/"trials.json",data)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]))
        w.writeheader();w.writerows(data)
    md=["# DRNAS New Horizon SAT R4c — density veto preregistered test","",
        f"72 fresh generated formulas, 4 repeats, 4 arms, {len(data)} total trials.",
        "Original source and native solver SHA fixed. Not blind external real SAT.","",
        "| Class | Policy | Solved | PAR2 seconds |",
        "|---|---|---:|---:|"]
    for g,vs in report.items():
        for policy,x in vs.items():
            md.append(f"| {g} | {policy} | {x['solved']}/{x['n']} | {x['par2_s']:.6f} |")
    md.extend(["",
       "Threshold is an economics heuristic, never a logical conclusion.",
       "SAT witnesses checked against ORIGINAL source; native UNSAT lacks independent LRAT.",
       "Microsecond process and parser timing sensitive to runner noise."])
    (ROOT/"summary.md").write_text("\n".join(md)+"\n")
    print("NH_R4C_FINAL",json.dumps({k:report[k] for k in
       ("all","pure_xor","dense_2sat","sparse_2sat","sparse_late","dense_late")},
       sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="new_horizon_r4c/r190-driver")
    x=p.parse_args()
    if x.command=="selftest":selftest()
    elif x.command=="freeze":freeze()
    elif x.command=="verify":print("NH_R4C_VERIFY_PASS",len(verify()))
    elif x.command=="shard":shard(x.shard,pathlib.Path(x.binary))
    elif x.command=="audit":audit()
