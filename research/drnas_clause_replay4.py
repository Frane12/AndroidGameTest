#!/usr/bin/env python3
"""CLAUSE-REPLAY4: frozen X5 no-instrument repeat of original SAT2024 retention A/B.

Primary case: REAL36 original #16 scheduling Break_unsat_06_07.xml, 5
independent matched serial repetitions, same X5 source/binary and flags,
except the already-existing --x5-retain policy switch. Two easy scheduling
controls (#6/#12, 3 repetitions) and two hard scheduling controls (#24/#28,
2 repetitions) are preregistered. Never promote from this test or treat
UNKNOWN counts as solved. SAT model/DRAT original CNF check on each success.
"""
from __future__ import annotations
import hashlib,json,os,random,resource,signal,subprocess,sys,tempfile,time,statistics
from pathlib import Path

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research"))
import drnas_x55_cpu_real36 as REAL

OUT=Path("clause_replay4")
OUT.mkdir(exist_ok=True)
BIN=(R/"build/drnas-clause-replay4").resolve()
DRAT=(R/"build/drat-trim").resolve()
CAP=4.0
PROTOCOL=((16,5),(6,3),(12,3),(24,2),(28,2))
ARMS=("BASELINE","RETAIN")

def sha(data):return hashlib.sha256(data).hexdigest()
def emit(name,data):print(name+" "+json.dumps(data,sort_keys=True),flush=True)

