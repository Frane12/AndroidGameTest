#!/usr/bin/env python3
"""GF-CDCL-NOVEL2 source-only smoke, original SHA, 1CPU, 2x2x4 arms.
Previously seen cases, not a blind or certified UNSAT benchmark.
"""
import json,os,pathlib,random,re,subprocess,tempfile,time,hashlib
import drnas_xorabc3_live_trail as abc3
import drnas_equiv9_prospective_seed_holdout as e9
import r158x_causal_benchmark as telemetry

ROOT=pathlib.Path("mre_gf_cdcl_novel2")
BIN=ROOT/"bin/gf_cdcl_novel2"
CAP=6.0
ARMS={"clean":"clean","direct":"direct_boundary",
      "novel2":"novel2","novel2_shadow":"novel2_shadow"}
def need(cond,msg):
    if not cond: raise RuntimeError("GFCDCL_NOVEL2_FAIL_CLOSED "+msg)
def trial(case,rep,arm):
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    started=time.perf_counter()
    src=abc3.abc2.prev.source(case)
    n,cnf=e9.x22.read_cnf(src)
    need(hashlib.sha256(src.read_bytes()).hexdigest()==case["sha256"],
         "original SHA mismatch")
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        tsv=pathlib.Path(tmp)/"original-certified.tsv"
        rows=0
        if arm!="clean":
            info,_=abc3.export_native(src,tsv)
            rows=info["rows"]
        left=CAP-(time.perf_counter()-started)
        need(left>1.1,"source extraction exceeded budget")
        cmd=[str(BIN.resolve()),ARMS[arm],str(src.resolve()),
             str(tsv.resolve()),str(max(1.0,left-0.5))]
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,
              timeout=max(0.05,left-0.02),check=False)
        except subprocess.TimeoutExpired:
            p=None
        status="TIMEOUT";backend="TIMEOUT";verified=False;metrics={}
        if p is not None:
            need(p.returncode in (0,10,20),
                 "CaDiCaL exit "+str(p.returncode)+" "+p.stderr[-1000:])
            output,t,stats,nrows,derived=telemetry.parse_native(p.stdout.encode(),ARMS[arm])
            backend=t["status"]
            status="TIMEOUT" if backend=="UNKNOWN" else backend
            if backend=="SAT":
                model=abc3.get_model(output)
                need(model and e9.x22.holds(cnf,model),
                     "SAT invalid against original CNF")
                verified=True
            if arm!="clean":
                need(nrows==rows,"certified source-row mismatch")
            match=re.search(r"^R158X_RESULT .*?$",p.stdout,re.M)
            need(match is not None,"native result telemetry missing")
            kv={}
            for field in match.group().split():
                if "=" in field:
                    k,v=field.split("=",1)
                    kv[k]=v
            metrics={k:int(kv[k]) for k in
              ("derived_direct_proposals","source_direct_proposals",
               "derived_shadow_candidates","source_rows_skipped",
               "derived_rows_examined","direct_proposals",
               "reason_clauses_completed","source_rows") if k in kv}
            metrics.update({k:stats.get(k) for k in
              ("conflicts","decisions","propagations","learned")})
    elapsed=time.perf_counter()-started
    if elapsed>=CAP:status="TIMEOUT";verified=False
    need(status!="SAT" or verified,"invalid SAT status")
    return dict(sha=case["sha256"],arm=arm,rep=rep,cap=CAP,
       status=status,backend_status=backend,SAT_original_verified=verified,
       UNSAT_independent_LRAT=False,one_logical_CPU=cpu,
       original_SHA_checked=True,E2E_wall_s=round(elapsed,6),
       metrics=metrics,source_label="frozen_nonblind")
def main():
    ROOT.mkdir(exist_ok=True)
    m=abc3.verify()
    # Select by original-CNF source XOR structure ONLY. Never inspect times,
    # model outcomes, or prior benchmark scores when freezing this pilot.
    ranked=[]
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        tsv=pathlib.Path(tmp)/"rows.tsv"
        for case in sorted(m["cases"],key=lambda x:x["sha256"]):
            info,_=abc3.export_native(abc3.abc2.prev.source(case),tsv)
            rows=[]
            for line in tsv.read_text().splitlines():
                parts=list(map(int,line.split()))
                rows.append((tuple(sorted(parts[2:])),parts[1]))
            seen=set(rows);derived=set()
            for i in range(len(rows)):
                for j in range(i+1,len(rows)):
                    a,pa=rows[i];b,pb=rows[j]
                    diff=tuple(sorted(set(a)^set(b)))
                    if 2<=len(diff)<=8 and (diff,pa^pb) not in seen:
                        derived.add((diff,pa^pb))
            short=sum(len(v)<=4 for v,_ in derived)
            if derived:
                ranked.append((short,len(derived),len(rows),case["sha256"],case))
    ranked.sort(key=lambda r:(-r[0],-r[1],-r[2],r[3]))
    need(len(ranked)>=2,"at least two source-only XOR-cross-row controls")
    selected={"xor_cross_"+str(i):ranked[i][4] for i in range(2)}
    print("GFCDCL_NOVEL2_SELECTOR "+json.dumps([
       dict(source_sha=r[3],short_cross_rows=r[0],
            derived_cross_rows=r[1],source_rows=r[2])
       for r in ranked[:2]],sort_keys=True),flush=True)
    print("GFCDCL_NOVEL2_FROZEN "+json.dumps(
      dict(sources={k:v["sha256"] for k,v in selected.items()},
           arms=list(ARMS),reps=2,cap_s=CAP,one_cpu=True,
           selected_by="source_only_short_cross_GF2_count",
           previously_seen_not_blind=True)),flush=True)
    records=[]
    for label,case in sorted(selected.items()):
        for rep in range(2):
            arms=list(ARMS)
            random.Random(case["sha256"]+str(rep)+"novel2").shuffle(arms)
            for arm in arms:
                r=trial(case,rep,arm)
                r["label"]=label
                records.append(r)
                print("GFCDCL_NOVEL2_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
                (ROOT/"smoke.json").write_text(json.dumps(records,indent=2)+"\n")
    need(len(records)==16,"16 matched attempts required")
    need(all(r["original_SHA_checked"] and
         (r["status"]!="SAT" or r["SAT_original_verified"]) for r in records),
         "verification failure")
    print("GFCDCL_NOVEL2_SMOKE_PASS 16",flush=True)
if __name__=="__main__":main()
