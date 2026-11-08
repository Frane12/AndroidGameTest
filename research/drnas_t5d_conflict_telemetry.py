#!/usr/bin/env python3
"""DRNAS T5D: source-pinned conflict/decision forensics, not a benchmark claim.

Reuses EXACT SUCCESSFUL T5 compiled CaDiCaL binary, source manifest, and
original CNF bytes from run 42480784137. It only shortens the *internal*
solver time cap equally in all four arms (while retaining the external
watchdog cap), so CaDiCaL can print statistics and the bridge can emit a
terminal result even on previously censored TIMEOUT cases. Results are
diagnostic and MUST NOT be combined with official T5 PAR-2.
"""
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import sys
import time

ROOT=pathlib.Path("ultimate_t5")
OUT=pathlib.Path("t5d")
RUN=42480784137
SOURCE_COMMIT="9e19b29dbaf203392ed54bd8fce324b21cc5d30d"
MANIFEST_SHA="2e6169009e985555e43e81d9b534f3bb307cef93963329694ef42459bef3c2e2"
TARGETS=[
"99718c1729a8de3347a9946f1836421d",  # 114 proposals / 48 reason completions
"27495ba0093076d2e39a9b218e521ee2",  # eligible, zero proposals
"6d815089fb4095208754622b4c44a8f7"  # 1.2s prep regression
]
MODES=("t_clean","t5_novel_shadow","t5_novel_active","t2_derived_rows")
REPS=2
MARGIN_S=1.5

sys.path.insert(0,str(pathlib.Path("research").resolve()))
import ultimate_t5_benchmark as bench

def need(b,msg):
    if not b:raise RuntimeError("T5D_AUDIT_FAIL_CLOSED "+str(msg))

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def reference():
    need(bench.PROTO=="DRNAS-T5-20261108-CERTIFIED-NOVEL-GF2-8ARM-PAIRED-v1",
         "wrong frozen T5 protocol")
    pin=json.loads((ROOT/"build-pin.json").read_text())
    need(pin["source_commit"]==SOURCE_COMMIT,"changed source commit")
    need(pin["original_manifest_sha"]==MANIFEST_SHA,"changed source manifest SHA pin")
    need(digest("ultimate_r2/frozen/manifest.json")==MANIFEST_SHA,
         "source manifest bytes drift")
    for path,sha in pin["binaries"].items():
        need(digest(path)==sha,"binary/source SHA drift: "+path)
    cases={x["id"]:x for x in bench.cases()}
    need(len(cases)==20 and all(x in cases for x in TARGETS),
         "selected original CNF not in frozen cohort")
    for x in TARGETS:
        p=bench.FROZEN/(x+".cnf")
        need(p.exists() and digest(p)==cases[x]["sha256"],
             "original source SHA mismatch "+x)
    return cases,pin

