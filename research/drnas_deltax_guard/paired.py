#!/usr/bin/env python3
"""DELTAX-GUARD1 proof-first matched A/B on frozen HARD28 synthetic sources.

JOIN, DELTAX-SHADOW, unrestricted DELTAX, clone-gated DELTAX are ALL modes
of the same newly compiled native executable. SAT models checked on source;
all accepted UNSAT require original-source independent DRAT. No speculative
clone result is accepted as truth, and UNKNOWN gets no solved credit.
"""
import argparse,collections,hashlib,json,os,random,signal,subprocess,sys,tempfile,time
from pathlib import Path

R=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(R/"research/drnas_deltax"),str(R/"research"),str(R/"tests")]
import hard_formulas
import drnas_x55_cpu_real36 as B
from test_drnas_deltax import validate_alias,canon
from test_drnas_deltacoop2 import check_witness

ARMS=("join","deltax-shadow","deltax","deltax-guard")
BINARY=R/"build/drnas-deltax-guard"
DRAT=R/"build/drat-trim"
CAP=6.0
SHARDS=4
FROZEN_HARD28="dd9924240b970ab70a764cc8be6a260e141c0bc823b7601e5dc01df6ce123240"

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def emit(prefix,x):print(prefix+" "+json.dumps(x,sort_keys=True),flush=True)
def sources():
    p=R/"deltax_hard_inputs/manifest.json"
    rows=json.loads(p.read_text())
    assert len(rows)==28 and sha(p)==FROZEN_HARD28,(
        "FROZEN_SYNTHETIC_SOURCE_SET_CHANGED",sha(p))
    return rows

