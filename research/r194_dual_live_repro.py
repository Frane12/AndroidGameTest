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

ROOT=pathlib.Path("r194")
FROZEN=ROOT/"frozen"
SOURCE_SHA="9eebc6fc1e8ad3006fc3ecc8b451e1e57d3087932190ba5a91fd60aabf278658"
PROTO="DRNAS-R194-REPLAY-EXTERNAL-SAT-12-SEED-2-ORDER-v1"
TARGET_ID="20ca08f58828637815d93f46ef60b517"
SEEDS=(0,1,3,7,11,17,29,43,61,83,127,191)
MODES=("default","sat","dual_keep_default","dual_keep_sat")
SHARDS=8
REPS=24

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

def native(binary,source,cap,mode,order,seed):
    started=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),str(source),str(cap),
                          str(mode),str(order),str(seed)],capture_output=True,
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


def selected():
    cases=verify()
    c=[x for x in cases if x["id"]==TARGET_ID]
    need(len(c)==1 and c[0]["cohort"]=="reused_external_original",
         "R193 positive source absent or no longer external")
    need(cap_for(c[0])==30.0,"R193 external cap drift")
    return c[0]

def selftest():
    need(len(SEEDS)==12 and len(set(SEEDS))==12,"seed selection drift")
    need(MODES==("default","sat","dual_keep_default","dual_keep_sat"),
         "reproduction arm drift")
    need(REPS==24 and SHARDS==8,"reproduction matrix drift")
    print("R194_SELFTEST_PASS",flush=True)

def trial(case,mode,seed,order,binary):
    path=FROZEN/(case["id"]+".cnf")
    need(sha(path)==case["sha256"],"original frozen CNF SHA drift")
    cap=30.0
    started=time.perf_counter()
    x=native(binary,path,cap,mode,order,seed)
    elapsed=time.perf_counter()-started
    status=x["status"]
    if elapsed>=cap:status="TIMEOUT"
    need(status in ("SAT","TIMEOUT"),
         "R193 positive known SAT source returned UNSAT")
    proof="CAPPED"
    model_hash=None
    if status=="SAT":
        _,original=helpers.gf.dimacs(path)
        helpers.gf.sat_check(original,x["model"])
        # SAT model is always checked against the immutable ORIGINAL, not
        # preprocessing output; do not require identical SAT assignments.
        model_hash=hashlib.sha256(json.dumps(x["model"],sort_keys=True).encode()).hexdigest()
        proof="SAT_WITNESS_VERIFIED_ON_ORIGINAL_SHA"
    return dict(id=case["id"],source_sha256=case["sha256"],
       mode=mode,seed=seed,order=order,cap_s=cap,
       status=status,elapsed_s=round(elapsed,6),
       par2_s=round(2*cap if status=="TIMEOUT" else elapsed,6),
       proof=proof,model_sha256=model_hash,
       choice=x["choice"],reason=x["reason"],
       pilot_s=round(sum(p["elapsed_s"] for p in x["pilots"]),6),
       preserves_winning_solver=x["preserved"],
       **x["stats"])

def shard(idx,binary):
    case=selected()
    need(0<=idx<SHARDS and binary.is_file(),"invalid shard/binary")
    pin=read(ROOT/"pin.json")
    need(sha(binary)==pin["binary_sha256"],"R194 patched native binary SHA drift")
    need(pin["source_sha256"]==case["sha256"],"R194 source pin drift")
    out=[]
    for i,seed in enumerate(SEEDS):
        if i%SHARDS!=idx:continue
        for order in (0,1):
            arms=list(MODES)
            random.Random(PROTO+case["sha256"]+str(seed)+str(order)).shuffle(arms)
            for mode in arms:
                r=trial(case,mode,seed,order,binary)
                out.append(r)
                save(ROOT/f"shard-{idx}.json",out)
                print("R194_TRIAL",json.dumps({k:r[k] for k in
                   ("id","source_sha256","mode","seed","order","status",
                    "elapsed_s","par2_s","proof","pilot_s","choice")},sort_keys=True),
                    flush=True)
    need(len(out)==sum(i%SHARDS==idx for i in range(len(SEEDS)))*2*len(MODES),
         "incomplete seed/order shard")
    print("R194_SHARD_PASS",idx,len(out),flush=True)

