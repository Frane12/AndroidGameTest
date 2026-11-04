#!/usr/bin/env python3
"""R84 four real mixed-XOR formulas, native CDCL diagnostic cohort.

Prospective hypotheses: (1) R32u did not find short safely attachable XOR
relations, (2) the original 16-decision cadence was too sparse, (3) derived
reasons exist but do not reduce conflicts. R84 is a causal ABlation on
ALREADY-SEEN R82/R83 real originals, NOT a new blind performance benchmark.

Same pinned original Kissat source (8af8e56f...), same run, pinned CPU,
45s resource cap. Four modes:
  clean upstream Kissat;
  passive R32u instrumentation (16-decision sampling, NO assignments);
  active R32u 16-decision cadence;
  active R32u 4-decision cadence.
R84 native read-only snapshots contain approximate CDCL conflict progress
at timeout; conflict-after-attachment is NOT proof of reason use by 1-UIP.
"""
from __future__ import annotations
import argparse,hashlib,json,os,random,re,subprocess,time
from pathlib import Path
import r83_live_xor_cdcl_wide as r83
import r32p_real_satcomp26_benchmark as r32p

PROTO="DRNAS-R84-XOR-CDCL-FOUR-STRUCTURAL-FORENSICS-20261104-v1"
SOURCE_PROTO=r83.R82_PROTO
CASES=(
 "66204949278cdd9d81e102eace6d4669",
 "98a991c902324b02349e766ad357cdc6",
 "ae9c53347ee8072745ed230992e164ee",
 "4f09ef861ee74e50dc101765e1ce27fb",
)
MODES=("clean","passive16","active16","active4")
CAP=45.0
REPS=2
SHARDS=4
PROGRESS=re.compile(r"^c R84_PROGRESS (.+)$",re.M)
BEGIN=re.compile(r"^c R84_BEGIN active=(\d+) interval=(\d+) prepared=(\d+)$",re.M)
SOURCE_ROW=r83.SOURCE_ROW

def ck(ok,msg):
    if not ok: raise RuntimeError("R84_FAIL_CLOSED "+str(msg))
def sha(p):return r83.sha(p)
def save(path,data):
    Path(path).write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def cohort(root):
    mf=json.loads((Path(root)/"manifest.json").read_text())
    ck(mf["protocol"]==SOURCE_PROTO and len(mf["cases"])==48,"R82 frozen original cohort drift")
    available={c["gbd"]:c for c in mf["cases"]}
    ck(set(CASES)<=available.keys(),"missing one of four documented mixed-XOR real formulas")
    cases=[available[g] for g in CASES]
    ck(all(c["group"]=="mixed_exact" and c["structural_xor_positive"] for c in cases),
       "not precommitted mixed-XOR cohort")
    return mf,cases

def parse_progress(stdout,mode):
    parsed=[]
    for raw in PROGRESS.findall(stdout):
        try:
            row={k:int(v) if k not in ("cpu_ms",) else float(v)
                 for k,v in (item.split("=",1) for item in raw.split())}
        except Exception as e:
            raise RuntimeError("invalid R84 telemetry "+str(e))
        parsed.append(row)
    if mode=="clean":
        ck(not parsed and not BEGIN.search(stdout),"clean solver has injected monitor")
        return dict(begin=None,snapshots=0,last=None,first=None,
                    attached=0,eligible=0,conflicting_rows=0,
                    conflicts_after_first_attach=0)
    starts=BEGIN.findall(stdout)
    ck(len(starts)==1,"missing or duplicate R84_BEGIN in native stdout")
    active,interval,prepared=map(int,starts[0])
    exp_active,exp_interval=(mode!="passive16"),(4 if mode=="active4" else 16)
    ck(active==exp_active and interval==exp_interval,
       "native GF2 mode / scan interval changed")
    ck(bool(parsed),"no R84 timeout-safe progress snapshots")
    last=parsed[-1];first=parsed[0]
    ck(last["rows"]==prepared and last["active"]==active and
       last["interval"]==interval,"native progress/header inconsistent")
    for left,right in zip(parsed,parsed[1:]):
        for key in ("scans","examined","rejected","eligible","attached",
                    "fully_conflicting","conflicts","decisions","propagations"):
            ck(left[key]<=right[key],"nonmonotonic native "+key)
    if mode=="passive16":ck(last["attached"]==0,"passive mode attached GF2 reasons")
    ck(last["eligible"]>=last["attached"],"more reasons than valid available candidates")
    return dict(begin=dict(active=active,interval=interval,prepared=prepared),
                snapshots=len(parsed),last=last,first=first,
                attached=last["attached"],eligible=last["eligible"],
                conflicting_rows=last["fully_conflicting"],
                conflicts_after_first_attach=last["conflicts_after_first_attach"])

