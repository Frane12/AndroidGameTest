#!/usr/bin/env python3
"""Original SAT2025 #299: preregistered native X59 CDCL ablation.
Research input was previously exposed in REAL2025; THIS IS A DEVELOPMENT
DIAGNOSTIC, NOT A BLIND HOLDOUT. Never use it for promotion.
"""
import collections,hashlib,json,os,resource,signal,statistics,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"cdcl299_diag_results"
TARGET="b9ed6fd14f4fc969ec966a4b54c36872"
TARGET_SHA="c46261a9a52b8080ddc040f6b58e7a48eb651993ff6f67ae78830848b8e14fb2"
CAP=8.0
ARMS={
 "BASE":[],
 "RESTARTS":["--x5-restarts"],
 "RETAIN":["--x5-retain"],
 "RESTART_RETAIN":["--x5-restarts","--x5-retain"],
 "MIN_OFF":["--x5-no-minimize"],
 "MIN_OFF_RESTART":["--x5-no-minimize","--x5-restarts"],
 "GC_OFF":["--x5-no-gc"],
 "HOTWATCH":["--x58-hotwatch"],
 "STAMP_GLUE":["--x59-stamp-glue"],
 "CLAUSE_SCORE":["--sat-clause1-score"],
 "CLAUSE_PROBE":["--sat-clause1-probe"],
 "MATH":["--sat-construct-ms","100"],
 "CaDiCaL":None
}
def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        while data:=f.read(1<<20):h.update(data)
    return h.hexdigest()
def witness_ok(source,model_path):
    assign={}
    for l in model_path.read_text(errors="replace").splitlines():
        if not l.startswith("v "):continue
        for tok in l[2:].split():
            lit=int(tok)
            if not lit:continue
            if abs(lit) in assign and assign[abs(lit)]!=(lit>0):return False
            assign[abs(lit)]=(lit>0)
    n=m=None;count=0;open_clause=False;satisfied=False
    with source.open() as f:
        for line in f:
            words=line.split()
            if not words or words[0] in ("c","%"):continue
            if words[0]=="p":
                if n is not None or len(words)!=4:return False
                n,m=map(int,words[2:])
                if len(assign)!=n:return False
                continue
            if n is None:return False
            for v in words:
                lit=int(v)
                if lit:
                    open_clause=True
                    satisfied=satisfied or assign.get(abs(lit))==(lit>0)
                else:
                    if not satisfied:return False
                    open_clause=False;satisfied=False;count+=1
    return n is not None and not open_clause and count==m
def command(arm,cnf):
    if arm=="CaDiCaL":return [str(ROOT/"build/cadical"),"-q","--no-binary",str(cnf)]
    return [str(ROOT/"build/drnas-sat-native-x59"),str(cnf),"--mode","core",
            "--time","7.8","--stats",*ARMS[arm]]
def trial(src,arm,rep,cpu):
    cmd=command(arm,src)
    with tempfile.TemporaryDirectory(prefix="real299-") as td:
        out=Path(td)/"stdout";err=Path(td)/"stderr"
        def limits():
            os.sched_setaffinity(0,{cpu})
            resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,)*2)
            resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2)
        begin=time.perf_counter()
        with out.open("w") as o,err.open("w") as e:
            p=subprocess.Popen(cmd,stdout=o,stderr=e,
                               start_new_session=True,preexec_fn=limits)
            timed=False
            try:p.wait(timeout=CAP)
            except subprocess.TimeoutExpired:
                timed=True
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.wait()
        solver_s=time.perf_counter()-begin
        stdout=out.read_text(errors="replace");stderr=err.read_text(errors="replace")
        status="TIMEOUT" if timed else "UNKNOWN"
        telemetry={}
        for line in stderr.splitlines():
            for prefix in ("X41_STATS ","X5_STATS ","X58_STATS ",
                           "X59_STATS ","SAT_CONSTRUCT_STATS ","SAT_CLAUSE1_STATS "):
                if line.startswith(prefix):
                    try:telemetry[prefix.strip()]=json.loads(line[len(prefix):])
                    except ValueError:pass
        if not timed:
            if p.returncode==10:
                if "s SATISFIABLE" not in stdout or not witness_ok(src,out):
                    raise RuntimeError(f"INVALID_SAT {arm} {stderr[-300:]}")
                status="SAT_VERIFIED"
            elif p.returncode==20:
                # Prior independently checked CaDiCaL SAT on unchanged original.
                raise RuntimeError("FALSE_UNSAT_ON_KNOWN_SAT "+arm)
            elif p.returncode not in (0,153):
                raise RuntimeError(f"SOLVER_CRASH {arm} code={p.returncode} stderr={stderr[-360:]}")
        e2e=time.perf_counter()-begin
        accepted=status=="SAT_VERIFIED" and e2e<=CAP
        return dict(arm=arm,rep=rep,status=status,accepted=accepted,
            solver_s=round(solver_s,6),e2e_s=round(e2e,6),
            PAR2_s=round(e2e if accepted else 2*CAP,6),
            telemetry=telemetry,solver_rc=p.returncode,source_sha256=TARGET_SHA)
def main():
    OUT.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    manifest=json.loads((ROOT/"sat_real2025_inputs/manifest.json").read_text())
    src=next(x for x in manifest["ready_sources"] if x["gbd"]==TARGET)
    assert src["sha256"]==TARGET_SHA
    path=ROOT/src["path"];assert sha(path)==TARGET_SHA
    if src["vars"]!=960 or src["clauses"]!=62749:raise RuntimeError("source dimensions drift")
    rows=[];started=time.perf_counter()
    for rep in range(2):
        arms=list(ARMS)
        arms=arms[rep%len(arms):]+arms[:rep%len(arms)]
        for arm in arms:
            row=trial(path,arm,rep,cpu)
            rows.append(row)
            stats=row["telemetry"].get("X41_STATS",{})
            print("CDCL299_TRIAL "+json.dumps(dict(arm=arm,rep=rep,
              status=row["status"],PAR2_s=row["PAR2_s"],
              conflicts=stats.get("conflicts"),decisions=stats.get("decisions"),
              propagations=stats.get("propagations"),learnt=stats.get("learnt"),
              restarts=stats.get("restarts")),sort_keys=True),flush=True)
    final={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        final[arm]=dict(solved=sum(r["accepted"] for r in rr),
           PAR2_s=round(sum(r["PAR2_s"] for r in rr),6),
           median_e2e_s=round(statistics.median(r["e2e_s"] for r in rr),6))
    (OUT/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    (OUT/"protocol.json").write_text(json.dumps(dict(source_sha256=TARGET_SHA,
       source_gbd=TARGET,one_logical_cpu=cpu,cap_e2e_s=CAP,repetitions=2,
       already_known_source=True,not_blind=True,source_size_vars=960,
       source_size_clauses=62749,arm_flags=ARMS,git_sha=os.getenv("GITHUB_SHA"),
       native_binary_sha256=sha(ROOT/"build/drnas-sat-native-x59"),
       cadical_sha256=sha(ROOT/"build/cadical")),
       indent=2,sort_keys=True)+"\n")
    print("CDCL299_FINAL "+json.dumps(dict(arms=final,source_sha256=TARGET_SHA,
        elapsed_s=round(time.perf_counter()-started,3)),sort_keys=True),flush=True)
if __name__=="__main__":main()