def trial(s,arm,cap,rawdir):
    src=R/s["path"]
    assert sha(src)==s["sha256"]
    raw=src.read_bytes()
    n,cs=B.parse_cnf(raw)
    assert n==s["nvars"] and len(cs)==s["nclauses"]
    with tempfile.TemporaryDirectory() as tmp:
        proof=Path(tmp)/"test.drat"
        cmd=[str(BINARY.resolve()),str(src.resolve()),
             "--mode","core","--time",str(max(.05,cap-.10)),
             "--stats","--x5-no-minimize","--coop4","gate",
             "--coop4-eager","--coop5","off","--delta2",arm,
             "--proof",str(proof)]
        start=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        killed=False
        try:out,err=p.communicate(timeout=cap+.20)
        except subprocess.TimeoutExpired:
            killed=True;os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
        wall=time.perf_counter()-start
        status="TIMEOUT" if killed else "UNKNOWN"
        check_s=0.
        if not killed:
            assert p.returncode in (0,10,20,153),(
                "SOLVER_PROCESS_ERROR",s["name"],arm,p.returncode,err[-900:])
            if p.returncode==10:
                start_check=time.perf_counter()
                assert B.check_sat(out,cs,n),("INVALID_ORIGINAL_SAT",s["name"],arm)
                check_s=time.perf_counter()-start_check
                status="SAT_VERIFIED"
            elif p.returncode==20:
                if proof.exists() and proof.stat().st_size:
                    start_check=time.perf_counter()
                    try:
                        chk=subprocess.run([str(DRAT),str(src),str(proof)],
                            text=True,capture_output=True,timeout=35)
                        assert chk.returncode>=0 and "s VERIFIED" in chk.stdout,(
                            "ORIGINAL_DRAT_INVALID",s["name"],arm,
                            chk.stdout[-500:],chk.stderr[-500:])
                        status="UNSAT_CERTIFIED"
                    except subprocess.TimeoutExpired:
                        status="UNSAT_CHECK_TIMEOUT"
                    check_s=time.perf_counter()-start_check
                else:status="UNSAT_UNVERIFIED"
        stats={}
        aliases=[];probes=[];causal=[];witnesses=0
        originals={canon(c) for c in cs}
        for line in err.splitlines():
            tag,sep,body=line.partition(" ")
            if tag in ("X41_STATS","DELTAX_STATS","DELTAX_GUARD_STATS",
                       "DELTAX_GUARD_SOURCE","DELTAX_CAUSAL_STATS","DELTA2_JOIN"):
                assert tag not in stats,("DUPLICATE_STATS",tag)
                stats[tag]=json.loads(body)
            elif tag=="DELTAX_ALIAS":
                e=json.loads(body)
                validate_alias(e,originals)
                assert e["installed"]==(arm in ("deltax","deltax-guard"))
                aliases.append(e)
            elif tag=="DELTAX_GUARD_PROBE":
                e=json.loads(body)
                assert e["same_main_snapshot"],("CLONE_LEAK",s["name"])
                assert e["baseline_decisions"]>=0 and e["trial_decisions"]>=0
                probes.append(e)
            elif tag=="DELTAX_CAUSAL_PROPAGATION":
                causal.append(json.loads(body))
            elif tag=="DELTA2_WITNESS":
                w=json.loads(body)
                check_witness(w)
                assert all(canon(c) in originals for side in ("left","right")
                           for c in w[side]["cnf"]),("NON_SOURCE_WITNESS",s["name"])
                witnesses+=1
        if not killed:
            assert all(tag in stats for tag in (
                "X41_STATS","DELTAX_STATS","DELTAX_GUARD_STATS",
                "DELTAX_GUARD_SOURCE","DELTAX_CAUSAL_STATS","DELTA2_JOIN")),(
                    "MISSING_TELEMETRY",s["name"],arm,err[-900:])
        gate=stats.get("DELTAX_GUARD_STATS",{})
        srcgate=stats.get("DELTAX_GUARD_SOURCE",{})
        delta=stats.get("DELTAX_STATS",{})
        caus=stats.get("DELTAX_CAUSAL_STATS",{})
        core=stats.get("X41_STATS",{})
        if not killed:
            assert delta["mode"]==arm
            assert srcgate["invalid_derivations_rejected"]==0,(
                "INVALID_SOURCE_RESOLUTION",s["name"],arm,srcgate)
            assert gate["inconsistent_clones"]==0,(
                "CLONE_RESULT_CONTRADICTION",s["name"],arm,gate)
            if arm not in ("deltax","deltax-guard"):
                assert delta["proof_carrying_injected"]==0 and not causal
            if arm in ("join","deltax-shadow"):
                assert gate["checks"]==0
            if arm in ("deltax","deltax-guard"):
                assert len(aliases)<=delta["proof_carrying_injected"]
                assert len(causal)<=caus["real_enqueues_with_deltax_reason"]
            if arm=="deltax":
                assert gate["checks"]==0
            if arm=="deltax-guard":
                assert srcgate["guard_selected"]==delta["proof_carrying_injected"]
                assert gate["accepted"]==delta["proof_carrying_injected"]
                assert gate["checks"]==gate["accepted"]+gate["rejected"]+gate["budget_rejections"]
                assert len(probes)<=gate["checks"]
                for event in causal:
                    assert canon(event["reason_clause"]) in {
                        canon(x["forward"]) for x in aliases},(
                            "NOT_A_DELTAX_REASON",s["name"],event)
        verified=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=cap
        result={
           "source":s["name"],"family":s["family"],"sha256":s["sha256"],
           "arm":arm,"status":status,"verified":verified,
           "wall_e2e_s":wall,"proof_check_s":check_s,
           "par2_verified_s":wall if verified else 2*cap,
           "decisions":core.get("decisions"),"conflicts":core.get("conflicts"),
           "learned":core.get("learnt"),
           "deltax_lemmas":delta.get("proof_carrying_injected",0),
           "causal_enqueues":caus.get("real_enqueues_with_deltax_reason",0),
           "guard_checks":gate.get("checks",0),
           "guard_accepted":gate.get("accepted",0),
           "guard_rejected":gate.get("rejected",0),
           "guard_budget_rejected":gate.get("budget_rejections",0),
           "guard_invalid_source":srcgate.get("invalid_derivations_rejected",0),
           "guard_clones_inconsistent":gate.get("inconsistent_clones",0),
           "guard_baseline_probe_decisions":gate.get("baseline_probe_decisions",0),
           "guard_trial_probe_decisions":gate.get("trial_probe_decisions",0),
           "nonlinear_witnesses":witnesses
        }
        rawdir.mkdir(parents=True,exist_ok=True)
        (rawdir/(s["name"]+"-"+arm+".stderr")).write_text(err[-85000:])
        if aliases or probes or causal:
            save(rawdir/(s["name"]+"-"+arm+".events.json"),
                 {"aliases":aliases,"probe_samples":probes,"causal":causal})
        emit("DELTAX_GUARD_TRIAL",{k:v for k,v in result.items() if k!="sha256"})
        return result

