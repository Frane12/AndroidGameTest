#!/usr/bin/env python3
"""MRE4 P1: actual watched-binary reason telemetry on two certified CRR lemmas.

Uses a source-pinned, instrumented CryptoMiniSat 5.11.15 to attribute
non-inprocessing CDCL watched-clause visits, unit implications and conflicts
to the *actual internal watch IDs* assigned during native clause insertion.
All modes use this exact patched library with same config and equal paired
source SHA+seed. Does not imply improved performance, only verified events.
"""
from __future__ import annotations

import argparse, collections, hashlib, json, os, pathlib, random, re
import statistics, subprocess, sys, tempfile, time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre1_cross_representation as mre1
import mre2_impact_gate as mre2
import mre2_cdcl_pilot as pilot
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

PROTO="DRNAS-MRE4-PINNED-CMS-IN-CDCL-WATCH-ID-2CLAUSE-2SEED-2REPEAT-v1"
ROOT=pathlib.Path("mre4")
MODES=("xor_baseline","shadow","lemma_0","lemma_1","both","all8")
SEEDS=2
REPS=2
CAP=22.0


def need(b,why):
    if not b:
        raise RuntimeError("MRE4_FAIL_CLOSED "+str(why))


def setup():
    case=pilot.select_case(0)
    source=r195.FROZEN/case["name"]
    need(r195.digest(source)==case["sha256"],"frozen SHA mismatch")
    n,original=exact.parse_dimacs(source)
    rows,proofs,dinfo=mre1.derive(original)
    need(dinfo["proof_replayed"],"missing independent proof replay")
    selected,gate=mre2.gate(original,proofs)
    need(len(proofs)==8 and len(selected)==2,
         "expected 8 proof-checked CRR clauses and 2 selected")
    need(all(len(rec["clause"])==2 for rec in selected),
         "this instrument only traces binary selected lemmas")
    tags=[tuple(rec["clause"]) for rec in selected]
    need(tags[0]!=tags[1],"duplicate tagged clause")
    print("MRE4_TARGET",json.dumps(dict(sha=case["sha256"],
          name=case["name"],vars=n,original_clauses=len(original),
          proof_checked=len(proofs),gate_selected=len(selected),
          tag0=tags[0],tag1=tags[1],gate=gate),sort_keys=True),flush=True)
    return case,source,n,original,rows,proofs,selected,tags


def parse_trace(text):
    regex=r"^DRNAS_TRACE tag=([01]) attached=(\d+) id=(\d+) visits=(\d+) units=(\d+) conflicts=(\d+)$"
    found=[(int(m[1]),[int(m[i]) for i in range(2,7)])
           for m in re.finditer(regex,text,re.M)]
    need(len(found)==2 and {v[0] for v in found}=={0,1},
         "missing two native CDCL trace records")
    m=re.search(r"^DRNAS_TRACE_INPUT marked0=(\d+) marked1=(\d+) original_count=(\d+) total_count=(\d+)$",text,re.M)
    need(m is not None,"missing tagged-CNF input ledger")
    return {v[0]:dict(attached=v[1][0],id=v[1][1],
            visits=v[1][2],units=v[1][3],conflicts=v[1][4]) for v in found}, \
           dict(marked0=int(m[1]),marked1=int(m[2]),
                original_count=int(m[3]),total_count=int(m[4]))


