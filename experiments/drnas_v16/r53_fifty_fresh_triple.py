#!/usr/bin/env python3
"""R53 preregistered 50 official SATComp2026 CNFs, 3 paired repeats.
Unseen = excluded from known R32p/R32r/R52/R32u registries, NOT all history.
Sample IDs before any timing, without selecting via any solver results.
"""
import argparse, collections, hashlib, json, os, random, re, statistics
from pathlib import Path
import r52_prospective_2026_toprefs as prior
r32p=prior.r32p
r32r=prior.r32r
PROTO="DRNAS-R53-50-FRESH-TRIPLE-20261103-v1"
SALT="DRNAS-R53-PREREGISTERED-ID-ORDER-20261103"
MODES=("kissat_pinned","drnas_r49_gate","cadical_3_0_1")
TARGET=50
REPS=3
SHARDS=12
CAP=40.0
MAX_TRIES=350
prior.CAP=CAP
def check(v,msg):
    if not v: raise RuntimeError("R53_AUDIT_FAIL "+str(msg))
def digest(path): return prior.digest(path)
def stamp(s): return hashlib.sha256((SALT+":"+s).encode()).hexdigest()
def write(path,obj): Path(path).write_text(json.dumps(obj,indent=2)+"\n")
def load(path): return json.loads(Path(path).read_text())
def freeze(a):
    d=Path(a.out);d.mkdir(parents=True,exist_ok=True)
    original=prior.fetch_bytes(prior.URI,100000).decode().strip().splitlines()
    ids=[x.strip().rsplit("/",1)[-1] for x in original]
    check(len(ids)==400 and len(set(ids))==400,"official 400 source registry changed")
    known={h for _,h in r32p.PINS}|{h for _,h in r32r.PINS}
    check(len(known)==37,"prior exclusion registry changed")
    manifest_proofs=[]
    for path in sorted(Path(a.prior).rglob("manifest.json")):
        blob=path.read_text()
        found=set(re.findall(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])",blob))&set(ids)
        known|=found
        manifest_proofs.append(dict(path=str(path),sha256=digest(path),
                                    recognized_official_ids=len(found)))
    check(len(manifest_proofs)>=2,"must download R52 and R32u prior manifests")
    ordering=sorted(set(ids)-known,key=stamp)
    check(len(ordering)>=TARGET,"not enough unused IDs")
    r32p.CNF_LIMIT=48*1024*1024
    cases=[];trace=[]
    for g in ordering[:MAX_TRIES]:
        t=dict(gbd=g,index=ids.index(g))
        try:
            raw,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+g,28*1024*1024,seconds=65)
            cnf,compression=r32p.decode(raw)
            check(len(cnf)<=48*1024*1024,"decoded instance too large")
            n,m=r32p.parse_dimacs_metadata(cnf)
            name=g+".cnf";path=d/name;path.write_bytes(cnf)
            cases.append(dict(gbd=g,name=name,sha256=digest(path),
                bytes=len(cnf),variables=n,clauses=m,
                compressed_bytes=len(raw),compression=compression,
                source_url="https://benchmark-database.de/file/"+g,
                source_redirect=redirect,index=ids.index(g)))
            t.update(state="FROZEN",size=len(cnf))
        except Exception as exc:
            (d/(g+".cnf")).unlink(missing_ok=True)
            t.update(state="SKIPPED",reason=str(exc)[:180])
        trace.append(t)
        print("R53_FREEZE",json.dumps(t),flush=True)
        if len(cases)==TARGET: break
    check(len(cases)==TARGET,"could not freeze exactly 50 eligible originals")
    check(not(set(c["gbd"] for c in cases)&known),"prior-case overlap")
    write(d/"manifest.json",dict(protocol=PROTO,
        official_registry_sha256=hashlib.sha256("\n".join(original).encode()).hexdigest(),
        selection="first 50 size-eligible salted SHA256 official instance IDs",
        selection_uses_solver_scores=False,salt=SALT,
        not_globally_unseen_guaranteed=True,
        exclusion_proofs=manifest_proofs,excluded_known_gbd=sorted(known),
        cases=cases,attempt_log=trace,cap_s=CAP,reps=REPS,modes=MODES))
    (d/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["name"]+"\n" for c in cases))
    print("R53_FREEZE_PASS",len(cases),len(trace),flush=True)
