#!/usr/bin/env python3
"""DRNAS R196 causal evaluation of CaDiCaL split256.

8 SHA-frozen R195 official/real source originals × 4 fixed solver seeds
× 7 native modes = 224 paired attempts. Four development-sensitive real
sources are deliberately preselected and four negative controls chosen
from SHA-ordered R195 unsolved sources. NOT an independent blind holdout.

No mode may access the instance ID, true answer, winner, R195 outcome or
source cohort. Every mode receives precisely the same original CNF.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random,re,subprocess,time,statistics
import r188_feedback_benchmark as helper
ROOT=pathlib.Path("r196")
SOURCE=ROOT/"frozen"
R195_MANIFEST_SHA="caae5fe7abde52e3d886add24bf23cd925411504e9c866dddcbd2fc8cb595be4"
CA_COMMIT="31f9aae44947c673dc6190c9beb399acb9ffec6a"
PROTO="DRNAS-R196-CAUSAL-SPLIT256-8REAL-4SEEDS-7ARM-20261107-v1"
TARGETS=(
  "1236c1406a2749b8022b5196e93de589", # real SAT profile-sensitive
  "20ca08f58828637815d93f46ef60b517", # default-only sporadic SAT
  "262a226a47330987f038128579967405", # repeatable Split256 UNSAT speed
  "db099269d468029b70419bf4a49e99a1", # Split256 extra SAT timeout escape
)
SEEDS=(11,23,37,47)
MODES=("default","limit_cancel","split128_twice","split256",
       "split512","split256_rebuild","split256_trace")
SHARDS=8
CAP_S=45.0
NEGATIVE_CONTROLS=4
R195_PREVIOUS={"1236c1406a2749b8022b5196e93de589":"SAT",
               "20ca08f58828637815d93f46ef60b517":"SAT",
               "262a226a47330987f038128579967405":"UNSAT",
               "db099269d468029b70419bf4a49e99a1":"SAT"}

def need(ok,msg):
    if not ok:raise AssertionError("R196_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def source_setup():
    """Freeze selection before timed work; no per-seed tuning allowed."""
    source=ROOT/"archive"/"frozen"
    need(sha(source/"manifest.json")==R195_MANIFEST_SHA,
         "R195 original frozen 37-source SHA mismatch")
    manifest=read(source/"manifest.json")
    need(len(manifest["cases"])==37,"unexpected R195 source set")
    known={c["id"]:c for c in manifest["cases"]}
    need(all(id in known for id in TARGETS),"R195 source target missing")
    # Negative controls: precisely four R195 cases previously all TIMEOUT,
    # selected by SHA hash only, stratified 2 archived + 2 newer.
    prior_solved=set(TARGETS)
    controls=[]
    for cohort in ("reused_real_r193","new_r193_holdout_official_2026"):
        pool=[c for c in manifest["cases"]
              if c["id"] not in prior_solved and c["cohort"]==cohort]
        pool.sort(key=lambda c:hashlib.sha256(
           (PROTO+"NEG_CTRL"+c["original_sha256"]).encode()).hexdigest())
        need(len(pool)>=2,"insufficient control CNFs")
        controls+=pool[:2]
    need(len(controls)==NEGATIVE_CONTROLS,"negative control mismatch")
    selected=[known[id] for id in TARGETS]+controls
    need(len({c["original_sha256"] for c in selected})==8,"duplicate source")
    SOURCE.mkdir(parents=True,exist_ok=True)
    rows=[]
    for c in selected:
        path=source/(c["id"]+".cnf")
        need(sha(path)==c["original_sha256"],"original R195 CNF drift")
        target=SOURCE/(c["id"]+".cnf")
        target.write_bytes(path.read_bytes())
        rows.append(dict(id=c["id"],source_sha256=sha(target),
            label="prior_R195_decisive" if c["id"] in TARGETS else "negative_control",
            cohort=c["cohort"],prior_expected=c["expected"],
            source=c["source"],bytes=target.stat().st_size,cap_s=CAP_S))
    random.Random(PROTO+"SOURCE_ORDER").shuffle(rows)
    save(SOURCE/"r196-manifest.json",dict(protocol=PROTO,sources=rows,
       archived_manifest_sha256=R195_MANIFEST_SHA,
       source_selection_development_R195_not_blind=True,
       four_negative_controls_deterministic_sha_order=True,
       source_winners_never_used_by_modes=True,
       same_source_and_seed_per_mode=True,
       ca_commit=CA_COMMIT,
       modes=MODES,seeds=SEEDS,shards=SHARDS,cap_s=CAP_S))
    verify()
    print("R196_SOURCE_FREEZE_PASS",json.dumps(dict(
        n=len(rows),shas=[c["source_sha256"] for c in rows],
        id=[c["id"] for c in rows],
        manifest_sha=sha(SOURCE/"r196-manifest.json"))),flush=True)

def verify():
    x=read(SOURCE/"r196-manifest.json")
    need(x["protocol"]==PROTO and len(x["sources"])==8,"unexpected R196 corpus")
    need(x["archived_manifest_sha256"]==R195_MANIFEST_SHA,
         "R195 archive source reference changed")
    for c in x["sources"]:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["source_sha256"],
             "original CNF source SHA mismatch "+c["id"])
    return x["sources"]

def native(binary,source,seed,mode,cap):
    start=time.perf_counter()
    args=[str(pathlib.Path(binary).resolve()),
          str(pathlib.Path(source).resolve()),str(cap),mode,str(seed)]
    try:
        pr=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            timeout=cap+3,check=False)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",elapsed_s=time.perf_counter()-start,
              model={},pilot_s=0.,rebuild_s=0.,counts={},pilot_counts={},
              calls=0,bound=0,preserved=False,watchdog=True)
    raw=pr.stdout.decode(errors="replace")
    err=pr.stderr.decode(errors="replace")
    need(pr.returncode==0,"R196 native driver error "+err[-900:])
    m=re.search(r"(?m)^R182_STATUS status=(SAT|UNSAT|TIMEOUT) solver_s=([0-9.]+) variables=(\d+)$",raw)
    need(m is not None,"R196 solver result missing")
    match=re.search(r"(?m)^R196_POLICY mode=(\w+) seed=(\d+) windows=(\d+) "
        r"bound=(\d+) preserved=(\d+) pilot_s=([0-9.]+) "
        r"rebuild_s=([0-9.]+) active_final=(\d+) "
        r"redundant_final=(\d+) irredundant_final=(\d+) "
        r"native_elapsed_s=([0-9.]+)$",raw)
    need(match is not None and match[1]==mode and int(match[2])==seed,
         "R196 native policy mismatch")
    mode_preserved=int(match[5])==1
    if mode=="split256_rebuild" and m[1]=="TIMEOUT":
        # A terminal result during the pilot may legitimately skip rebuilding.
        need(mode_preserved in (True,False),"bad rebuild state")
    elif mode!="split256_rebuild":
        need(mode_preserved,"unexpected lost learned state")
    def parse_stats(stage):
        rx=(r"(?ms)^R196_STATS_BEGIN stage="+re.escape(stage)+
            r"\n(.*?)^R196_STATS_END stage="+re.escape(stage)+r"$")
        m2=re.search(rx,raw)
        if not m2:return {}
        sec=m2[1]
        counters={}
        for key in ("conflicts","decisions","propagations","restarts"):
            hit=re.search(r"(?m)^\s*(?:c\s+)?"+key+r":\s+(\d+)\b",sec)
            counters[key]=int(hit[1]) if hit else None
        return counters
    final=parse_stats("final")
    pilot=parse_stats("after_pilot")
    need(final and final.get("conflicts") is not None,
         "native final CDCL counter missing")
    if mode=="split256_trace":
        need(pilot and pilot.get("conflicts") is not None,
             "split256_trace pilot CDCL diagnostic missing")
    elif pilot:
        need(False,"unexpected diagnostic snapshot altered arm")
    model={}
    if m[1]=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                for token in line[2:].split():
                    lit=int(token)
                    if lit==0:continue
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "inconsistent R196 SAT witness")
                    model[abs(lit)]=(lit>0)
    return dict(status=m[1],elapsed_s=time.perf_counter()-start,
        model=model,pilot_s=float(match[6]),rebuild_s=float(match[7]),
        calls=int(match[3]),bound=int(match[4]),preserved=mode_preserved,
        active=int(match[8]),redundant=int(match[9]),
        irredundant=int(match[10]),counts=final,pilot_counts=pilot,
        watchdog=False)

def selftest():
    need(len(MODES)==7 and len(TARGETS)==4 and
         len(SEEDS)==4 and SHARDS==8 and CAP_S==45,
         "R196 precommit drift")
    need(len(set(SEEDS))==len(SEEDS) and len(set(MODES))==len(MODES),
         "R196 duplicate modes/seeds")
    print("R196_SELFTEST_PASS",flush=True)

def trial(case,mode,seed,binary):
    path=SOURCE/(case["id"]+".cnf")
    start=time.perf_counter()
    need(sha(path)==case["source_sha256"],"source SHA mutated before trial")
    result=native(binary,path,seed,mode,CAP_S)
    status=result["status"]
    if status=="SAT":
        _,clauses=helper.gf.dimacs(path)
        helper.gf.sat_check(clauses,result["model"])
        proof="SAT_ORIGINAL_SOURCE_MODEL_CHECKED"
    elif status=="UNSAT":
        proof="NATIVE_CADICAL_UNSAT_NO_INDEPENDENT_LRAT"
    else:proof="CAP"
    expected=(case["prior_expected"] if case["prior_expected"]!="UNKNOWN"
              else R195_PREVIOUS.get(case["id"],"UNKNOWN"))
    if status!="TIMEOUT" and expected in ("SAT","UNSAT"):
        need(status==expected,"R196 disagrees with historical answer")
    elapsed=time.perf_counter()-start
    if elapsed>=CAP_S:status="TIMEOUT"
    return dict(id=case["id"],sha256=case["source_sha256"],
        cohort=case["cohort"],label=case["label"],
        seed=seed,mode=mode,cap_s=CAP_S,status=status,
        elapsed_s=round(elapsed,6),
        par2_s=round(2*CAP_S if status=="TIMEOUT" else elapsed,6),
        pilot_s=round(result["pilot_s"],6),
        rebuild_s=round(result["rebuild_s"],6),
        windows=result["calls"],bound=result["bound"],
        preserved=result["preserved"],active=result.get("active"),
        redundant=result.get("redundant"),
        irredundant=result.get("irredundant"),
        counters=result["counts"],after_pilot_counters=result["pilot_counts"],
        watchdog=result["watchdog"],proof=proof)

def shard(idx,binary):
    cases=verify()
    need(0<=idx<SHARDS and pathlib.Path(binary).is_file(),
         "bad shard or binary")
    pin=read(ROOT/"pin.json")
    need(sha(binary)==pin["native_driver_sha256"],"binary SHA changed")
    # Exactly one frozen source per shard; every seed and method tested there.
    case=cases[idx]
    rows=[]
    for seed in SEEDS:
        order=list(MODES)
        random.Random(PROTO+case["source_sha256"]+str(seed)).shuffle(order)
        for mode in order:
            r=trial(case,mode,seed,binary)
            rows.append(r)
            save(ROOT/f"shard-{idx}.json",rows)
            print("R196_TRIAL",json.dumps({k:r[k] for k in
                ("id","seed","mode","status","elapsed_s","pilot_s",
                 "windows","preserved","counters","after_pilot_counters")}),
                 flush=True)
    need(len(rows)==len(SEEDS)*len(MODES),"incomplete R196 shard")
    print("R196_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cases=verify()
    pin=read(ROOT/"pin.json")
    need(sha(ROOT/"r196-driver")==pin["native_driver_sha256"],
         "R196 audit binary mismatch")
    rows=[]
    for idx in range(SHARDS):
        subset=read(ROOT/f"shard-{idx}.json")
        need(len(subset)==len(SEEDS)*len(MODES),
             "missing or incomplete source shard "+str(idx))
        rows+=subset
    need(len(rows)==len(cases)*len(SEEDS)*len(MODES),
         "missing paired source/seed runs")
    groups=collections.defaultdict(list)
    frozen={c["source_sha256"]:c for c in cases}
    for r in rows:
        c=frozen.get(r["sha256"])
        need(c is not None and c["id"]==r["id"],
             "bad original source identity")
        need(abs(r["par2_s"]-
            (2*CAP_S if r["status"]=="TIMEOUT" else r["elapsed_s"]))<1e-5,
            "invalid R196 PAR2")
        need(r["seed"] in SEEDS and r["mode"] in MODES,
             "unexpected mode or seed")
        if not r["watchdog"]:
            need(isinstance(r["counters"].get("conflicts"),int),
                 "missing native conflict count")
        groups[r["sha256"],r["seed"]].append(r)
    for c in cases:
        for seed in SEEDS:
            group=groups[c["source_sha256"],seed]
            need(len(group)==len(MODES) and
                 {r["mode"] for r in group}==set(MODES),
                 "incomplete paired seed")
            need(len({r["status"] for r in group if r["status"]!="TIMEOUT"})<=1,
                 "contradictory SAT vs UNSAT")
    def summary(subset):
        ans={}
        hashes={c["source_sha256"] for c in subset}
        for mode in MODES:
            group=[r for r in rows if r["mode"]==mode and r["sha256"] in hashes]
            ans[mode]=dict(n=len(group),solved=sum(r["status"]!="TIMEOUT" for r in group),
                sat=sum(r["status"]=="SAT" for r in group),
                unsat=sum(r["status"]=="UNSAT" for r in group),
                par2_s=round(sum(r["par2_s"] for r in group),6),
                elapsed_s=round(sum(r["elapsed_s"] for r in group),6),
                pilot_s=round(sum(r["pilot_s"] for r in group),6),
                watchdogs=sum(r["watchdog"] for r in group))
        baseline=ans["default"]["par2_s"]
        for mode in MODES:ans[mode]["PAR2_speedup_vs_default"]=round(
           baseline/ans[mode]["par2_s"],6)
        return ans
    cohort={"all":cases,
       "R195_decisive":[c for c in cases if c["label"]=="prior_R195_decisive"],
       "SHA_selected_negative_controls":[c for c in cases if c["label"]=="negative_control"]}
    cohort.update({c["id"]:[c] for c in cases})
    summaries={key:summary(subset) for key,subset in cohort.items()}
    deltas=[]
    for case in cases:
        for seed in SEEDS:
            g={r["mode"]:r for r in groups[case["source_sha256"],seed]}
            delta=g["default"]["par2_s"]-g["split256"]["par2_s"]
            deltas.append(dict(id=case["id"],seed=seed,delta_PAR2_s=round(delta,6),
                default_status=g["default"]["status"],
                split256_status=g["split256"]["status"],
                default_conflicts=g["default"]["counters"].get("conflicts"),
                split256_conflicts=g["split256"]["counters"].get("conflicts"),
                split256_rebuild_status=g["split256_rebuild"]["status"],
                limit_cancel_status=g["limit_cancel"]["status"],
                trace_status=g["split256_trace"]["status"]))
    outputs=dict(protocol=PROTO,status="R196_CAUSAL_ABLATION_AUDIT_PASS",
        source_count=len(cases),seeds=len(SEEDS),attempts=len(rows),
        same_source_SHA_and_seed_per_arm=True,old_R195_sources_reused_not_blind=True,
        no_production_selector_trained=True,
        source_sat_models_checked=True,native_unsat_independent_LRAT_absent=True,
        notes=[
          "If cancel-limit behaves like default, just setting the limit did not cause the speedup.",
          "If split256 differs from rebuild, preserving the complete solver state matters; cannot isolate learned clauses from other state.",
          "Pilot stats snapshots may perturb time; split256_trace is a diagnostic control, not a speedup claim.",
          "CaDiCaL stats are collected at finalization and pilot for trace arm; they do not establish causality alone.",
          "Only reused R195 originals: new blind SHA-disjoint external CNF holdout required before general claims."],
        summary=summaries,paired_per_source_seed=deltas)
    save(ROOT/"report.json",outputs)
    save(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    md=["# DRNAS R196 — isolate why 256-conflict split changes CDCL",
        "",f"{len(cases)} SHA-pinned R195 original sources × {len(SEEDS)} seeds × "
        f"{len(MODES)} modes = {len(rows)} paired trials.",
        "All R195 reused sources: this is causal replication, not a blind holdout.",
        "","| Cohort | Arm | Solved | PAR2 s | Speedup vs default |",
        "|---|---|---:|---:|---:|"]
    for key in ("all","R195_decisive","SHA_selected_negative_controls"):
        for mode,v in summaries[key].items():
            md.append(f"| {key} | {mode} | {v['solved']}/{v['n']} | "+
                      f"{v['par2_s']:.6f} | {v['PAR2_speedup_vs_default']:.4f}× |")
    md+=["","## Limits","SAT models checked against untouched original CNFs.",
         "Native UNSAT not independently verified with LRAT.",
         "Stopping/restarting preserves many dimensions of solver state; no mechanism is proven from this experiment alone.",
         "GitHub shared runners cause timing noise; interpretation requires more seeds and new blind originals."]
    (ROOT/"summary.md").write_text("\n".join(md)+"\n")
    print("R196_FINAL",json.dumps({k:summaries[k] for k in (
        "all","R195_decisive","SHA_selected_negative_controls")},sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("cmd",choices=("selftest","freeze","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--binary",default="r196/r196-driver")
    args=ap.parse_args()
    if args.cmd=="selftest":selftest()
    elif args.cmd=="freeze":source_setup()
    elif args.cmd=="verify":print("R196_VERIFY_PASS",len(verify()),flush=True)
    elif args.cmd=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()
