#!/usr/bin/env python3
"""R65XL real SAT Competition 2025 frozen unseen XOR-vs-control comparison.

First SHA-freeze never-before-used official 2025 original GBD sources; select by
real CNF and structural complete XOR recognition ONLY, never solver outcome.
We check all R82, R73, R85 candidate attempt lists and R72 historical prefix.
Three exact XOR-containing sources + three structural controls (if available).
Then compare clean upstream Kissat, native passive and native active with
default preprocessing (practical SAT), and a no-preprocess mechanism ablation.
Native active uses certified source GF(2) rows evaluated on the live CDCL trail,
same source-row proof and original SAT witness checks. UNSAT unproven by LRAT.
"""
from __future__ import annotations
import argparse, hashlib, json, os,random,re,subprocess,time,collections,math
from pathlib import Path
import r85_fresh_abcd as r85
import r73_fresh_quick_unseen_2025 as r73
import r52_prospective_2026_toprefs as r52
import r83_live_xor_cdcl_wide as r83
import r32p_real_satcomp26_benchmark as r32p
import r63_real2026_xor_prevalence_fallback as r63
import r65xl_live_trial as live

PROTO="DRNAS-R65XL-UNSEEN-REAL2025-XOR-REAL-SOLVE-20261104-v1"
SALT="DRNAS-R65XL-UNSEEN-REAL2025-STRUCTURE-BEFORE-RUNTIME-20261104"
TARGET_XOR,TARGET_CONTROL=3,3
SHARDS=TARGET_XOR+TARGET_CONTROL
MAX_FETCH=170
REPS=2
CAP=60.0
MODES=("clean_default","native_passive_default","native_live_default",
       "clean_noprep","native_passive_noprep",
       "native_fixed_noprep","native_adaptive_noprep")
GATE=re.compile(r"^c R65XLV2_SOURCE_GATE (.+)$",re.M)
CAP_SOURCES=(4096,60000,12*1024*1024)

def ck(condition,reason):
    if not condition:raise RuntimeError("R65XL_REAL2025_FAIL_CLOSED "+str(reason))

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def store(p,v):
    Path(p).write_text(json.dumps(v,sort_keys=True,indent=2)+"\n")

def score(gbd):
    return hashlib.sha256((SALT+"/"+gbd).encode()).hexdigest()