def trial(case,source,mode,clean,native,verified_rows):
    environment=os.environ.copy()
    if mode!="clean":
        environment.update(R32B_MODE="r32u",
           R32U_ACTIVE="0" if mode=="passive16" else "1",
           R84_SCAN_EVERY="4" if mode=="active4" else "16",
           R32S_PASSIVE_TRACE="1",
           R32L_TRACE="0",R32M_PHASES="0")
    argv=[str(clean if mode=="clean" else native),str(source)]
    st=time.monotonic();finished=False;stdout="";answer="TIMEOUT"
    try:
        proc=subprocess.run(argv,env=environment,capture_output=True,
                            text=True,errors="replace",timeout=CAP)
        ck(proc.returncode in (10,20),
           "native crash/error code "+str(proc.returncode)+" "+proc.stderr[-240:])
        stdout=proc.stdout;finished=True
        answer="SAT" if proc.returncode==10 else "UNSAT"
    except subprocess.TimeoutExpired as e:
        stdout=e.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
    elapsed=time.monotonic()-st
    if answer=="SAT":r32p.verify_sat_witness(source,stdout)
    ck(not finished or not case["source_verified_status"] or
       answer==case["official_status"],"published official result disagreement")
    diagnosis=parse_progress(stdout,mode)
    if mode!="clean":
        emitted=[(tuple(int(z) for z in names.split(",")),int(rhs))
                 for rhs,names in SOURCE_ROW.findall(stdout)]
        if emitted:
            fingerprint=tuple(emitted)
            key=case["sha256"]
            if key not in verified_rows:
                ck(r83.source_prove_rows(source,emitted)==len(emitted),
                   "GF2 original source proof failed")
                verified_rows[key]=fingerprint
            else:
                ck(verified_rows[key]==fingerprint,
                   "different native parity proof rows across interventions")
        ck(len(emitted)==diagnosis["begin"]["prepared"],"R32u native certified row count differs")
        diagnosis["source_rows_certified"]=len(emitted)
    else:diagnosis["source_rows_certified"]=0
    return dict(answer=answer if finished and elapsed<=CAP else "TIMEOUT",
                wall_s=round(min(elapsed,CAP),6),
                par2_s=round(elapsed if finished and elapsed<=CAP else 2*CAP,6),
                telemetry=diagnosis,
                sat_original_witness_checked=(answer=="SAT"),
                external_unsat_proof_checked=False)

