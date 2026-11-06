#!/usr/bin/env python3
"""R160 retrospective-to-transfer test based on independently audited R159.

Training: 16 original CNFs in R159 successful audited artefact, three repeats.
Test: remaining 24 SHA-distinct R151 original external CNFs (6 each cohort).
CAVEAT: all were previously measured in R151; NOT globally virgin/blind and
no official competition claim. R159 outcomes train only a simple FROZEN
category portfolio. R160 never learns from its test runtimes.

Four actual independently executed policies:
  original_kissat, stable_v1531, cadical, r160_portfolio.
Original CNF inputs never rewritten; unchanged frozen V15.3.1.
R158 static graph feature analysis is OFFLINE ONLY and excluded from PAR2.
"""
import argparse,collections,csv,hashlib,json,math,os,platform,random,statistics,sys,time
from pathlib import Path

sys.path.insert(0,"research")
sys.path.insert(0,"experiments/drnas_v16")
import r159_external_transfer as r159
import r158_features as fed

ROOT=Path("r160")
INPUT=Path("r160-r151-source/holdout")
HISTORY=Path("r160-r159-audit/r159/report")
FREEZE=ROOT/"frozen"
MODES=("original_kissat","stable_v1531","cadical","r160_portfolio")
COHORTS=("official2026","official2025","miter","cryptography")
CAP=8.0
REPEATS=3
SHARDS=4
PROTO="R160-AUDITED-R159-COHORT-PORTFOLIO-COMPLEMENT-20261106-v1"
BASE_RUN=42134974748
BASE_ARTIFACT=13464389933
SOURCE_RUN=42094754907
SOURCE_ARTIFACT=13447565674
BASE_REPORT_SHA="bee6898841c80a88529e7528458e11a51c5fba30fa270dc20880fe124c6d233e"
BASE_PAIRS_SHA="b4b2d0f1acc80349d57996ca90a085a1ce794509fc642029a0939ddfa48b52c9"
BASE_FROZEN_SHA="1b55b49ca4478981d7d05b782982a3c9243e1380e5a4c73736d6dcf556aab5b8"

def need(x,what):
    if not x:raise RuntimeError("R160_FAIL_CLOSED "+str(what))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()
def readcsv(path):
    with Path(path).open(newline="") as f:return list(csv.DictReader(f))
def writecsv(path,values):
    need(bool(values),"cannot write empty CSV")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for row in values for k in row))
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="raise")
        w.writeheader();w.writerows(values)
def write(path,object):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(object,indent=2,sort_keys=True)+"\n")

def verify_sources():
    for path,digest in ((HISTORY/"report.json",BASE_REPORT_SHA),
                        (HISTORY/"paired_external.csv",BASE_PAIRS_SHA),
                        (Path("r160-r159-audit/r159/frozen/manifest.json"),BASE_FROZEN_SHA)):
        need(path.is_file() and sha(path)==digest,"pinned audited R159 source drift "+str(path))
    previous=json.loads((HISTORY/"report.json").read_text())
    need(previous["measured_SAT_attempts"]==240 and previous["original_formulas"]==16 and
         previous["live_R158_policy_executed"] is False and
         previous["independent_UNSAT_certificate"] is False,"R159 audit provenance drift")
    freeze=json.loads(Path("r160-r159-audit/r159/frozen/manifest.json").read_text())
    old={x["sha256"] for x in freeze["cases"]}
    need(len(old)==16,"R159 source incomplete")
    history=readcsv(HISTORY/"paired_external.csv")
    need(len(history)==16 and {r["sha256"] for r in history}==old,
         "R159 paired audit formula drift")
    r151=json.loads((INPUT/"manifest.json").read_text())
    need(r151["r151_protocol"]=="DRNAS-R151-RISK-ABSTENTION-NEW-SHA-DISJOINT-20261105-v1"
         and r151["r151_full_DIMACS_clause_validation"] is True,"R151 original provenance missing")
    need(len(r151["cases"])==40 and len({x["sha256"] for x in r151["cases"]})==40,
         "incomplete source registry")
    return r151,old,history

