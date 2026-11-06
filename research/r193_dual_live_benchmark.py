#!/usr/bin/env python3
"""DRNAS R193: dual live pilot on EVERY SHA-frozen R190/R191/R192 CNF.

Same native CaDiCaL commit, six matched arms, two reps, 8 shards.
Two live candidates (default / sat) do 2x128 conflicts each, alternating
probe order by SHA and repetition. One is selected and continues in-process,
preserving its learned clauses; the other is discarded.

Two causal controls force retention of default/sat after doing *both* pilots.
No adaptive routing uses benchmark outcomes, family, ID, or expected status.
25 previously seen external originals have 30s caps, vs 15s previously;
therefore do NOT directly compare their PAR2 totals with R192.
The other 77 CNFs retain their R190 caps. NOT a blind real benchmark.
IPASIR Learner callbacks are offers (length), not exact LBD/propagations.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,pathlib,random,re,subprocess,time
import r188_feedback_benchmark as helpers

ROOT=pathlib.Path("r193")
FROZEN=ROOT/"frozen"
SOURCE_SHA="9eebc6fc1e8ad3006fc3ecc8b451e1e57d3087932190ba5a91fd60aabf278658"
PROTO="DRNAS-R193-TWO-LIVE-SOLVER-PAIRED-v1"
MODES=("default","sat","dual_fast","dual_learning",
       "dual_keep_default","dual_keep_sat")
SHARDS=8
REPS=2

def need(condition,reason):
    if not condition:raise RuntimeError("R193_FAIL_CLOSED "+str(reason))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text())
def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def verify():
    need(sha(FROZEN/"manifest.json")==SOURCE_SHA,"R190 original manifest SHA drift")
    d=read(FROZEN/"manifest.json")
    need(d["protocol"]=="DRNAS-R190-GENERAL-CDCL-FROZEN-STRUCTURAL-ROUTER-v1"
         and len(d["cases"])==102,"original source protocol mismatch")
    for case in d["cases"]:
        need(sha(FROZEN/(case["id"]+".cnf"))==case["sha256"],
             "original CNF changed: "+case["id"])
    return d["cases"]

def cap_for(case):
    if case["cohort"]=="reused_external_original":return 30.0
    return float(case["cap_s"])

def native(binary,source,cap,mode,order):
    started=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),str(source),str(cap),
                          str(mode),str(order)],capture_output=True,
                         timeout=cap+3,check=False)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",model={},elapsed=time.perf_counter()-started,
                    pilots=[],choice=None,reason="watchdog",preserved=False,
                    stats={"conflicts":-1,"decisions":-1,"propagations":-1,"learned":-1})
    elapsed=time.perf_counter()-started
    raw=p.stdout.decode(errors="replace")
    err=p.stderr.decode(errors="replace")
    need(p.returncode==0,"native solver error "+err[-900:])
    m=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",raw,re.M)
    need(m is not None,"native missing status: "+raw[-400:])
    status=m[1]
    reports=[]
    regex=(r"^R193_PILOT profile=(default|sat) window=(\d+) "
           r"elapsed_s=([0-9.]+) offers=(\d+) short3=(\d+) "
           r"active_after=(\d+) status=(SAT|UNSAT|UNKNOWN)$")
    for x in re.finditer(regex,raw,re.M):
        row=dict(profile=x[1],window=int(x[2]),elapsed_s=float(x[3]),
                 offers=int(x[4]),short3=int(x[5]),
                 active_after=int(x[6]),status=x[7])
        need(row["short3"]<=row["offers"],"invalid callback count")
        reports.append(row)
    choice=None;reason="baseline";preserved=False
    policy=re.search(r"^R193_DUAL choice=(default|sat) reason=(\w+) "
       r"pilot_default_s=([0-9.]+) pilot_sat_s=([0-9.]+) "
       r"offers_default=(\d+) offers_sat=(\d+) "
       r"short_default=(\d+) short_sat=(\d+) "
       r"completed_default=(\d+) completed_sat=(\d+) preserved=(\d+)$",raw,re.M)
    if mode.startswith("dual_"):
        need(policy is not None,"missing dual policy telemetry")
        choice=policy[1];reason=policy[2];preserved=policy[11]=="1"
        need(1<=len(reports)<=4,"missing/wrong number of dual pilot windows")
        for profile,i in (("default",9),("sat",10)):
            need(sum(p["profile"]==profile for p in reports)==int(policy[i]),
                 "dual window count mismatch")
        need(abs(sum(x["elapsed_s"] for x in reports if x["profile"]=="default")-
                 float(policy[3]))<1e-4,"default pilot duration accounting")
        need(abs(sum(x["elapsed_s"] for x in reports if x["profile"]=="sat")-
                 float(policy[4]))<1e-4,"sat pilot duration accounting")
    else:
        need(not reports and policy is None,"baseline accidentally dual")
    model={}
    if status=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                for lit in map(int,line[2:].split()):
                    if not lit:continue
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "conflicting SAT assignments")
                    model[abs(lit)]=lit>0
    return dict(status=status,model=model,elapsed=elapsed,pilots=reports,
                choice=choice,reason=reason,preserved=preserved,
                stats=helpers.stats(raw))

def selftest():
    need(len(MODES)==6 and len(set(MODES))==6,"six distinct methods")
    need(cap_for(dict(cohort="reused_external_original",cap_s=15))==30,
         "external cap not preregistered")
    need(cap_for(dict(cohort="new_seed_synthetic",cap_s=6))==6,
         "synthetic cap changed")
    print("R193_SELFTEST_PASS",flush=True)

def trial(case,mode,rep,binary):
    path=FROZEN/(case["id"]+".cnf")
    need(sha(path)==case["sha256"],"trial source hash drift")
    cap=cap_for(case)
    # For a given original+repeat, all modes that dual-probe use SAME order.
    order=int(hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest()[:4],16)%2
    start=time.perf_counter()
    x=native(binary,path,cap,mode,order)
    elapsed=time.perf_counter()-start
    status=x["status"]
    if elapsed>=cap:status="TIMEOUT"
    proof=("CAP" if status=="TIMEOUT" else
           "CADICAL_UNSAT_NOT_INDEPENDENTLY_LRAT_VERIFIED")
    if status=="SAT":
        _,original=helpers.gf.dimacs(path)
        helpers.gf.sat_check(original,x["model"])
        proof="SAT_WITNESS_CHECKED_ORIGINAL"
    if case["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==case["expected"],"known class disagrees with solver output")
    return dict(id=case["id"],source_sha256=case["sha256"],
        cohort=case["cohort"],family=case["family"],mode=mode,
        rep=rep,order=order,cap_s=cap,status=status,
        elapsed_s=round(elapsed,6),
        par2_s=round(2*cap if status=="TIMEOUT" else elapsed,6),
        pilot_s=round(sum(p["elapsed_s"] for p in x["pilots"]),6),
        pilots=x["pilots"],choice=x["choice"],reason=x["reason"],
        preserves_winning_solver=x["preserved"],proof=proof,**x["stats"])

def shard(idx,binary):
    cases=verify()
    need(binary.is_file() and 0<=idx<SHARDS,"bad native executable/shard")
    records=[]
    for case in cases[idx::SHARDS]:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+case["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                r=trial(case,arm,rep,binary)
                records.append(r)
                save(ROOT/f"shard-{idx}.json",records)
                print("R193_TRIAL",json.dumps({k:r[k] for k in
                    ("id","cohort","mode","rep","status","elapsed_s",
                     "pilot_s","choice","reason")},sort_keys=True),flush=True)
    need(len(records)==len(cases[idx::SHARDS])*REPS*len(MODES),
         "incomplete paired shard")
    print("R193_SHARD_PASS",idx,len(records),flush=True)

def audit():
    cases=verify();rows=[]
    for idx in range(SHARDS):
        part=read(ROOT/f"shard-{idx}.json")
        need(len(part)==len(cases[idx::SHARDS])*REPS*len(MODES),
             "incomplete frozen paired shard")
        rows.extend(part)
    need(len(rows)==102*2*6==1224,"exactly 1224 trials needed")
    by=collections.defaultdict(list)
    originals={c["sha256"]:c for c in cases}
    for x in rows:
        need(x["source_sha256"] in originals
             and x["id"]==originals[x["source_sha256"]]["id"],
             "formula identity mismatch")
        expect=2*x["cap_s"] if x["status"]=="TIMEOUT" else x["elapsed_s"]
        need(abs(x["par2_s"]-expect)<1e-5,"PAR2 incorrect")
        by[x["source_sha256"],x["rep"]].append(x)
    for case in cases:
        for rep in range(REPS):
            rr=by[case["sha256"],rep]
            need(len(rr)==6 and {r["mode"] for r in rr}==set(MODES),
                 "unpaired original/repetition")
            need(len({r["status"] for r in rr if r["status"]!="TIMEOUT"})<=1,
                 "contradictory SAT/UNSAT statuses")
            need(len({r["order"] for r in rr})==1,"non-matched pilot scheduling")
    cohorts={"all":cases}
    for tag in ("reused_external_original","reused_synthetic_control",
                "new_seed_synthetic"):
        cohorts[tag]=[c for c in cases if c["cohort"]==tag]
    result={}
    for name,subset in cohorts.items():
        modes={}
        for mode in MODES:
            recs=[r for c in subset for rep in range(REPS)
                  for r in by[c["sha256"],rep] if r["mode"]==mode]
            modes[mode]=dict(attempts=len(recs),
                solved=sum(r["status"]!="TIMEOUT" for r in recs),
                SAT=sum(r["status"]=="SAT" for r in recs),
                UNSAT=sum(r["status"]=="UNSAT" for r in recs),
                par2_s=round(sum(r["par2_s"] for r in recs),6),
                pilot_s=round(sum(r["pilot_s"] for r in recs),6),
                choices_sat=sum(r["choice"]=="sat" for r in recs),
                choices_default=sum(r["choice"]=="default" for r in recs),
                pilot_terminal=sum(any(p["status"] in ("SAT","UNSAT")
                        for p in r["pilots"]) for r in recs),
                retained_solver=sum(r["preserves_winning_solver"] for r in recs))
        result[name]=dict(formulas=len(subset),modes=modes,
             speedup_vs_default={k:round(modes["default"]["par2_s"]/
                                            v["par2_s"],6)
                                 for k,v in modes.items() if k!="default"},
             speedup_vs_sat={k:round(modes["sat"]["par2_s"]/
                                        v["par2_s"],6)
                             for k,v in modes.items() if k!="sat"})
    report=dict(protocol=PROTO,status="R193_PAIRED_AUDIT_PASS",
       cases=len(cases),attempts=len(rows),source_manifest_sha256=SOURCE_SHA,
       source_SHA_validated=True,SAT_witness_original_checked=True,
       UNSAT_without_independent_LRAT=True,
       reused_external_sources_not_blind=True,external_cap_extended_to_30_s=True,
       two_candidates_each_dual_on_every_formula=True,
       dual_pilot_alternating_order=True,
       winning_solver_learning_retained=True,
       IPASIR_learner_offers_not_LBD=True,
       groups=result)
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    with (ROOT/"summary.md").open("w") as out:
        out.write("# DRNAS R193: dual live CDCL pilot on every original CNF\n\n")
        out.write("Two SHA-identical CaDiCaL 2.1 solvers, one default and one sat. "
                  "2x128 conflicts each (unless a candidate solves), alternating "
                  "the pilot order. Pilot CPU, extra CNF read, and discarded loser "
                  "are charged. The selected live instance retains its learned "
                  "clauses. Causal controls always retain one fixed profile. "
                  "The 25 reused real original CNFs have a NEW 30s cap, versus "
                  "15s before, and are not a blind holdout. Other 77 caps unchanged. "
                  "SAT original witnesses checked; UNSAT not independently LRAT-checked. "
                  "IPASIR learned offers are not LBD/propagation.\\n\\n")
        out.write("| Cohort | Mode | Solved | PAR2 s | vs default | vs SAT | Chose SAT | Pilot s |\\n"
                  "|---|---|---:|---:|---:|---:|---:|---:|\\n")
        for cohort in ("reused_external_original","reused_synthetic_control",
                       "new_seed_synthetic","all"):
            for mode,s in result[cohort]["modes"].items():
                out.write(f"| {cohort} | {mode} | {s['solved']}/{s['attempts']} "
                          f"| {s['par2_s']} | "
                          f"{result[cohort]['speedup_vs_default'].get(mode,'—')} | "
                          f"{result[cohort]['speedup_vs_sat'].get(mode,'—')} | "
                          f"{s['choices_sat']} | {s['pilot_s']} |\\n")
        out.write("\\nNo promotion without prospective blind real sources, paired cap "
                  "and objective regression checks.\\n")
    print("R193_FINAL",json.dumps({"groups":result},sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--binary",default="r193/r193-driver")
    args=parser.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="verify":print("R193_VERIFY_PASS",len(verify()),flush=True)
    elif args.action=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()