def preflight():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    manifest=hard_formulas.write("deltax_hard_inputs")
    assert sources()==manifest
    chosen=[manifest[i] for i in (0,10,18,24)]
    out=Path("deltax_guard_preflight")
    pairs=[]
    for s in chosen:
        for a in ARMS:
            pairs.append(trial(s,a,3.0,out/"raw"))
    assert len(pairs)==16
    assert all(r["guard_invalid_source"]==0 and r["guard_clones_inconsistent"]==0 for r in pairs)
    assert sum(r["guard_checks"] for r in pairs)>0,("NO_GUARD_PROBES",pairs)
    save(out/"report.json",{
        "status":"PASS","cases_checked":4,"trials":len(pairs),
        "one_logical_cpu":True,"original_source_proof_checks":True,
        "source_manifest_sha256":FROZEN_HARD28,
        "guard_probe_trials":sum(r["guard_checks"] for r in pairs),
        "guard_accepted":sum(r["guard_accepted"] for r in pairs),
        "guard_rejected":sum(r["guard_rejected"] for r in pairs),
        "main_unmodified":True,"no_promotion":True
    })
    emit("DELTAX_GUARD_PREFLIGHT_PASS",{
        "cases_checked":4,"trials":len(pairs),
        "guard_probe_trials":sum(r["guard_checks"] for r in pairs)})

def shard(index):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    manifest=sources()
    cases=[s for i,s in enumerate(manifest) if i%SHARDS==index]
    out=Path(f"deltax_guard_shards/{index}")
    out.mkdir(parents=True,exist_ok=False)
    save(out/"manifest.json",{
        "shard":index,"dataset_sha":FROZEN_HARD28,"arms":ARMS,
        "cap_s":CAP,"one_cpu":sorted(os.sched_getaffinity(0)),
        "binary_sha256":sha(BINARY),"drat_sha256":sha(DRAT),
        "retrospective":True,"blind_holdout":False,"promotion":False
    })
    with (out/"trials.jsonl").open("w") as f:
        for s in cases:
            order=list(ARMS)
            random.Random(int(s["sha256"][:16],16)).shuffle(order)
            for arm in order:
                row=trial(s,arm,CAP,out/"raw")
                f.write(json.dumps(row,sort_keys=True)+"\n")
                f.flush()
    emit("DELTAX_GUARD_SHARD_PASS",{"shard":index,"trials":len(cases)*len(ARMS)})