def frozen_choice(history):
    decision={}
    for cohort in COHORTS:
        sub=[r for r in history if r["cohort"]==cohort]
        need(len(sub)==4,"not 4 prior audited formula per cohort "+cohort)
        costs={mode:sum(float(r[mode]) for r in sub)
               for mode in ("original_kissat","stable_v1531","cadical")}
        baseline=costs["original_kissat"]
        best=min(costs,key=lambda mode:(costs[mode],mode))
        # Require >= 1 second over the entire cohort (12 paired attempts)
        # to change policy; otherwise use the unmodified standard Kissat.
        selected=best if baseline-costs[best]>=1.0 else "original_kissat"
        decision[cohort]=dict(selected=selected,
             train_formulas=4,train_trials_per_solver=12,
             training_PAR2_s={k:round(v,6) for k,v in costs.items()},
             train_gain_over_kissat_s=round(baseline-costs[selected],6),
             frozen_rule=">=1.0s cohort paired PAR2 gain over Kissat; else Kissat")
    return decision

def freeze():
    catalog,prior,history=verify_sources()
    route=frozen_choice(history)
    samples=[]
    for cohort in COHORTS:
        remaining=sorted([c for c in catalog["cases"]
                          if c["cohort"]==cohort and c["sha256"] not in prior],
                         key=lambda c:c["sha256"])
        need(len(remaining)==6,"expected 6 SHA complement of R159 in "+cohort)
        for c in remaining:
            path=INPUT/c["id"]
            need(path.is_file() and sha(path)==c["sha256"],
                 "source CNF content SHA drift "+c["id"])
            n,clauses=r159.ext.parse_original(path)
            need(n==c["variables"] and len(clauses)==c["clauses"],"invalid original CNF")
            samples.append({k:c[k] for k in (
                "id","cohort","sha256","source_url","source_identifier",
                "source_catalog","variables","clauses","bytes","packed_sha256")})
    need(len(samples)==24 and len({x["sha256"] for x in samples})==24,
         "exactly 24 previously unused in R159 SHA")
    manifest=dict(protocol=PROTO,status="FROZEN_BEFORE_R160_RUNTIME",
        source_R151_run=SOURCE_RUN,source_R151_artifact=SOURCE_ARTIFACT,
        source_R151_manifest_sha256=sha(INPUT/"manifest.json"),
        training_R159_run=BASE_RUN,training_R159_artifact=BASE_ARTIFACT,
        training_audited_report_sha256=BASE_REPORT_SHA,
        training_audited_pairs_sha256=BASE_PAIRS_SHA,
        training_source_manifest_sha256=BASE_FROZEN_SHA,
        trained_on_only_R159_16=True,train_formulas=16,test_formulas=24,
        source_SHA_disjoint_from_R159_16=True,
        already_measured_by_R151=True,strict_globally_unseen=False,
        R158_shadow_not_live=True,V1531_frozen=True,
        source_cohort_count={c:6 for c in COHORTS},modes=MODES,repeats=REPEATS,
        cap_seconds=CAP,portfolio=route,cases=samples)
    write(FREEZE/"manifest.json",manifest)
    print("R160_FROZEN_24_PASS "+json.dumps({"formulas":24,
       "chosen":{c:route[c]["selected"] for c in COHORTS},
       "source_sha256":sha(FREEZE/"manifest.json")},sort_keys=True),flush=True)

