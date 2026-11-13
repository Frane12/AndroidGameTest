#!/usr/bin/env python3
"""X5.5: paired sample-based CPU profiling for X5.4 BCP scan variants.

Six arms: frozen X5.4 fixed and rotated watches, X5.5 fixed and rotated
watches with profiling OFF and ON. The original 36 SHA come from REAL36 STRICT
artifact (not from a generator or screened by solve outcome). SAT witnesses
are checked against the original CNF; UNSAT requires independently verified
DRAT on the same CNF. Check cost is reported separately. Time cap is solve E2E.
Two repeats of the same original are a cluster, not two independent sources.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, resource
import signal, statistics, subprocess, tempfile, time

ROOT=pathlib.Path("real36_frozen")
CAP=10.0
SHARDS=12
REPS=2
ARMS=("X54_CONTROL","X54_ROTATE","X55_CONTROL_OFF","X55_CONTROL_ON","X55_ROTATE_OFF","X55_ROTATE_ON")
BIN={
 "X54_CONTROL":"build/drnas-x54",
 "X54_ROTATE":"build/drnas-x54",
 "X55_CONTROL_OFF":"build/drnas-x55",
 "X55_CONTROL_ON":"build/drnas-x55",
 "X55_ROTATE_OFF":"build/drnas-x55",
 "X55_ROTATE_ON":"build/drnas-x55",
}
POLICY={arm:"baseline" for arm in ARMS}
PROFILED={"X55_CONTROL_ON","X55_ROTATE_ON"}


def sha(data):return hashlib.sha256(data).hexdigest()
def emit(key,obj):print(key+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")


def official_manifest():
    original=json.loads((ROOT/"manifest.json").read_text())
    old=json.loads((ROOT/"protocol.json").read_text())
    if sha((ROOT/"manifest.json").read_bytes())!=old["manifest_sha256"]:
        raise RuntimeError("Original frozen REAL36 manifest mismatch")
    if len(original)!=36 or len({v["sha256"] for v in original})!=36:
        raise RuntimeError("Original input cardinality/SHA mismatch")
    for v in original:
        p=pathlib.Path(v["path"])
        if sha(p.read_bytes())!=v["sha256"]:raise RuntimeError("Original CNF drift: "+str(p))
    return original,old


def freeze():
    sources,original=official_manifest()
    versions={
        "original_source_run":43387395060,
        "prior_x53_run":43399730112,
        "prior_x54_run":43402461614,
        "frozen_binary_run":43386621130,
        "original_manifest_sha256":original["manifest_sha256"],
        "binary_sha256":{k:sha(pathlib.Path(p).read_bytes()) for k,p in BIN.items()},
        "source_sha256":[s["sha256"] for s in sources],
        "source_families":dict(collections.Counter(s["family"] for s in sources)),
        "count":36,"shards":SHARDS,"repeats":REPS,"cap_s":CAP,
        "arms":list(ARMS),"total_trials":36*REPS*len(ARMS),
        "proof_file_size_limit_bytes":512*1024*1024,
        "selection":"Unchanged REAL36 STRICT metadata/size-selected official SAT2024 CNFs",
        "experiment":"retrospective sealed policy ablation, NOT a novel blind benchmark",
        "policy":"X54/X55 same CDCL & deletion policy; rotation and CPU profiler separately toggled",
        "proof":"All solver UNSAT answers require successful independent drat-trim check",
        "caveat":"The original selection is not representative of all industrial SAT problems",
    }
    save("x55_freeze/protocol.json",versions)
    emit("X55_FREEZE",versions)


def parse_cnf(raw):
    try:s=raw.decode("ascii")
    except UnicodeDecodeError as e:raise RuntimeError("Non-ascii original CNF") from e
    n=expected=None;clauses=[];c=[]
    for line in s.splitlines():
        l=line.strip()
        if not l or l[0] in ("c","%"):continue
        if l.startswith("p "):
            a=l.split()
            if n is not None or len(a)!=4 or a[0:2]!=["p","cnf"]:raise RuntimeError("Bad DIMACS header")
            n,expected=int(a[2]),int(a[3]);continue
        for word in l.split():
            if word.startswith(("c","%")):break
            lit=int(word)
            if abs(lit)>n:raise RuntimeError("Literal outside CNF")
            if lit:c.append(lit)
            else:clauses.append(tuple(c));c=[]
    if n is None or c or len(clauses)!=expected:raise RuntimeError("Incomplete original DIMACS")
    return n,clauses


def check_sat(stdout,clauses,n):
    vals={}
    try:
        for line in stdout.splitlines():
            if not line.startswith("v "):continue
            for word in line[2:].split():
                lit=int(word)
                if lit==0:continue
                if abs(lit)>n or (abs(lit) in vals and vals[abs(lit)]!=(lit>0)):
                    return False
                vals[abs(lit)]=(lit>0)
        return all(any(vals.get(abs(lit))==(lit>0) for lit in c) for c in clauses)
    except ValueError:return False


def run_process(cmd,stdout,stderr,usage,timeout):
    def fsize():
        resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024))
    with stdout.open("w") as out,stderr.open("w") as err:
        started=time.perf_counter()
        p=subprocess.Popen(["/usr/bin/time","-f","%U %S %M","-o",str(usage),*cmd],
                 stdout=out,stderr=err,start_new_session=True,preexec_fn=fsize)
        expired=False
        try:p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            expired=True
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
        elapsed=time.perf_counter()-started
    rss=None;cpu_s=None
    if usage.exists():
        row=usage.read_text(errors="replace").splitlines()
        for ln in row:
            vals=ln.split()
            if len(vals)==3:
                try:cpu_s=float(vals[0])+float(vals[1]);rss=int(vals[2])
                except ValueError:pass
    return p.returncode,elapsed,expired,rss,cpu_s


def record(src,arm,rep,temp):
    cnf=pathlib.Path(src["path"])
    raw=cnf.read_bytes()
    if sha(raw)!=src["sha256"]:raise RuntimeError("Original SHA mismatch")
    n,clauses=parse_cnf(raw)
    out=temp/"run.out";err=temp/"run.err";usage=temp/"run.usage";proof=temp/"run.drat"
    for p in (out,err,usage,proof):p.unlink(missing_ok=True)
    if arm in POLICY:
        cmd=[BIN[arm],str(cnf),"--mode","core","--time",str(CAP),
             "--stats","--proof",str(proof),"--x52-proof-deletions"]
        cmd+=["--x53-policy",POLICY[arm],"--x53-progress"]
        if "ROTATE" in arm:cmd.append("--x54-rotate-watches")
        if arm in PROFILED:cmd.append("--x55-profile")
    elif arm=="KISSAT":cmd=[BIN[arm],str(cnf),str(proof)]
    else:cmd=[BIN[arm],"-q","--no-binary",str(cnf),str(proof)]
    rc,wall,expired,rss,cpu=run_process(cmd,out,err,usage,CAP+0.30)
    out_text=out.read_text(errors="replace");err_text=err.read_text(errors="replace")
    native={};x53={};progress=[];x55={};x55_progress=[]
    for line in err_text.splitlines():
        if line.startswith("X41_STATS "):
            try:native=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X53_STATS "):
            try:x53=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X53_PROGRESS "):
            try:progress.append(json.loads(line.split(" ",1)[1]))
            except json.JSONDecodeError:pass
        if line.startswith("X55_PROFILE "):
            try:x55=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X55_PROGRESS "):
            try:x55_progress.append(json.loads(line.split(" ",1)[1]))
            except json.JSONDecodeError:pass
    reported="TIMEOUT" if expired else "UNKNOWN"
    check_s=0.0;checker_status="not_needed"
    if not expired:
        if rc==10:
            reported="SAT_VERIFIED" if check_sat(out_text,clauses,n) else "WRONG_SAT"
            if reported=="WRONG_SAT":raise RuntimeError(f"Incorrect SAT: {arm} {src['id']} {rep}")
        elif rc==20:
            reported="UNSAT_UNVERIFIED";checker_status="no_proof"
            if proof.exists() and proof.stat().st_size>0:
                tick=time.perf_counter()
                try:
                    ck=subprocess.run(["build/drat-trim",str(cnf),str(proof)],
                        capture_output=True,text=True,timeout=12)
                    check_s=time.perf_counter()-tick
                    if ck.returncode==0 and "s VERIFIED" in ck.stdout:
                        reported="UNSAT_CERTIFIED";checker_status="verified"
                    else:checker_status="unverified_or_rejected"
                except subprocess.TimeoutExpired:
                    check_s=time.perf_counter()-tick
                    checker_status="checker_timeout"
        elif rc==153 and proof.exists() and proof.stat().st_size==512*1024*1024:
            reported="PROOF_SIZE_LIMIT"
            checker_status="resource_censored"
        elif rc not in (0,):reported="PROCESS_ERROR"
    if arm in POLICY and not expired and rc in (0,10,20) and not x53:
        raise RuntimeError("Missing final X53 telemetry")
    if arm in PROFILED and not expired and rc in (0,10,20) and not x55:
        raise RuntimeError("Missing final X55 CPU profile")
    accepted=wall<=CAP and reported in ("SAT_VERIFIED","UNSAT_CERTIFIED")
    status="timeout" if expired else reported
    last=x53 if x53 else progress[-1] if progress else {}
    return {
        "source_id":src["id"],"sha256":src["sha256"],"family":src["family"],
        "rep":rep,"arm":arm,"status":status,"accepted":accepted,
        "PAR2_s":round(wall if accepted else 2*CAP,6),
        "solve_e2e_s":round(wall,6),"proof_audit_s":round(check_s,6),
        "checker_status":checker_status,"returncode":rc,
        "maxrss_kib":rss,"cpu_s":cpu,"native":native,
        "x53":x53,"last_progress":last if not x53 else progress[-1] if progress else {},
        "telemetry_partial":bool((expired or reported=="PROOF_SIZE_LIMIT") and (progress or x55_progress)),
        "progress_samples":len(progress),
        "x55":x55,"x55_last_progress":x55_progress[-1] if x55_progress else {},
        "x55_progress_samples":len(x55_progress),
        "proof_size_limited":reported=="PROOF_SIZE_LIMIT",
        "proof_size_bytes":proof.stat().st_size if proof.exists() else 0,
    }


def shard_run(index):
    if index not in range(SHARDS):raise ValueError("Shard out of range")
    original,_=official_manifest()
    frozen=json.loads(pathlib.Path("x55_freeze/protocol.json").read_text())
    if frozen["source_sha256"] != [s["sha256"] for s in original]:
        raise RuntimeError("Source manifest not frozen")
    for arm in ARMS:
        if sha(pathlib.Path(BIN[arm]).read_bytes())!=frozen["binary_sha256"][arm]:
            raise RuntimeError("Binary checksum mismatch")
    selected=[src for src in original if src["id"]%SHARDS==index]
    if len(selected)!=3:raise RuntimeError("Unexpected original shard size")
    output=pathlib.Path(f"x55_shards/{index}");output.mkdir(parents=True,exist_ok=True)
    with (output/"trials.jsonl").open("w") as fd,tempfile.TemporaryDirectory() as d:
        temp=pathlib.Path(d)
        for src in selected:
            for rep in range(REPS):
                names=list(ARMS)
                shift=(src["id"]+rep*3)%len(names)
                names=names[shift:]+names[:shift]
                for arm in names:
                    row=record(src,arm,rep,temp)
                    fd.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n");fd.flush()
                    emit("X55_TRIAL",{k:row[k] for k in (
                        "source_id","family","rep","arm","status","accepted",
                        "PAR2_s","solve_e2e_s","progress_samples","maxrss_kib")})
                emit("X54_PROGRESS",{"shard":index,"source_id":src["id"],"reps_done":rep+1})
    save(output/"report.json",{"shard":index,"sources":[v["sha256"] for v in selected],
        "manifest_sha256":frozen["original_manifest_sha256"],
        "binary_sha256":frozen["binary_sha256"],
        "source_count":len(selected),"trials":len(selected)*REPS*len(ARMS)})
    emit("X55_SHARD_FINAL",{"shard":index,"trials":len(selected)*REPS*len(ARMS)})


def sum_arm(rows):
    result={
        "attempts":len(rows),"SAT":sum(r["accepted"] and r["status"]=="SAT_VERIFIED" for r in rows),
        "UNSAT":sum(r["accepted"] and r["status"]=="UNSAT_CERTIFIED" for r in rows),
        "solved":sum(r["accepted"] for r in rows),
        "PAR2_s":round(sum(r["PAR2_s"] for r in rows),5),
        "E2E_s":round(sum(r["solve_e2e_s"] for r in rows),5),
        "proof_audit_s":round(sum(r["proof_audit_s"] for r in rows),5),
        "proof_unverified":sum(r["status"]=="UNSAT_UNVERIFIED" for r in rows),
        "thread_cpu_s":round(sum(r["cpu_s"] or 0 for r in rows),6),
        "bcp_binary_sample_cpu_ns":sum((r["x55"] or r["x55_last_progress"]).get("bcp_binary_sample_cpu_ns",0) for r in rows),
        "bcp_watch_sample_cpu_ns":sum((r["x55"] or r["x55_last_progress"]).get("bcp_watch_sample_cpu_ns",0) for r in rows),
        "proof_size_limited":sum(r["proof_size_limited"] for r in rows),
        "telemetry_partial":sum(r["telemetry_partial"] for r in rows),
    }
    fields=("x54_rotated_scans","x54_true_reuse","x54_deleted_never_reused","x54_deleted_reused",
            "watch_entries","dead_watch_entries","blocker_hits","long_literal_checks",
            "watch_moves","binary_checks","trail_pops","unit_events","conflict_events",
            "reason_uses","analysis_uses","conflict_clause_uses",
            "deleted_unused","deleted_used","protected_lbd","protected_recent",
            "protected_reused","live_learnt","live_used","live_unused")
    result["telemetry_totals"]={k:sum((r["x53"] or r["last_progress"]).get(k,0)
                                      for r in rows) for k in fields}
    names=("analysis","select","reduce","proof","garbage_collect")
    phases={}
    for name in names:
        calls=samples=sample_cpu_ns=0
        for r in rows:
            t=r["x55"] or r["x55_last_progress"]
            calls+=t.get(name+"_calls",0)
            samples+=t.get(name+"_samples",0)
            sample_cpu_ns+=t.get(name+"_sample_cpu_ns",0)
        phases[name]={"calls":calls,"samples":samples,
                       "sample_cpu_ns":sample_cpu_ns,
                       "systematic_extrapolated_cpu_s":round(128*sample_cpu_ns/1e9,6) if samples else None}
    raw_bcp=result["bcp_binary_sample_cpu_ns"]+result["bcp_watch_sample_cpu_ns"]
    result["cpu_sample_profile"]={
        "bcp_binary_estimate_s":round(result["bcp_binary_sample_cpu_ns"]*1024/1e9,6),
        "bcp_watch_estimate_s":round(result["bcp_watch_sample_cpu_ns"]*1024/1e9,6),
        "bcp_sample_total_estimate_s":round(raw_bcp*1024/1e9,6),
        "bcp_trail_samples":sum((r["x55"] or r["x55_last_progress"]).get("bcp_trail_samples",0) for r in rows),
        "phase":phases,
        "caution":"Systematic sampling; extrapolation not exact. Compare separate matched arms and avoid adding nested GC to reduction."
    }
    return result


def comparison(rows,baseline,candidate):
    grouped=collections.defaultdict(list)
    for r in rows:grouped[(r["sha256"],r["rep"])].append(r)
    per_source=collections.defaultdict(float)
    per_source_reps=collections.Counter()
    for (sha,rep),trial in grouped.items():
        by={v["arm"]:v for v in trial}
        if set(by)!=set(ARMS):raise RuntimeError("Unpaired trial")
        per_source[sha]+=by[candidate]["PAR2_s"]-by[baseline]["PAR2_s"]
        per_source_reps[sha]+=1
    if any(n!=REPS for n in per_source_reps.values()):
        raise RuntimeError("Different repetitions in formula cluster")
    values=list(per_source.values());rng=random.Random(531145)
    boot=sorted(sum(rng.choices(values,k=len(values))) for _ in range(3000))
    return {"observed_PAR2_delta_s":round(sum(values),5),
        "95pct_cluster_bootstrap_delta_s":[round(boot[75],5),round(boot[2924],5)],
        "source_count":len(values),"two_repeats_same_source":True}


def finish():
    original,_=official_manifest()
    frozen=json.loads(pathlib.Path("x55_freeze/protocol.json").read_text())
    allrows=[]
    for idx in range(SHARDS):
        directory=pathlib.Path("x55_downloads")/f"x55-shard-{idx}"
        r=json.loads((directory/"report.json").read_text())
        if r["manifest_sha256"]!=frozen["original_manifest_sha256"]:
            raise RuntimeError("Shard manifest mismatch")
        if r["binary_sha256"]!=frozen["binary_sha256"]:
            raise RuntimeError("Inconsistent binary version")
        batch=[json.loads(line) for line in (directory/"trials.jsonl").read_text().splitlines()]
        if len(batch)!=3*REPS*len(ARMS):raise RuntimeError("Incomplete shard")
        allrows.extend(batch)
    expected={(s["sha256"],rep,arm) for s in original for rep in range(REPS) for arm in ARMS}
    actual={(r["sha256"],r["rep"],r["arm"]) for r in allrows}
    if len(allrows)!=len(expected) or expected!=actual:raise RuntimeError("Incorrect trial pairing")
    incorrect=[r for r in allrows if r["status"] in ("WRONG_SAT","PROCESS_ERROR")]
    if incorrect:raise RuntimeError("Incorrect or errored solver output")
    allrows.sort(key=lambda r:(r["source_id"],r["rep"],r["arm"]))
    report={
        "status":"COMPLETE","protocol":frozen,
        "overall":{a:sum_arm([r for r in allrows if r["arm"]==a]) for a in ARMS},
        "families":{f:{a:sum_arm([r for r in allrows
                   if r["family"]==f and r["arm"]==a]) for a in ARMS}
                   for f in sorted(set(r["family"] for r in allrows))},
        "comparisons":{
            "rotation_unprofiled":comparison(allrows,"X54_CONTROL","X54_ROTATE"),
            "recompiled_control":comparison(allrows,"X54_CONTROL","X55_CONTROL_OFF"),
            "recompiled_rotate":comparison(allrows,"X54_ROTATE","X55_ROTATE_OFF"),
            "profiling_overhead_control":comparison(allrows,"X55_CONTROL_OFF","X55_CONTROL_ON"),
            "profiling_overhead_rotate":comparison(allrows,"X55_ROTATE_OFF","X55_ROTATE_ON"),
            "rotation_with_profiler":comparison(allrows,"X55_CONTROL_ON","X55_ROTATE_ON")
        },
        "reference_comparisons":{},
        "limitations":[
            "Original SAT2024 application-labelled CNFs, but reused retrospective REAL36 strict set (not blind).",
            "Selection from small compressed official formulas, not representative of overall industrial SAT.",
            "X55 changes no CDCL policy; CPU sampling and watcher rotation are independently toggled.",
            "Phase times use systematic CPU samples and are not exact additive runtime partitions.",
            "The optional CPU profiler overhead must be measured against the same X55 binary with profile disabled.",
            "Hardware counters are conditional on perf_event permissions; absence of data means unavailable, not zero.",
            "Nested garbage-collection CPU samples overlap the larger reduction phase.",
            "Proof size limit is resource censoring, never an incorrect solver answer.",
            "Source-cluster bootstrap treats two repetitions as dependent.",
            "Independent DRAT checker costs are separate from solver E2E; all solvers write proofs during solving.",
            "No branch promotion based on these retrospective results."
        ],
    }
    dest=pathlib.Path("x55_final");dest.mkdir(exist_ok=True)
    save(dest/"report.json",report)
    with (dest/"paired_trials.jsonl").open("w") as fd:
        for r in allrows:fd.write(json.dumps(r,sort_keys=True,separators=(",",":"))+"\n")
    emit("X55_FINAL",report)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("freeze","shard","finish"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.stage=="freeze":freeze()
    elif a.stage=="shard":shard_run(a.shard)
    else:finish()


if __name__=="__main__":main()
