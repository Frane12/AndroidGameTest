#!/usr/bin/env python3
"""DRNAS R191: genuine early CDCL pilot on frozen 102 formulas.

Compared arms: clean default, clean sat profile, in-place 256-conflict resume,
bounded probe+sat restart, probe+default shadow, and a telemetry-based chooser.
A native CaDiCaL Learner callback counts short learned clauses, NOT LBD.
The probe is charged to wall clock and always uses the original SHA-pinned CNF.
No family labels, expected SAT/UNSAT labels, or outcomes affect the choice.
25 reused real external formulas all timed out previously at 15s; no blind claims.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,pathlib,random,re,subprocess,time
import r188_feedback_benchmark as old

ROOT=pathlib.Path("r191")
FROZEN=ROOT/"frozen"
SOURCE_SHA="9eebc6fc1e8ad3006fc3ecc8b451e1e57d3087932190ba5a91fd60aabf278658"
PROTO="DRNAS-R191-EARLY-CDCL-CERTIFIED-PILOT-v1"
MODES=("default","sat","probe_continue","probe_sat","probe_shadow","adaptive")
REPS=2
SHARDS=8

def need(ok,msg):
    if not ok:raise RuntimeError("R191_FAIL_CLOSED "+str(msg))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text())
def write(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")

def verify():
    need(sha(FROZEN/"manifest.json")==SOURCE_SHA,
        "R190 manifest SHA does not match pinned original")
    m=read(FROZEN/"manifest.json")
    need(m["protocol"]=="DRNAS-R190-GENERAL-CDCL-FROZEN-STRUCTURAL-ROUTER-v1" and
         len(m["cases"])==102,"manifest protocol/count unexpected")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "original CNF changed: "+c["id"])
    return m["cases"]

def driver(binary,path,seconds,mode):
    start=time.perf_counter()
    if seconds<=0.13:return ("TIMEOUT",0,{},dict(),dict())
    try:
        p=subprocess.run([str(binary.resolve()),str(path),str(seconds),mode],
             capture_output=True,timeout=seconds+3,check=False)
    except subprocess.TimeoutExpired:
        return ("TIMEOUT",time.perf_counter()-start,{},dict(),dict())
    elapsed=time.perf_counter()-start
    raw=p.stdout.decode(errors="replace")
    err=p.stderr.decode(errors="replace")
    need(p.returncode==0,"native solver returned "+str(p.returncode)+": "+err[-500:])
    sm=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",raw,re.M)
    need(sm is not None,"missing native status "+raw[-200:])
    status=sm[1]
    model={}
    if status=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                for lit in map(int,line[2:].split()):
                    if lit==0:continue
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "inconsistent native witness")
                    model[abs(lit)]=lit>0
    stats=old.stats(raw)
    probe={}
    pm=re.search(r"^R191_PROBE (.+)$",raw,re.M)
    if pm:
        for key,val in re.findall(r"(\w+)=([^\s]+)",pm.group(1)):
            if key=="result":probe[key]=val
            elif key in ("seconds","mean_len"):probe[key]=float(val)
            else:probe[key]=int(val)
    return status,elapsed,model,stats,probe

def source_shape(path):
    # Router uses only source CNF header: no instance label or answer.
    with pathlib.Path(path).open("r",encoding="ascii") as f:
        for line in f:
            if line.startswith("p cnf "):
                a=line.split()
                need(len(a)==4,"bad DIMACS header")
                return int(a[2]),int(a[3])
    raise RuntimeError("DIMACS header missing")

def policy(probe):
    """Fixed before benchmarking. No tuning on R191 trial outcomes.

    Short learned clauses indicate promising local propagation, not LBD.
    Significant early variable elimination means default preprocessing may
    already be productive. Never send unknown problems to UNSAT-only mode.
    """
    learned=probe.get("learned",0)
    before=max(1,probe.get("active_before",1))
    reduction=(before-probe.get("active_after",before))/before
    short=probe.get("short3",0)/max(1,learned)
    mean=probe.get("mean_len",100)
    if reduction>=0.15:return "default","strong_preprocess_reduction"
    if learned>=16 and short>=0.35:return "sat","many_short_learned"
    if learned>=32 and mean<=8:return "sat","low_mean_clause_size"
    return "default","uncertain_fallback"

def selftest():
    need(policy(dict(learned=40,short3=20,mean_len=4,
                    active_before=100,active_after=98))[0]=="sat",
         "short-learning telemetry should choose sat")
    need(policy(dict(learned=40,short3=20,mean_len=4,
                    active_before=100,active_after=75))[0]=="default",
         "preprocessing progress should choose default")
    need(policy(dict(learned=0,short3=0,mean_len=0,
                    active_before=10,active_after=10))[0]=="default",
         "uncertainty must fall back conservatively")
    print("R191_SELFTEST_PASS",flush=True)

def trial(c,mode,rep,binary):
    path=FROZEN/(c["id"]+".cnf")
    need(sha(path)==c["sha256"],"frozen CNF differs in trial")
    started=time.perf_counter()
    cap=float(c["cap_s"])
    selected="default";reason="plain";pilot={};pilot_elapsed=0
    status="TIMEOUT";model={}
    stats=dict(conflicts=-1,decisions=-1,propagations=-1,learned=-1)
    if mode in ("default","sat","probe_continue"):
        selected={"default":"default","sat":"sat",
                  "probe_continue":"continue"}[mode]
        status,_,model,stats,pilot=driver(binary,path,
                    max(0.10,cap-(time.perf_counter()-started)),selected)
    else:
        n,m=source_shape(path)
        # The easy-case guard prevents unnecessary probe overhead.
        # Its no-probe choice is tested against both static baselines.
        if n<80 or m<500:
            reason="small_source_no_probe"
            selected="default" if mode=="probe_shadow" else "sat"
        else:
            probe_limit=min(0.55,max(0.28,cap*0.06))
            status,pilot_elapsed,model,stats,pilot=driver(
                        binary,path,probe_limit,"probe")
            need("result" in pilot or status=="TIMEOUT",
                 "native probe telemetry missing")
            if status=="TIMEOUT":
                if mode=="probe_shadow":
                    selected="default";reason="shadow_replay"
                elif mode=="probe_sat":
                    selected="sat";reason="fixed_sat_replay"
                else:
                    selected,reason=policy(pilot)
            else:
                selected="pilot_solved";reason="pilot_terminal"
        if selected!="pilot_solved":
            left=cap-(time.perf_counter()-started)
            if left>0.13:
                status,_,model,stats,_=driver(binary,path,left,selected)
            else:status="TIMEOUT"
    elapsed=time.perf_counter()-started
    if elapsed>=cap:status="TIMEOUT"
    proof="CAP" if status=="TIMEOUT" else "CADICAL_UNSAT_NOT_INDEPENDENT_LRAT"
    if status=="SAT":
        _,clauses=old.gf.dimacs(path)
        old.gf.sat_check(clauses,model)
        proof="SAT_MODEL_VERIFIED_ON_ORIGINAL"
    if status!="TIMEOUT" and c["expected"]!="UNKNOWN":
        need(status==c["expected"],"expected SAT/UNSAT mismatch for "+c["id"])
    return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
       family=c["family"],rep=rep,mode=mode,status=status,
       selected=selected,reason=reason,
       elapsed_s=round(elapsed,6),
       par2_s=round(2*cap if status=="TIMEOUT" else elapsed,6),
       cap_s=cap,pilot_s=round(pilot_elapsed,6),
       probe=pilot,proof=proof,**stats)

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and binary.is_file(),"invalid shard or missing binary")
    rows=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,mode,rep,binary)
                rows.append(r)
                write(ROOT/f"shard-{index}.json",rows)
                print("R191_TRIAL",json.dumps({k:r[k] for k in (
                    "id","cohort","mode","selected","status","elapsed_s",
                    "pilot_s","conflicts")},sort_keys=True),flush=True)
    need(len(rows)==len(cases[index::SHARDS])*REPS*len(MODES),
         "partial benchmark shard")
    print("R191_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=verify()
    chunks=[]
    for i in range(SHARDS):
        part=read(ROOT/f"shard-{i}.json")
        need(len(part)==len(cases[i::SHARDS])*REPS*len(MODES),
             "shard missing some arms")
        chunks+=part
    need(len(chunks)==102*REPS*len(MODES),"expected exactly 1224 attempts")
    by=collections.defaultdict(list)
    original={c["sha256"]:c for c in cases}
    for r in chunks:
        need(r["sha256"] in original and r["id"]==original[r["sha256"]]["id"],
             "source SHA mismatch")
        target=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(r["par2_s"]-target)<1e-5,"PAR2 mismatch")
        by[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            part=by[c["sha256"],rep]
            need(len(part)==len(MODES) and {a["mode"] for a in part}==set(MODES),
                 "incomplete paired source")
            need(len({a["status"] for a in part if a["status"]!="TIMEOUT"})<=1,
                 "solver contradictions in paired arms")
    cohorts={"all":cases}
    for cohort in ("reused_external_original","reused_synthetic_control",
                   "new_seed_synthetic"):
        cohorts[cohort]=[c for c in cases if c["cohort"]==cohort]
    result={}
    for name,subset in cohorts.items():
        s={}
        for mode in MODES:
            rows=[a for c in subset for rep in range(REPS)
                  for a in by[c["sha256"],rep] if a["mode"]==mode]
            s[mode]=dict(attempts=len(rows),
                solved=sum(a["status"]!="TIMEOUT" for a in rows),
                sat=sum(a["status"]=="SAT" for a in rows),
                unsat=sum(a["status"]=="UNSAT" for a in rows),
                par2_s=round(sum(a["par2_s"] for a in rows),6),
                probe_s=round(sum(a["pilot_s"] for a in rows),6),
                probe_terminal=sum(a["selected"]=="pilot_solved" for a in rows),
                chose_default=sum(a["selected"]=="default" for a in rows),
                chose_sat=sum(a["selected"]=="sat" for a in rows))
        result[name]=dict(formulas=len(subset),modes=s,
            speedup_vs_default={m:round(s["default"]["par2_s"]/s[m]["par2_s"],5)
                for m in MODES if m!="default"})
    report=dict(protocol=PROTO,status="R191_PAIRED_AUDIT_PASS",
        source_sha256=SOURCE_SHA,formulas=len(cases),attempts=len(chunks),
        sat_models_checked=True,
        independent_unsat_lrat=False,
        early_learning_length_not_LBD=True,
        same_sha_binary_and_sources=True,
        fresh_real_blind_holdout=False,
        groups=result)
    write(ROOT/"report.json",report)
    write(ROOT/"all-trials.json",chunks)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# DRNAS R191 — genuine CDCL first-conflict feedback\n\n")
        f.write("102 frozen R190 same SHA CNFs; 25 reused real, 13 reused "
                "synthetic, 64 new-seed synthetic. NOT blind external real. "
                "Six arms, two repetitions, 8 shards. Clean, SAT, limited "
                "probe+in-place continuation, fixed probe+SAT, probe+default "
                "shadow, and early-telemetry decision. All pilot CPU/wall and "
                "restart time charged. Learner counts clause LENGTH, not LBD. "
                "SAT models checked on original CNF; CDCL UNSAT does not have "
                "independent LRAT.\n\n")
        f.write("| Cohort | Mode | Solved | PAR-2 s | Speedup | Pilot s |\n"
                "|---|---|---:|---:|---:|---:|\n")
        for name in ("reused_external_original","reused_synthetic_control",
                     "new_seed_synthetic","all"):
            for mode,r in result[name]["modes"].items():
                f.write(f"| {name} | {mode} | {r['solved']}/{r['attempts']} "
                    f"| {r['par2_s']} | "
                    f"{result[name]['speedup_vs_default'].get(mode,'—')} "
                    f"| {r['probe_s']} |\n")
        f.write("\nNo automatic promotion to default. Requires new blind real holdout.\n")
    print("R191_FINAL",json.dumps({"groups":{k:result[k] for k in
         ("all","new_seed_synthetic","reused_external_original")}},
          sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--binary",default="r191/r191-driver")
    args=ap.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="verify":
        print("R191_VERIFY_PASS",len(verify()),flush=True)
    elif args.action=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()