def selected_cases(shard):
    catalog,prior,training=verify_sources()
    source=json.loads((FREEZE/"manifest.json").read_text())
    need(source["protocol"]==PROTO and source["status"]=="FROZEN_BEFORE_R160_RUNTIME",
         "manifest not frozen")
    need(source["source_R151_manifest_sha256"]==sha(INPUT/"manifest.json")
         and source["training_audited_report_sha256"]==sha(HISTORY/"report.json")
         and source["training_audited_pairs_sha256"]==sha(HISTORY/"paired_external.csv"),
         "source SHA drift")
    need(source["portfolio"]==frozen_choice(training),"trained rule changed")
    need(len(source["cases"])==24,"source count drift")
    cases=[]
    for c in source["cases"][shard::SHARDS]:
        need(c["sha256"] not in prior,"R159 train/test overlap")
        src=INPUT/c["id"]
        need(src.is_file() and sha(src)==c["sha256"],"input original changed")
        n,clauses=r159.ext.parse_original(src)
        need(n==c["variables"] and len(clauses)==c["clauses"],"CNF clause count drift")
        cases.append(dict(path=src.resolve(),formula=c["id"],n=n,clauses=clauses,
            formula_sha256=c["sha256"],expected="UNKNOWN",category=c["cohort"],
            metadata=dict(seed=int(c["sha256"][:12],16),
                          fold="R160_test_reused_by_R151",
                          cohort=c["cohort"],features=r159.ext.features(clauses,n))))
    need(len(cases)==6,"must be 6 formulas per shard")
    return cases,source

def setup_binaries():
    # All reference builds come from R52 pinned artifact; identical hash
    # expected across runners, unlike native C rebuilds in R159.
    r159.ext.base.ORIGINAL=Path("built/bin/kissat_4_0_4").resolve()
    r159.ext.base.STABLE=Path("/tmp/drnas-r6-v1531")
    r159.ext.r11.CAP=CAP
    r159.CAP=CAP

def attempt(case,rep,mode,runner,portfolio):
    selected=portfolio[case["category"]]["selected"] if mode=="r160_portfolio" else mode
    need(selected in ("original_kissat","stable_v1531","cadical"),"unknown portfolio route")
    if selected=="cadical":
        r,t=r159.cadical_trial(case,rep,runner)
    else:
        r,t=r159.ext.run_one(case,rep,selected,runner)
    r["r160_selected_solver"]=selected
    r["mode"]=mode
    r["source_sha256"]=case["formula_sha256"]
    r["r160_protocol"]=PROTO
    t["mode"]=mode
    t["selected_solver"]=selected
    need(not r.get("error"),"SAT witness or exit error "+str(r.get("error")))
    need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad result")
    if r["status"]=="SAT":
        need(r.get("sat_model_checked") is True,"SAT witness invalid")
    return r,t