def measure(a):
    m=load(Path(a.sources)/"manifest.json")
    check(m["protocol"]==PROTO and len(m["cases"])==TARGET,"frozen cohort")
    shard=int(a.shard);check(shard in range(SHARDS),"shard")
    bins={"kissat_pinned":Path(a.kissat_pinned).resolve(),
          "cadical_3_0_1":Path(a.cadical_3_0_1).resolve()}
    bins["drnas_r49_gate"]=bins["kissat_pinned"]
    check(all(p.is_file() for p in bins.values()),"missing pinned binaries")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    write(out/"meta.json",dict(protocol=PROTO,shard=shard,
         manifest_sha256=digest(Path(a.sources)/"manifest.json"),
         binary_sha256={k:digest(p) for k,p in bins.items()},
         run_sha=os.getenv("GITHUB_SHA","local"),
         runner=os.getenv("RUNNER_NAME","local")))
    rows=[]
    for case in m["cases"][shard::SHARDS]:
        src=Path(a.sources)/case["name"]
        check(digest(src)==case["sha256"],"changed source")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(stamp(case["sha256"]+":"+str(rep)),16)).shuffle(modes)
            for mode in modes:
                result=prior.trial(src,mode,bins)
                row=dict(gbd=case["gbd"],sha256=case["sha256"],
                         repetition=rep+1,**result)
                rows.append(row)
                print("R53_TRIAL",case["gbd"],rep+1,mode,row["answer"],
                    row["wall_s"],row["par2_s"],flush=True)
                write(out/"rows.json",rows)
    check(len(rows)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
          "incomplete shard")
