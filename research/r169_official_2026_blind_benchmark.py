#!/usr/bin/env python3
"""R169: preregistered 2026 SAT Main native GF2 vs 5 references.
Primary 96 fresh source identifiers; automatic *disjoint* 48 confirmation
iff primary audit passes a frozen gate. No cherry-picking after source reads.
Results are research-only, not an official SAT Competition ranking.
"""
import argparse, collections, hashlib, json, os, pathlib, random, re, shutil, subprocess, sys, time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r167_blind2026 as transport
import r166_independent_verifier as independent

ROOT=pathlib.Path("r169")
MANIFEST=pathlib.Path("research/r169_official_2026_frozen_manifest.json")
MODES=("drnas_r167","cadical_clean","kissat404","cryptominisat","minisat","picosat")
PREFIX="R169"
NATIVE_SHA="84e1d72c9700084d092fe15eabd5a143976b7340bf18ed2e8d8e840cd08c471e"
CPP_SHA="a770469333defdf37b877e57137223e8cd16353df89fee40cc0de6c773e04398"

def check(cond,msg):
    if not cond:raise RuntimeError("R169_AUDIT_FAIL "+str(msg))
def digest(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def manifest():
    m=load(MANIFEST)
    check(m["protocol"]=="DRNAS-R169-2026-MAIN-PRE-REGISTERED-144-96+48-v1","wrong protocol")
    check(m["official_uri_git_blob_sha1"]=="2b86a4d685b492a844646f378ac3f3415fd131d5","official index changed")
    check(m["modes"]==list(MODES) and m["repetitions"]==2 and m["cap_per_solver_s"]==15,"protocol settings drift")
    check(len(m["primary"])==96 and len(m["confirmation"])==48,"cohort sizes changed")
    check(m["primary_shards"]==12 and m["confirmation_shards"]==6,"shard settings changed")
    old=set(m["known_prior_2026_indices_excluded"])
    seen=set()
    for stage in ("primary","confirmation"):
        for c in m[stage]:
            idx=c["index"];name=c["gbd_md5"]
            check(idx not in old and idx not in seen and 0<=idx<400,"reused old or duplicate official index")
            check(re.fullmatch(r"[a-f0-9]{32}",name) is not None,"invalid official GBD ID")
            seen.add(idx)
    check(len(seen)==144,"formula count not frozen")
    return m
def check_official_index(m):
    path=ROOT/"official.uri"
    check(path.is_file(),"official index not downloaded")
    blob=subprocess.check_output(["git","hash-object",str(path)],text=True).strip()
    check(blob==m["official_uri_git_blob_sha1"],"official source manifest drift")
    lines=path.read_text().splitlines()
    check(len(lines)==400,"official 2026 source count changed")
    for case in m["primary"]+m["confirmation"]:
        check(lines[case["index"]].endswith("/"+case["gbd_md5"]),"GBD ID differs from preregistration")
def setup(stage,validate_binary=True):
    m=manifest()
    check(stage in ("primary","confirmation"),"wrong stage")
    check_official_index(m)
    base=ROOT/stage;base.mkdir(parents=True,exist_ok=True)
    transport.ROOT=base
    if validate_binary:
        check(digest("r167/native")==NATIVE_SHA,"frozen R167 binary changed")
        check(digest("research/r167_native_exact_gf2.cpp")==CPP_SHA,"frozen C++ source changed")
        pin=load("r167/build-pin.json")
        check(pin["binary_sha256"]==NATIVE_SHA and pin["source_cpp_sha256"]==CPP_SHA,"frozen native artifact mismatch")
        kpin=load("r166x/kissat-pin.json")
        check(kpin["kissat_version"]=="4.0.4" and kpin["kissat_commit"]==m["kissat_commit"],"Kissat source drift")
        check(digest("r166x/bin/kissat")==kpin["kissat_binary_sha256"],"Kissat binary drift")
        for mode in ("cryptominisat5","minisat","picosat"):
            check(shutil.which(mode),"missing reference binary "+mode)
    return m,base
def verify_sat_model(src,model_text,kind):
    vals={}
    lines=model_text.splitlines()
    started=False
    for line in lines:
        s=line.strip()
        if not s:continue
        if kind=="minisat":
            if s=="SAT":started=True;continue
            if not started:continue
            tokens=s.split()
        else:
            if not (s.startswith("v ") or s.startswith("v\t")):continue
            tokens=s.split()[1:]
        for token in tokens:
            try:l=int(token)
            except ValueError:continue
            if l==0:continue
            v=abs(l)
            check(v not in vals or vals[v]==(l>0),"contradictory SAT model literal")
            vals[v]=(l>0)
    check(vals,"SAT output without model")
    clauses=0
    current=False; clause_ok=False
    with pathlib.Path(src).open("r",errors="strict") as f:
        for line in f:
            s=line.strip()
            if not s or s.startswith(("c","p ","%")):continue
            for token in s.split():
                v=int(token)
                if v:
                    current=True
                    if vals.get(abs(v))==(v>0):clause_ok=True
                else:
                    check(clause_ok,"SAT witness does not satisfy original source clause "+str(clauses))
                    clauses+=1;current=False;clause_ok=False
    check(not current,"unfinished source CNF clause")
    return clauses
def external_command(mode,source,out):
    if mode=="kissat404":return [str(pathlib.Path("r166x/bin/kissat").resolve()),str(source.resolve())]
    if mode=="cryptominisat":return ["cryptominisat5",str(source.resolve())]
    if mode=="picosat":return ["picosat",str(source.resolve())]
    if mode=="minisat":return ["minisat","-verb=0",str(source.resolve()),str(out.resolve())]
    raise ValueError("Unknown external solver "+mode)
def external_trial(stage_dir,c,source,mode,rep,cap):
    outfile=stage_dir/f"model-{c['index']}-{mode}-{rep}.txt"
    outfile.unlink(missing_ok=True)
    cmd=external_command(mode,source,outfile)
    beg=time.perf_counter()
    try:
        proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",wall_s=cap,par2_s=2*cap,route="OS_CENSORED_TIMEOUT",
                    SAT_model_verified=False,GF2_cert_replayed=False)
    wall=time.perf_counter()-beg
    check(proc.returncode in (0,10,20),"reference crashed "+mode+" return="+str(proc.returncode)+
          " stderr="+proc.stderr[-450:].decode(errors="replace"))
    output=proc.stdout.decode(errors="replace")
    model=outfile.read_text(errors="replace") if mode=="minisat" and outfile.is_file() else output
    merged=output+"\n"+model
    if re.search(r"(?m)^\s*s?\s*UNSATISFIABLE\s*$|^\s*UNSAT\s*$",merged):status="UNSAT"
    elif re.search(r"(?m)^\s*s?\s*SATISFIABLE\s*$|^\s*SAT\s*$",merged):status="SAT"
    elif proc.returncode==20:status="UNSAT"
    elif proc.returncode==10:status="SAT"
    else:raise RuntimeError("External solver no conclusive status "+mode)
    check(proc.returncode in (0,10 if status=="SAT" else 20),"solver exit/result mismatch "+mode)
    if status=="SAT":verify_sat_model(source,model,mode)
    return dict(status=status,wall_s=round(wall,6),par2_s=round(wall,6),
                route="EXTERNAL_"+mode.upper(),SAT_model_verified=(status=="SAT"),
                GF2_cert_replayed=False)
