#!/usr/bin/env python3
"""R83: honest native live XOR-CDCL reason-bridge controlled experiment.

Reuses SHA-checked, already soundness-tested R32u native Kissat engine.
Unlike pre-solve clause injection, R32u's active mode evaluates sound GF2
rows on the ACTUAL CDCL assignment trail and assigns implied literals with
native CNF reasons. R83 adds a source-structure gate with runtime scan cost.
Replays R82's independently chosen real 2025/2026 originals: NOT new holdout.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, random, re, subprocess, time
from pathlib import Path
import r32p_real_satcomp26_benchmark as r32p
import r63_real2026_xor_prevalence_fallback as r63
import r32t_certified_short_xor as cert

PROTO="DRNAS-R83-NATIVE-LIVE-XOR-CDCL-R82-WIDE-CONTROL-20261104-v1"
R82_PROTO="DRNAS-R82-WIDE-OFFICIAL-2025-2026-NOSCREEN-20261104-v1"
CAP=35.0
REPS=2
SHARDS=12
MODES=("clean_pinned","passive_native","active_native","r83_structural_gate",
       "kissat_404","cadical_301")
SOURCE_ROW=re.compile(r"^c R32U_SOURCE_ROW rhs=(\d+) vars=([\d,]+)$",re.M)
XOR_ASSIGN=re.compile(r"^c R32U_ASSIGN equation=(\d+) target_ext=(\d+) sign=(-?\d+)",re.M)
MODE=re.compile(r"^c R32U_MODE active=(\d+) prepared=(\d+) max_reasons=(\d+)$",re.M)
STATS=re.compile(r"^c R32U_STATS active=(\d+) rows=(\d+) scans=(\d+) candidates=(\d+) attached=(\d+)",re.M)

def ck(cond,msg):
    if not cond: raise RuntimeError("R83_FAIL_CLOSED "+str(msg))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()
def outjson(path,obj): Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def expected_gate(case):
    return bool(case["supported"] and case["complete_blocks"] is not None
                and case["complete_blocks"]>=2)

def source_prove_rows(original, emitted):
    """Independent linear-span proof using only complete ORIGINAL CNF XOR blocks."""
    if not emitted:return 0
    source,guard=cert.load_original(original)
    ck(guard is None,"native emitted XOR rows outside independent source proof scope "+str(guard))
    axioms=cert.complete_parity_axioms(source)
    basis={}
    def insert(bits,rhs):
        while bits:
            pivot=(bits&-bits).bit_length()
            if pivot not in basis:
                basis[pivot]=(bits,rhs)
                return
            bits^=basis[pivot][0];rhs^=basis[pivot][1]
        ck(not rhs,"contradictory XOR axiom in source proof")
    for vs,rhs in axioms:
        insert(cert.to_bitrow(vs),rhs)
    for vs,rhs in emitted:
        bits=cert.to_bitrow(vs)
        while bits:
            pivot=(bits&-bits).bit_length()
            ck(pivot in basis,"native XOR row is outside original parity span")
            bits^=basis[pivot][0];rhs^=basis[pivot][1]
        ck(rhs==0,"native XOR parity differs from original source entailment")
    return len(emitted)

def native_telemetry(stdout,mode,source,proof_cache):
    emitted=[(tuple(int(v) for v in variables.split(",")),int(rhs))
             for rhs,variables in SOURCE_ROW.findall(stdout)]
    mode_label=MODE.findall(stdout)
    events=XOR_ASSIGN.findall(stdout)
    if mode in ("clean_pinned","kissat_404","cadical_301"):
        ck(not emitted and not events,"world reference solver emitted native XOR hooks")
        return dict(source_rows=0,events=0,reason_attached_at_least=0,
                    native_mode="none",original_parity_proof_checked=False)
    ck(len(mode_label)<=1,"multiple incompatible native XOR activation tags")
    active=(mode=="active_native" or mode=="r83_structural_gate")
    if mode_label:
        ck(int(mode_label[0][0])==int(active),"native active/passive selector mismatch")
        ck(int(mode_label[0][1])==len(emitted),"source parity count mismatch")
    else:
        ck(not emitted and not events,"native XOR output without active mode record")
    if mode=="passive_native":ck(not events,"passive XOR performed forbidden active assignment")
    # Proof check is independent of solve timing: both versions run on same
    # binary, the source proof verifier is benchmarking infrastructure.
    if emitted:
        key=sha(source)
        prior=proof_cache.get(key)
        if prior is None:
            verified=source_prove_rows(source,emitted)
            proof_cache[key]=tuple(emitted)
        else:
            ck(prior==tuple(emitted),"source native parity rows changed across repetitions")
            verified=len(emitted)
    else: verified=0
    st=STATS.findall(stdout)
    lower=len(events)
    if st:lower=max(lower,int(st[-1][4]))
    return dict(source_rows=len(emitted),events=len(events),
                reason_attached_at_least=lower,
                native_mode="active" if active else "passive",
                original_parity_proof_checked=(verified==len(emitted)))

def run_one(mode,source,case,paths,proof_cache):
    start=time.monotonic()
    which=mode
    used_gate=False
    features=None
    if mode=="r83_structural_gate":
        features=r63.inspect_exact_xor(source,case["variables"],case["clauses"])
        ck(features["supported"]==case["supported"] and
           features["complete_blocks"]==case["complete_blocks"] and
           features["pure_exact_xor"]==case["pure_exact_xor"],
           "R83 gate scan differs from frozen original-source structure")
        used_gate=bool(features["supported"] and features["complete_blocks"] is not None
                       and features["complete_blocks"]>=2)
        if not used_gate:which="clean_pinned"
    binary=paths["native"] if which in ("passive_native","active_native","r83_structural_gate") \
                else paths[which]
    env=os.environ.copy()
    if binary==paths["native"]:
        env.update(R32B_MODE="r32u",R32U_ACTIVE="1" if which!="passive_native" else "0",
                   R32S_PASSIVE_TRACE="0",R32L_TRACE="0",R32M_PHASES="0")
    remain=CAP-(time.monotonic()-start)
    answer="TIMEOUT";stdout="";stderr="";finished=False
    if remain>0:
        try:
            p=subprocess.run([str(binary),str(source)],capture_output=True,text=True,
                errors="replace",timeout=remain,env=env)
            stdout=p.stdout;stderr=p.stderr
            ck(p.returncode in (10,20),
               "unexpected exit "+str(p.returncode)+" "+stderr[-320:])
            answer="SAT" if p.returncode==10 else "UNSAT"
            finished=True
        except subprocess.TimeoutExpired as exc:
            stdout=exc.stdout or b""
            if isinstance(stdout,bytes): stdout=stdout.decode(errors="replace")
            stderr=exc.stderr or b""
            if isinstance(stderr,bytes): stderr=stderr.decode(errors="replace")
    if answer=="SAT": r32p.verify_sat_witness(source,stdout)
    wall=time.monotonic()-start
    solved=finished and wall<=CAP
    if case["source_verified_status"] and solved:
        ck(answer==case["official_status"],"published official SAT2026 status mismatch")
    telemetry=native_telemetry(stdout,which,source,proof_cache)
    return dict(answer=answer if solved else "TIMEOUT",solved=solved,
        wall_s=round(min(wall,CAP),6),par2_s=round(wall if solved else 2*CAP,6),
        solver_binary=which,gate_activated=used_gate,
        native=telemetry,source_sat_witness_checked=(answer=="SAT"),
        official_status_verified=(case["source_verified_status"] if solved else None),
        unsat_proof_independently_replayed=False)

def measure(a):
    root=Path(a.sources)
    mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==R82_PROTO and len(mf["cases"])==48,"R82 frozen source provenance mismatch")
    ck(0<=a.shard<SHARDS,"shard index")
    compiled=Path(a.compiled).resolve();world=Path(a.world).resolve()
    import subprocess as sp
    ck(sp.run(["sha256sum","-c","baselines.sha256"],cwd=compiled,
              stdout=sp.DEVNULL).returncode==0,"R32u clean/native binaries changed")
    ck(sp.run(["sha256sum","-c","binaries.sha256"],cwd=world,
              stdout=sp.DEVNULL).returncode==0,"world solver binaries changed")
    paths=dict(clean_pinned=compiled/"clean",native=compiled/"native",
               kissat_404=world/"kissat_4_0_4",cadical_301=world/"cadical_3_0_1")
    ck(all(p.exists() and os.access(p,os.X_OK) for p in paths.values()),
       "missing executable solver")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    work=Path(a.out);work.mkdir(parents=True,exist_ok=True)
    rows=[];proof_cache={}
    manifest_sha=sha(root/"manifest.json")
    for case in mf["cases"][a.shard::SHARDS]:
        source=root/case["filename"]
        ck(sha(source)==case["sha256"],"original DIMACS changed")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(hashlib.sha256(
                (PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
            for mode in modes:
                result=run_one(mode,source,case,paths,proof_cache)
                row=dict(gbd=case["gbd"],sha256=case["sha256"],
                         group=case["group"],year=case["year"],
                         xor_positive=case["structural_xor_positive"],
                         prior_drnas_benchmarked=case["prior_drnas_benchmarked"],
                         rep=rep,mode=mode,**result)
                rows.append(row)
                outjson(work/"r83-shard.json",dict(protocol=PROTO,shard=a.shard,
                        source_manifest_sha=manifest_sha,
                        binaries={k:sha(v) for k,v in paths.items()},
                        rows=rows))
                print("R83_TRIAL",json.dumps({k:row[k] for k in
                    ("gbd","group","rep","mode","answer","wall_s","par2_s",
                     "gate_activated")}),flush=True)
    ck(len(rows)==len(mf["cases"][a.shard::SHARDS])*REPS*len(MODES),
       "shard incomplete")
    print("R83_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==R82_PROTO and len(mf["cases"])==48,"R82 source cohort drift")
    cases=mf["cases"];rows=[];pins=set()
    for shard in range(SHARDS):
        path=Path(a.combined)/("r83-shard-"+str(shard))/"results"/"r83-shard.json"
        ck(path.is_file(),"missing shard "+str(shard))
        j=json.loads(path.read_text())
        ck(j["protocol"]==PROTO and j["shard"]==shard and
           j["source_manifest_sha"]==sha(root/"manifest.json"),
           "shard data provenance mismatch")
        pins.add(json.dumps(j["binaries"],sort_keys=True))
        ck(len(j["rows"])==len(cases[shard::SHARDS])*REPS*len(MODES),
           "wrong shard trial count")
        rows.extend(j["rows"])
    ck(len(pins)==1 and len(rows)==len(cases)*REPS*len(MODES),
       "inconsistent SHA binary or incomplete benchmark")
    for case in cases:
        sub=[r for r in rows if r["sha256"]==case["sha256"]]
        ck(len(sub)==REPS*len(MODES),"source missing paired trials")
        for rep in range(REPS):
            part=[r for r in sub if r["rep"]==rep]
            ck(len(part)==len(MODES) and set(x["mode"] for x in part)==set(MODES),
               "unpaired mode permutation")
            answers={r["answer"] for r in part if r["answer"]!="TIMEOUT"}
            ck(len(answers)<=1,"SAT/UNSAT contradictory verdict")
            if case["source_verified_status"]:
                ck(all(v==case["official_status"] for v in answers),
                   "official SAT2026 answer discrepancy")
            for r in part:
                ck(r["native"]["original_parity_proof_checked"] or
                   r["native"]["source_rows"]==0,"missing original CNF linear source certification")
                if r["mode"]=="passive_native":
                    ck(r["native"]["reason_attached_at_least"]==0,
                       "passive control modified native trail")
                if r["mode"]=="r83_structural_gate":
                    ck(r["gate_activated"]==expected_gate(case),
                       "structural gate drift")
    groups={"ALL":cases,
            "YEAR_2025":[c for c in cases if c["year"]==2025],
            "YEAR_2026":[c for c in cases if c["year"]==2026],
            "XOR_PRESENT":[c for c in cases if c["structural_xor_positive"]],
            "CONTROL":[c for c in cases if not c["structural_xor_positive"]]}
    summary={}
    for group,group_cases in groups.items():
        ids={c["sha256"] for c in group_cases}
        summary[group]={}
        for mode in MODES:
            rr=[r for r in rows if r["sha256"] in ids and r["mode"]==mode]
            summary[group][mode]=dict(trials=len(rr),solved=sum(x["solved"] for x in rr),
                par2_s=round(sum(x["par2_s"] for x in rr),6),
                attached_lower_bound=sum(x["native"]["reason_attached_at_least"] for x in rr),
                native_source_rows=sum(x["native"]["source_rows"] for x in rr))
    rng=random.Random(831341)
    inference={}
    for group in ("ALL","YEAR_2025","YEAR_2026","XOR_PRESENT","CONTROL"):
        cs=groups[group];paired=[]
        for c in cs:
            results=[r for r in rows if r["sha256"]==c["sha256"]]
            p={m:sum(r["par2_s"] for r in results if r["mode"]==m)/REPS for m in MODES}
            paired.append(p)
        inference[group]={}
        for mode,base in (("active_native","passive_native"),
                          ("r83_structural_gate","clean_pinned"),
                          ("r83_structural_gate","active_native")):
            n=len(paired);diff=[x[base]-x[mode] for x in paired]
            if n:
                samples=[]
                for _ in range(2000):
                    samples.append(sum(diff[rng.randrange(n)] for _ in range(n))/n)
                samples.sort()
                values=dict(n=n,mean_saved_s=round(sum(diff)/n,6),
                            ci_95_mean_saved_s=[round(samples[50],6),
                                                round(samples[1949],6)])
            else:values=dict(n=0,mean_saved_s=None,ci_95_mean_saved_s=None)
            inference[group][mode+"_minus_"+base]=values
    result=dict(protocol=PROTO,status="PASS_UNOFFICIAL",sources=len(cases),
        trials=len(rows),source_years=mf["year_counts"],
        original_r82_manifest_sha256=sha(root/"manifest.json"),
        solver_sha256=json.loads(next(iter(pins))),
        groups={k:len(v) for k,v in groups.items()},
        summary=summary,paired_bootstrap=inference,rows=rows,
        limitations=[
         "R83 reuses R82 frozen real originals: method development, NOT independent unseen holdout.",
         "R32u native in-process CDCL XOR reason propagation already existed in earlier R32u, now tested more broadly.",
         "R83 adds a precommitted structure gate; runtime scanning fully charged.",
         "Full assignment conflicts and incremental Gaussian trail back-substitution not implemented.",
         "Source rows independently checked by linear span of complete original-CNF XOR equations.",
         "No independent UNSAT proof check in this run: 2025 UNSAT provisional, 2026 checked against published labels.",
         "Kissat 4.0.4 and CaDiCaL 3.0.1 are real comparators, not asserted 2026 winners.",
         "A 35-second timeout differs from official SAT competitions; do not claim world ranking.",
         "Bootstrap unit is unique formula, not each repeated trial."
        ])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    outjson(out/"r83-final.json",result)
    lines=["# DRNAS R83 — native XOR-to-CDCL reason bridge", "",
        "48 frozen R82 original SAT2025/2026 formulas, two repeats, 35s",
        "cap. Provenance SHA audits and independent GF2 source-span proofs.",
        "Native active mode attaches entailed CNF reasons during Kissat's CDCL.",
        "R83 gate enables active mode only on certified XOR structure.",
        "NOT a new-source independent holdout.", "",
        "| Mode | Solved / 96 | PAR2 s | XOR reason attaches (lower bound) |",
        "|---|---:|---:|---:|"]
    for mode,s in summary["ALL"].items():
        lines.append(f"| {mode} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} | {s['attached_lower_bound']} |")
    lines.extend(["","## By source cohort"])
    for group in ("YEAR_2025","YEAR_2026","XOR_PRESENT","CONTROL"):
        lines+=["",f"### {group}","| Mode | Solved | PAR2 s |","|---|---:|---:|"]
        for m,s in summary[group].items():
            lines.append(f"| {m} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} |")
    lines+=["","## Source-paired bootstrap (seconds saved, 95% CI)"]
    for group,comp in inference.items():
        for name,v in comp.items():
            lines.append(f"- {group}, {name}: {v}")
    lines+=["","## Limits"]+["- "+x for x in result["limitations"]]
    (out/"r83-final.md").write_text("\n".join(lines)+"\n")
    print("R83_FINAL_AUDIT_PASS",json.dumps(summary["ALL"]),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    m=sub.add_parser("measure")
    for k in ("sources","compiled","world","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):a.add_argument("--"+k,required=True)
    x=p.parse_args()
    if x.cmd=="measure":measure(x)
    else:audit(x)
if __name__=="__main__":main()