def measure(a):
    root=Path(a.sources).resolve()
    mf,cases=cohort(root)
    ck(0<=a.shard<SHARDS,"shard outside 0..3")
    bins=Path(a.bins).resolve()
    ck(subprocess.run(["sha256sum","-c","r84-binaries.sha256"],cwd=bins,
         stdout=subprocess.DEVNULL).returncode==0,"R84 solver binary SHA failure")
    clean=bins/"clean";native=bins/"native-r84"
    ck(clean.is_file() and native.is_file() and
       os.access(clean,os.X_OK) and os.access(native,os.X_OK),
       "R84 executable missing")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    case=cases[a.shard]
    source=root/case["filename"]
    ck(sha(source)==case["sha256"],"original CNF SHA drift")
    rows=[];verified={}
    for rep in range(REPS):
        order=list(MODES)
        random.Random(int(hashlib.sha256(
           (PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(order)
        for mode in order:
            result=trial(case,source,mode,clean,native,verified)
            row=dict(gbd=case["gbd"],sha256=case["sha256"],year=case["year"],
                     group=case["group"],rep=rep,mode=mode,**result)
            rows.append(row)
            save(out/"r84-shard.json",dict(protocol=PROTO,shard=a.shard,
               source_manifest_sha=sha(root/"manifest.json"),
               binary_sha={"clean":sha(clean),"native":sha(native)},
               rows=rows))
            stat=result["telemetry"]
            print("R84_TRIAL",json.dumps(dict(gbd=case["gbd"],rep=rep,
                 mode=mode,answer=result["answer"],wall_s=result["wall_s"],
                 par2_s=result["par2_s"],original_rows=stat["source_rows_certified"],
                 snapshots=stat["snapshots"],scans=stat["last"]["scans"] if stat["last"] else 0,
                 eligible=stat["eligible"],attached=stat["attached"],
                 conflicting_rows=stat["conflicting_rows"],
                 conflicts=stat["last"]["conflicts"] if stat["last"] else None)),
                 flush=True)
    ck(len(rows)==len(MODES)*REPS,"incomplete 8-way paired shard")
    print("R84_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf,cases=cohort(root)
    rows=[];pins=set()
    for shard in range(SHARDS):
        path=Path(a.combined)/f"r84-shard-{shard}"/"results"/"r84-shard.json"
        ck(path.exists(),"missing source shard "+str(shard))
        data=json.loads(path.read_text())
        ck(data["protocol"]==PROTO and data["shard"]==shard and
           data["source_manifest_sha"]==sha(root/"manifest.json"),"wrong source/origin")
        pins.add(json.dumps(data["binary_sha"],sort_keys=True))
        ck(len(data["rows"])==len(MODES)*REPS,"missing mode/repeat row")
        for rep in range(REPS):
            r=[x for x in data["rows"] if x["rep"]==rep]
            ck({x["mode"] for x in r}==set(MODES),"unpaired comparisons")
            vals={x["answer"] for x in r if x["answer"]!="TIMEOUT"}
            ck(len(vals)<=1,"contradictory original CNF verdict")
            if cases[shard]["source_verified_status"]:
                ck(all(v==cases[shard]["official_status"] for v in vals),
                   "official status mismatch")
        rows+=data["rows"]
    ck(len(pins)==1 and len(rows)==len(CASES)*REPS*len(MODES),
       "incomplete or unpinned benchmark")
    summary={}
    for m in MODES:
        rr=[r for r in rows if r["mode"]==m]
        def total(key):
            return sum(r["telemetry"][key] for r in rr)
        summary[m]=dict(trials=len(rr),
             solved=sum(r["answer"]!="TIMEOUT" for r in rr),
             par2_s=round(sum(r["par2_s"] for r in rr),6),
             reason_attached_at_least=total("attached"),
             eligible_at_least=total("eligible"),
             conflicting_parity_rows_at_least=total("conflicting_rows"),
             original_source_rows=sum(r["telemetry"]["source_rows_certified"] for r in rr),
             samples=sum(r["telemetry"]["snapshots"] for r in rr),
             total_conflicts_at_last_snapshot=sum(
               (r["telemetry"]["last"] or {}).get("conflicts",0) for r in rr),
             decisions_at_last_snapshot=sum(
               (r["telemetry"]["last"] or {}).get("decisions",0) for r in rr))
    result=dict(protocol=PROTO,status="PASS_UNOFFICIAL",cases=[c["gbd"] for c in cases],
      source_manifest_sha=sha(root/"manifest.json"),
      solver_binary_sha=json.loads(next(iter(pins))),
      trials=len(rows),summary=summary,rows=rows,
      limitations=[
       "Four already-studied REAL official competition originals selected by XOR structure; R84 is NOT blind.",
       "R84 telemetry is an observation of one native solver process; timeout counters are lower bounds and sampled every ~2 CPU seconds.",
       "Conflict rows are fully-assigned mismatched parity observations, NOT guaranteed CDCL conflict-analysis events.",
       "Conflicts after first attachment are chronological correlation, NOT proof the attached reason was used by 1-UIP.",
       "Native R32u provenance and CDCL assignment mechanism unchanged; active4 changes ONLY scan cadence.",
       "35-second R83 benchmark is not directly comparable to R84's 45-second cap.",
       "UNSAT proof not replayed externally; original SAT models and GF2 source parity proofs checked.",
       "If source R32u guards disable native source capture, active techniques have no eligible equations; report this explicitly.",
       "No world-record or general SAT algorithm superiority claim from this diagnostic sample."
      ])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    save(out/"r84-final.json",result)
    report=["# DRNAS R84 — why native XOR reasoning did not beat Kissat",
      "Four retrospective real mixed XOR CNFs; same original source SHA in every arm.",
      "Three same-native-binary comparison modes (passive16, active16, active4) + clean Kissat.",
      "Two repetitions; end-to-end native solve cap 45s, timeout PAR2=90s.",
      "On timeouts counters are **last observed** and lower bounds.",
      "",
      "| Method | Solved / 8 | PAR-2 (s) | Source-certified XOR rows | Eligible occurrences | Reason attachments | Conflicting parity rows |",
      "|---|---:|---:|---:|---:|---:|---:|"]
    for m,v in summary.items():
        report.append(f"| {m} | {v['solved']}/8 | {v['par2_s']:.3f} | "+
            f"{v['original_source_rows']} | {v['eligible_at_least']} | "+
            f"{v['reason_attached_at_least']} | {v['conflicting_parity_rows_at_least']} |")
    report+=["","## Per-formula results"]
    for c in cases:
        rr=[r for r in rows if r["gbd"]==c["gbd"]]
        report.extend(["",f"### {c['gbd']}"])
        for m in MODES:
            vals=[r for r in rr if r["mode"]==m]
            report.append(f"- {m}: PAR-2 {[v['par2_s'] for v in vals]}; "+
              f"certified original rows {[v['telemetry']['source_rows_certified'] for v in vals]}; "+
              f"last scanned decisions {[v['telemetry']['last']['decisions'] if v['telemetry']['last'] else None for v in vals]}; "+
              f"attached {[v['telemetry']['attached'] for v in vals]}; "+
              f"conflicts {[v['telemetry']['last']['conflicts'] if v['telemetry']['last'] else None for v in vals]}")
    report+=["","## Caveats"]+["- "+s for s in result["limitations"]]
    (out/"r84-final.md").write_text("\n".join(report)+"\n")
    print("R84_FINAL_AUDIT_PASS",json.dumps({m:{k:v[k] for k in
       ("solved","par2_s","original_source_rows","eligible_at_least",
        "reason_attached_at_least","conflicting_parity_rows_at_least")}
        for m,v in summary.items()}),flush=True)

def selftest():
    ck(len(set(CASES))==4,"four unique real original inputs")
    sample="c R84_BEGIN active=1 interval=16 prepared=7\n"+\
      "c R84_PROGRESS active=1 interval=16 rows=7 scans=8 examined=23 rejected=3 eligible=1 attached=1 fully_conflicting=0 conflicts=112 conflicts_after_first_attach=4 decisions=64 propagations=490 restarts=1 cpu_ms=2100.1 final=0\n"
    p=parse_progress(sample,"active16")
    ck(p["attached"]==1 and p["eligible"]==1,"telemetry parser selftest failed")
    print("R84_NATIVE_PROGRESS_PARSER_SELFTEST_PASS")

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    m=sub.add_parser("measure")
    for k in ("sources","bins","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):a.add_argument("--"+k,required=True)
    q=p.parse_args()
    if q.cmd=="selftest":selftest()
    elif q.cmd=="measure":measure(q)
    else:audit(q)
if __name__=="__main__":main()