def audit():
    case=selected()
    pin=read(ROOT/"pin.json")
    need(sha(ROOT/"r194-driver")==pin["binary_sha256"],"audit executable drift")
    rows=[];seen=set()
    for idx in range(SHARDS):
        subset=read(ROOT/f"shard-{idx}.json")
        need(len(subset)==sum(i%SHARDS==idx for i in range(len(SEEDS)))*2*len(MODES),
             "missing shard records")
        for r in subset:
            key=(r["seed"],r["order"],r["mode"])
            need(key not in seen,"duplicate seed/order/mode")
            seen.add(key)
            need(r["id"]==case["id"] and r["source_sha256"]==case["sha256"],
                 "paired original CNF mismatch")
            need(r["seed"] in SEEDS and r["order"] in (0,1) and r["mode"] in MODES,
                 "unregistered experiment")
            need(r["status"] in ("SAT","TIMEOUT"),"wrong SAT answer")
            need(abs(r["par2_s"]-(60 if r["status"]=="TIMEOUT"
                  else r["elapsed_s"]))<1e-5,"PAR-2 drift")
            if r["status"]=="SAT":
                need(r["proof"]=="SAT_WITNESS_VERIFIED_ON_ORIGINAL_SHA"
                     and r["model_sha256"],"missing verified original SAT model")
            rows.append(r)
    need(len(rows)==len(SEEDS)*2*len(MODES)==96,"R194 96 trials not complete")
    outcomes={}
    for mode in MODES:
        a=[r for r in rows if r["mode"]==mode]
        solved=[r["elapsed_s"] for r in a if r["status"]=="SAT"]
        outcomes[mode]=dict(trials=len(a),solved=len(solved),
          par2_s=round(sum(r["par2_s"] for r in a),6),
          mean_solved_s=round(sum(solved)/len(solved),6) if solved else None,
          max_solved_s=max(solved) if solved else None,
          pilot_s=round(sum(r["pilot_s"] for r in a),6))
    pairs=[]
    for seed in SEEDS:
        for order in (0,1):
            a={r["mode"]:r for r in rows if r["seed"]==seed and r["order"]==order}
            need(set(a)==set(MODES),"one paired mode missing")
            pairs.append(dict(seed=seed,order=order,
               default=a["default"]["status"],dual_keep_default=a["dual_keep_default"]["status"],
               default_par2_s=a["default"]["par2_s"],
               dual_par2_s=a["dual_keep_default"]["par2_s"],
               delta_par2_s=round(a["default"]["par2_s"]-
                                  a["dual_keep_default"]["par2_s"],6)))
    report=dict(protocol=PROTO,status="R194_SEED_REPLAY_AUDIT_PASS",
       source_original_id=TARGET_ID,source_sha256=case["sha256"],
       R193_original_manifest_sha256=SOURCE_SHA,original_source_reused_not_blind=True,
       caDiCaL_commit=pin["caDiCaL_commit"],
       separate_seeds=len(SEEDS),seed_order_pairs=len(pairs),attempts=len(rows),
       same_source_sha=True,SAT_witness_original_verified=True,
       independent_LRAT_for_UNSAT=False,not_global_world_benchmark=True,
       methods=outcomes,pairs=pairs,
       speedup_vs_default=round(outcomes["default"]["par2_s"]/
                                outcomes["dual_keep_default"]["par2_s"],6))
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R194 independent-seed replay of ONE R193 external SAT formula\n\n")
        f.write("12 precommitted CaDiCaL seeds, two pilot orders, four matched "
                "modes = 96 trials. Same previously seen R193 original; NOT blind.\n\n")
        f.write("| Mode | SAT/24 | PAR2 seconds | Mean solved seconds |\n"
                "|---|---:|---:|---:|\n")
        for name,v in outcomes.items():
            f.write(f'| {name} | {v["solved"]}/24 | {v["par2_s"]} | {v["mean_solved_s"]} |\n')
        f.write("\nNo claim of external-family speedup without new SHA independent sources.\n")
    print("R194_FINAL",json.dumps({k:report[k] for k in
       ("source_original_id","source_sha256","attempts","methods",
        "speedup_vs_default")},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r194/r194-driver")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="verify":
        c=selected()
        print("R194_SOURCE_VERIFIED",c["id"],c["sha256"],flush=True)
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