def drnas_trial(stage_dir,c,source,mode,rep,cap):
    proof=stage_dir/f"proof-{c['gbd_md5']}-{rep}.json"
    proof.unlink(missing_ok=True)
    cmd=[str(pathlib.Path("r167/native").resolve()),str(source.resolve()),"--cap",str(cap)]
    if mode=="cadical_clean":cmd+=["--force-clean"]
    else:cmd+=["--proof",str(proof.resolve())]
    beg=time.perf_counter()
    p=subprocess.run(cmd,capture_output=True,timeout=cap+20)
    wall=time.perf_counter()-beg
    check(p.returncode in (0,10,20),"native executable failed "+p.stderr[-800:].decode(errors="replace"))
    output=p.stdout.decode(errors="replace")
    info=transport.parse_output(output,p.returncode,source,cap,"clean" if mode=="cadical_clean" else "auto")
    status=info["status"]
    check(status in ("SAT","UNSAT","TIMEOUT"),"unrecognized native status")
    if status!="TIMEOUT":check(wall<=cap+0.05,"solver went over cap without timeout")
    replay=False
    if mode=="drnas_r167" and info["method"]=="NATIVE_EXACT_GF2":
        check(proof.is_file(),"missing native GF2 source-proof")
        verified=independent.verify(source,load(proof))
        check(verified["status"]==status,"independent GF2 certificate mismatch")
        replay=True
    else:
        check(not proof.exists(),"unexpected GF2 proof outside exact route")
    return dict(status=status,wall_s=round(wall,6),
                par2_s=round(2*cap if status=="TIMEOUT" else wall,6),
                route=info["method"],xor_rows=info["xor_rows"],
                SAT_model_verified=(status=="SAT"),GF2_cert_replayed=replay)