def audit(a):
    root=Path(a.sources);m=load(root/"manifest.json")
    check(m["protocol"]==PROTO and len(m["cases"])==TARGET,"wrong cohort")
    check(not(set(x["gbd"] for x in m["cases"])&
                set(m["excluded_known_gbd"])),"prior overlap")
    rows=[];seen=set();binhash=collections.defaultdict(set)
    for shard in range(SHARDS):
        f=Path(a.combined)/("r53-shard-"+str(shard))/"results"
        meta=load(f/"meta.json")
        check(meta["shard"]==shard and meta["manifest_sha256"]==digest(
              root/"manifest.json"),"source manifest mismatch")
        for k,v in meta["binary_sha256"].items():binhash[k].add(v)
        for item in load(f/"rows.json"):
            key=(item["gbd"],item["mode"],item["repetition"])
            check(key not in seen,"duplicate trial")
            seen.add(key);rows.append(item)
    check(len(rows)==TARGET*REPS*len(MODES) and
          all(len(s)==1 for s in binhash.values()),
          "incomplete 450 trials or binary mismatch")
    per={}
    for case in m["cases"]:
        g=case["gbd"];rr=[r for r in rows if r["gbd"]==g]
        check(len(rr)==REPS*len(MODES) and
              all(r["sha256"]==case["sha256"] for r in rr),"case mismatch")
        check(len({r["answer"] for r in rr if r["answer"]!="TIMEOUT"})<=1,
              "inconsistent SAT versus UNSAT")
        per[g]={}
        for mode in MODES:
            sub=[r for r in rr if r["mode"]==mode]
            check(len(sub)==REPS and
                  {r["repetition"] for r in sub}=={1,2,3},
                  "repetitions missing")
            per[g][mode]=dict(
                solved=sum(r["answer"]!="TIMEOUT" for r in sub),
                median_par2=statistics.median(r["par2_s"] for r in sub),
                sum_par2=sum(r["par2_s"] for r in sub),
                wall_s=[r["wall_s"] for r in sub],
                answers=[r["answer"] for r in sub])
    summary={}
    for mode in MODES:
        rr=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(trials=len(rr),
            solved_trials=sum(r["answer"]!="TIMEOUT" for r in rr),
            fully_solved_cases=sum(per[g][mode]["solved"]==3 for g in per),
            at_least_once_solved_cases=sum(per[g][mode]["solved"]>0 for g in per),
            timeouts=sum(r["answer"]=="TIMEOUT" for r in rr),
            par2_sum_s=round(sum(r["par2_s"] for r in rr),6),
            gates=sum(bool(r["r49_gate"]) for r in rr))
    base=summary["kissat_pinned"]["par2_sum_s"]
    for v in summary.values():
        v["gain_over_kissat_pct"]=round(100*(1-v["par2_sum_s"]/base),4)
    gen=random.Random(20261103);ids=list(per);ci={}
    for reference in ("kissat_pinned","cadical_3_0_1"):
        boot=[]
        for _ in range(2000):
            sample=[ids[gen.randrange(TARGET)] for j in ids]
            den=sum(per[g][reference]["sum_par2"] for g in sample)
            num=sum(per[g]["drnas_r49_gate"]["sum_par2"] for g in sample)
            boot.append(100*(1-num/den))
        boot.sort()
        ci[reference]=[round(boot[49],3),round(boot[1950],3)]
    report=dict(protocol=PROTO,summary=summary,cluster_bootstrap_CI95_pct=ci,
        per_instance=per,rows=rows,manifest=m,
        binary_sha256={k:next(iter(v)) for k,v in binhash.items()},
        limitation="not globally unseen; not official competition; UNSAT without separate LRAT")
    write(a.out,report)
    md=["# DRNAS R53 — 50 known-registry-unseen official 2026 cases x 3 repeats",
      "Sample selected by salted hash, without using solver results. 40s cap, PAR-2 timeout 80s.",
      "Not an official competition score or guarantee of globally never-seen problems.",
      "","| Solver | Solved trials | All repeats solved | PAR-2 total (s) | Gain vs Kissat |",
      "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        q=summary[mode]
        md.append(f'| {mode} | {q["solved_trials"]}/150 | {q["fully_solved_cases"]}/50 | {q["par2_sum_s"]:.3f} | {q["gain_over_kissat_pct"]:+.2f}% |')
    md+=["",f'Bootstrap 95% vs Kissat: {ci["kissat_pinned"]}; vs CaDiCaL: {ci["cadical_3_0_1"]}.',
      "","## Per-formula median PAR-2 seconds over 3 runs",
      "| Instance ID prefix | Kissat | DRNAS R49 | CaDiCaL | DRNAS solved |",
      "|---|---:|---:|---:|---:|"]
    for c in m["cases"]:
        p=per[c["gbd"]]
        md.append("| "+c["gbd"][:12]+" | "+" | ".join(
          f'{p[k]["median_par2"]:.3f}' for k in MODES)+
          f' | {p["drnas_r49_gate"]["solved"]}/3 |')
    md+=["","Full GBD IDs, exact individual times and source SHA256 in JSON."]
    Path(a.markdown).write_text("\n".join(md)+"\n")
    print("R53_FINAL_AUDIT_PASS",json.dumps(summary),flush=True)
def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("freeze");f.add_argument("--out",required=True);f.add_argument("--prior",required=True)
    t=sub.add_parser("measure")
    for n in ("sources","shard","out","kissat_pinned","cadical_3_0_1"):
        t.add_argument("--"+n,required=True)
    q=sub.add_parser("audit")
    for n in ("sources","combined","out","markdown"):
        q.add_argument("--"+n,required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a)
    elif a.cmd=="measure":measure(a)
    else:audit(a)
if __name__=="__main__":main()
