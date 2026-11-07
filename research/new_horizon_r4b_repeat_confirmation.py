#!/usr/bin/env python3
"""DRNAS New Horizon SAT R4b: prospective repeats on new (non-blind) seeds.

48 distinct SHA-pinned formulas × 5 reps × 4 policies = 960 matched runs.
Separate from R4b development run. New generator seeds do NOT imply a blind
real-world holdout. No family/answer/source identifier is provided to router.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random,statistics
import new_horizon_r4b as sol
import new_horizon_r4_benchmark as old_large
import new_horizon_r2_benchmark as old_two
import new_horizon_r3_benchmark as old_unknown
import new_horizon_benchmark as old_pure

ROOT=pathlib.Path("new_horizon_r4b_confirm")
FROZEN=ROOT/"frozen"
PROTO="NH_R4B_PROSPECTIVE_48x5x4_CONFIRM_20261107_v1"
POLICIES=("clean","r4","pure_only","r4b")
REPS=5
SHARDS=4
GROUPS=("pure_xor","small_2sat","large_2sat","late_disproof","general_3cnf")
SIZES={"pure_xor":12,"small_2sat":12,"large_2sat":8,"late_disproof":8,"general_3cnf":8}
N=sum(SIZES.values())

def need(ok,msg):
    if not ok:raise AssertionError("NH_R4B_CONFIRM_FAIL_CLOSED "+str(msg))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text())
def write(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def dimacs(n,clauses):
    return f"p cnf {n} {len(clauses)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in clauses)

def case(family,i):
    if family=="pure_xor":
        n,clauses,expected=old_pure.generated_pure(1800+i)
    elif family=="small_2sat":
        n,clauses,expected=old_two.generated_two(1800+i)
    elif family=="large_2sat":
        n,clauses,expected=old_large.large_2sat(1800+i)
    elif family=="general_3cnf":
        n,clauses,expected=old_unknown.generate_unknown(150+i)
    elif family=="late_disproof":
        # Source-wide clauses 1..96 are implications. The late clause 97
        # proves the prefix's apparent 2SAT label was never a certificate.
        n=128+i
        clauses=[(1,)]+[(-k,k+1) for k in range(1,96)]
        clauses.extend([(1,2,3),(10+i,11+i,12+i)])
        expected="SAT"
    else:raise ValueError("unknown family")
    return n,clauses,expected

def selftest():
    sol.selftest()
    checked=0
    for family in GROUPS:
        for i in range(SIZES[family]):
            n,c,expected=case(family,i)
            need(n>0 and len(c)>0,"invalid source")
            if family=="pure_xor":
                exact,rows,covered=sol.pure.detect_exact(c)
                need(exact and covered==len(c) and sol.pure.gaussian(rows)["status"]==expected,
                     "pure source wrong SAT label")
            elif family in ("small_2sat","large_2sat"):
                need(sol.r2.is_2cnf(c) and sol.r2.solve_2sat(n,c)["status"]==expected,
                     "source complete 2SAT label")
            elif family=="late_disproof":
                need(not sol.r2.is_2cnf(c) and len(c)>64,
                     "late-disproof test incorrectly constructed")
            elif family=="general_3cnf":
                need(not sol.r2.is_2cnf(c),"general CNF accidentally 2SAT")
            checked+=1
    print("NH_R4B_CONFIRM_SELFTEST_PASS",checked,flush=True)

def freeze():
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in GROUPS:
        for i in range(SIZES[family]):
            n,clauses,expected=case(family,i)
            name=f"confirm-{family}-{i}"
            p=FROZEN/(name+".cnf")
            p.write_text(dimacs(n,clauses))
            cases.append(dict(id=name,source_sha256=sha(p),
                  family=family,expected=expected,cap_s=(2.0 if family=="general_3cnf" else 3.0)))
    need(len(cases)==N and len({c["source_sha256"] for c in cases})==N,
         "duplicated source SHA or case count")
    random.Random(PROTO).shuffle(cases)
    write(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,reps=REPS,
        policies=POLICIES,shards=SHARDS,external_blind=False,
        generator_seed_families_known=True,
        source_file_id_and_expected_not_available_to_selector=True))
    verify()
    print("NH_R4B_CONFIRM_FREEZE_PASS",json.dumps(
       dict(cases=len(cases),manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    data=read(FROZEN/"manifest.json")
    need(data["protocol"]==PROTO and len(data["cases"])==N,"bad manifest")
    for c in data["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["source_sha256"],
             "source SHA mismatch")
    return data["cases"]

def trial(c,policy,rep,binary):
    path=FROZEN/(c["id"]+".cnf")
    need(sha(path)==c["source_sha256"],"original SHA changed during benchmark")
    result=sol.run_one(path,binary,float(c["cap_s"]),policy,
           ROOT/"scratch"/f"{c['source_sha256'][:16]}-{policy}-{rep}")
    status=result["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"invalid solver status")
    if status!="TIMEOUT":
        need(status==c["expected"],"wrong solved answer for source")
    elapsed=round(result["elapsed"],6)
    evidence=result.get("r4b_evidence") or {}
    return dict(id=c["id"],sha256=c["source_sha256"],group=c["family"],
         policy=policy,rep=rep,status=status,elapsed_s=elapsed,
         par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
         cap_s=c["cap_s"],route=result["route"],proof=result["proof"],
         observed_s=round(evidence.get("scan_s",0),6),
         source_complete=evidence.get("complete_source"))

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),"missing native or shard")
    data=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            order=list(POLICIES)
            random.Random(PROTO+c["source_sha256"]+str(rep)).shuffle(order)
            for policy in order:
                row=trial(c,policy,rep,binary)
                data.append(row)
                write(ROOT/f"shard-{index}.json",data)
                print("NH_R4B_CONFIRM_TRIAL",json.dumps({k:row[k] for k in
                    ("id","policy","status","elapsed_s","route")}),flush=True)
    need(len(data)==len(cases[index::SHARDS])*REPS*len(POLICIES),
         "incomplete shard")
    print("NH_R4B_CONFIRM_SHARD_PASS",index,len(data),flush=True)

def audit():
    cases=verify()
    lookup={c["source_sha256"]:c for c in cases}
    rows=[]
    for i in range(SHARDS):
        part=read(ROOT/f"shard-{i}.json")
        need(len(part)==len(cases[i::SHARDS])*REPS*len(POLICIES),
             "missing or incomplete shard")
        rows.extend(part)
    need(len(rows)==N*REPS*len(POLICIES),"wrong total run count")
    paired=collections.defaultdict(list)
    for r in rows:
        c=lookup.get(r["sha256"])
        need(c is not None and c["id"]==r["id"],"wrong source ID/SHA")
        should=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(r["par2_s"]-should)<1e-5,"invalid PAR2")
        paired[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            group=paired[c["source_sha256"],rep]
            need(len(group)==len(POLICIES) and
                 {r["policy"] for r in group}==set(POLICIES),"unpaired run")
            need(len({r["status"] for r in group if r["status"]!="TIMEOUT"})<=1,
                 "contradictory status")
    summary={}
    cohorts=dict(all=cases,**{name:[c for c in cases if c["family"]==name]
                              for name in GROUPS})
    for name,subset in cohorts.items():
        source_sha={c["source_sha256"] for c in subset}
        summary[name]={}
        for policy in POLICIES:
            x=[r for r in rows if r["sha256"] in source_sha and r["policy"]==policy]
            timings=[r["elapsed_s"] for r in x if r["status"]!="TIMEOUT"]
            summary[name][policy]=dict(trials=len(x),
               solved=sum(r["status"]!="TIMEOUT" for r in x),
               par2_s=round(sum(r["par2_s"] for r in x),6),
               elapsed_s=round(sum(r["elapsed_s"] for r in x),6),
               median_s=round(statistics.median(timings),6) if timings else None,
               routes=dict(collections.Counter(r["route"] for r in x)))
    report=dict(protocol=PROTO,status="NH_R4B_REPEAT_CONFIRM_AUDIT_PASS",
        sources=N,attempts=len(rows),repeats=REPS,same_binary=True,
        SHA_original_matched=True,SAT_original_models_checked=True,
        UNSAT_LRAT_not_independently_replayed=True,
        NOT_EXTERNAL_BLIND=True,
        CONFIRMATION_ONLY_NEW_SEEDS_KNOWN_FAMILIES=True,
        submillisecond_noise_may_dominate=True,summary=summary)
    write(ROOT/"report.json",report)
    write(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    md=["# DRNAS R4b early advantage repeat confirmation","",
        f"{N} new seed sources; {REPS} repetitions; {len(rows)} trials; 4 frozen policies.",
        "Not a blind real industrial evaluation.","",
        "| Class | Policy | Solved | PAR2 seconds | Median seconds |",
        "|---|---|---:|---:|---:|"]
    for group,x in summary.items():
        for mode,v in x.items():
            md.append(f"| {group} | {mode} | {v['solved']}/{v['trials']} | "+
                      f"{v['par2_s']:.6f} | {v['median_s']} |")
    (ROOT/"summary.md").write_text("\n".join(md)+"\n")
    print("NH_R4B_CONFIRM_FINAL",json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="new_horizon_r4b_confirm/r190-driver")
    args=p.parse_args()
    if args.command=="selftest":selftest()
    elif args.command=="freeze":freeze()
    elif args.command=="verify":print("NH_R4B_CONFIRM_VERIFY_PASS",len(verify()))
    elif args.command=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()
