#!/usr/bin/env python3
"""Eight frozen original 2026 graph-coloring CNFs: external VeriPB proof audit.

Development-retrospective only. IDs are selected by source catalog family
for this AUDIT, never provided to the graph recognizer or proof checker.
All 8 are part of previously frozen 67 source SHA manifest.
"""
import hashlib,json,os,pathlib,resource,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as frozen

OUT=ROOT/"results/graphclique_original8"
EMITTER=ROOT/"research/graphclique/emit_veripb.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
CAP=8.0

def one(src):
    cnf=ROOT/src["path"]
    assert frozen.sha(cnf)==src["sha256"],"source changed"
    base=OUT/str(src["id"])
    base.mkdir(parents=True,exist_ok=False)
    pb=base/"source-proof.pbp";meta=base/"source-proof.json"
    start=time.perf_counter()
    cmd=[sys.executable,str(EMITTER),"--cnf",str(cnf),
         "--pbp",str(pb),"--meta",str(meta)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP)
    if r.returncode!=0 or not pb.exists():
        raise RuntimeError("emitter failed on source "+str(src["id"])+": "+r.stdout[-250:])
    info=json.loads(meta.read_text())
    assert info["source_sha256"]==src["sha256"]
    remaining=CAP-(time.perf_counter()-start)
    if remaining<=0:raise RuntimeError("no external checker budget on original "+str(src["id"]))
    checked=subprocess.run([str(VERIPB),"--cnf",str(cnf),str(pb)],
        capture_output=True,text=True,timeout=remaining)
    if checked.returncode!=0 or "s VERIFIED UNSATISFIABLE" not in checked.stdout+checked.stderr:
        raise RuntimeError("external VeriPB rejected original "+str(src["id"])+": "+checked.stdout[-300:])
    elapsed=time.perf_counter()-start
    if elapsed>CAP:raise RuntimeError("over E2E cap on original "+str(src["id"]))
    result={"id":src["id"],"source_sha256":src["sha256"],
        "source_vars":src["variables"],"source_clauses":src["clauses"],
        "catalog_label":src["catalog_label"],
        "verdict":"UNSAT_VERIPB_VERIFIED",
        "colors":info["color_count"],"clique_size":info["clique_size"],
        "proof_bytes":pb.stat().st_size,
        "proof_sha256":hashlib.sha256(pb.read_bytes()).hexdigest(),
        "e2e_s":round(elapsed,6),"search_nodes":info["search_nodes"]}
    print("GRAPH_CLIQUE_ORIGINAL "+json.dumps(result,sort_keys=True),flush=True)
    return result

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    sources=frozen.frozen_sources()["sources"]
    graph_sources=[s for s in sources if s["family"]=="graph-coloring"]
    assert len(graph_sources)==8,"do not silently change original graph-family scope"
    OUT.mkdir(parents=True,exist_ok=True)
    trials=[one(s) for s in graph_sources]
    result={"status":"PASS","retrospective_originals":len(trials),
        "source_frozen":True,"source_sha256":[x["source_sha256"] for x in trials],
        "catalog_unknown_but_formally_proved":[x["id"] for x in trials
            if x["catalog_label"]=="unknown"],
        "max_e2e_s":max(x["e2e_s"] for x in trials),
        "tot_e2e_s":round(sum(x["e2e_s"] for x in trials),6),
        "verified_veripb":len(trials),"trials":trials,
        "not_blind":True,"no_main_promotion":True}
    (OUT/"final.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("GRAPH_CLIQUE_ORIGINAL8_FINAL "+json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":main()