def run_one(shared,rep,repeat,mode,binary):
    case,source,n,original,rows,proofs,selected,tags=shared
    start=time.perf_counter()
    if mode=="all8":
        imported=proofs
    elif mode=="both":
        imported=selected
    elif mode.startswith("lemma_"):
        imported=[selected[int(mode.split("_")[1])]]
    else:
        imported=[]
    need(all(tuple(p["clause"]) in {tuple(q["clause"]) for q in proofs}
             for p in imported),"unproven imported lemma")
    # Every prep arm independently reconstructs and checks the source XORs.
    mre1.replay_source_xors(original,rows)
    meta_src=rows
    prep_s=time.perf_counter()-start
    seed=int(hashlib.sha256((mre2.PROTO+case["sha256"]+str(rep))
                           .encode()).hexdigest()[:8],16)
    status="TIMEOUT"
    native={}
    trace=None
    trace_input=None
    core_s=None
    with tempfile.TemporaryDirectory(prefix="drnas-mre4-") as tmp:
        d=pathlib.Path(tmp)
        cnf,xor,empty=d/"input.cnf",d/"source.tsv",d/"empty.tsv"
        mre1.write_cnf(cnf,n,original,imported)
        mre1.write_xors(xor,meta_src)
        empty.write_text("")
        env=os.environ.copy()
        env["DRNAS_TAG_0"]=",".join(str(l) for l in tags[0])
        env["DRNAS_TAG_1"]=",".join(str(l) for l in tags[1])
        env["DRNAS_ORIG_COUNT"]=str(len(original))
        remain=CAP-(time.perf_counter()-start)
        if remain>0.1:
            t=time.perf_counter()
            try:
                p=subprocess.run([str(pathlib.Path(binary).resolve()),str(cnf),
                   str(xor),str(empty),"source_xor_no_gauss",str(seed)],
                   text=True,capture_output=True,timeout=remain,
                   env=env,check=False)
            except subprocess.TimeoutExpired:
                p=None
            core_s=time.perf_counter()-t
            if p is not None:
                need(p.returncode==0,"tagged CMS failed: "+p.stderr[-900:])
                status,model,native=r195.parsed_native(p.stdout)
                trace,trace_input=parse_trace(p.stdout)
                if status=="SAT":
                    r195.verify_model(source,model)
                need(status==case["expected"],"incorrect native verdict")
                need(trace_input["original_count"]==len(original),
                     "incorrect baseline clause input count")
                need(trace_input["total_count"]==len(original)+len(imported),
                     "input clause count")
                for tag in (0,1):
                    ought=sum(1 for q in imported if tuple(q["clause"])==tags[tag])
                    need(ought==trace_input["marked%d"%tag]==trace[tag]["attached"],
                         "tagged CRR clause was not attached to native binary watcher")
                    need(trace[tag]["visits"]>=trace[tag]["units"]+trace[tag]["conflicts"],
                         "invalid event counter invariant")
    wall_s=time.perf_counter()-start
    if wall_s>=CAP:
        status="TIMEOUT"
    return dict(protocol=PROTO,source_sha256=case["sha256"],
                case=case["name"],rep=rep,repeat=repeat,seed=seed,
                mode=mode,status=status,wall_s=round(wall_s,6),
                core_s=round(core_s,6) if core_s is not None else None,
                prep_s=round(prep_s,6),
                par2_s=round(2*CAP if status=="TIMEOUT" else wall_s,6),
                imported=len(imported),source_xor_rows=len(rows),
                native_cdcl_propagations=native.get("propagations"),
                native_cdcl_conflicts=native.get("conflicts"),
                native_cdcl_decisions=native.get("decisions"),
                actual_native_watch_tags=trace,
                trace_input=trace_input,
                selected_binary_clauses=tags,otf_gauss=False,
                proof=("ORIGINAL_CNF_SAT_MODEL_CHECKED" if status=="SAT"
                       else "UNSAT_NO_INDEPENDENT_LRAT" if status=="UNSAT"
                       else "CAP_TIMEOUT"),
                instrumented_source_commit="3b709118fd08eb1d15f25e0e239dbc596f967b60",
                github_sha=os.environ.get("GITHUB_SHA","local"))


