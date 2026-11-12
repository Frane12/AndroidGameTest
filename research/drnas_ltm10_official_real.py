#!/usr/bin/env python3
"""LTM10 REAL: frozen policy trained and tested on distinct ORIGINAL SAT2024 CNFs.
Pilot, not a globally blind competition result. No solver parameter is selected on holdout.
"""
import argparse, bz2, gzip, hashlib, json, lzma, os, pathlib, re, resource
import shutil, statistics, subprocess, time
from remotezip import RemoteZip

ARCHIVE="https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1"
POLICIES={"conservative":"1.0,0.85","explore":"0.7,0.95","aggressive":"1.4,0.75"}
ARMS=("LTM9_FIXED","LTM10_LEARNED","Kissat","CaDiCaL","CryptoMiniSat")
ROOT=pathlib.Path("ltm10_official_real")
TRAIN_CAP=4.0
TEST_CAP=8.0
SEEDS=(17,29)
MAX_RAW=16000000

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True),flush=True)

def unpack(name,data):
    lower=name.lower()
    if lower.endswith(".cnf.xz"):
        dec=lzma.LZMADecompressor()
        raw=dec.decompress(data,max_length=MAX_RAW+1)
        if not dec.eof:raise ValueError("exceeded xz decompression limit")
    elif lower.endswith(".cnf.gz"):
        raw=gzip.decompress(data)
    elif lower.endswith(".cnf.bz2"):
        raw=bz2.decompress(data)
    elif lower.endswith(".cnf"):
        raw=data
    else:raise ValueError("unexpected extension")
    if not 0<len(raw)<=MAX_RAW:raise ValueError("decompression too large/empty")
    return raw

def parse_cnf(raw):
    n=expected=None
    clauses=[]
    current=[]
    for line in raw.decode("ascii",errors="replace").splitlines():
        row=line.strip()
        if not row or row[0] in ("c","%"):continue
        if row.startswith("p "):
            p=row.split()
            if n is not None or len(p)!=4 or p[1]!="cnf":
                raise ValueError("invalid DIMACS header")
            n,expected=int(p[2]),int(p[3])
            if n<0 or expected<0:raise ValueError("negative header")
            continue
        if n is None:raise ValueError("clauses precede header")
        for token in row.split():
            lit=int(token)
            if abs(lit)>n:raise ValueError("literal out of range")
            if lit:current.append(lit)
            else:
                clauses.append(tuple(current))
                current=[]
                if len(clauses)>expected:raise ValueError("too many clauses")
    if n is None or len(clauses)!=expected or current:
        raise ValueError("invalid DIMACS clause count")
    return n,clauses

def bucket(n,clauses):
    binary=sum(len(c)==2 for c in clauses)
    density=len(clauses)/max(1,n)
    return ("binary" if binary>=len(clauses)*.55 else "mixed")+"|"+(
        "dense" if density>4 else "sparse")