def shard(stage,index):
    m,folder=setup(stage,validate_binary=True)
    n=m["primary_shards"] if stage=="primary" else m["confirmation_shards"]
    check(0<=index<n,"invalid shard")
    if hasattr(os,"sched_getaffinity"):
        mask=os.sched_getaffinity(0)
        if mask:os.sched_setaffinity(0,{min(mask)})
    sources=[];trials=[];errors=[]
    selected=m[stage]
    for offset,c in enumerate(selected):
        if offset%n!=index:continue
        srcmeta,source=transport.acquire(c,offset)
        sources.append(srcmeta)
        save(folder/f"shard-{index}.json",dict(stage=stage,shard=index,sources=sources,trials=trials,failures=errors))
        print("R169_SOURCE",json.dumps(dict(stage=stage,**srcmeta),sort_keys=True),flush=True)
        if source is None:continue
        for rep in range(m["repetitions"]):
            modes=list(MODES)
            random.Random("DRNAS-R169-BLIND-ORDER-"+stage+c["gbd_md5"]+str(rep)).shuffle(modes)
            for mode in modes:
                try:
                    row=drnas_trial(folder,c,source,mode,rep,float(m["cap_per_solver_s"])) if mode in ("drnas_r167","cadical_clean") else external_trial(folder,c,source,mode,rep,float(m["cap_per_solver_s"]))
                    row=dict(index=c["index"],gbd_md5=c["gbd_md5"],source_sha256=srcmeta["source_sha256"],mode=mode,rep=rep,cap_s=m["cap_per_solver_s"],**row)
                    trials.append(row)
                    print("R169_TRIAL",json.dumps(dict(stage=stage,**row),sort_keys=True),flush=True)
                except Exception as err:
                    obj=dict(index=c["index"],gbd_md5=c["gbd_md5"],rep=rep,mode=mode,
                             kind="TRIAL_ERROR_NOT_TIMEOUT",error=str(err)[:1000])
                    errors.append(obj)
                    print("R169_TRIAL_ERROR",json.dumps(dict(stage=stage,**obj),sort_keys=True),flush=True)
                save(folder/f"shard-{index}.json",dict(stage=stage,shard=index,sources=sources,trials=trials,failures=errors))
    print("R169_SHARD_PASS",stage,index,len(sources),len(trials),len(errors),flush=True)