def aggregate():
    src=sources()
    data=[];manifests=[]
    for index in range(SHARDS):
        root=Path(f"deltax_guard_downloads/deltax-guard-shard-{index}/deltax_guard_shards/{index}")
        manifests.append(json.loads((root/"manifest.json").read_text()))
        data.extend(json.loads(line) for line in (root/"trials.jsonl").read_text().splitlines())
    expect={(s["sha256"],a) for s in src for a in ARMS}
    actual=[(r["sha256"],r["arm"]) for r in data]
    assert len(actual)==len(set(actual))==len(expect)==112 and set(actual)==expect
    for m in manifests:
        assert m["dataset_sha"]==FROZEN_HARD28
        assert tuple(m["arms"])==ARMS and m["cap_s"]==CAP and len(m["one_cpu"])==1
        assert m["binary_sha256"]==manifests[0]["binary_sha256"]
        assert m["drat_sha256"]==manifests[0]["drat_sha256"]
        assert m["retrospective"] and not m["blind_holdout"] and not m["promotion"]
    verdict=collections.defaultdict(set)
    for row in data:
        if row["verified"]:verdict[row["sha256"]].add(row["status"])
    assert all(len(x)<=1 for x in verdict.values()),"CONTRADICTORY_VERIFIED_VERDICTS"
    arms={}
    for a in ARMS:
        rr=[r for r in data if r["arm"]==a]
        arms[a]={
            "trials":len(rr),"verified":sum(r["verified"] for r in rr),
            "decisions":sum(r["decisions"] or 0 for r in rr),
            "conflicts":sum(r["conflicts"] or 0 for r in rr),
            "lemmas_injected":sum(r["deltax_lemmas"] for r in rr),
            "causal_enqueues":sum(r["causal_enqueues"] for r in rr),
            "guard_checks":sum(r["guard_checks"] for r in rr),
            "guard_accepted":sum(r["guard_accepted"] for r in rr),
            "guard_rejected":sum(r["guard_rejected"] for r in rr),
            "guard_budget_rejected":sum(r["guard_budget_rejected"] for r in rr),
            "invalid_source_steps":sum(r["guard_invalid_source"] for r in rr),
            "clones_inconsistent":sum(r["guard_clones_inconsistent"] for r in rr)
        }
    bykey={(r["sha256"],r["arm"]):r for r in data}
    paired=[];matched=[]
    for case in src:
        b=bykey[(case["sha256"],"join")]
        d=bykey[(case["sha256"],"deltax")]
        g=bykey[(case["sha256"],"deltax-guard")]
        assert b["verified"] and d["verified"] and g["verified"],(
            "NO_FAIR_VERIFIED_COMPARISON",case["name"])
        row={
            "name":case["name"],"family":case["family"],
            "join_dec":b["decisions"],"deltax_dec":d["decisions"],
            "guard_dec":g["decisions"],
            "join_conf":b["conflicts"],"deltax_conf":d["conflicts"],
            "guard_conf":g["conflicts"],
            "guard_accepted":g["guard_accepted"],"guard_rejected":g["guard_rejected"],
            "guard_budget_rejected":g["guard_budget_rejected"],
            "guard_causal":g["causal_enqueues"]
        }
        paired.append(row)
        if case["family"]=="php_unsat":matched.append(row)
    report={
        "status":"COMPLETE","sources":len(src),"trials":len(data),
        "one_logical_cpu":True,"proof_first":True,
        "retrospective_synthetic":True,"blind_holdout":False,
        "promotion":False,"no_speed_claim":True,
        "arms":arms,
        "guard_better_decisions_than_plain_deltax":
            sum(x["guard_dec"]<x["deltax_dec"] for x in paired),
        "guard_worse_decisions_than_plain_deltax":
            sum(x["guard_dec"]>x["deltax_dec"] for x in paired),
        "guard_better_conflicts_than_plain_deltax":
            sum(x["guard_conf"]<x["deltax_conf"] for x in paired),
        "guard_worse_conflicts_than_plain_deltax":
            sum(x["guard_conf"]>x["deltax_conf"] for x in paired),
        "guard_better_conflicts_than_join":
            sum(x["guard_conf"]<x["join_conf"] for x in paired),
        "guard_worse_conflicts_than_join":
            sum(x["guard_conf"]>x["join_conf"] for x in paired),
        "php_repro":matched,
        "paired_details":paired
    }
    assert arms["deltax-guard"]["invalid_source_steps"]==0
    assert arms["deltax-guard"]["clones_inconsistent"]==0
    save("deltax_guard_final/report.json",report)
    save("deltax_guard_final/trials.json",data)
    emit("DELTAX_GUARD_FINAL",{k:v for k,v in report.items() if k not in ("paired_details","php_repro")})

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("preflight","shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.stage=="preflight":preflight()
    elif args.stage=="shard":shard(args.shard)
    else:aggregate()
