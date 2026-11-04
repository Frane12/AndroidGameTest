#!/usr/bin/env python3
"""DRNAS R89: source-only structural gate + cheap marginal BCP utility probe.

Controlled DEVELOPMENT replay: EXACT 60 original official/archival CNFs from R88.3.
Never select instances by previous times, SAT answers or source IDs.
The rules below are explicitly hypotheses informed by R88.3 (not blind).
All arms use pinned Kissat -s and strict 12s total budget including preprocessing.
All generated clauses retain the R88.3 independently replayed subset-RUP proof
ledger; rejecting lemmas never changes SAT/UNSAT semantics. NOT a world claim.

Arms: clean, matched duplicate-original placebo, certified8, structure_gate,
and marginal_probe. The last two do NO augmented CNF rewrite when rejected.
The payoff hypothesis is that low-value lemmas should not enter CDCL at all.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, os, random, sqlite3, statistics, subprocess, tempfile, time
from pathlib import Path
import r88_cooperative as old
import r88_cooperative_v2 as v2
import r88_lemma_utility_v3 as prev

PROTO="DRNAS-R89-TARGETED-LEMMA-MARGINAL-BCP-20261104-v1"
SOURCE_PROTO="DRNAS-R88-BULK-OFFICIAL-CNF-20261104-v1"
MODES=("clean","placebo","certified8","structure_gate","marginal_probe")
YEARS=(0,2025,2026); SHARDS=4; REPS=2
CAP=12.0; PROBE_LIMIT_S=0.070; PROBE_MAX_CLAUSES=1200
NEGATIVE_DIAGNOSTIC_ID="ed9f304b537a768f462bd1c723c5396e"

def ck(v,msg):
    if not v: raise RuntimeError("R89_FAIL_CLOSED "+str(msg))
def sha(p): return old.sha(p)
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")

def structural_gate(f):
    """PREDECLARED source-only policy. No source hash or runtime is a feature.

    Disconnected CNFs have independently solvable components; cross-component
    broadcasts can disturb CDCL. Other cases must have sufficiently dense
    short/horn structure to motivate community exchange.
    """
    reasons=[]
    if f["components"]!=1:reasons.append("disconnected_or_empty")
    if f["clauses"]<512 or f["active_variables"]<128:
        reasons.append("small_or_sparse")
    if f["binary_fraction"]<0.25 and f["horn_fraction"]<0.60:
        reasons.append("no_dense_binary_or_horn_substrate")
    return (not reasons),reasons

def marginal_bcp_probe(original,lemmas):
    """Bounded local-propagation *diagnostic*, not an equivalence certificate.

    Compare original subset vs augmented subset on four fixed single-variable
    signed assumptions from selected learned clauses. Retain only if additional
    propagated literals/conflict observed in >=2 probes. This is a prospective
    hypothesis, not a guarantee that more propagations improve full CDCL.
    """
    start=time.monotonic()
    if not lemmas:return dict(eligible=False,reason="no_lemmas",
                             tested=0,gains=0,extra_forced=0,seconds=0.0)
    stride=max(1,(len(original)+PROBE_MAX_CLAUSES-1)//PROBE_MAX_CLAUSES)
    sample=original[::stride][:PROBE_MAX_CLAUSES]
    picked=[]
    for clause in lemmas:
        for lit in clause:
            v=abs(lit)
            if v not in picked:picked.append(v)
            if len(picked)==2:break
        if len(picked)==2:break
    assumptions=[(x,) for v in picked for x in (v,-v)]
    gained=0;extra=0;tested=0;aborted=False
    for trial in assumptions:
        if time.monotonic()-start>=PROBE_LIMIT_S:
            aborted=True;break
        a_conf,a_trail=old.bcp_conflict(sample,trial,collect=True)
        if time.monotonic()-start>=PROBE_LIMIT_S:
            aborted=True;break
        b_conf,b_trail=old.bcp_conflict(sample+lemmas,trial,collect=True)
        tested+=1
        added=len(set(b_trail)-set(a_trail))
        useful=(b_conf and not a_conf) or (not a_conf and added>=2)
        if useful:gained+=1
        extra+=max(0,added)
    seconds=time.monotonic()-start
    # Partial/time-aborted probes cannot authorize a change to the solver.
    good=(not aborted and tested>=2 and gained>=2)
    return dict(eligible=good,reason=("observable_marginal_propagation" if good
       else "incomplete_or_no_marginal_BCP_gain"),
       tested=tested,gains=gained,extra_forced=extra,aborted=aborted,
       seconds=round(seconds,6))

def result(exe,source,path,charged,meta,lemmas=0,probe=None):
    z=prev.checked_runtime(exe,path,source,charged)
    return dict(**z,charged_prep_s=round(charged,6),
        used_added_clauses=lemmas,decision=meta,probe=probe)


def make_preparations(source,n,clauses,parse_s,folder):
    """One deterministic certified learner; no hidden double-training.
    Charged to each eligible learning arm separately, never to clean.
    """
    tick=time.monotonic()
    raw,proof=old.cooperative_learn(clauses,max_lemmas=16,rounds=2)
    selected,_=v2.select_useful(clauses,raw,proof,cap=16)
    chosen=[tuple(c) for c in selected[:8]]
    learn_s=time.monotonic()-tick
    placebo=v3.chosen_placebo(clauses,chosen)
    ans={}
    for mode,extras in (("certified8",chosen),("placebo",placebo)):
        tick=time.monotonic()
        out=Path(folder)/(mode+".cnf")
        if extras:v2.save_augmented(n,clauses,extras,out)
        else:out=source
        rewrite=time.monotonic()-tick
        ans[mode]=dict(path=out,extra_count=len(extras),
            parse_s=parse_s,learn_s=learn_s if mode=="certified8" else 0,
            write_s=rewrite,
            charged_prep=parse_s+rewrite+(
                learn_s if mode=="certified8" else 0))
    return ans,chosen

def measure(a):
    root=Path(a.sources).resolve()
    manifest=json.loads((root/"manifest.json").read_text())
    ck(manifest["protocol"]==SOURCE_PROTO and manifest["year"]==a.year
       and manifest["shard"]==a.shard and len(manifest["cases"])==5,
       "unknown frozen R88.3 original source cohort")
    binaries=Path(a.compiled).resolve()
    ck(subprocess.run(["sha256sum","-c","r87-binaries.sha256"],
          cwd=binaries,capture_output=True).returncode==0,
       "pinned clean Kissat SHA drift")
    executable=binaries/"clean"
    ck(executable.is_file() and os.access(executable,os.X_OK),"pinned Kissat missing")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    provenance=dict(protocol=PROTO,
       original_manifest_sha256=sha(root/"manifest.json"),
       pinned_clean_sha256=sha(executable),year=a.year,shard=a.shard,
       runner=os.environ.get("RUNNER_NAME"),run_id=os.environ.get("GITHUB_RUN_ID"),
       commit=os.environ.get("GITHUB_SHA"))
    rows=[]
    for c in manifest["cases"]:
        source=root/c["filename"]
        ck(sha(source)==c["sha256"],"original source SHA mismatch")
        t=time.monotonic()
        n,clauses=old.read_cnf(source)
        parse_s=time.monotonic()-t
        t=time.monotonic()
        features=old.fingerprint(n,clauses)
        features_s=time.monotonic()-t
        structural_ok,structural_reasons=structural_gate(features)
        with tempfile.TemporaryDirectory() as tmp:
            p,chosen=make_preparations(source,n,clauses,parse_s,tmp)
            # No double learning: the probe sees exactly those rows which
            # certified8 would append. Its time is charged only to the arm
            # that uses the probe; the shared learning time is charged too.
            t=time.monotonic()
            probe=(marginal_bcp_probe(clauses,chosen) if structural_ok else
                   dict(eligible=False,reason="source_structural_reject",
                        tested=0,gains=0,extra_forced=0,seconds=0.0))
            probe_cost=time.monotonic()-t if structural_ok else 0
            prepared=p["certified8"]
            matched=p["placebo"]
            for rep in range(REPS):
                order=list(MODES)
                random.Random(int(hashlib.sha256(
                  (PROTO+c["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(order)
                for mode in order:
                    if mode=="clean":
                        outcome=result(executable,source,source,0,
                                       "unchanged_original")
                    elif mode=="placebo":
                        outcome=result(executable,source,matched["path"],
                            matched["charged_prep"],"matched_original_clause_duplicates",
                            matched["extra_count"])
                    elif mode=="certified8":
                        outcome=result(executable,source,prepared["path"],
                            prepared["charged_prep"],"all_certified8",
                            prepared["extra_count"])
                    else:
                        charge=parse_s+features_s
                        allowed=structural_ok
                        reason=("structure_pass" if allowed else
                                "structure_reject:"+",".join(structural_reasons))
                        if structural_ok:
                            # Even a rejected candidate costs its acquisition.
                            charge+=prepared["learn_s"]
                            if mode=="marginal_probe":
                                charge+=probe_cost
                                allowed=bool(probe["eligible"])
                                reason=("probe_pass" if allowed else "probe_reject")
                        if allowed:
                            charge+=prepared["write_s"]
                            path=prepared["path"]
                            added=prepared["extra_count"]
                            if not added:reason="zero_certified_lemmas_fallback"
                        else:
                            path=source;added=0
                        outcome=result(executable,source,path,charge,
                            reason,added,probe if mode=="marginal_probe" else None)
                    expected=c.get("official_status","UNKNOWN")
                    if expected in ("SAT","UNSAT") and outcome["answer"]!="TIMEOUT":
                        ck(expected==outcome["answer"],"official source outcome mismatch")
                    row=dict(source_sha=c["sha256"],source_id=c["gbd"],
                         year=c["year"],structure=features["structure"],
                         features=dict(components=features["components"],
                           binary_fraction=features["binary_fraction"],
                           horn_fraction=features["horn_fraction"],
                           clauses=features["clauses"],active_variables=features["active_variables"]),
                         rep=rep,mode=mode,source_known_from_R88v3=True,
                         **outcome)
                    rows.append(row)
                    write(out/"rows.json",dict(**provenance,rows=rows))
                    print("R89_TRIAL",json.dumps(dict(year=a.year,shard=a.shard,
                        source=c["gbd"],rep=rep,mode=mode,
                        answer=outcome["answer"],par2_s=outcome["par2_s"],
                        decision=outcome["decision"],
                        lemmas=outcome["used_added_clauses"],
                        conflicts=outcome["stats"]["conflicts"])),flush=True)
    ck(len(rows)==5*REPS*len(MODES),"missing paired measurements")
    print("R89_SHARD_PASS",a.year,a.shard,len(rows),flush=True)

def audit(a):
    sourced=Path(a.sources);combined=Path(a.combined)
    allrows=[];ids=set();pins=set();runners=set()
    for year in YEARS:
        for shard in range(SHARDS):
            tag=f"{year}-{shard}"
            root=sourced/("r88-sources-"+tag)/"sources"
            mf=root/"manifest.json"
            ck(mf.is_file(),"missing source manifest "+tag)
            manifest=json.loads(mf.read_text())
            ck(manifest["protocol"]==SOURCE_PROTO and
                manifest["year"]==year and manifest["shard"]==shard and
                len(manifest["cases"])==5,"wrong original case cohort")
            for c in manifest["cases"]:
                ck(sha(root/c["filename"])==c["sha256"],"original SHA drift")
                ck(c["sha256"] not in ids,"cross-shard repeated source")
                ids.add(c["sha256"])
            p=combined/("r89-results-"+tag)/"results"/"rows.json"
            ck(p.is_file(),"missing finished shard "+tag)
            report=json.loads(p.read_text())
            ck(report["protocol"]==PROTO and
                report["original_manifest_sha256"]==sha(mf) and
                report["year"]==year and report["shard"]==shard,
                "source or protocol mismatch")
            ck(report["runner"] and report["commit"] and report["run_id"],
                "missing runner/commit provenance")
            runners.add((report["runner"],report["commit"],report["run_id"]))
            pins.add(report["pinned_clean_sha256"])
            rr=report["rows"]
            ck(len(rr)==5*REPS*len(MODES),"missing paired trials")
            for c in manifest["cases"]:
                for rep in range(REPS):
                    pair=[x for x in rr if x["source_sha"]==c["sha256"] and
                          x["rep"]==rep]
                    ck(len(pair)==len(MODES) and
                       {x["mode"] for x in pair}==set(MODES),"missing arm")
                    ck(all(x["answer"] in ("SAT","UNSAT","TIMEOUT") and
                           (x["par2_s"]==CAP*2 if x["answer"]=="TIMEOUT"
                            else 0<=x["par2_s"]<=CAP) and
                            x["charged_prep_s"]>=0 and
                            0<=x["used_added_clauses"]<=16
                           for x in pair),"budget/answer error")
                    ck(len({x["answer"] for x in pair if x["answer"]!="TIMEOUT"})<=1,
                       "contradictory solver outcomes")
                    by={x["mode"]:x for x in pair}
                    ck(by["clean"]["used_added_clauses"]==0 and
                       by["certified8"]["used_added_clauses"]<=8 and
                       by["placebo"]["used_added_clauses"]==
                       by["certified8"]["used_added_clauses"],
                       "placebo/certified8 source control failed")
            allrows+=rr
    ck(len(ids)==60 and len(allrows)==60*REPS*len(MODES) and
       len(pins)==1,
       "incomplete 60-source binary/runner cohort")
    groups={}
    for group,rows in (("ALL",allrows),
        ("ARCHIVE",[r for r in allrows if r["year"]==0]),
        ("SAT2025",[r for r in allrows if r["year"]==2025]),
        ("SAT2026",[r for r in allrows if r["year"]==2026]),
        ("DISCONNECTED",[r for r in allrows if r["features"]["components"]!=1])):
        groups[group]={}
        for mode in MODES:
            rr=[x for x in rows if x["mode"]==mode]
            groups[group][mode]=dict(n=len(rr),
               solved=sum(x["answer"]!="TIMEOUT" for x in rr),
               par2_s=round(sum(x["par2_s"] for x in rr),6),
               prep_s=round(sum(x["charged_prep_s"] for x in rr),6),
               extra_clauses=sum(x["used_added_clauses"] for x in rr),
               counter_completions=sum(x["answer"]!="TIMEOUT" and
                   x["stats"]["conflicts"] is not None for x in rr))
    paired={}
    for r in allrows:paired.setdefault((r["source_sha"],r["mode"]),[]).append(r)
    bootstrap={}; rng=random.Random(890114)
    for mode in MODES[1:]:
        diffs=[sum(x["par2_s"] for x in paired[s,"clean"])/REPS
              -sum(x["par2_s"] for x in paired[s,mode])/REPS for s in sorted(ids)]
        draws=sorted(sum(diffs[rng.randrange(len(diffs))] for _ in diffs)/len(diffs)
                     for _ in range(3000))
        bootstrap[mode]=dict(mean_saved_s_per_source=round(statistics.mean(diffs),6),
          bootstrap_95ci_s=[round(draws[74],6),round(draws[2924],6)])
    # Source-level diagnosis is DESCRIPTIVE, never a gating feature.
    diagnostic=[]
    for r in allrows:
        if r["source_id"]==NEGATIVE_DIAGNOSTIC_ID:
            diagnostic.append({k:r[k] for k in
               ("source_id","mode","rep","decision","par2_s","charged_prep_s",
                "used_added_clauses")})
    modes_with_study=[x for x in allrows if
        x["mode"] in ("structure_gate","marginal_probe")]
    decisions=dict(collections.Counter(x["decision"] for x in modes_with_study))
    result=dict(protocol=PROTO,status="PASS_KNOWN_SOURCE_DEVELOPMENT_ONLY",
       total_trials=len(allrows),distinct_sources=len(ids),pinned_binary_sha=next(iter(pins)),
       groups=groups,paired_bootstrap=bootstrap,gate_decisions=decisions,
       known_negative_formula_diagnostic=diagnostic,
       limitations=[
        "R89 selected policies after R88.3 diagnostics, on the exact same known 60 source inputs; no independent holdout.",
        "No runtime labels, solved times or source identifiers participate in gate decisions.",
        "Full 12s budget includes source parse, features, certified learning, marginal probing and solve, as applicable.",
        "A positive marginal BCP propagation signal is a heuristic, not proven CDCL acceleration.",
        "Only original-CNF SAT witness checks, no independent UNSAT LRAT validation.",
        "Kissat -s statistical counters available only for finished solves, never inferred for timeout.",
        "Inter-run timing variability on hosted GitHub hardware can exceed observed small differences.",
        "Historical analytic databases and frozen V15.3.1 unchanged."
       ])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    write(out/"r89-final.json",result)
    with (out/"r89-paired.csv").open("w",newline="") as f:
        columns=("source_sha","source_id","year","rep","mode","structure",
            "answer","par2_s","charged_prep_s","used_added_clauses","decision")
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for r in allrows:w.writerow({k:r[k] for k in columns})
    db=sqlite3.connect(out/"r89_targeted.sqlite")
    db.execute("CREATE TABLE results (source_sha TEXT, source_id TEXT, year INTEGER, rep INTEGER, mode TEXT, answer TEXT, par2 REAL, prep REAL, admitted INTEGER, decision TEXT, conflicts INTEGER, PRIMARY KEY(source_sha,rep,mode))")
    db.executemany("INSERT INTO results VALUES(?,?,?,?,?,?,?,?,?,?,?)",[
       (r["source_sha"],r["source_id"],r["year"],r["rep"],r["mode"],
        r["answer"],r["par2_s"],r["charged_prep_s"],r["used_added_clauses"],
        r["decision"],r["stats"]["conflicts"]) for r in allrows])
    db.commit();db.close()
    lines=["# R89 targeted cooperative admission laboratory",
      "", "**Development replay of known 60 original CNFs — NOT blind holdout**.",
      "Each method gets one 12s start-to-finish capped interval.",
      "","| Group | Solver | Solved | PAR-2 s | Preprocessing s | Admitted clauses |",
      "|---|---|---:|---:|---:|---:|"]
    for group,rs in groups.items():
        for mode,q in rs.items():
            lines.append(f"| {group} | {mode} | {q['solved']}/{q['n']} | {q['par2_s']:.3f} | {q['prep_s']:.3f} | {q['extra_clauses']} |")
    lines+=["","## Gate decisions"]+[f"- {k}: {v}" for k,v in sorted(decisions.items())]
    lines+=["","## Original-source bootstrap (seconds saved vs clean; 95% CI)"]
    lines+=[f"- {k}: {v}" for k,v in bootstrap.items()]
    lines+=["","## Known regression formula — diagnostic only"]
    lines +=[f"- {r}" for r in diagnostic]
    lines+=["","## Limitations"]+["- "+x for x in result["limitations"]]
    (out/"r89-report.md").write_text("\n".join(lines)+"\n")
    print("R89_FULL_PAIRED_AUDIT_PASS",len(allrows),
          json.dumps(groups["ALL"],sort_keys=True),flush=True)

def selftest():
    ck(len(MODES)==5 and CAP==12 and REPS==2,"fixed protocol changed")
    f=dict(components=2,clauses=5000,active_variables=500,
           binary_fraction=.95,horn_fraction=.99)
    ck(not structural_gate(f)[0],"disconnected must never receive broadcast")
    f["components"]=1
    ck(structural_gate(f)[0],"connected dense source should be eligible")
    f["binary_fraction"]=.01;f["horn_fraction"]=.1
    ck(not structural_gate(f)[0],"sparse source should be skipped")
    ck(marginal_bcp_probe([],[])["eligible"] is False,"no-lemma fallback")
    # Soundness logic still lives in old cooperative_learn / v2.select_useful.
    toy=[(1,),(-1,2),(3,4)]
    raw,stats=old.cooperative_learn(toy,max_lemmas=16,rounds=2)
    x,_=v2.select_useful(toy,raw,stats)
    ck(len(x)<=16 and all(entry["bcp_verified"] for entry in stats["proof_chain"]),
       "RUP proof ledger missing")
    print("R89_PRECOMMITTED_SOURCE_GATE_AND_RUP_SELFTEST_PASS")

if __name__=="__main__":
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    m=sub.add_parser("measure")
    for k in ("sources","compiled","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--year",type=int,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):a.add_argument("--"+k,required=True)
    z=p.parse_args()
    if z.cmd=="selftest":selftest()
    elif z.cmd=="measure":measure(z)
    else:audit(z)