def run(src,arm):
    raw=Path(src["path"]).read_bytes()
    assert sha(raw)==src["sha256"]
    n,clauses=REAL.parse_cnf(raw)
    assert n==src["nvars"] and len(clauses)==src["nclauses"]
    with tempfile.TemporaryDirectory() as td:
        proof=Path(td)/"out.drat"
        cmd=[str(BIN),str(Path(src["path"]).resolve()),
             "--mode","core","--time",str(CAP),"--stats",
             "--x5-no-minimize","--proof",str(proof),
             "--x5-retain" if arm=="RETAIN" else "--x5-no-retain"]
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        t=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        timeout=False
        try:out,err=p.communicate(timeout=CAP+.75)
        except subprocess.TimeoutExpired:
            timeout=True;os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
        wall=time.perf_counter()-t
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu=max(0.0,after.ru_utime+after.ru_stime-
                    before.ru_utime-before.ru_stime)
        assert timeout or p.returncode in (0,10,20),(
            "NATIVE_BAD_EXIT",src["id"],arm,p.returncode,err[-700:])
        status="TIMEOUT" if timeout else (
            "SAT" if p.returncode==10 else "UNSAT" if p.returncode==20 else "UNKNOWN")
        verified=False;proof_s=0.0
        if status=="SAT":
            verified=REAL.check_sat(out,clauses,n)
            assert verified,("ORIGINAL_SAT_INVALID",src["id"])
        if status=="UNSAT":
            assert proof.exists() and proof.stat().st_size>0,("NO_UNSAT_PROOF",src["id"])
            check=time.perf_counter()
            c=subprocess.run([str(DRAT),str(Path(src["path"]).resolve()),
                str(proof)],capture_output=True,text=True,timeout=90)
            verified=c.returncode==0 and "s VERIFIED" in c.stdout
            proof_s=time.perf_counter()-check
            assert verified,("ORIGINAL_UNSAT_INVALID",src["id"],c.stdout[-500:])
        telemetry={}
        if not timeout:
            for line in err.splitlines():
                tag,sep,data=line.partition(" ")
                if tag in ("X41_STATS","X5_STATS"):
                    assert tag not in telemetry
                    telemetry[tag]=json.loads(data)
            assert "X41_STATS" in telemetry and "X5_STATS" in telemetry
            assert telemetry["X41_STATS"]["status"]==status
        stats=telemetry.get("X41_STATS",{})
        return {"status":status,"verified":verified,"wall_s":wall,"cpu_s":cpu,
            "proof_check_s":proof_s,"PAR2_s":wall if verified and wall<=CAP else 2*CAP,
            "conflicts":stats.get("conflicts"),"decisions":stats.get("decisions"),
            "removed":stats.get("reduce_removed"),
            "protected":telemetry.get("X5_STATS",{}).get("protected_clauses")}

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    originals,old=REAL.official_manifest()
    src={s["id"]:s for s in originals}
    assert len(originals)==36
    assert all(i in src for i,reps in PROTOCOL)
    protocol={
        "status":"FROZEN_BEFORE_EXECUTION",
        "source":"original SATCompetition2024 REAL36 original frozen CNFs",
        "original_real36_run":43387395060,
        "original_manifest_sha256":old["manifest_sha256"],
        "source_ids":[{"id":i,"repeats":rep,"sha256":src[i]["sha256"],
            "family":src[i]["family"],"filename":src[i]["filename"]}
            for i,rep in PROTOCOL],
        "arms":list(ARMS),"both_same_compiled_X5":True,
        "one_logical_CPU":True,"cap_s":CAP,
        "matched_order_randomized_predefined":True,
        "no_telemetry_instrumentation":True,
        "repeat_counts_fixed_no_tuning":True,
        "independent_original_SAT_and_UNSAT_verification":True,
        "retrospective_not_blind":True,
        "no_main_edits":True,"no_promotion":True}
    p=OUT/"manifest.json"
    p.write_text(json.dumps(protocol,indent=2,sort_keys=True)+"\n")
    emit("REPLAY4_FROZEN",{"sha256":sha(p.read_bytes()),
        "ids":list(PROTOCOL),"same_binary":True,"one_CPU":True})
    schedule=[(i,j) for i,reps in PROTOCOL for j in range(reps)]
    random.Random(141142).shuffle(schedule)
    rows=[]
    for i,rep in schedule:
        order=list(ARMS)
        random.Random(int(src[i]["sha256"][:12],16)+rep).shuffle(order)
        values={}
        for arm in order:values[arm]=run(src[i],arm)
        a,b=values["BASELINE"],values["RETAIN"]
        assert not(a["verified"] and b["verified"] and a["status"]!=b["status"]),(
            "SOURCE_VERIFIED_CONTRADICTION",i,rep)
        row={"id":i,"repeat":rep,"source_SHA256":src[i]["sha256"],
            "BASELINE":a,"RETAIN":b}
        rows.append(row)
        emit("REPLAY4_PAIR",{"id":i,"rep":rep,
            "baseline_status":a["status"],"retain_status":b["status"],
            "base_wall_s":round(a["wall_s"],5),"retain_wall_s":round(b["wall_s"],5),
            "base_cpu_s":round(a["cpu_s"],5),"retain_cpu_s":round(b["cpu_s"],5),
            "base_conflicts":a["conflicts"],"retain_conflicts":b["conflicts"],
            "base_removed":a["removed"],"retain_removed":b["removed"]})
    by_id={}
    for i,reps in PROTOCOL:
        sample=[r for r in rows if r["id"]==i]
        assert len(sample)==reps and len({r["repeat"] for r in sample})==reps
        x,y=[r["BASELINE"] for r in sample],[r["RETAIN"] for r in sample]
        full=[r for r in sample if r["BASELINE"]["verified"] and r["RETAIN"]["verified"]]
        by_id[str(i)]={
            "name":src[i]["filename"],"family":src[i]["family"],"repetitions":reps,
            "both_verified":len(full),
            "baseline_verified":sum(r["verified"] for r in x),
            "retain_verified":sum(r["verified"] for r in y),
            "baseline_median_e2e_s":statistics.median(r["wall_s"] for r in x),
            "retain_median_e2e_s":statistics.median(r["wall_s"] for r in y),
            "baseline_median_cpu_s":statistics.median(r["cpu_s"] for r in x),
            "retain_median_cpu_s":statistics.median(r["cpu_s"] for r in y),
            "baseline_PAR2_s":sum(r["PAR2_s"] for r in x),
            "retain_PAR2_s":sum(r["PAR2_s"] for r in y),
            "retain_faster_matched_verified":sum(
                r["RETAIN"]["wall_s"]<r["BASELINE"]["wall_s"] for r in full),
            "baseline_faster_matched_verified":sum(
                r["RETAIN"]["wall_s"]>r["BASELINE"]["wall_s"] for r in full)}
    final={
        "status":"COMPLETE","repeated_cases":len(PROTOCOL),"paired_runs":len(rows),
        "verified_runs":sum(r[a]["verified"] for r in rows for a in ARMS),
        "each_original_model_or_unsat_drat_checked":True,
        "source_SHA256_frozen_before_execution":True,"one_logical_cpu":True,
        "same_binary":True,"source_retrospective_not_blind":True,
        "main_modified":False,"solver_promoted":False,
        "by_source":by_id,"protocol_SHA256":sha(p.read_bytes())}
    (OUT/"paired.jsonl").write_text(
        "".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    (OUT/"report.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    emit("REPLAY4_FINAL",final)

if __name__=="__main__":main()
