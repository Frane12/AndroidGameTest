#!/usr/bin/env python3
"""Measure authentic SAT Competition 2026 CNFs; short and long wall-clock caps.
Frozen 18 sample, 9 train, 9 holdout. All modes have the SAME input,
binary/CPU core, per-mode cap and randomized trial ordering.
Returns per-run min/max solved times, explicit censored timeouts.
"""
import argparse,csv,hashlib,json,os,random,re,subprocess,time
from pathlib import Path
from official_shortlong_select import download_and_features,SALT
CAPS=(2.0,15.0)
REPEATS=2
MODES=("ca_plain","orig_v76","orig_v76_plain","v92_sparse","v92_structural")
FIELDS=("id","split","stratum","sha256","cap_s","rep","mode","status",
        "wall_s","error","choice","hints","extended","gate_reason")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    p.add_argument("--shard",type=int,required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--exe",required=True)
    args=p.parse_args()
    assert 0<=args.shard<6
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    mfile=Path(args.manifest)
    m=json.loads(mfile.read_text())
    assert m["protocol"]==SALT and len(m["cases"])==18
    selection=m["cases"][args.shard*3:(args.shard+1)*3]
    assert len(selection)==3
    core=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    binary=str(Path(args.exe).resolve())
    (root/"meta.json").write_text(json.dumps({
        "shard":args.shard,"cases":selection,"caps":CAPS,
        "repeats":REPEATS,"modes":MODES,"cpu_core":core,
        "selection_manifest_sha256":hashlib.sha256(mfile.read_bytes()).hexdigest()},indent=2))
    rows=[];issues=[]
    with (root/"raw.csv").open("w",newline="") as fp:
        writer=csv.DictWriter(fp,fieldnames=FIELDS);writer.writeheader()
        for item in selection:
            case=item["id"];dest=root/(case+".cnf")
            try:
                check=download_and_features(case,dest)
                assert check["sha256"]==item["sha256"],"DIMACS hash drift"
                assert check["features"]==item["features"],"CNF features drift"
                print("OFFICIAL_VERIFIED_INPUT",case,check["sha256"],flush=True)
            except Exception as e:
                issues.append(f"{case}: DOWNLOAD_OR_HASH_ERROR {e}")
                for cap in CAPS:
                    for rep in range(REPEATS):
                        for mode in MODES:
                            row=dict(id=case,split=item["split"],stratum=item["stratum"],
                                     sha256=item["sha256"],cap_s=cap,rep=rep,
                                     mode=mode,status="INPUT_ERROR",wall_s=0,
                                     error=str(e),choice="",hints="",extended="",gate_reason="")
                            writer.writerow(row);rows.append(row)
                fp.flush();continue
            for cap in CAPS:
                for rep in range(REPEATS):
                    modes=list(MODES)
                    random.Random(1787+int(case[:8],16)+int(cap)*891+rep*7711).shuffle(modes)
                    if rep==1:modes.reverse()
                    for mode in modes:
                        seed=(830031+rep*527+int(item["sha256"][:8],16))%2**32
                        command=[binary,mode,str(dest),str(seed)]
                        started=time.monotonic()
                        extra={};error=""
                        try:
                            result=subprocess.run(command,capture_output=True,text=True,
                                timeout=cap,check=False)
                            sec=time.monotonic()-started
                            if result.returncode!=0:raise ValueError(
                                f"returncode={result.returncode}; {result.stderr[-300:]}")
                            found=[line for line in result.stdout.splitlines()
                                   if line.startswith("DRNAS_CAUSAL\t")]
                            if len(found)!=1:raise ValueError("not exactly one DRNAS_CAUSAL result")
                            attrs=dict(part.split("=",1) for part in found[0].split("\t")[1:])
                            if attrs["mode"]!=mode:raise ValueError("solver mode mismatch")
                            status=attrs["answer"]
                            if status!=item["official_label"]:raise ValueError(
                                "SAT/UNSAT answer contradicts official label")
                            extra={k:attrs.get(k,"") for k in ("v92_choice","hints","extended","gate_reason")}
                        except subprocess.TimeoutExpired:
                            status="TIMEOUT";sec=cap
                        except Exception as e:
                            status="ERROR";sec=time.monotonic()-started;error=str(e)
                            issues.append(f"{case} {mode} {cap} {rep}: {error}")
                        row=dict(id=case,split=item["split"],stratum=item["stratum"],
                                 sha256=item["sha256"],cap_s=cap,rep=rep,mode=mode,
                                 status=status,wall_s=round(sec,6),error=error,
                                 choice=extra.get("v92_choice",""),
                                 hints=extra.get("hints",""),
                                 extended=extra.get("extended",""),
                                 gate_reason=extra.get("gate_reason",""))
                        writer.writerow(row);rows.append(row);fp.flush()
                        print("OFFICIAL_TIMING",case[:8],item["split"],
                              "cap",cap,"rep",rep,mode,status,row["wall_s"],flush=True)
            dest.unlink(missing_ok=True)
    assert len(rows)==3*len(CAPS)*REPEATS*len(MODES),len(rows)
    bymode={}
    for mode in MODES:
        values=[r for r in rows if r["mode"]==mode]
        observed=[r["wall_s"] for r in values if r["status"] in ("SAT","UNSAT")]
        bymode[mode]={"solved":len(observed),"n":len(values),
               "shortest_s":min(observed) if observed else None,
               "longest_s":max(observed) if observed else None,
               "timeout":sum(r["status"]=="TIMEOUT" for r in values)}
    (root/"summary.json").write_text(json.dumps({
        "shard":args.shard,"modes":bymode,"issues":issues,"count":len(rows),
        "caution":"max actual time unknown for timed-out trials"},indent=2))
    if issues:raise RuntimeError("Incomplete or invalid official test: "+"; ".join(issues[:5]))
    print("OFFICIAL_SHARD_PASS",args.shard,len(rows),flush=True)
if __name__=="__main__":main()