def run_shard(seed_index,binary):
    need(seed_index in (0,1),"seed index")
    shared=setup()
    ROOT.mkdir(parents=True,exist_ok=True)
    out=[]
    for repeat in range(REPS):
        arms=list(MODES)
        random.Random(PROTO+str(seed_index)+str(repeat)).shuffle(arms)
        for mode in arms:
            row=run_one(shared,seed_index,repeat,mode,binary)
            out.append(row)
            (ROOT/("seed-%d.json"%seed_index)).write_text(
                json.dumps(out,sort_keys=True)+"\n")
            print("MRE4_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(out)==REPS*len(MODES)==12,"missing paired native trace trials")
    print("MRE4_SHARD_PASS",seed_index,len(out),flush=True)


def audit():
    rows=[]
    for seed in range(SEEDS):
        rows+=json.loads((ROOT/("seed-%d.json"%seed)).read_text())
    need(len(rows)==SEEDS*REPS*len(MODES)==24,"missing source-paired records")
    paired=collections.defaultdict(dict)
    for row in rows:
        need(row["protocol"]==PROTO and row["otf_gauss"] is False,
             "protocol or OTF mismatch")
        need(row["instrumented_source_commit"]==
             "3b709118fd08eb1d15f25e0e239dbc596f967b60",
             "upstream source changed")
        need(row["source_sha256"]==pilot.select_case(0)["sha256"],
             "source SHA changed")
        need(row["status"]=="SAT" and
             row["proof"]=="ORIGINAL_CNF_SAT_MODEL_CHECKED",
             "expected independently validated SAT")
        need(row["actual_native_watch_tags"] is not None,
             "no per-binary watcher events")
        for tag in (0,1):
            tr=row["actual_native_watch_tags"][str(tag)]
            need(tr["attached"] in (0,1),"bad tag attachment")
            need(tr["visits"]>=tr["units"]+tr["conflicts"],
                 "tag stats corrupted")
        key=(row["rep"],row["repeat"])
        need(row["mode"] not in paired[key],"duplicate mode")
        paired[key][row["mode"]]=row
    for p in paired.values():
        need(set(p)==set(MODES),"missing control arm")
        need(len({x["seed"] for x in p.values()})==1,"paired native seed mismatch")
        need(len({tuple(map(tuple,x["selected_binary_clauses"]))
                  for x in p.values()})==1,"tag clause drift")
    summary={}
    for mode in MODES:
        q=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(
            par2_s=round(sum(r["par2_s"] for r in q),6),
            mean_core_s=round(statistics.mean(r["core_s"] for r in q),6),
            prep_s=round(sum(r["prep_s"] for r in q),6),
            mean_cdcl_propagations=round(statistics.mean(
                r["native_cdcl_propagations"] for r in q),2),
            mean_cdcl_decisions=round(statistics.mean(
                r["native_cdcl_decisions"] for r in q),2),
            mean_cdcl_conflicts=round(statistics.mean(
                r["native_cdcl_conflicts"] for r in q),2),
            watch0_visits=sum(r["actual_native_watch_tags"]["0"]["visits"] for r in q),
            watch0_units=sum(r["actual_native_watch_tags"]["0"]["units"] for r in q),
            watch0_conflicts=sum(r["actual_native_watch_tags"]["0"]["conflicts"] for r in q),
            watch1_visits=sum(r["actual_native_watch_tags"]["1"]["visits"] for r in q),
            watch1_units=sum(r["actual_native_watch_tags"]["1"]["units"] for r in q),
            watch1_conflicts=sum(r["actual_native_watch_tags"]["1"]["conflicts"] for r in q),
            clause0_attached=sum(r["actual_native_watch_tags"]["0"]["attached"] for r in q),
            clause1_attached=sum(r["actual_native_watch_tags"]["1"]["attached"] for r in q))
    per_pair=[]
    for (seed,repeat),p in sorted(paired.items()):
        base=p["xor_baseline"]
        per_pair.append(dict(seed=seed,repeat=repeat,
            baseline_s=base["wall_s"],
            arms={k:dict(time_s=v["wall_s"],
               delta_vs_xor_s=round(v["wall_s"]-base["wall_s"],6),
               tag0=v["actual_native_watch_tags"]["0"],
               tag1=v["actual_native_watch_tags"]["1"])
               for k,v in p.items()}))
    report=dict(protocol=PROTO,measurements=24,
      original_SHA=rows[0]["source_sha256"],
      cms_pinned_upstream_sha=rows[0]["instrumented_source_commit"],
      native_binary_watch_ID_tagging=True,
      event_scope="non-inprocessing PropEngine::prop_bin_cl visited/unit/conflict",
      does_NOT_observe_removed_or_rewritten_watch_IDs=True,
      independent_original_SAT_witness_check=True,
      trial_pins=sorted({(r["rep"],r["seed"]) for r in rows}),
      non_blind_reused_official_formula=True,
      summary=summary,paired=per_pair)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE4_FINAL",json.dumps(report,sort_keys=True),flush=True)


def selftest():
    need(SEEDS*REPS*len(MODES)==24,"wrong design")
    need(MODES[2:4]==("lemma_0","lemma_1"),"missing separate clause tracing")
    print("MRE4_SELFTEST_PASS",PROTO,flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","shard","audit"))
    ap.add_argument("--seed",type=int,default=0)
    ap.add_argument("--binary",default="mre4/native")
    a=ap.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":run_shard(a.seed,a.binary)
    else:audit()