def freeze(a):
    old=json.loads((Path(a.old)/"manifest.json").read_text())
    prior73=json.loads((Path(a.r73)/"manifest.json").read_text())
    prior85=json.loads((Path(a.r85)/"manifest.json").read_text())
    ck(old["protocol"]==r83.R82_PROTO and len(old["cases"])==48,
       "R82 source attempt ledger missing")
    ck(prior73["protocol"]==r73.PROTO,"R73 source attempt ledger missing")
    ck(prior85["protocol"]==r85.PROTO and len(prior85["cases"])==12,
       "R85 independent 2025 source list missing")
    idx=r52.fetch_bytes(r73.SC2025,100000)
    ids=[line.rsplit("/",1)[-1] for line in idx.decode().strip().splitlines()]
    ck(len(ids)>=300 and len(ids)==len(set(ids)),"official 2025 source index mismatch")
    blocked={c["gbd"] for c in old["cases"]}
    blocked.update(x["gbd"] for x in old["source_selection_attempts"])
    blocked.update(c["gbd"] for c in prior73["cases"])
    blocked.update(x["gbd"] for x in prior73["selection_attempts"])
    # R72 conservative candidate prefix exclusion exactly matching prior R85.
    p72="DRNAS-R72-NEW-SHA-AND-ATTEMPT-DISJOINT-20261103-v1"
    blocked.update(sorted(ids,key=lambda g:hashlib.sha256((p72+":"+g).encode()).hexdigest())[:150])
    blocked.update(c["gbd"] for c in prior85["cases"])
    blocked.update(x["gbd"] for x in prior85["source_attempts"])
    blocked_sha={c["sha256"] for c in old["cases"]}
    blocked_sha.update(c["sha256"] for c in prior73["cases"])
    blocked_sha.update(c["sha256"] for c in prior85["cases"])
    candidates=sorted(set(ids)-blocked,key=score)
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    selection=[];attempts=[];xor=ctrl=0
    r32p.CAP_BYTES=24*1024*1024
    # Predeclare support scope before reading any solver results.
    for g in candidates[:MAX_FETCH]:
        if xor==TARGET_XOR and ctrl==TARGET_CONTROL:break
        row=dict(gbd=g,year=2025)
        file=root/("2025-"+g+".cnf")
        try:
            compressed,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+g,
                16*1024*1024,seconds=20)
            raw,encoding=r32p.decode(compressed)
            ck(len(raw)<=24*1024*1024,"DIMACS source exceeds allowed cap")
            n,nclauses=r32p.parse_dimacs_metadata(raw)
            ck(n<=CAP_SOURCES[0] and nclauses<=CAP_SOURCES[1]
               and len(raw)<=CAP_SOURCES[2],"source exceeds native scope")
            file.write_bytes(raw)
            digest=sha(file)
            ck(digest not in blocked_sha and
               all(digest!=c["sha256"] for c in selection),
               "source SHA previously benchmarked")
            structure=r63.inspect_exact_xor(file,n,nclauses)
            eligible=bool(structure["supported"] and structure["complete_blocks"]>=2)
            if (eligible and xor>=TARGET_XOR) or (not eligible and ctrl>=TARGET_CONTROL):
                file.unlink(missing_ok=True)
                row.update(state="COHORT_FILLED",xor=eligible)
                attempts.append(row)
                continue
            entry=dict(gbd=g,year=2025,filename=file.name,sha256=digest,
                variables=n,clauses=nclauses,source_url="https://benchmark-database.de/file/"+g,
                source_bytes=len(raw),compressed_bytes=len(compressed),
                encoding=encoding,redirect=redirect,
                group="xor_exact" if eligible else "control",
                structural_xor_positive=eligible,
                official_status="UNKNOWN",source_verified_status=False,**structure)
            selection.append(entry)
            xor+=int(eligible);ctrl+=int(not eligible)
            row.update(state="ACCEPTED",xor=eligible,sha256=digest,
                       variables=n,clauses=nclauses,
                       blocks=structure["complete_blocks"])
        except Exception as e:
            file.unlink(missing_ok=True)
            row.update(state="UNSUPPORTED_SOURCE",
                       why=(type(e).__name__+" "+str(e))[:180])
        attempts.append(row)
        print("R65XL_FRESH_ATTEMPT",json.dumps(row,sort_keys=True),flush=True)
    ck(xor==TARGET_XOR and ctrl==TARGET_CONTROL,
       f"only obtained {xor}/{TARGET_XOR} real XOR and {ctrl}/{TARGET_CONTROL} real controls; fail closed instead of reusing sources")
    selection.sort(key=lambda c:score(c["gbd"]))
    ck(len(selection)==SHARDS and len({x["gbd"] for x in selection})==SHARDS,
       "source count/provenance mismatch")
    ck(not set(x["gbd"] for x in selection)&blocked,
       "historically used GBD selected")
    report=dict(protocol=PROTO,year=2025,salt=SALT,
       source_index=r73.SC2025,source_index_sha256=hashlib.sha256(idx).hexdigest(),
       prior_sha=dict(r82=sha(Path(a.old)/"manifest.json"),
                      r73=sha(Path(a.r73)/"manifest.json"),
                      r85=sha(Path(a.r85)/"manifest.json")),
       prior_excluded_gbd=len(blocked),max_attempts=MAX_FETCH,
       attempted=len(attempts),selection_rule="SHA-ranked official 2025 GBD, excluding prior R82 R73 R85 and conservative R72 prefix; first 3 XOR positive + 3 non-XOR controls; never screen by solver runtime",
       cases=selection,attempts=attempts,cap_s=CAP,repeats=REPS,
       modes=MODES,limitations=[
          "Official SAT Competition 2025 original CNF GBD sources; R85/R82/R73 documented candidates and R72 prefix blocked",
          "Undocumented historical uses elsewhere in project cannot be categorically excluded",
          "Preselected XOR-enriched cohort is not representative of all SAT2025 problems",
          "Hard bound vars<=4096, clauses<=60000, size<=12MiB biases sample",
          "First 3 XOR-positive and 3 controls, selected without timing/answer, frozen before measuring",
          "SAT models checked against untouched original; UNSAT no LRAT external proof",
          "Native live is in-process GF2/CDCL propagation, not separate workers exchanging learnt clauses"])
    store(root/"manifest.json",report)
    (root/"source.sha256").write_text("".join(
       c["sha256"]+"  "+c["filename"]+"\n" for c in selection))
    print("R65XL_REAL2025_FRESH_FROZEN_PASS",json.dumps({
       "sources":len(selection),"xor":xor,"controls":ctrl,
       "attempts":len(attempts),"excluded":len(blocked)}),flush=True)