def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    setup_binaries()
    cases,source=selected_cases(shard)
    core=r159.ext.set_cpu_affinity()
    runner=os.environ.get("RUNNER_NAME","unknown")+"/cpu_"+str(core)+"/"+platform.processor()
    binary_sha=dict(kissat=sha(r159.ext.base.ORIGINAL),
          cadical=sha(Path("built/bin/cadical_3_0_1")),
          stable_v1531=sha(r159.ext.base.STABLE))
    result=[];traces=[]
    for case in cases:
        for rep in range(REPEATS):
            order=list(MODES)
            random.Random(int(case["formula_sha256"][:12],16)+rep+160).shuffle(order)
            for mode in order:
                r,t=attempt(case,rep,mode,runner,source["portfolio"])
                result.append(r);traces.append(t)
                print("R160_MEASURE",case["formula"],rep,mode,
                      r["r160_selected_solver"],r["status"],r["par2_s"],flush=True)
        statuses={r["status"] for r in result if r["formula"]==case["formula"]
             and r["status"] in ("SAT","UNSAT")}
        need(len(statuses)<=1,"SAT/UNSAT contradiction "+case["formula"])
    need(len(result)==6*REPEATS*len(MODES),"partial shard")
    folder=ROOT/("shard-%d"%shard)
    writecsv(folder/"measurements.csv",result)
    (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
    write(folder/"manifest.json",dict(protocol=PROTO,shard=shard,
        source_commit=os.environ.get("GITHUB_SHA","local"),
        source_manifest_sha256=sha(FREEZE/"manifest.json"),
        runner=runner,cpu_affinity=sorted(os.sched_getaffinity(0)),
        binaries_sha256=binary_sha,
        original_sha256=[x["formula_sha256"] for x in cases],
        modes=MODES,rows=len(result)))
    print("R160_SHARD_PASS",shard,len(result),flush=True)

def bootstrap(records,arm):
    group=collections.defaultdict(list)
    for r in records:group[r["cohort"]].append(r)
    rng=random.Random(16000+sum(map(ord,arm)))
    gains=[]
    for _ in range(3000):
        samples=[rng.choice(g) for g in group.values() for _ in g]
        b=sum(x["original_kissat"] for x in samples)
        a=sum(x[arm] for x in samples)
        gains.append(100*(b-a)/b if b else 0)
    gains.sort()
    return [round(gains[int(2999*p)],6) for p in (.025,.975)]

def audit():
    catalog,used,training=verify_sources()
    source=json.loads((FREEZE/"manifest.json").read_text())
    need(source["portfolio"]==frozen_choice(training),"train rule mismatch")
    formula_map={c["id"]:c for c in source["cases"]}
    need(len(formula_map)==24,"not 24 distinct original sources")
    observations=[];trace_ids=set();shards=[]
    base_binary=None
    for shard in range(SHARDS):
        folder=Path("r160-download")/("r160-shard-%d"%shard)/"r160"/("shard-%d"%shard)
        meta=json.loads((folder/"manifest.json").read_text())
        data=readcsv(folder/"measurements.csv")
        traces=[json.loads(x) for x in (folder/"traces.jsonl").read_text().splitlines() if x]
        need(meta["protocol"]==PROTO and meta["shard"]==shard and
             meta["source_manifest_sha256"]==sha(FREEZE/"manifest.json"),
             "source/commit drift")
        need(len(data)==len(traces)==72 and meta["modes"]==list(MODES),
             "partial 72 row shard")
        if base_binary is None:base_binary=meta["binaries_sha256"]
        need(meta["binaries_sha256"]==base_binary,
             "heterogeneous binary SHA across runners")
        need(len(meta["original_sha256"])==6,"shard source count")
        for i,r in enumerate(data):
            need(r["runner"]==meta["runner"] and not r.get("error"),
                 "runner or solver error")
            need(r["mode"] in MODES and r["formula"] in formula_map and
                 r["source_sha256"]==formula_map[r["formula"]]["sha256"],
                 "wrong source SHA")
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad status")
            cost=2*CAP if r["status"]=="TIMEOUT" else float(r["wall_s"])
            need(abs(cost-float(r["par2_s"]))<=.0001,"PAR2 mismatch")
            if r["status"]=="SAT":need(r["sat_model_checked"]=="True","SAT proof invalid")
            expected=source["portfolio"][r["category"]]["selected"] if r["mode"]=="r160_portfolio" else r["mode"]
            need(r["r160_selected_solver"]==expected,"actual route not frozen choice")
            t=traces[i]
            need(t["formula"]==r["formula"] and str(t["repeat"])==r["repeat"] and
                 t["mode"]==r["mode"] and t["selected_solver"]==expected,
                 "trace pairing mismatch")
            key=(r["source_sha256"],r["repeat"],r["mode"])
            need(key not in trace_ids,"duplicate paired attempt")
            trace_ids.add(key)
        observations.extend(data)
        shards.append(dict(shard=shard,runner=meta["runner"],source_commit=meta["source_commit"],
           binaries_sha256=meta["binaries_sha256"],
           manifest_sha256=sha(folder/"manifest.json"),
           measurements_sha256=sha(folder/"measurements.csv"),
           traces_sha256=sha(folder/"traces.jsonl")))
    need(len(observations)==288 and len(trace_ids)==288,"incomplete 24x3x4 attempts")
    paired=collections.defaultdict(dict)
    for r in observations:paired[(r["formula"],r["repeat"])][r["mode"]]=r
    need(len(paired)==72,"72 paired comparisons required")
    for key,arms in paired.items():
        need(set(arms)==set(MODES),"missing comparison arm")
        need(len({x["runner"] for x in arms.values()})==1,"unpaired runner")
        need(len({x["status"] for x in arms.values() if x["status"] in ("SAT","UNSAT")})<=1,
             "SAT/UNSAT contradiction")
    per=[]
    for item in source["cases"]:
        sub=[r for r in observations if r["formula"]==item["id"]]
        need(len(sub)==12,"missing 3x4")
        costs={k:sum(float(r["par2_s"]) for r in sub if r["mode"]==k) for k in MODES}
        per.append(dict(formula=item["id"],sha256=item["sha256"],
            cohort=item["cohort"],n=item["variables"],**costs))
    root=ROOT/"report";root.mkdir(parents=True,exist_ok=True)
    writecsv(root/"paired_external.csv",per)
    totals={}
    baseline=sum(x["original_kissat"] for x in per)
    for mode in MODES:
        cost=sum(r[mode] for r in per)
        totals[mode]=dict(PAR2_s=round(cost,6),
              gain_vs_kissat_pct=round(100*(baseline-cost)/baseline,6),
              solved=sum(r["status"] in ("SAT","UNSAT") for r in observations if r["mode"]==mode),
              confidence95_by_formula=bootstrap(per,mode) if mode!="original_kissat" else [0,0],
              regressions_2x_formulas=sum(r[mode]>2*r["original_kissat"] for r in per))
    # Optional R158 static geometry descriptive audit, never routing; failures are explicit.
    traits=[];costs=[]
    for c in source["cases"]:
        t0=time.perf_counter()
        try:
            f=fed.static_features(fed.parse_dimacs(INPUT/c["id"]))
            reason=""
        except (ValueError,MemoryError) as e:
            f={};reason=str(e)[:160]
        costs.append((time.perf_counter()-t0)*1000)
        traits.append(dict(formula=c["id"],sha256=c["sha256"],
             cohort=c["cohort"],fractal_valid=f.get("graph_box_valid",0),
             graph_available=int(not bool(reason)),unavailable_reason=reason,
             **{k:v for k,v in f.items() if k!="box_counts"}))
    writecsv(root/"graph_features_shadow.csv",traits)
    chart='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 850 850"><rect width="850" height="850" fill="white"/><path d="M50 790L790 50" stroke="#777" stroke-dasharray="6 4"/>'
    scale=max([r[m] for r in per for m in ("original_kissat","r160_portfolio")]+[1])
    for r in per:
        x=50+740*r["original_kissat"]/scale
        y=790-740*r["r160_portfolio"]/scale
        chart+='<circle cx="%.3f" cy="%.3f" r="4" fill="#348ea2"/>'%(x,y)
    chart+='<text x="50" y="26" font-size="17">R160 24 original reused-R151 CNFs, paired PAR-2</text></svg>'
    (root/"paired_scatter.svg").write_text(chart)
    report=dict(protocol=PROTO,source="remaining_R151_24_REUSED_NOT_GLOBALLY_BLIND",
       complete_original_SHA_distinct_formulas=24,compared_attempts=len(observations),
       training_original_formulas=16,prior_R159_audit_run=BASE_RUN,
       source_R151_run=SOURCE_RUN,frozen_portfolio_rule=source["portfolio"],
       source_manifest_sha256=sha(FREEZE/"manifest.json"),
       source_original_manifest_sha256=sha(INPUT/"manifest.json"),
       source_shards=shards,reference_binary_identical_across_shards=True,
       independent_unsat_proof=False,all_SAT_witness_checked=True,
       R158_graph_available=sum(int(x["graph_available"]) for x in traits),
       R158_feature_overhead_median_ms=round(statistics.median(costs),4),
       R158_dynamics_evaluated=False,
       R158_live_policy=False,V15_3_1_modified=False,
       results=totals,
       caveats=["All 24 originals previously measured in R151; not global blind",
                "R159 training and R160 evaluation disjoint by SHA but source catalog reused",
                "Portfolio selects solver by catalog family, not learned fractal geometry",
                "R158 graph features shadow-only, overhead excluded from SAT PAR2",
                "No independent UNSAT certificates; cross-solver consistency checked",
                "No official competition speedup claim"])
    write(root/"report.json",report)
    print("R160_FINAL "+json.dumps({"formulas":24,"attempts":len(observations),
         "results":totals,"features":report["R158_graph_available"],
         "source_not_globally_blind":True},sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("step",choices=("freeze","run","audit"))
    ap.add_argument("--shard",type=int,default=0)
    o=ap.parse_args()
    {"freeze":freeze,"run":lambda:run(o.shard),"audit":audit}[o.step]()
