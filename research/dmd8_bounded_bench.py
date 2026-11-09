#!/usr/bin/env python3
"""DRNAS DMD8: benchmark bounded synthetic assumption-UP signal vs real SAT E2E.

DMD7 24 original sources are scanned using source-only proof candidates.
The 9 prior DMD7 positive original SHA are then tested with 7 single-core
arms: CaDiCaL clean, Kissat, DMD7 placebo, DMD7 top1, DMD8 probe placebo,
DMD8 gated top1 and gated top4. 9*2*7 = 126 8-second E2E trials.

DMD8's cheap native probe measures early implication depth under
counterfactual synchronous two-round UP, NOT actual CaDiCaL/CDCL trail.
The E2E solver instrument measures actual decisions/conflicts after selection.
Every used candidate is still independently proven from original CNF parent
clauses via the DMD7 exhaustive truth table replayer.
No genuinely unseen holdout; no SAT winner claim without full PAR2 audit.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,resource,tempfile,time
import dmd7_proof_first_bench as prior

ROOT=pathlib.Path("mre_dmd8")
PROBE=ROOT/"bin/dmd8_probe"
PROTO="DRNAS-DMD8-BOUND-UP-SOURCE-GATED-9SHA-7ARM-2REP-8S-v1"
CAP=8.0
PROBE_MS=250
REPS=2
SHARDS=4
ARMS=("cadical_clean","kissat_original","dmd7_placebo","dmd7_top1",
      "dmd8_probe_shadow","dmd8_top1","dmd8_top4")
GATED=("dmd8_probe_shadow","dmd8_top1","dmd8_top4")
def need(ok,msg):
    if not ok:raise RuntimeError("DMD8_FAIL_CLOSED "+str(msg))
def setup():
    prior.ROOT=ROOT
    prior.EXPAND=ROOT/"bin/dmd7_expand"
    prior.setup()
def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def used_cpu():
    q=resource.getrusage(resource.RUSAGE_CHILDREN)
    return q.ru_utime+q.ru_stime
def cpu():
    return min(os.sched_getaffinity(0))
def selected_manifest():
    setup()
    src=json.loads((ROOT/"manifest.json").read_text())
    need(src["protocol"]==prior.PROTO and src["source_only_screen"] and
         len(src["all_sources"])==24 and len(src["selected"])==9 and
         src["selected"]==[r["sha256"] for r in src["selected_cases"]],
         "DMD7 original source-only selection mismatch")
    return src
def freeze():
    ROOT.mkdir(exist_ok=True)
    prior.manifest()
    predecessor=selected_manifest()
    m=dict(protocol=PROTO,training="previously tested DMD7/DMD5 formula cohort",
       reuse_not_blind=True,no_auto_promotion=True,
       source_selection="DMD7 source-only certified candidate count, not solver outcomes",
       original_screened=24,
       selected_sha=predecessor["selected"],
       selected_source_files=[c["filename"] for c in predecessor["selected_cases"]],
       candidate_signatures={c["sha256"]:c["candidate_signature"]
                             for c in predecessor["selected_cases"]},
       expected_sources=9,shards=SHARDS,reps=REPS,cap_s=CAP,probe_ms=PROBE_MS,
       arms=ARMS,expected_trials=9*REPS*len(ARMS),
       cpu_model="one pinned logical CPU per solver; no parallel portfolio",
       synthetic_probe="identical counterfactual assumptions, two synchronous UP rounds",
       probe_score="25 x early_conflict + 4 x earlier_round1_assignments + earlier_round2_assignments",
       probe_budget="native source-only 250ms including CNF parse; max 16 first source-ranked candidates, 2 probes per candidate",
       finite_cost_in_E2E=True,
       local_parent_resolution_truth_table_replayed=True,
       original_SAT_replayed=True,UNSAT_independent_LRAT=False,
       code_sha={s:sha(pathlib.Path("research")/s) for s in (
           "dmd8_sync_up_probe.cpp","dmd8_bounded_bench.py")},
       binary_sha={s:sha(ROOT/"bin"/s) for s in (
           "dmd7_expand","dmd8_probe","dmd5_live","dmd1_anf")},
       kissat_sha=sha(prior.d5.KISSAT),
       DMD7_manifest_digest=digest(predecessor))
    (ROOT/"dmd8_manifest.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    print("DMD8_FREEZE_PASS",json.dumps({k:v for k,v in m.items()
          if k not in ("candidate_signatures","code_sha","binary_sha")},
          sort_keys=True),flush=True)
def check():
    m=json.loads((ROOT/"dmd8_manifest.json").read_text())
    p=selected_manifest()
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["cap_s"]==CAP and m["shards"]==SHARDS and
         m["expected_sources"]==9 and m["reps"]==REPS and
         m["expected_trials"]==9*REPS*len(ARMS) and
         m["selected_sha"]==p["selected"] and
         m["DMD7_manifest_digest"]==digest(p),
         "DMD8 frozen registry/experiment drift")
    for file,h in m["code_sha"].items():
        need(sha(pathlib.Path("research")/file)==h,"DMD8 source code drift "+file)
    for file,h in m["binary_sha"].items():
        need(sha(ROOT/"bin"/file)==h,"native binary SHA drift "+file)
    need(sha(prior.d5.KISSAT)==m["kissat_sha"],
         "pinned Kissat SHA changed")
    bysha={c["sha256"]:c for c in prior.sources()}
    need(all(bysha[s]["filename"]==f for s,f in
             zip(m["selected_sha"],m["selected_source_files"])),
         "source SHA -> filename changed")
    return m,p,bysha

def candidate_only(path,n,clauses):
    with path.open("w") as f:
        f.write(f"p cnf {n} {len(clauses)}\n")
        for c in clauses:
            f.write(" ".join(map(str,c))+" 0\n")

def run_probe(case,work,n,original,candidates):
    need(0<len(candidates)<=48,"empty/unbounded proof candidates")
    doc=work/"dmd8_candidate_only.cnf"
    candidate_only(doc,n,candidates)
    process=[PROBE,case["path"],doc,PROBE_MS]
    rc,out,err,seconds,child,timed=prior.d5.d1.run_process(
        process,1.2,cpu())
    need(not timed and rc==0,"native probe failed "+err[-250:])
    prefix="DMD8_PROBE "
    items=[json.loads(l[len(prefix):]) for l in out.splitlines()
           if l.startswith(prefix)]
    need(len(items)==1,"probe missing/duplicated telemetry")
    x=items[0]
    need(x["protocol"]=="DMD8-SYNC-UP-TWO-ROUND-v1" and
         x["probe_rounds"]==2 and x["per_candidate_max_probes"]==2 and
         x["max_candidates"]==16,
         "bounded UP protocol changed")
    ids=x["selected_indices"]
    need(len(ids)==len(set(ids)) and len(ids)<=4 and
         all(type(i)==int and 0<=i<min(16,len(candidates)) for i in ids),
         "unknown candidate selected")
    if x["abstained"]:
        need(not ids and not x["features"],"abstention leaked partial selection")
    else:
        need(x["candidate_count"]==len(candidates) and
             x["scored"]==min(16,len(candidates)) and
             len(x["features"])==x["scored"],
             "candidate/probe coverage mismatch")
        need(all(a["index"]==i and a["score"]>=0 and a["probes"]<=2
                 for i,a in enumerate(x["features"])),
             "unregistered feature")
        need(all(x["features"][i]["score"]>0 for i in ids),
             "non-positive probe score injected")
        order=sorted((a for a in x["features"] if a["score"]>0),
                     key=lambda v:(-v["score"],v["index"]))
        need(ids==[a["index"] for a in order[:4]],
             "native ranked candidate order was changed")
    return x,seconds

def trial(case,entry,arm,rep):
    need(arm in ARMS and rep in range(REPS),"unregistered arm/rep")
    pinned=cpu()
    os.sched_setaffinity(0,{pinned})
    source=pathlib.Path(case["path"])
    need(prior.d5.d1.sha(source)==case["sha256"],
         "original CNF SHA mismatch")
    start=time.monotonic()
    child_start=used_cpu()
    n,original=prior.d5.d1.read_cnf(source)
    chosen=[]
    proved=[]
    signature=None
    source_proof=False
    probe={"abstained":False,"selected_indices":[],"features":[],
           "scored":0,"synthetic_probe_not_CDCL":True}
    probe_seconds=0.0
    with tempfile.TemporaryDirectory(prefix="dmd8-e2e-") as temp:
        work=pathlib.Path(temp)
        if arm not in ("cadical_clean","kissat_original"):
            nn,cs,proved,raw=prior.derive(case,work)
            need(nn==n and cs==original and
                 prior.digest(raw["certificates"])==entry["candidate_signature"] and
                 len(proved)==entry["proof_verified"],
                 "proof candidates altered after frozen source-only screen")
            signature=prior.digest(raw["certificates"])
            source_proof=True
            if arm=="dmd7_top1":
                chosen=proved[:1]
            elif arm in GATED:
                p,probe_seconds=run_probe(case,work,n,original,proved)
                probe={**p,"synthetic_probe_not_CDCL":True}
                indexes=p["selected_indices"]
                if arm=="dmd8_top1":indexes=indexes[:1]
                if arm=="dmd8_top4":indexes=indexes[:4]
                if arm!="dmd8_probe_shadow":
                    chosen=[proved[i] for i in indexes]
            else:
                need(arm=="dmd7_placebo","unknown source arm")
        status,verified,cdcl,_=prior.d5.solve(
            source,n,original,chosen,
            "kissat" if arm=="kissat_original" else "cadical",
            CAP,start,work,pinned)
    elapsed=time.monotonic()-start
    need(status!="SAT" or verified,"original model verification failed")
    need(prior.d5.d1.sha(source)==case["sha256"],
         "original SHA mutated during benchmark")
    score_sum=sum(a["score"] for a in probe["features"])
    top_score=max((a["score"] for a in probe["features"]),default=0)
    return dict(protocol=PROTO,
       original_sha256=case["sha256"],filename=case["filename"],
       arm=arm,rep=rep,one_logical_cpu=True,pinned_cpu=pinned,
       cohort="reused_DMD7_source_only_selected_original_sha",
       source_SHA_verified=True,
       original_proof_replayed=source_proof,
       proof_sha256=signature,source_proved_lemmas=len(proved),
       probe=probe,probe_wall_s=round(probe_seconds,6),
       probe_positive_candidates=sum(x["score"]>0 for x in probe["features"]),
       probe_total_score=score_sum,probe_top_score=top_score,
       selected_lemmas=len(chosen),selected_lemma_digest=prior.digest(chosen),
       selected_shapes=dict(collections.Counter(prior.d5.shape(c) for c in chosen)),
       status=status,SAT_original_verified=verified,
       UNSAT_independent_LRAT=False,
       cap_s=CAP,e2e_s=round(elapsed,6),
       PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
       child_CPU_s=round(used_cpu()-child_start,6),
       cdcl_stats=cdcl)

def selftest():
    setup()
    need(PROBE.is_file() and prior.EXPAND.is_file() and
         prior.d5.LIVE.is_file() and prior.d5.KISSAT.is_file(),
         "native binaries missing")
    with tempfile.TemporaryDirectory(prefix="dmd8-selftest-") as td:
        w=pathlib.Path(td);source=w/"toy.cnf"
        source.write_text("p cnf 4 3\n-1 2 0\n-2 3 0\n-4 1 0\n")
        c={"path":str(source),"sha256":prior.d5.d1.sha(source)}
        n,cs,proved,raw=prior.derive(c,w)
        need((-1,3) in proved,
             "original two-parent resolution candidate absent")
        probe,sec=run_probe(c,w,n,cs,proved)
        need(not probe["abstained"] and
             any(x["early_round1"]>0 for x in probe["features"]) and
             len(probe["selected_indices"])>0,
             "native two-round shortcut probe missed expected early UP gain")
    print("DMD8_SELFTEST_PASS",json.dumps({
        "native_early_UP_impact":True,"original_two_parent_truth_table":True,
        "probe_not_real_CDCL":True,
        "source_proved_lemmas":len(proved),
        "positive_probe_candidates":len(probe["selected_indices"]),
        "native_probe_s":round(sec,6)},sort_keys=True),flush=True)

def shard(index):
    need(0<=index<SHARDS,"unregistered shard index")
    m,p,bysha=check()
    items=p["selected_cases"][index::SHARDS]
    rows=[]
    for entry in items:
        source=bysha[entry["sha256"]]
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(source["sha256"]+str(rep)+"dmd8").shuffle(arms)
            for arm in arms:
                result=trial(source,entry,arm,rep)
                rows.append(result)
                (ROOT/f"shard-{index}.json").write_text(
                    json.dumps(rows,sort_keys=True))
                print("DMD8_TRIAL",json.dumps(result,sort_keys=True),flush=True)
    expected=len(items)*REPS*len(ARMS)
    need(len(rows)==expected,"incomplete DMD8 shard")
    print("DMD8_SHARD_PASS",index,expected,flush=True)

def audit():
    m,p,bysha=check()
    rows=[]
    for i in range(SHARDS):
        q=ROOT/f"shard-{i}.json"
        need(q.is_file(),"missing shard")
        xs=json.loads(q.read_text())
        need(len(xs)==len(p["selected_cases"][i::SHARDS])*REPS*len(ARMS),
             "shard coverage mismatch")
        rows+=xs
    expected={(c["sha256"],rep,arm) for c in p["selected_cases"]
              for rep in range(REPS) for arm in ARMS}
    index={(r["original_sha256"],r["rep"],r["arm"]):r for r in rows}
    need(len(rows)==len(index)==len(expected)==126 and
         set(index)==expected,"missing/duplicate source-paired trials")
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["one_logical_cpu"] and r["source_SHA_verified"],
             "1CPU E2E source protocol mismatch")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT") and
             (r["status"]!="SAT" or r["SAT_original_verified"]),
             "incorrect SAT/UNSAT status or unverified original SAT")
        if r["selected_lemmas"]:
            need(r["original_proof_replayed"] and
                 (r["arm"] in ("dmd7_top1","dmd8_top1","dmd8_top4")),
                 "unproved candidate activated")
    summary={}
    paired={}
    for arm in ARMS:
        items=[r for r in rows if r["arm"]==arm]
        summary[arm]=dict(
          trials=len(items),solved=sum(r["status"]!="TIMEOUT" for r in items),
          SAT_verified=sum(r["status"]=="SAT" for r in items),
          UNSAT_backend_only=sum(r["status"]=="UNSAT" for r in items),
          PAR2_s=round(sum(r["PAR2_s"] for r in items),6),
          CPU_s=round(sum(r["child_CPU_s"] for r in items),6),
          appended_lemmas=sum(r["selected_lemmas"] for r in items),
          activated_trials=sum(r["selected_lemmas"]>0 for r in items),
          positive_probe_trials=sum(r["probe_positive_candidates"]>0 for r in items),
          probe_abstentions=sum(r["probe"].get("abstained",False) for r in items),
          probe_time_s=round(sum(r["probe_wall_s"] for r in items),6),
          conflicts_reported=sum(r["cdcl_stats"].get("conflicts",0) for r in items),
          decisions_reported=sum(r["cdcl_stats"].get("decisions",0) for r in items),
          CDCL_counters_are_censored_on_timeouts=True)
    ref=summary["cadical_clean"]["PAR2_s"]
    for a in summary.values():
        a["speedup_x_vs_clean"]=round(ref/a["PAR2_s"],6)
    for arm in ARMS:
        if arm in ("cadical_clean","kissat_original"):continue
        match=[]
        for src in p["selected_sha"]:
            for rep in range(REPS):
                x=index[(src,rep,arm)]
                clean=index[(src,rep,"cadical_clean")]
                p0=index[(src,rep,"dmd8_probe_shadow")]
                match.append((x,clean,p0))
        positive=[(x,b,s) for x,b,s in match if x["selected_lemmas"]>0]
        paired[arm]=dict(
          paired=len(match),
          with_lemmas=len(positive),
          accepted_solved_with_lemmas=sum(
              x["status"]!="TIMEOUT" for x,b,s in positive),
          wins_vs_clean=sum(x["PAR2_s"]<b["PAR2_s"]-.02 for x,b,s in match),
          losses_vs_clean=sum(x["PAR2_s"]>b["PAR2_s"]+.02 for x,b,s in match),
          net_PAR2_gain_vs_clean_s=round(sum(b["PAR2_s"]-x["PAR2_s"]
                  for x,b,s in match),6),
          net_PAR2_gain_vs_probe_shadow_s=round(sum(s["PAR2_s"]-x["PAR2_s"]
                  for x,b,s in match),6),
          selected_cases=[dict(filename=x["filename"],rep=x["rep"],
                      added=x["selected_lemmas"],status=x["status"],
                      probe_top_score=x["probe_top_score"],
                      E2E_gain_vs_shadow_s=round(s["PAR2_s"]-x["PAR2_s"],6))
                      for x,b,s in positive])
    # The GATED arms must see same deterministic candidate probe features
    # unless one of their native budgets independently exhausted.
    probe_disagreements=[]
    for source in p["selected_sha"]:
        for rep in range(REPS):
            group=[index[(source,rep,arm)] for arm in GATED]
            ready=[x for x in group if not x["probe"].get("abstained")]
            if ready:
                probes=[x["probe"]["features"] for x in ready]
                if any(z!=probes[0] for z in probes[1:]):
                    probe_disagreements.append(dict(source=source,rep=rep))
    report=dict(protocol=PROTO,source_roster=p["selected"],
        source_count=9,trials=126,cap_s=CAP,one_CPU=True,
        source_selection_blind_to_solver_outcomes=True,
        globally_unseen=False,independent_local_resolution_replayed=True,
        original_SAT_witness_verified=True,UNSAT_independent_LRAT=False,
        source_only_counterfactual_probe_not_real_CDCL=True,
        immutable_original_SHA=True,results=summary,paired=paired,
        probe_determinism_mismatches=probe_disagreements,
        no_auto_promotion=True,rows=rows)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DMD8_FINAL",json.dumps({k:v for k,v in report.items()
      if k!="rows"},sort_keys=True),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","freeze","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    a=ap.parse_args()
    setup()
    {"selftest":selftest,"freeze":freeze,"shard":lambda:shard(a.shard),
     "audit":audit}[a.action]()
