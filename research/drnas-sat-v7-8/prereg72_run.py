#!/usr/bin/env python3
"""Run one shard of the pre-registered DRNAS 72-CNF experiment.
Same runner, pinned single CPU, randomized paired order, 2 seeds.
Native CaDiCaL model checks SAT; UNSAT needs independent proof for formal claims.
Missing downloads / invalid results are explicitly retained as errors.
"""
import argparse,bz2,csv,gzip,hashlib,json,lzma,math,os,random,re,select,signal,subprocess,time,urllib.request
from pathlib import Path
MODES=["orig_v76","hybrid_gate_with_observer","ca_plain"]
CAP=20
REPEATS=2
SHARDS=12
MAX_RAW=64*1024*1024
MAX_CNF=160*1024*1024
FIELDS=["id","stratum","label","sha256","repeat","seed","mode",
        "status","wall_s","error","log"]
def fetch(case,dest):
    url="https://benchmark-database.de/file/"+case
    req=urllib.request.Request(url,headers={
        "User-Agent":"DRNAS-pre-registered-72-2026/1.0",
        "Accept":"application/octet-stream"})
    with urllib.request.urlopen(req,timeout=90) as response:
        data=response.read(MAX_RAW+1)
    if len(data)>MAX_RAW:raise RuntimeError("CNF download too large")
    if data.startswith(b"\xfd7zXZ\x00"):buf=lzma.decompress(data)
    elif data.startswith(b"\x1f\x8b"):buf=gzip.decompress(data)
    elif data.startswith(b"BZh"):buf=bz2.decompress(data)
    else:buf=data
    if len(buf)>MAX_CNF:raise RuntimeError("CNF decompressed size too large")
    if b"p cnf " not in buf[:100000]:raise RuntimeError("Downloaded data is not DIMACS CNF")
    digest=hashlib.sha256(buf).hexdigest()
    dest.write_bytes(buf)
    return dict(url=url,raw_sha256=hashlib.sha256(data).hexdigest(),
                dimacs_sha256=digest,cnf_bytes=len(buf),raw_bytes=len(data))