def manifest(path):
    mf=json.loads((path/"manifest.json").read_text())
    ck(mf["protocol"]==PROTO and len(mf["cases"])==SHARDS,
       "frozen source protocol mismatch")
    ck(sum(c["group"]=="xor_exact" for c in mf["cases"])==TARGET_XOR,
       "XOR vs control cohort changed")
    ck(len({c["sha256"] for c in mf["cases"]})==SHARDS,
       "duplicate original formula")
    for c in mf["cases"]:
        ck(c["year"]==2025 and sha(path/c["filename"])==c["sha256"],
           "original SAT2025 CNF changed")
    return mf

def parse_gate(text):
    mm=GATE.findall(text)
    ck(len(mm)<=1,"multiple source-guard snapshots")
    if not mm:return None
    return {k:int(v) for t in mm[0].split() if "=" in t
            for k,v in [t.split("=",1)]}

def one(source,mode,clean,native,cache):
    isclean=mode.startswith("clean_")
    passive="passive" in mode
    if mode in ("clean_default","native_passive_default","native_live_default"):
        flags=[]
    else:
        flags=list(live.FLAGS)
    env=os.environ.copy()
    if not isclean:
        env.update(R32B_MODE="r32u",R32U_ACTIVE="0" if passive else "1",
             R84_SCAN_EVERY="16",R85_DIVERSE="0",R85_CAP="64",
             R65XL_POLICY="fixed" if passive or mode=="native_fixed_noprep" else "adaptive",
             R32S_PASSIVE_TRACE="0")
    started=time.monotonic()
    exe=clean if isclean else native
    try:
        proc=subprocess.run([str(exe)]+flags+[str(source)],env=env,
              capture_output=True,text=True,errors="replace",timeout=CAP)
        ck(proc.returncode in (10,20),
           f"solver exited {proc.returncode}: {proc.stderr[-260:]}")
        result="SAT" if proc.returncode==10 else "UNSAT"
        stdout=proc.stdout
    except subprocess.TimeoutExpired as exc:
        result="TIMEOUT"
        stdout=exc.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
    elapsed=time.monotonic()-started
    if result=="SAT":
        r32p.verify_sat_witness(source,stdout)
    tel=None;liv=None;gate=None
    if not isclean:
        mapped="A_passive16" if passive else "B_active16"
        tel=r85.parse_counts(stdout,mapped,source,cache)
        liv=live.parse_live(stdout,
           "gf2_passive16" if passive else
           ("gf2_live_fixed16" if mode=="native_fixed_noprep" else "gf2_live_adaptive"))
        ck(tel["last"]["attached"]==liv["last"]["xor_to_cdcl_reasons"],
           "native attached reason telemetry mismatch")
        ck(tel["last"]["first_uip_reason_uses"]==liv["last"]["cdcl_first_uip_uses"],
           "native first UIP counter mismatch")
        gate=parse_gate(stdout)
        ck(gate is not None and gate["eq_capacity"]==4096,
           "wide original-source gate absent")
    return dict(answer=result if elapsed<=CAP else "TIMEOUT",
       wall_s=round(min(elapsed,CAP),6),
       par2_s=round(elapsed if result!="TIMEOUT" and elapsed<=CAP else 2*CAP,6),
       sat_original_model_verified=result=="SAT",
       external_unsat_proof_verified=False,
       source_gate=gate,telemetry=tel,live=liv)