def pick_sources(out):
    # Official earlier pilot used 8 quantiles from 70KB..2MB.
    # Exclude that exposed cohort by archive entry, not only by filename of extracted CNF.
    with RemoteZip(ARCHIVE,timeout=90) as z:
        entries=sorted((x for x in z.infolist()
            if not x.is_dir() and x.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2"))),
            key=lambda x:(x.file_size,x.filename))
        old=[x for x in entries if 70000<=x.file_size<=2000000]
        assert len(old)>=12, "official source archive changed"
        known={old[((len(old)-1)*(2*i+1))//16].filename for i in range(8)}
        # Use smaller genuine instances than the previous 8s pilot, which solved none in DRNAS.
        pool=[x for x in entries if 1000<=x.file_size<70000 and x.filename not in known]
        if len(pool)<24:
            pool=[x for x in entries if 1000<=x.file_size<=130000 and x.filename not in known]
        if len(pool)<16:raise RuntimeError("not enough independent size-filtered CNFs")
        # Size-stratified ordering fixed before measuring solver performance.
        positions=sorted(set(((len(pool)-1)*(2*i+1))//72 for i in range(36)))
        chosen=[]
        seen=set()
        for pos in positions:
            entry=pool[pos]
            try:
                raw=unpack(entry.filename,z.read(entry))
                n,clauses=parse_cnf(raw)
                digest=hashlib.sha256(raw).hexdigest()
                if digest in seen:continue
                seen.add(digest)
                target=out/"sources"/(digest+".cnf")
                target.write_bytes(raw)
                chosen.append(dict(name=entry.filename,sha256=digest,n=n,
                    clauses=len(clauses),compressed_bytes=entry.file_size,
                    raw_bytes=len(raw),path=str(target),bucket=bucket(n,clauses),
                    stage="train" if len(chosen)%2==0 else "holdout",
                    parsed_clauses=clauses))
            except (ValueError, EOFError, OSError) as e:
                emit("LTM10_REAL_SKIP",{"archive_entry":entry.filename,"reason":str(e)[:180]})
            if len(chosen)>=24:break
    if len(chosen)<16 or len(chosen)%2:
        raise RuntimeError("insufficient balanced original CNF sources")
    train=[x for x in chosen if x["stage"]=="train"]
    hold=[x for x in chosen if x["stage"]=="holdout"]
    assert len(train)==len(hold) and not {x["sha256"] for x in train}&{x["sha256"] for x in hold}
    def public(x):
        return {k:v for k,v in x.items() if k!="parsed_clauses"}
    for x in chosen:emit("LTM10_REAL_SOURCE",public(x))
    return train,hold,[public(x) for x in chosen]

def witness_ok(n,clauses,out):
    values={}
    try:
        for line in out.splitlines():
            if not line.startswith("v "):continue
            for token in line[2:].split():
                lit=int(token)
                if not lit:continue
                if abs(lit)>n or (abs(lit) in values and values[abs(lit)]!=(lit>0)):
                    return False
                values[abs(lit)]=lit>0
    except ValueError:return False
    return all(any(values.get(abs(lit))==(lit>0) for lit in clause) for clause in clauses)

def command(arm,src,seed,policy,cap):
    path=src["path"]
    if arm in ("LTM9_FIXED","LTM10_LEARNED","training"):
        return ["mre_atlas23/bin/drnas_ltm9",path,"--mode","LTM8_FAST",
                "--time",str(cap),"--seed",str(seed),"--policy",POLICIES[policy]]
    if arm=="Kissat":return ["kissat","-q",f"--seed={seed}",path]
    if arm=="CaDiCaL":return ["cadical","-q",f"--seed={seed}",path]
    if arm=="CryptoMiniSat":return ["cryptominisat5","--threads=1","--verb=0",path]
    raise ValueError(arm)

def trial(arm,src,seed,policy,cap):
    env=dict(os.environ,DRNAS_LTM8_MEMORY="",OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1")
    start=time.monotonic()
    try:
        p=subprocess.run(command(arm,src,seed,policy,cap),capture_output=True,text=True,
            timeout=cap,env=env,preexec_fn=lambda:resource.setrlimit(
                resource.RLIMIT_AS,(3*1024**3,3*1024**3)))
        rc=p.returncode
        stdout=p.stdout
        diagnostics=(p.stderr+"\n"+p.stdout)[-1800:]
    except subprocess.TimeoutExpired:
        rc=124
        stdout=""
        diagnostics="time cap"
    elapsed=time.monotonic()-start
    if rc==10:
        status="SAT_VERIFIED" if witness_ok(src["n"],src["parsed_clauses"],stdout) else "INVALID_SAT"
    elif rc==20:status="UNSAT_UNVERIFIED"
    elif rc in (0,124):status="TIMEOUT" if rc==124 else "UNKNOWN"
    else:status="ERROR"
    reported=status in ("SAT_VERIFIED","UNSAT_UNVERIFIED")
    verified=status=="SAT_VERIFIED"
    stats={}
    if arm in ("LTM9_FIXED","LTM10_LEARNED","training"):
        for name in ("conflicts","decisions","propagations","restarts","learnts","learned"):
            hits=re.findall(r"(?<!\w)"+name+r"=(\d+)",stdout)
            if hits:stats[name]=int(hits[-1])
    return dict(arm=arm,sha256=src["sha256"],source=src["name"],bucket=src["bucket"],
        policy=policy,seed=seed,returncode=rc,status=status,stats=stats,
        php_marker="LTM9_PHP_CERT" in stdout,
        e2e_s=round(elapsed,6),
        PAR2_reported_s=round(elapsed if reported else 2*cap,6),
        PAR2_verified_s=round(elapsed if verified else 2*cap,6),
        diagnostics=diagnostics if status in ("ERROR","INVALID_SAT") else "")

def summarize(rows):
    totals={}
    for arm in ARMS:
        xx=[x for x in rows if x["arm"]==arm]
        totals[arm]=dict(trials=len(xx),
            solved_reported=sum(x["status"] in ("SAT_VERIFIED","UNSAT_UNVERIFIED") for x in xx),
            SAT_verified=sum(x["status"]=="SAT_VERIFIED" for x in xx),
            UNSAT_unverified=sum(x["status"]=="UNSAT_UNVERIFIED" for x in xx),
            errors=sum(x["status"] in ("ERROR","INVALID_SAT") for x in xx),
            PAR2_reported_s=round(sum(x["PAR2_reported_s"] for x in xx),6),
            PAR2_verified_s=round(sum(x["PAR2_verified_s"] for x in xx),6),
            conflicts_sum=sum(x["stats"].get("conflicts",0) for x in xx),
            conflicts_records=sum("conflicts" in x["stats"] for x in xx),
            decisions_sum=sum(x["stats"].get("decisions",0) for x in xx),
            decisions_records=sum("decisions" in x["stats"] for x in xx))
    return totals

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest:
        assert parse_cnf(b"c test\np cnf 2 2\n1 0\n-2 0\n")[0]==2
        assert witness_ok(2,[(1,),(-2,)],"v 1 -2 0\n")
        assert not witness_ok(2,[(1,)],"v -1 0\n")
        print("LTM10_REAL_SELFTEST_PASS")
        return
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    for binary in ("kissat","cadical","cryptominisat5"):
        if not shutil.which(binary):raise RuntimeError("missing reference: "+binary)
    if ROOT.exists():raise RuntimeError("refusing stale benchmark directory")
    (ROOT/"sources").mkdir(parents=True)
    train,hold,manifest=pick_sources(ROOT)
    (ROOT/"manifest.json").write_text(json.dumps(dict(archive=ARCHIVE,
        source_count=len(manifest),train_count=len(train),holdout_count=len(hold),
        official_original_cnf=True,global_blind=False,one_logical_cpu=True,cpu=cpu,
        training_cap_s=TRAIN_CAP,test_cap_s=TEST_CAP,seeds=SEEDS,arms=ARMS,
        known_pilot_excluded=True,independent_unsat_proof=False,sources=manifest),indent=2))
    # Train ONLY on actual train sources. Measured E2E PAR2, default to fixed conservative.
    by_bucket={}
    with (ROOT/"training.jsonl").open("w") as fd:
        for src in train:
            for policy in POLICIES:
                row=trial("training",src,17,policy,TRAIN_CAP)
                fd.write(json.dumps(row)+"\n");fd.flush()
                emit("LTM10_REAL_TRAIN",row)
                if row["status"] in ("ERROR","INVALID_SAT"):
                    raise RuntimeError("training solver invalid/failed")
                by_bucket.setdefault(src["bucket"],{}).setdefault(src["sha256"],{})[policy]=row
    memory={}
    for b,sources in by_bucket.items():
        baseline=[v["conservative"]["PAR2_reported_s"] for v in sources.values()]
        best_name="conservative"
        best_median=statistics.median(baseline)
        reports={}
        for name in POLICIES:
            scores=[v[name]["PAR2_reported_s"] for v in sources.values()]
            med=statistics.median(scores)
            wins=sum(v[name]["PAR2_reported_s"]+.01<v["conservative"]["PAR2_reported_s"] for v in sources.values())
            reports[name]=dict(median_PAR2=med,wins=wins,observations=len(scores))
            if name!="conservative" and len(scores)>=3 and med<best_median*.9 and (
                    sum(baseline)-sum(scores)>.4) and wins>=max(2,len(scores)//2):
                best_name=name
                best_median=med
        memory[b]=dict(policy=best_name,source_count=len(sources),train_metrics=reports)
    (ROOT/"frozen_memory.json").write_text(json.dumps(memory,indent=2,sort_keys=True))
    emit("LTM10_REAL_FROZEN_MEMORY",memory)
    # Holdout policy is frozen; rotate order and use source-disjoint paired testing.
    rows=[]
    claims={}
    with (ROOT/"results.jsonl").open("w") as fd:
        for ix,src in enumerate(hold):
            learned=memory.get(src["bucket"],{}).get("policy","conservative")
            for rep,seed in enumerate(SEEDS):
                order=list(ARMS)
                offset=(ix+rep)%len(order)
                for arm in order[offset:]+order[:offset]:
                    policy="conservative" if arm=="LTM9_FIXED" else learned if arm=="LTM10_LEARNED" else "external"
                    row=trial(arm,src,seed,policy,TEST_CAP)
                    row["rep"]=rep
                    row["shard"]=ix//3
                    rows.append(row)
                    fd.write(json.dumps(row)+"\n");fd.flush()
                    emit("LTM10_REAL_TRIAL",row)
                    if row["status"] in ("ERROR","INVALID_SAT"):
                        raise RuntimeError("invalid SAT result or solver failure: "+str(row))
                    if row["status"] in ("SAT_VERIFIED","UNSAT_UNVERIFIED"):
                        answer="SAT" if row["status"]=="SAT_VERIFIED" else "UNSAT"
                        old=claims.setdefault(src["sha256"],answer)
                        if old!=answer:raise RuntimeError("SAT/UNSAT solver disagreement: "+src["sha256"])
    totals=summarize(rows)
    shards={str(i):summarize([r for r in rows if r["shard"]==i])
            for i in sorted({r["shard"] for r in rows})}
    by_bucket_report={b:summarize([r for r in rows if r["bucket"]==b])
            for b in sorted({r["bucket"] for r in rows})}
    ratios={ref:round(totals[ref]["PAR2_reported_s"]/max(1e-9,totals["LTM10_LEARNED"]["PAR2_reported_s"]),5)
            for ref in ARMS if ref!="LTM10_LEARNED"}
    result=dict(official_original_cnf=True,pilot=True,globally_blind=False,
        train_count=len(train),holdout_count=len(hold),total_trials=len(rows),
        frozen_memory=memory,totals=totals,shards=shards,buckets=by_bucket_report,
        reference_PAR2_over_LTM10=ratios,independent_unsat_proof=False,
        note="UNSAT without independently checked LRAT/DRAT remains unverified. Native stats may be absent.")
    (ROOT/"summary.json").write_text(json.dumps(result,indent=2))
    emit("LTM10_REAL_FINAL",result)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as fd:
            fd.write("## LTM10 original SAT2024 CNF pilot\n")
            fd.write(f"{len(train)} train / {len(hold)} disjoint holdout CNF, 2 repeats, {TEST_CAP:g}s cap; one logical CPU. Holdout policy frozen.\n\n")
            fd.write("| Solver | Solved | SAT verified | UNSAT unverified | PAR2 reported (s) | PAR2 verified (s) | Conflicts (records) | Decisions (records) |\n|---|---:|---:|---:|---:|---:|---:|---:|\n")
            for arm,v in totals.items():
                fd.write(f"| {arm} | {v['solved_reported']}/{v['trials']} | {v['SAT_verified']} | {v['UNSAT_unverified']} | {v['PAR2_reported_s']:.3f} | {v['PAR2_verified_s']:.3f} | {v['conflicts_records']} | {v['decisions_records']} |\n")
            fd.write("\nUNSAT results do not have independently verified proof; no claim of global superiority.\n")

if __name__=="__main__":main()