def execute(binary,cnf,mode,seed,logfile,cap):
    cmd=[str(binary),mode,str(cnf),str(seed)]
    with logfile.open("wb") as output:
        started=time.monotonic()
        proc=subprocess.Popen(cmd,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        fd=os.pidfd_open(proc.pid)
        try:
            poll=select.poll();poll.register(fd,select.POLLIN)
            ms=max(0,math.ceil(1000*(cap-(time.monotonic()-started))))
            if not poll.poll(ms):
                os.killpg(proc.pid,signal.SIGKILL)
                proc.wait()
                return "TIMEOUT",float(cap),""
            rc=proc.wait()
            elapsed=time.monotonic()-started
        finally:
            os.close(fd)
    output=logfile.read_text(errors="replace")
    if rc!=0:return "ERROR",elapsed,"Exit "+str(rc)+": "+output[-350:]
    found=re.findall(r"^DRNAS_CAUSAL\tmode=(\S+)\tanswer=(SAT|UNSAT)\t",output,re.M)
    if len(found)!=1 or found[0][0]!=mode:
        return "ERROR",elapsed,"Missing or ambiguous solver result record"
    return found[0][1],elapsed,""
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    p.add_argument("--shard",type=int,required=True)
    p.add_argument("--binary",required=True)
    p.add_argument("--outdir",required=True)
    a=p.parse_args()
    if not 0<=a.shard<SHARDS:raise ValueError("Shard 0..11 required")
    manifest=json.loads(Path(a.manifest).read_text())
    assert manifest["protocol"]=="DRNAS-2026-preregistered-72-v1"
    cases=manifest["cases"]
    assert len(cases)==72 and len({x["id"] for x in cases})==72
    selected=cases[a.shard*6:(a.shard+1)*6]
    assert len(selected)==6
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    binary=Path(a.binary).resolve()
    rows=[];sources=[];errors=[]
    with (out/"raw.csv").open("w",newline="",encoding="utf8") as fp:
        writer=csv.DictWriter(fp,fieldnames=FIELDS);writer.writeheader()
        for case in selected:
            name=case["id"]
            cnf=out/(name+".cnf")
            try:
                source=fetch(name,cnf)
                sources.append(dict(id=name,**source))
                print("PREREG_INPUT",name,source["dimacs_sha256"],
                      source["cnf_bytes"],flush=True)
            except Exception as e:
                errors.append(dict(id=name,stage="fetch",error=str(e)))
                print("PREREG_FETCH_ERROR",name,repr(e),flush=True)
                # Store explicit missing-data row for every scheduled solver / seed.
                for rep in range(REPEATS):
                    for mode in MODES:
                        row=dict(id=name,stratum=case["stratum"],label=case["label"],
                                 sha256="",repeat=rep,seed="",mode=mode,
                                 status="INPUT_ERROR",wall_s=0,error=str(e),log="")
                        writer.writerow(row);rows.append(row)
                fp.flush()
                continue
            for rep in range(REPEATS):
                seed=(7707000+527*rep+int(name[:8],16))%2**32
                order=MODES[:]
                random.Random(20261031+int(name[:8],16)+rep*1447).shuffle(order)
                for mode in order:
                    log=out/(name[:8]+f"_r{rep}_"+mode+".log")
                    try:
                        status,elapsed,error=execute(binary,cnf,mode,seed,log,CAP)
                    except Exception as e:
                        status,elapsed,error="ERROR",0.0,str(e)
                    if status in ("SAT","UNSAT") and case["label"] in ("SAT","UNSAT") and status!=case["label"]:
                        error="Contradicts official verified SAT Competition label"
                        status="ERROR"
                    row=dict(id=name,stratum=case["stratum"],label=case["label"],
                        sha256=source["dimacs_sha256"],repeat=rep,seed=seed,
                        mode=mode,status=status,wall_s=round(elapsed,5),
                        error=error,log=str(log.name))
                    rows.append(row);writer.writerow(row);fp.flush()
                    print("PREREG_RESULT",name[:8],case["stratum"],rep,mode,
                          status,round(elapsed,5),error[:80],flush=True)
            cnf.unlink(missing_ok=True)
    for name in MODES:
        assert sum(r["mode"]==name for r in rows)==len(selected)*REPEATS
    score={}
    for stratum in sorted({case["stratum"] for case in selected}):
        sub=[r for r in rows if r["stratum"]==stratum]
        score[stratum]={}
        for mode in MODES:
            rs=[r for r in sub if r["mode"]==mode]
            if any(r["status"] in ("ERROR","INPUT_ERROR") for r in rs):
                score[stratum][mode]={"invalid":True,"n_rows":len(rs)}
            else:
                costs=[r["wall_s"] if r["status"] in ("SAT","UNSAT") else 2*CAP for r in rs]
                score[stratum][mode]={
                    "solved":sum(r["status"] in ("SAT","UNSAT") for r in rs),
                    "n_rows":len(rs),"mean_par2_s":round(sum(costs)/len(costs),4)}
    summary={"protocol":manifest["protocol"],"shard":a.shard,
        "manifest_sha256":hashlib.sha256(Path(a.manifest).read_bytes()).hexdigest(),
        "cpu_affinity_single_core":cpu,"cap_s":CAP,"repeats":REPEATS,
        "modes":MODES,"input_cases":selected,"download_sources":sources,
        "errors":errors,"rows":rows,"stratum_scores":score,
        "cautions":["Public-label-informed stratified subset; not a blind representative holdout",
          "Within-job single-core affinity, cross-job CPU models may vary",
          "SAT witness checked in native DRNAS code; UNSAT requires external certificate check",
          "Time-outs are not UNSAT; PAR2 assigns 40 seconds",
          "No pre-experiment tuning on these 72 selected IDs"] }
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    (out/"summary.md").write_text(
        "# Pre-registered 72-CNF SAT 2026 evaluation: shard "+str(a.shard)+"\n\n"+
        "Subset selected before runs using public official results; **not blind or representative**.\n\n"+
        "| Stratum | Mode | Solved | Runs | Mean PAR2 (s) |\n|---|---|---:|---:|---:|\n"+
        "".join(f"| {st} | {mode} | {obj.get('solved','INVALID')} | {obj['n_rows']} | {obj.get('mean_par2_s','INVALID')} |\n"
            for st,v in score.items() for mode,obj in v.items())+
        "\nAll exact inputs, model outcomes, timeouts, and errors are retained in summary.json.\n")
    if errors or any(r["status"]=="ERROR" for r in rows):
        raise RuntimeError("Incomplete/invalid preregistered shard; check artifacts")
    print("PREREG_SHARD_PASS",a.shard,len(rows),flush=True)
if __name__=="__main__":main()