def measure(a):
    root=Path(a.sources).resolve()
    mf=manifest(root)
    ck(0<=a.shard<SHARDS,"invalid source shard")
    compiled=Path(a.compiled).resolve()
    clean=compiled/"old"/"clean"
    native=compiled/"new"/"native-r65xl-v2"
    ck(all(p.is_file() and os.access(p,os.X_OK) for p in (clean,native)),
       "missing exact compiled binaries")
    ck(subprocess.run(["sha256sum","-c","r65xl-binaries.sha256"],
             cwd=compiled/"old",capture_output=True).returncode==0,
       "Kissat baseline SHA changed")
    ck(subprocess.run(["sha256sum","-c","r65xl-v2-binaries.sha256"],
             cwd=compiled/"new",capture_output=True).returncode==0,
       "native R65XLV2 binary SHA changed")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    case=mf["cases"][a.shard]
    source=root/case["filename"]
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cache={};rows=[]
    for rep in range(REPS):
        order=list(MODES)
        rnd=int(hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)
        random.Random(rnd).shuffle(order)
        for mode in order:
            x=one(source,mode,clean,native,cache)
            row=dict(gbd=case["gbd"],sha256=case["sha256"],
                    group=case["group"],rep=rep,mode=mode,**x)
            rows.append(row)
            store(out/"results.json",dict(protocol=PROTO,shard=a.shard,
                    source_manifest_sha=sha(root/"manifest.json"),
                    binaries={"clean":sha(clean),"native":sha(native)},rows=rows))
            last=(x.get("live") or {}).get("last") or {}
            print("R65XL_REAL2025_TRIAL",json.dumps({
                "gbd":case["gbd"],"group":case["group"],"rep":rep,"mode":mode,
                "answer":x["answer"],"time":x["wall_s"],"par2":x["par2_s"],
                "source_rows":last.get("rows",0),
                "live_reasons":last.get("xor_to_cdcl_reasons",0),
                "first_uip_uses":last.get("cdcl_first_uip_uses",0),
                "trail_row_checks":last.get("trail_row_checks",0),
                "guard":x.get("source_gate")},sort_keys=True),flush=True)
    ck(len(rows)==len(MODES)*REPS,"incomplete matched formula")
    print("R65XL_REAL2025_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources).resolve()
    mf=manifest(root)
    allrows=[];pins=set()
    for sh,c in enumerate(mf["cases"]):
        file=Path(a.combined)/f"r65xl2025-shard-{sh}"/"results"/"results.json"
        ck(file.is_file(),"missing source shard "+str(sh))
        j=json.loads(file.read_text())
        ck(j["protocol"]==PROTO and j["shard"]==sh
           and j["source_manifest_sha"]==sha(root/"manifest.json"),
           "source SHA/protocol drift")
        pins.add(json.dumps(j["binaries"],sort_keys=True))
        sub=j["rows"]
        ck(len(sub)==len(MODES)*REPS,"incomplete mode matrix")
        for rep in range(REPS):
            subrep=[r for r in sub if r["rep"]==rep]
            ck({r["mode"] for r in subrep}==set(MODES) and
               len(subrep)==len(MODES),"missing matched modes")
            ck(all(r["sha256"]==c["sha256"] and r["gbd"]==c["gbd"]
                 and r["group"]==c["group"] for r in subrep),
               "formula/group SHA drift")
            verdict={r["answer"] for r in subrep if r["answer"]!="TIMEOUT"}
            ck(len(verdict)<=1,"contradictory original SAT results")
        allrows+=sub
    ck(len(pins)==1 and len(allrows)==SHARDS*REPS*len(MODES),
       "inconsistent solver binary pins or missing rows")
    groups={}
    for group in ("ALL","xor_exact","control"):
        part=[r for r in allrows if group=="ALL" or r["group"]==group]
        result={}
        for m in MODES:
            rows=[r for r in part if r["mode"]==m]
            stats=[((r.get("live") or {}).get("last") or {}) for r in rows]
            result[m]=dict(trials=len(rows),
                solved=sum(r["answer"]!="TIMEOUT" for r in rows),
                par2_s=round(sum(r["par2_s"] for r in rows),6),
                attached=sum(s.get("xor_to_cdcl_reasons",0) for s in stats),
                first_uip_uses=sum(s.get("cdcl_first_uip_uses",0) for s in stats),
                trail_checks=sum(s.get("trail_row_checks",0) for s in stats))
        groups[group]=result
    pairs=[]
    for c in mf["cases"]:
        subset=[r for r in allrows if r["sha256"]==c["sha256"]]
        pairs.append(dict(gbd=c["gbd"],group=c["group"],xor_blocks=c["complete_blocks"],
            mean={m:round(sum(r["par2_s"] for r in subset if r["mode"]==m)/REPS,6)
                  for m in MODES}))
    comparisons={}
    for mode,baseline in (("native_live_default","clean_default"),
         ("native_live_default","native_passive_default"),
         ("native_adaptive_noprep","clean_noprep"),
         ("native_adaptive_noprep","native_passive_noprep"),
         ("native_adaptive_noprep","native_fixed_noprep")):
        for group in ("ALL","xor_exact","control"):
            ps=[x for x in pairs if group=="ALL" or x["group"]==group]
            delta=[x["mean"][baseline]-x["mean"][mode] for x in ps]
            # Unique source is bootstrap unit, not repeats. Exploratory only.
            rng=random.Random(int(hashlib.sha256((mode+baseline+group).encode()).hexdigest(),16))
            draws=sorted(sum(delta[rng.randrange(len(delta))] for _ in delta)/len(delta)
                         for _ in range(2000))
            comparisons[f"{group}/{mode}_vs_{baseline}"]=dict(
                 mean_saved_par2_s_per_source=round(sum(delta)/len(delta),6),
                 bootstrap_95ci=[round(draws[49],6),round(draws[1949],6)])
    report=dict(protocol=PROTO,status="PASS_EXPLORATORY_OFFICIAL_ORIGINALS",
         sources=SHARDS,trials=len(allrows),source_manifest_sha=sha(root/"manifest.json"),
         binary_pins=json.loads(next(iter(pins))),groups=groups,
         comparisons=comparisons,per_source=pairs,
         limitations=mf["limitations"]+[
          "Selection prior to solver timing, but small enriched sample cannot support a world ranking",
          "60s wall clock per attempt, one process on pinned CPU, fixed binaries, two repeats",
          "Two settings are distinct: actual default Kissat and mechanism no-preprocess",
          "No independent original UNSAT LRAT replay; SAT model always checked",
          "Unique SHA original source, not repeated measurement, is statistical unit"])
    store(a.json,report)
    lines=["# R65x Live – genuinely new SAT Competition 2025 XOR impact",
          "", "Six new SHA-frozen originals: 3 complete XOR + 3 structural controls.",
          "Default Kissat separately from no-preprocess causal ablation. 60s cap;",
          "two repeats, single CPU, 84 total runs.",
          "", "| Cohort | Mode | Solved | PAR2 s | XOR reasons | First-UIP uses | Trail checks |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for g,modes in groups.items():
        for m,v in modes.items():
            lines.append(f"| {g} | {m} | {v['solved']}/{v['trials']} | "+
                         f"{v['par2_s']:.3f} | {v['attached']} | "+
                         f"{v['first_uip_uses']} | {v['trail_checks']} |")
    lines+=["","## Every frozen original, PAR2 average over two repeats",
         "| GBD | Cohort | XOR blocks | Clean default | Live default | Clean no-prep | Live no-prep |",
         "|---|---|---:|---:|---:|---:|---:|"]
    for x in pairs:
        v=x["mean"]
        lines.append(f"| {x['gbd'][:12]} | {x['group']} | {x['xor_blocks']} | "+
                     f"{v['clean_default']:.3f} | {v['native_live_default']:.3f} | "+
                     f"{v['clean_noprep']:.3f} | {v['native_adaptive_noprep']:.3f} |")
    lines+=["","## Per-source bootstrap, exploratory"] + [
          "- "+name+": "+str(data) for name,data in comparisons.items()]
    lines+=["","## Limitations"]+["- "+v for v in report["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R65XL_REAL2025_FINAL_AUDIT_PASS",json.dumps(groups["ALL"],sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();sp=p.add_subparsers(dest="cmd",required=True)
    x=sp.add_parser("freeze")
    for k in ("old","r73","r85","out"):x.add_argument("--"+k,required=True)
    x=sp.add_parser("measure")
    for k in ("sources","compiled","out"):x.add_argument("--"+k,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sp.add_parser("audit")
    for k in ("sources","combined","json","md"):x.add_argument("--"+k,required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a)
    elif a.cmd=="measure":measure(a)
    else:audit(a)

if __name__=="__main__":main()