def audit(stage):
    m,folder=setup(stage,validate_binary=False)
    n=m["primary_shards"] if stage=="primary" else m["confirmation_shards"]
    sources=[];trials=[];failures=[]
    for i in range(n):
        s=load(folder/f"shard-{i}.json")
        check(s["stage"]==stage and s["shard"]==i,"shard index wrong")
        sources+=s["sources"];trials+=s["trials"];failures+=s["failures"]
    selected=m[stage]
    check(len(sources)==len(selected),"not all source indices attempted")
    check({(s["index"],s["gbd_md5"]) for s in sources}=={(s["index"],s["gbd_md5"]) for s in selected},
          "source selection changed")
    ok={s["gbd_md5"]:s for s in sources if s["status"]=="SOURCE_OK"}
    seen=set()
    for t in trials:
        key=(t["gbd_md5"],t["rep"],t["mode"])
        check(key not in seen,"duplicate record");seen.add(key)
        check(t["gbd_md5"] in ok and t["source_sha256"]==ok[t["gbd_md5"]]["source_sha256"],"wrong source SHA")
        check(t["mode"] in MODES and t["rep"] in (0,1),"invalid trial coordinate")
        expected=2*t["cap_s"] if t["status"]=="TIMEOUT" else t["wall_s"]
        check(abs(t["par2_s"]-expected)<0.00001,"bad PAR2")
        check(t["status"]!="SAT" or t["SAT_model_verified"],"unchecked SAT model")
    pairs=[]
    for c in selected:
        if c["gbd_md5"] not in ok:continue
        for rep in range(m["repetitions"]):
            match={t["mode"]:t for t in trials if t["gbd_md5"]==c["gbd_md5"] and t["rep"]==rep}
            if set(match)!=set(MODES):continue
            answers={t["status"] for t in match.values() if t["status"]!="TIMEOUT"}
            check(len(answers)<=1,"contradictory SAT/UNSAT answer for "+c["gbd_md5"])
            pairs.append(dict(index=c["index"],gbd_md5=c["gbd_md5"],rep=rep,modes=match))
    complete={mode:[p["modes"][mode] for p in pairs] for mode in MODES}
    summaries={}
    for mode,arr in complete.items():
        summaries[mode]=dict(trials=len(arr),solved=sum(t["status"]!="TIMEOUT" for t in arr),
                             SAT=sum(t["status"]=="SAT" for t in arr),
                             UNSAT=sum(t["status"]=="UNSAT" for t in arr),
                             exact=sum(t["route"]=="NATIVE_EXACT_GF2" for t in arr),
                             PAR2_s=round(sum(t["par2_s"] for t in arr),6),
                             total_measured_wall_s=round(sum(t["wall_s"] for t in arr),6))
    distinct_unique=[]
    for c in selected:
        local=[p for p in pairs if p["gbd_md5"]==c["gbd_md5"]]
        if len(local)!=2:continue
        if all(p["modes"]["drnas_r167"]["status"] in ("SAT","UNSAT") and
               all(p["modes"][other]["status"]=="TIMEOUT" for other in MODES if other!="drnas_r167")
               for p in local):
            distinct_unique.append(c["gbd_md5"])
    auto=summaries["drnas_r167"];refs=[summaries[x] for x in MODES if x!="drnas_r167"]
    best=min((x["PAR2_s"] for x in refs),default=0)
    regressions={p["gbd_md5"] for p in pairs if p["modes"]["cadical_clean"]["status"]!="TIMEOUT" and
                p["modes"]["drnas_r167"]["status"]=="TIMEOUT"}
    no_issues=(not failures and len(ok)>=70 and len(pairs)>=140 and len(regressions)<=2)
    win=(no_issues and ((len(distinct_unique)>=2 and auto["PAR2_s"]<best)
           or (auto["solved"]>=4 and auto["PAR2_s"]<=0.90*best and auto["PAR2_s"]<best)))
    eligible=(stage=="primary" and win)
    report=dict(protocol=m["protocol"],stage=stage,status="R169_RESEARCH_AUDIT",
        official_2026=True,not_official_competition=True,
        preregistered_sources=len(selected),source_ok=len(ok),infra_sources=len(selected)-len(ok),
        valid_matched_repetitions=len(pairs),expected_repetitions=len(selected)*m["repetitions"],
        mode_results=summaries,unique_r167_wins=distinct_unique,
        cadical_regressed_source_count=len(regressions),
        first_stage_promising=eligible,failures=failures,sources=sources,
        pairs=pairs,cap_s=m["cap_per_solver_s"],
        limitations=["Official source indices preregistered, disjoint R167/R168 but may overlap unindexed historical work",
           "Original CNF SHA256 recorded; independent SAT witness and exact GF2 certificate replay required",
           "UNSAT from ordinary CDCL or references not independently LRAT/FRAT proven",
           "15-second limit not SAT Competition conditions; cross-runner CPU differences",
           "Reference versions recorded; timeout is censored, not solved time",
           "Only complete six-mode paired repetitions enter score, infrastructure failures separate"])
    save(folder/"report.json",report)
    lines=[f"# R169 official SAT 2026 Main {stage} — preregistered blind benchmark","",
      f"Original source CNFs acquired {len(ok)}/{len(selected)}. Complete 6-mode repetitions {len(pairs)}/{len(selected)*m['repetitions']}. Failures {len(failures)}.",
      "15-second per solver cap; two repeats; compare paired originals and statuses.", "",
      "| Solver | Solved | PAR2 (seconds) | SAT | UNSAT | Exact GF2 |",
      "|---|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        q=summaries[mode];lines.append(f'| {mode} | {q["solved"]}/{q["trials"]} | {q["PAR2_s"]:.4f} | {q["SAT"]} | {q["UNSAT"]} | {q["exact"]} |')
    lines.extend(["",f"Unique confirmed DRNAS source wins: {len(distinct_unique)}",
      f"Clean CaDiCaL regression source count: {len(regressions)}",
      f"Automatic disjoint 48-case confirmation gate: {'PASS' if eligible else 'NOT_TRIGGERED'}",
      "","RESEARCH ONLY. Blind selected list is not an official SAT Competition leaderboard."])
    (folder/"summary.md").write_text("\n".join(lines)+"\n")
    print("R169_FINAL",json.dumps({k:report[k] for k in ("stage","source_ok","infra_sources","valid_matched_repetitions",
      "mode_results","unique_r167_wins","first_stage_promising","cadical_regressed_source_count")},sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--stage",choices=("primary","confirmation"),required=True)
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.stage,a.shard)
    else:audit(a.stage)