def capture(mode,case,rep):
    source=bench.FROZEN/(case["id"]+".cnf")
    cap=float(case["cap_s"])
    need(cap in (20.,30.),"source cap policy changed")
    # SAME reduced budget for every arm; not comparable to old 20s/30s PAR2.
    external_deadline=time.monotonic_ns()+int(cap*1e9)
    reserved_deadline=external_deadline-int(MARGIN_S*1e9)
    env=dict(os.environ)
    env["ULTIMATE_T_MODE"]=mode
    env["ULTIMATE_R2_DEADLINE_NS"]=str(reserved_deadline)
    script=("import sys,os;"
            "sys.path.insert(0,'research');"
            "import ultimate_t5_fallback as m;"
            "sys.argv=['research/ultimate_t5_fallback.py',sys.argv[1]];"
            "sys.exit(m.main())")
    command=[sys.executable,"-c",script,str(source)]
    start=time.monotonic()
    # A single CPU core per job; current T5 source compiled binary is reused.
    result=subprocess.run(command,env=env,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,timeout=cap+.8)
    wall=time.monotonic()-start
    stdout=result.stdout.decode(errors="replace")
    stderr=result.stderr.decode(errors="replace")
    need(result.returncode in (0,10,20),
         f"native wrapper failed mode={mode} rc={result.returncode} stderr={stderr[-1500:]}")
    match=re.search(r"R166X_RESULT mode=\S+ status=(SAT|UNSAT|UNKNOWN)\b",stdout)
    need(match is not None,f"native terminal result missing {mode}: {stdout[-1200:]}")
    need("R166X_STATS_BEGIN mode=" in stdout and
         "R166X_STATS_END mode=" in stdout,
         f"CaDiCaL terminal statistics missing mode={mode}")
    status=match.group(1)
    need(not (status=="SAT" and case["expected"]=="UNSAT") and
         not (status=="UNSAT" and case["expected"]=="SAT"),
         "original CNF known status contradicted")
    if status=="SAT":
        model=bench.prior.model(result.stdout)
        bench.prior.helper.gf.sat_check(bench.prior.helper.gf.dimacs(source)[1],model)
    # Native UNSAT is checked against known reference result, not independent LRAT.
    gate_match=re.search(r"ULTIMATE_T_GATE (\{[^\n]+\})",stdout)
    need(gate_match is not None,"source gate missing")
    gate=json.loads(gate_match.group(1))
    need(gate["source_sha256"]==case["sha256"],"gate source SHA mismatch")
    begin=stdout.index("R166X_STATS_BEGIN")
    end=stdout.index("R166X_STATS_END",begin)
    stats=stdout[begin:end]
    significant=[v.strip() for v in stats.splitlines()
                 if re.search(r"\b(conflicts?|decisions?|propagations?|learned|learnt|restarts)\b",
                              v,re.I)]
    progress=[]
    for m in re.finditer(r"R166X_PROGRESS ([^\n]+)",stdout):
        progress.append(dict(re.findall(r"(\w+)=([^\s]+)",m.group(1))))
    terminal_line=re.search(r"R166X_RESULT ([^\n]+)",stdout).group(1)
    terminal=dict(re.findall(r"(\w+)=([^\s]+)",terminal_line))
    folder=OUT/"traces";folder.mkdir(parents=True,exist_ok=True)
    name=f"{case['id']}-{mode}-rep{rep}.log"
    (folder/name).write_text(stdout+"\n=== STDERR ===\n"+stderr)
    obj=dict(id=case["id"],source_sha256=case["sha256"],family=case["family"],
             cohort=case["cohort"],mode=mode,rep=rep,
             original_cap_s=cap,internal_reserve_s=MARGIN_S,
             status=status,wall_s=round(wall,6),terminal=terminal,
             gate={k:gate.get(k) for k in
                   ("eligible","reason","selected_rows","derived_rows","prep_s",
                    "native_expected")},
             progress_samples=len(progress),last_progress=(progress[-1] if progress else {}),
             raw_stats_lines=significant,
             stats_printed=True,independent_unsat_lrat=False,
             trace_file=str(folder/name))
    return obj

def run():
    cases,pin=reference()
    if hasattr(os,"sched_getaffinity"):
        cpus=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(cpus)})
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for id in TARGETS:
        c=cases[id]
        for rep in range(REPS):
            order=list(MODES)
            random.Random("T5D-PINNED-CONFLICTS-v1"+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                row=capture(mode,c,rep)
                rows.append(row)
                (OUT/"all-trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
                print("T5D_TRIAL",json.dumps({k:row[k] for k in
                      ("id","mode","rep","status","wall_s","gate","terminal",
                       "raw_stats_lines")},sort_keys=True),flush=True)
    need(len(rows)==len(TARGETS)*len(MODES)*REPS,"trials lost")
    need(all(x["stats_printed"] for x in rows),"partial final statistics")
    summary=dict(protocol="DRNAS-T5D-20261108-PINNED-CONFLICT-STATS-v1",
                 prior_t5_run=RUN,prior_t5_source_commit=SOURCE_COMMIT,
                 original_manifest_sha256=MANIFEST_SHA,
                 cases=TARGETS,methods=MODES,reps=REPS,
                 comparisons_are_diagnostic=True,not_blind=True,
                 interval_not_original_t5_cap=True,
                 internal_reserve_s=MARGIN_S,
                 solver_binaries=pin["binaries"],completed=len(rows),
                 native_unsat_independent_lrat=False,
                 status="T5D_PINNED_STATISTICS_PASS")
    (OUT/"report.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("T5D_PINNED_STATISTICS_PASS",json.dumps({
        "trials":len(rows),"sources":len(TARGETS),"prior_T5_run":RUN,
        "reserved_seconds":MARGIN_S},sort_keys=True),flush=True)

if __name__=="__main__":
    if len(sys.argv)==2 and sys.argv[1]=="verify":
        reference()
        print("T5D_FROZEN_SOURCE_SHA_AND_BINARY_PINS_PASS",flush=True)
    elif len(sys.argv)==2 and sys.argv[1]=="run":
        run()
    else:
        raise SystemExit("usage: drnas_t5d_conflict_telemetry.py verify|run")
