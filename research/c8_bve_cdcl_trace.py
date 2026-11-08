#!/usr/bin/env python3
"""DRNAS C8 — real CaDiCaL BVE and CDCL aggregate trace, factorial causal test.

Three frozen SAT development originals from C7:
 * fdfcd52a: many BVE eliminations but worse search;
 * 695d8f6a: 350 BVE tries and NO eliminated variables, strong search difference;
 * 037d21e0: BVE strongly improves conflicts.
2x2 CaDiCaL: elimination ON/OFF × vivification ON/OFF. 3 repetitions,
25s end-to-end cap, true SAT witness replay against original SHA.
Separately run verbose fresh solver processes capped at 1k, 5k, 20k,
50k conflicts and full verbose run; extract actual CaDiCaL aggregate
BVE tries, resolvents, eliminations, restarts, conflicts, decisions,
propagations, vivification and progress glue lines. These are NOT a
continuous trace, NOT exact per-variable BVE order, and NOT final PAR2.
NO claim that CaDiCaL --no-elim has *only* elimination effects.

Strict fail-closed audit on all original SHA, paired modes and attempts.
Prior C7 comparisons provide same-source CryptoMiniSat and Kissat controls
but ARE NOT mixed into C8 PAR2 scoring. Development cohort, not blind.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,subprocess,time
import c7_standard_solver_bve_crosscheck as c7
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO="DRNAS-C8-CADICAL-BVE-VIVIFY-3SHA-4ARM-3REP-25S-FOUR-CONFLICT-SNAPSHOTS-v1"
OUT=pathlib.Path("c8_out")
SOURCE_IDS=("fdfcd52a21824b7181d66672f283ba04",
            "695d8f6a2ee6e89e5a4f5d94abc3aca6",
            "037d21e060a2e3eab8b080aa84ceee75")
MODES=("default","noelim","novivify","noelim_novivify")
OPTIONS={"default":(),"noelim":("--no-elim",),
         "novivify":("--no-vivify",),
         "noelim_novivify":("--no-elim","--no-vivify")}
CAP=25.0
REPS=3
BUDGETS=(1000,5000,20000,50000)
STATS_NAMES=("conflicts","decisions","propagations","restarts","eliminated",
             "elimphases","elimrounds","elimtried","elimres",
             "elimrestried","elimgates","elimxors","vivified",
             "vivifications","vivifychecks","deduplicated",
             "learned","learnedlits","reductions")
STAT_RE=re.compile(r"^c\s+([A-Za-z][A-Za-z0-9_.-]*):\s+(\d+)(?:\s|$)",re.M)
def need(b,msg):
    if not b:raise RuntimeError("C8_FAIL_CLOSED "+str(msg))
def sources():
    cc,man=c7.get_cases()
    by={c["gbd"]:c for c in cc}
    need(all(k in by for k in SOURCE_IDS),"frozen source GBD not found")
    out=[by[k] for k in SOURCE_IDS]
    need(len({c["sha256"] for c in out})==3,
         "duplicate source in C8")
    for c in out:
        need(c7.digest(c["path"])==c["sha256"] and
             c["expected_status"]=="SAT","original SAT source SHA changed")
    return out
def cmd(mode,original,verbose=False,conflicts=None):
    need(mode in MODES,"unknown mode")
    a=["/usr/bin/cadical",*OPTIONS[mode]]
    if verbose:a+=["-v"]
    if conflicts is not None:
        need(conflicts in BUDGETS,"unregistered conflict snapshot")
        a+=["-c",str(conflicts)]
    return a+[str(original.resolve())]
def parse_stats(output):
    data={}
    for key,num in STAT_RE.findall(output):
        if key in STATS_NAMES:
            data[key]=int(num)
    glue=[l for l in output.splitlines()
          if re.search(r"\bglue\b",l,re.I) and re.search(r"\d",l)]
    # Keep only bounded progress samples, not an inferred numerical LBD.
    return data,glue[:30]
def validate_stats(data,mode):
    for k in ("conflicts","decisions","propagations","restarts"):
        need(k in data,"missing standard CaDiCaL CDCL counter "+k)
    need(data["conflicts"]>=0 and data["decisions"]>=0,
         "negative native statistics")
    if "eliminated" in data:
        if "noelim" in mode:
            need(data["eliminated"]==0,
                 "--no-elim unexpectedly eliminated variables")
    return True
def seed(c,rep):
    # Used for balanced run order only; CaDiCaL standard CLI here does not
    # honor an independent randomized seed. Pairs refer to source + repetition.
    return int(hashlib.sha256((PROTO+"|"+c["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)
def smoke():
    OUT.mkdir(exist_ok=True)
    tiny=OUT/"selftest-sat.cnf"
    tiny.write_text("p cnf 4 5\n1 2 0\n-1 2 0\n-2 3 0\n3 0\n4 0\n")
    success=[]
    for mode in MODES:
        p=subprocess.run(cmd(mode,tiny,verbose=True),
            capture_output=True,text=True,errors="replace",
            check=False,timeout=15)
        s,model=ref.external_parse(p)
        need(s=="SAT","CaDiCaL factorial option unsupported "+mode+
             " stderr "+p.stderr[-400:])
        cms.verify_model(tiny,model)
        stats,glue=parse_stats(p.stdout)
        validate_stats(stats,mode)
        success.append(dict(mode=mode,keys=sorted(stats),conflicts=stats["conflicts"]))
    print("C8_OPTION_FACTORIAL_SAT_MODEL_STATS_SMOKE_PASS",
          json.dumps(success,sort_keys=True),flush=True)
def full_trial(c,rep,mode):
    original=c["path"]
    need(c7.digest(original)==c["sha256"],"source changed between trials")
    env=os.environ.copy()
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd(mode,original),capture_output=True,
                text=True,errors="replace",timeout=CAP,check=False,env=env)
    except subprocess.TimeoutExpired:
        p=None
    wall=time.perf_counter()-start
    status="TIMEOUT";verified=False
    if p is not None:
        status,model=ref.external_parse(p)
        if status=="SAT":
            cms.verify_model(original,model)
            verified=True
        if status=="UNSAT":
            raise RuntimeError("C8_SAT_REFERENCE_CONTRADICTION original "+c["gbd"])
    if wall>CAP or status!="SAT":
        status="TIMEOUT";verified=False
    return dict(protocol=PROTO,cohort="C7 selected development SAT not blind",
        source_sha256=c["sha256"],gbd=c["gbd"],rep=rep,
        run_order_seed=seed(c,rep),independent_seed_applied=False,
        mode=mode,status=status,original_SAT_verified=verified,
        UNSAT_independent_LRAT=False,cap_s=CAP,wall_s=round(wall,6),
        PAR2_s=round(wall if status=="SAT" else 2*CAP,6),
        build_sha=os.getenv("GITHUB_SHA","LOCAL"))
def diagnostic(c,mode,budget):
    original=c["path"]
    need(c7.digest(original)==c["sha256"],"diagnostic source SHA mismatch")
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd(mode,original,verbose=True,conflicts=budget),
                capture_output=True,text=True,errors="replace",
                timeout=CAP,check=False)
    except subprocess.TimeoutExpired:
        p=None
    wall=time.perf_counter()-start
    status="DIAGNOSTIC_TIMEOUT";stats=None;glue=[]
    if p is not None:
        status,model=ref.external_parse(p)
        need(status in ("SAT","UNKNOWN"),"unexpected snapshot result")
        if status=="SAT":cms.verify_model(original,model)
        stats,glue=parse_stats(p.stdout)
        validate_stats(stats,mode)
    if wall>CAP:
        status="DIAGNOSTIC_TIMEOUT";stats=None;glue=[]
    return dict(protocol=PROTO,kind="fresh_bounded_CDCL_diagnostic_not_PAR2",
        source_sha256=c["sha256"],gbd=c["gbd"],mode=mode,
        budget_conflicts=budget,status=status,
        wall_s=round(wall,6),actual_aggregate_cadical_stats=stats,
        raw_glue_progress_samples=glue,
        not_continuous_trace=True,
        per_variable_BVE_order_instrumented=False,
        build_sha=os.getenv("GITHUB_SHA","LOCAL"))
def full_verbose(c,mode):
    original=c["path"]
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd(mode,original,verbose=True),
                capture_output=True,text=True,errors="replace",
                timeout=CAP,check=False)
    except subprocess.TimeoutExpired:
        p=None
    status="DIAGNOSTIC_TIMEOUT";stats=None;glue=[]
    if p is not None:
        status,model=ref.external_parse(p)
        need(status=="SAT","full verbose diagnostic did not terminate SAT")
        cms.verify_model(original,model)
        stats,glue=parse_stats(p.stdout)
        validate_stats(stats,mode)
    return dict(protocol=PROTO,kind="separate_full_verbose_not_PAR2",
        source_sha256=c["sha256"],gbd=c["gbd"],mode=mode,status=status,
        wall_s=round(time.perf_counter()-start,6),
        actual_aggregate_cadical_stats=stats,
        raw_glue_progress_samples=glue,
        not_continuous_trace=True,
        per_variable_BVE_order_instrumented=False)
def shard(i):
    cc=sources()
    need(i in range(3),"unregistered source shard")
    c=cc[i];OUT.mkdir(exist_ok=True)
    rows=[]
    for rep in range(REPS):
        order=list(MODES)
        random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(order)
        for mode in order:
            row=full_trial(c,rep,mode)
            rows.append(row)
            (OUT/("full-%d.json"%i)).write_text(
                json.dumps(rows,indent=2,sort_keys=True)+"\n")
            print("C8_FULL_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES),"full paired source incomplete")
    print("C8_FULL_SHARD_PASS",i,len(rows),flush=True)
    checks=[]
    for mode in MODES:
        for budget in BUDGETS:
            record=diagnostic(c,mode,budget)
            checks.append(record)
            (OUT/("trace-%d.json"%i)).write_text(
                json.dumps(checks,indent=2,sort_keys=True)+"\n")
            print("C8_BVE_SNAPSHOT",json.dumps(record,sort_keys=True),flush=True)
        full=full_verbose(c,mode)
        checks.append(full)
        (OUT/("trace-%d.json"%i)).write_text(
            json.dumps(checks,indent=2,sort_keys=True)+"\n")
        print("C8_FULL_VERBOSE",json.dumps(full,sort_keys=True),flush=True)
    need(len(checks)==len(MODES)*(len(BUDGETS)+1),
         "incomplete BVE + CDCL diagnostic trace")
    print("C8_TRACE_SHARD_PASS",i,len(checks),flush=True)
def audit():
    cc=sources()
    bysha={x["sha256"]:x for x in cc}
    rows=[];trace=[]
    for i in range(3):
        a=OUT/("full-%d.json"%i)
        t=OUT/("trace-%d.json"%i)
        need(a.exists() and t.exists(),"missing complete source shard")
        full=json.loads(a.read_text());tr=json.loads(t.read_text())
        need(len(full)==len(MODES)*REPS and
             len(tr)==len(MODES)*(len(BUDGETS)+1),
             "partial full or trace shard")
        rows.extend(full);trace.extend(tr)
    need(len(rows)==3*REPS*len(MODES) and len(trace)==3*len(MODES)*(len(BUDGETS)+1),
         "missing exact 36 full and 60 diagnostics")
    pairs=collections.defaultdict(dict)
    for row in rows:
        c=bysha.get(row["source_sha256"])
        need(c is not None and row["gbd"]==c["gbd"] and row["protocol"]==PROTO,
             "alien input SHA or protocol")
        need(row["rep"] in range(REPS) and row["mode"] in MODES and
             row["run_order_seed"]==seed(c,row["rep"]) and
             row["independent_seed_applied"] is False,
             "unpaired source+rep or fabricated independent seed")
        need(row["cap_s"]==CAP and row["status"] in ("SAT","TIMEOUT"),
             "invalid terminal/cap")
        need(row["status"]!="SAT" or row["original_SAT_verified"],
             "SAT model not verified on original SHA")
        need(row["status"]!="TIMEOUT" or
             row["PAR2_s"]==CAP*2,"timeout PAR2 penalty wrong")
        need(row["status"]!="SAT" or abs(row["PAR2_s"]-row["wall_s"])<0.000002,
             "solved PAR2 mismatch")
        key=(c["sha256"],row["rep"])
        need(row["mode"] not in pairs[key],"duplicate paired mode")
        pairs[key][row["mode"]]=row
    need(len(pairs)==3*REPS and all(set(v)==set(MODES) for v in pairs.values()),
         "incomplete 3 x 3 x 4 factorial")
    keyseen=set()
    for t in trace:
        c=bysha.get(t["source_sha256"])
        need(c is not None and t["gbd"]==c["gbd"] and t["protocol"]==PROTO,
             "diagnostic source SHA changed")
        kind=t["kind"]
        need(kind in ("fresh_bounded_CDCL_diagnostic_not_PAR2",
                      "separate_full_verbose_not_PAR2"),
             "diagnostic mixed with PAR2")
        if kind=="fresh_bounded_CDCL_diagnostic_not_PAR2":
            need(t["budget_conflicts"] in BUDGETS,"unregistered snapshot")
            key=(c["sha256"],t["mode"],t["budget_conflicts"])
        else:
            key=(c["sha256"],t["mode"],"full_verbose")
        need(t["mode"] in MODES and key not in keyseen,
             "duplicate or invalid trace")
        keyseen.add(key)
        need(t["status"] in ("SAT","UNKNOWN","DIAGNOSTIC_TIMEOUT"),
             "non-evidenced diagnostic terminal")
        if t["status"]!="DIAGNOSTIC_TIMEOUT":
            validate_stats(t["actual_aggregate_cadical_stats"],t["mode"])
    need(len(keyseen)==len(trace),"trace matrix incomplete")
    scores={}
    for mode in MODES:
        a=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(trials=len(a),solved=sum(x["status"]=="SAT" for x in a),
             timeouts=sum(x["status"]=="TIMEOUT" for x in a),
             PAR2_s=round(sum(x["PAR2_s"] for x in a),6),
             measured_wall_s=round(sum(x["wall_s"] for x in a),6))
    base=scores["default"]["PAR2_s"]
    for mode in MODES:
        scores[mode]["speedup_vs_cadical_default_x"]=round(base/scores[mode]["PAR2_s"],5)
    per_source=[]
    for c in cc:
        s=[x for x in rows if x["source_sha256"]==c["sha256"]]
        d=[x for x in trace if x["source_sha256"]==c["sha256"]]
        groups={mode:[x for x in s if x["mode"]==mode] for mode in MODES}
        per_source.append(dict(gbd=c["gbd"],original_SHA=c["sha256"],
            per_mode_full={m:dict(solved=sum(x["status"]=="SAT" for x in v),
                 PAR2_s=round(sum(x["PAR2_s"] for x in v),6),
                 times=[x["wall_s"] for x in sorted(v,key=lambda z:z["rep"])])
                for m,v in groups.items()},
            actual_cadical_trace=d))
    result=dict(protocol=PROTO,cohort="3 selected C7 previous development SAT SHA, NOT blind",
        source_SHA3=[x["sha256"] for x in cc],
        real_end_to_end_sat=True,original_SAT_witness_verified=True,
        independent_solver_seeds=False,UNSAT_independent_LRAT=False,
        restarts_decisions_propagations_BVE_are_actual_cadical_aggregates=True,
        BVE_attempt_order_and_rejection_reasons_NOT_instrumented=True,
        LBD_glue_progress_lines_not_histogram=True,
        checkpoints_fresh_processes_not_continuous=True,
        no_auto_promotion=True,
        full_trial_count=len(rows),diagnostic_trace_count=len(trace),
        budgets_conflicts=list(BUDGETS),cap_s=CAP,reps=REPS,
        modes=list(MODES),scores=scores,per_source=per_source)
    (OUT/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("C8_FINAL",json.dumps({k:v for k,v in result.items() if k!="per_source"},
                                sort_keys=True),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("verify","smoke","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    a=parser.parse_args()
    if a.action=="verify":
        print("C8_THREE_SOURCE_SHA_PINNED",len(sources()),flush=True)
    elif a.action=="smoke":smoke()
    elif a.action=="shard":shard(a.shard)
    else:audit()
