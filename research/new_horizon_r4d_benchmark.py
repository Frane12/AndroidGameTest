#!/usr/bin/env python3
"""New Horizon R4d: suffix-veto on the SAME R4c SHA corpus.

72 exact R4c original formulas + 8 new middle-disproof controls,
4 reps, 5 arms => 1600 SHA-paired trials. NOT blind external original SAT.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random
import new_horizon_r4d as r4d
import new_horizon_r4c as r4c

ROOT=pathlib.Path("new_horizon_r4d")
FROZEN=ROOT/"frozen"
OLD=ROOT/"source/new_horizon_r4c/frozen"
SOURCE_SHA="c8931d34ef876bd2ebabdda965492801142596412d0dee7b7e84f6d317e598f3"
PROTO="DRNAS_R4D_80x4x5_TAIL_VETO_SHA_PAIRS_v1"
OLD_COUNT=72
MIDDLE=8
N=OLD_COUNT+MIDDLE
REPS=4
SHARDS=4
POLICIES=("clean","pure_only","r4b","r4c","r4d")

def need(ok,msg):
    if not ok:raise AssertionError("NH_R4D_AUDIT_FAIL_CLOSED "+str(msg))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(pathlib.Path(path).read_text())
def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def dimacs(n,clauses):
    return f"p cnf {n} {len(clauses)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in clauses)
def middle_case(i):
    n=128+i
    clauses=[(1,)]+[(-j,j+1) for j in range(1,n)]
    # Source-wide 2SAT false, but a last-384-byte peek should miss it.
    clauses.insert(60+i%4,(1,2,3))
    clauses.append((-1,1)) # tautological terminal 2CNF for safe SAT status
    return n,clauses,"SAT"

def selftest():
    r4d.selftest()
    for i in range(MIDDLE):
        n,cs,expected=middle_case(i)
        need(not r4d.r2.is_2cnf(cs),"middle source accidentally 2SAT")
        with __import__("tempfile").TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/"t.cnf"
            p.write_text(dimacs(n,cs))
            ev=r4d.source_evidence(p)
            need(ev["route"]=="clean","middle source wrongly accepted")
    print("NH_R4D_SELFTEST_PASS",MIDDLE,flush=True)

def freeze():
    need(sha(OLD/"manifest.json")==SOURCE_SHA,"R4c original SHA mismatch")
    previous=load(OLD/"manifest.json")
    need(len(previous["cases"])==OLD_COUNT,"R4c source count drift")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in previous["cases"]:
        p=OLD/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"R4c original source drift")
        id="original-"+c["id"]
        dst=FROZEN/(id+".cnf")
        dst.write_bytes(p.read_bytes())
        cases.append(dict(id=id,sha256=sha(dst),family=c["family"],
             cap_s=c["cap_s"],expected=c["expected"],from_sha=c["sha256"]))
    for i in range(MIDDLE):
        n,cs,expected=middle_case(i)
        id="new_middle_clause-"+str(i)
        p=FROZEN/(id+".cnf")
        p.write_text(dimacs(n,cs))
        cases.append(dict(id=id,sha256=sha(p),family="middle_disproof",
             cap_s=3.0,expected=expected))
    need(len(cases)==N and len({c["sha256"] for c in cases})==N,
         "source duplicate or missing")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
        R4c_manifest_sha256=SOURCE_SHA,not_blind=True,
        exact_source_hash=True,same_native_binary=True,
        policies=POLICIES,repetitions=REPS))
    verify()
    print("NH_R4D_FREEZE_PASS",json.dumps(
         dict(formulas=N,manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    x=load(FROZEN/"manifest.json")
    need(x["protocol"]==PROTO and len(x["cases"])==N,"manifest drift")
    for c in x["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "sha source mismatch "+c["id"])
    return x["cases"]

def trial(c,policy,rep,binary):
    p=FROZEN/(c["id"]+".cnf")
    need(sha(p)==c["sha256"],"source SHA mutated before solver")
    x=r4d.run_one(p,binary,c["cap_s"],policy,
        ROOT/"scratch"/(c["sha256"][:16]+f"-{policy}-{rep}"))
    status=x["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"invalid answer")
    if status!="TIMEOUT":need(status==c["expected"],"SAT/UNSAT wrong on original")
    ev=x.get("r4d_evidence") or x.get("r4c_evidence") or x.get("r4b_evidence") or {}
    elapsed=round(x["elapsed"],6)
    return dict(id=c["id"],sha256=c["sha256"],family=c["family"],
         policy=policy,rep=rep,status=status,elapsed_s=elapsed,
         par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
         cap_s=c["cap_s"],route=x["route"],proof=x["proof"],reason=x["reason"],
         preview_s=round(ev.get("scan_s",0),6),scanned=ev.get("scanned"))

def shard(idx,binary):
    cases=verify()
    need(0<=idx<SHARDS and pathlib.Path(binary).is_file(),"bad shard or binary")
    rows=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            modes=list(POLICIES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                z=trial(c,mode,rep,binary)
                rows.append(z)
                save(ROOT/f"shard-{idx}.json",rows)
                print("NH_R4D_TRIAL",json.dumps({k:z[k] for k in
                     ("id","policy","status","elapsed_s","route","scanned")}),flush=True)
    need(len(rows)==len(cases[idx::SHARDS])*REPS*len(POLICIES),"shard count")
    print("NH_R4D_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cases=verify()
    bysha={c["sha256"]:c for c in cases}
    rows=[]
    for idx in range(SHARDS):
        v=load(ROOT/f"shard-{idx}.json")
        need(len(v)==len(cases[idx::SHARDS])*REPS*len(POLICIES),
             "incomplete shard "+str(idx))
        rows+=v
    need(len(rows)==N*REPS*len(POLICIES),"missing 1600 rows")
    paired=collections.defaultdict(list)
    for r in rows:
        c=bysha.get(r["sha256"])
        need(c is not None and r["id"]==c["id"],"wrong SHA / ID")
        target=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(target-r["par2_s"])<.00001,"PAR2 mismatched")
        paired[(r["sha256"],r["rep"])].append(r)
    for c in cases:
        for rep in range(REPS):
            z=paired[c["sha256"],rep]
            need(len(z)==len(POLICIES) and {r["policy"] for r in z}==set(POLICIES),
                 "source/rep policies incomplete")
            need(len({r["status"] for r in z if r["status"]!="TIMEOUT"})<=1,
                 "contradictory SAT/UNSAT across arms")
    groups={"all":cases}
    for family in set(c["family"] for c in cases):
        groups[family]=[c for c in cases if c["family"]==family]
    summary={}
    for label,grp in groups.items():
        shas={c["sha256"] for c in grp}
        summary[label]={}
        for policy in POLICIES:
            z=[r for r in rows if r["policy"]==policy and r["sha256"] in shas]
            summary[label][policy]=dict(n=len(z),
                solved=sum(r["status"]!="TIMEOUT" for r in z),
                par2_s=round(sum(r["par2_s"] for r in z),6),
                elapsed_s=round(sum(r["elapsed_s"] for r in z),6),
                preview_s=round(sum(r["preview_s"] for r in z),6),
                routes=dict(collections.Counter(r["route"] for r in z)),
                zero_clause_abstentions=sum(r["scanned"]==0 for r in z))
    save(ROOT/"report.json",dict(protocol=PROTO,
         status="NH_R4D_AUDIT_PASS_NOT_BLIND",
         sources=N,trials=len(rows),source_SHA_original_verified=True,
         all_methods_same_native=True,all_solved_SAT_witnesses_verified=True,
         native_UNSAT_independent_LRAT_absent=True,
         known_generator_families=True,summary=summary))
    save(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    md=["# New Horizon SAT R4d — bounded suffix veto evidence","",
       f"{N} SHA-frozen sources, {REPS} repeats, {len(POLICIES)} arms, {len(rows)} runs.",
       "All source/check timings included; no independent blind industrial SAT.","",
       "| Cohort | Mode | Solved | PAR2 seconds |",
       "|---|---|---:|---:|"]
    for g,v in summary.items():
        for mode,x in v.items():
            md.append(f"| {g} | {mode} | {x['solved']}/{x['n']} | {x['par2_s']:.6f} |")
    md+=["","Source tail is negative observation, not a positive certificate.",
         "Full source must still be verified before any special solve.",
         "Native UNSAT has no independently checked LRAT."]
    (ROOT/"summary.md").write_text("\n".join(md)+"\n")
    print("NH_R4D_FINAL",json.dumps({k:summary[k] for k in (
        "all","sparse_2sat","sparse_late","dense_2sat","dense_late",
        "pure_xor","middle_disproof")},sort_keys=True),flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("cmd",choices=("selftest","freeze","verify","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--binary",default="new_horizon_r4d/r190-driver")
    x=a.parse_args()
    if x.cmd=="selftest":selftest()
    elif x.cmd=="freeze":freeze()
    elif x.cmd=="verify":print("NH_R4D_VERIFY_PASS",len(verify()))
    elif x.cmd=="shard":shard(x.shard,pathlib.Path(x.binary))
    else:audit()
