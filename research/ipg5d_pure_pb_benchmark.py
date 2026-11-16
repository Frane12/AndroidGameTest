#!/usr/bin/env python3
"""Source-frozen pure VeriPB CP audit on W5/W7/W9 odd-wheel 3-coloring CNFs.

No SAT solver or DPLL proof producer is called. Only original source PB
cutting-plane steps are emitted. Labels are independently set by a small
three-color oracle before running the proof generator.
"""
import hashlib,json,os,pathlib,random,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg5d_pure"
GEN=ROOT/"research/ipg5d_pure_oddwheel_pb.py"
VP=ROOT/"veripb-tool/bin/veripb"
sys.path.insert(0,str(ROOT/"research"))
from ipg5c_general_benchmark import graph_3color_source,permute,three_color_oracle
from ipg1_fixtures import petersen

def run(args,limit=30):
    t=time.perf_counter()
    try:
        p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=limit)
        return p.returncode,round(time.perf_counter()-t,6),p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-t,6),"TIMEOUT"
def wheel(k):
    return k+1,[(i,(i+1)%k) for i in range(k)]+[(k,i) for i in range(k)]
def inputs():
    rng=random.Random(161126505)
    source=OUT/"sources";source.mkdir(parents=True,exist_ok=True)
    cases=[]
    def add(name,raw,expected,kind):
        path=source/(name+".cnf");path.write_bytes(raw)
        cases.append({"name":name,"sha256":hashlib.sha256(raw).hexdigest(),
                      "expected":expected,"kind":kind})
    for k in (5,7,9,6,8):
        n,edges=wheel(k)
        raw=graph_3color_source(n,edges)
        answer="SAT" if three_color_oracle(n,edges) else "UNSAT"
        assert (k%2==0)==(answer=="SAT")
        for trial in range(3 if k%2 else 1):
            add(f"wheel_{k}_{trial}",permute(raw,rng.randrange(10000000),f"wheel{k}_{trial}"),
                answer,"ODD_WHEEL" if k%2 else "EVEN_WHEEL_SAT")
    k33=[(a,b) for a in range(3) for b in range(3,6)]
    add("k33_sat",graph_3color_source(6,k33),"SAT","OTHER_SAT")
    k4=[(a,b) for a in range(4) for b in range(a+1,4)]
    add("k4_unsupported",graph_3color_source(4,k4),"UNSAT","OTHER_UNSUPPORTED")
    add("weighted_petersen_unsupported",petersen().encode(),"UNSAT","OTHER_UNSUPPORTED")
    (OUT/"frozen_manifest.json").write_text(json.dumps(
       {"seed":161126505,"cases":cases},indent=2,sort_keys=True)+"\n")
    return cases
def attempt(info):
    cnf=OUT/"sources"/(info["name"]+".cnf")
    dest=OUT/"trials"/info["name"];dest.mkdir(parents=True,exist_ok=True)
    proof=dest/"pure_veripb.pbp";meta=dest/"meta.json"
    sha=hashlib.sha256(cnf.read_bytes()).hexdigest()
    if sha!=info["sha256"]:raise ValueError("frozen manifest changed")
    rc,pt,out=run([sys.executable,GEN,"--cnf",cnf,"--proof",proof,
                   "--meta",meta,"--expected-sha256",sha],20)
    (dest/"generator.log").write_text(out)
    result={"name":info["name"],"kind":info["kind"],"expected":info["expected"],
            "source_sha256":sha,"producer_s":pt,"result":"UNKNOWN"}
    if info["kind"]=="ODD_WHEEL":
        if rc!=0 or not proof.exists():
            result["result"]="ERROR_NO_PURE_PB"
        else:
            data=json.loads(meta.read_text())
            result.update(pol_steps=data["pure_pol_steps"],rup_steps=data["rup_steps"],
                          proof_bytes=data["proof_bytes"],rim=data["odd_wheel_rim_length"])
            vr,vt,vout=run([VP,"--cnf",cnf,proof],30)
            (dest/"external_veripb.log").write_text(vout)
            result["veripb_s"]=vt
            result["result"]=(
                "PURE_CP_SOURCE_UNSAT_VERIFIED"
                if vr==0 and "s VERIFIED UNSATISFIABLE" in vout and
                data["pure_pol_steps"]==14 and data["rup_steps"]==0
                else "ERROR_VERIPB_REJECTED")
    else:
        if rc==0 or proof.exists():result["result"]="ERROR_UNSUPPORTED_ACCEPTED"
    print("IPG5D_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    return result
def negative_source_tests(cases):
    errors=[]
    case=next(x for x in cases if x["name"]=="wheel_5_0")
    cnf=OUT/"sources/wheel_5_0.cnf"
    tampered=OUT/"modified_original.cnf"
    tampered.write_bytes(cnf.read_bytes()+b"c changed exact source bytes\n")
    pb=OUT/"bad_sha.pbp"
    rc,_,_=run([sys.executable,GEN,"--cnf",tampered,"--proof",pb,
                 "--meta",OUT/"bad_sha.json",
                 "--expected-sha256",case["sha256"]],15)
    if rc==0 or pb.exists():errors.append("changed SHA accepted")
    # Remove one original source hub/rim conflict and update clause count.
    from ipg5d_pure_oddwheel_pb import source_wheel
    graph=source_wheel(cnf)
    h=graph["hub"];v=graph["rim"][0]
    edge=tuple(sorted((-graph["colors"][h][0],-graph["colors"][v][0])))
    lines=cnf.read_text().splitlines()
    possible=[i for i,line in enumerate(lines) if
              not line.startswith(("c","p")) and
              tuple(sorted(int(x) for x in line.split() if x!="0"))==edge]
    if len(possible)!=1:errors.append("could not locate source spoke")
    else:
        del lines[possible[0]]
        for i,line in enumerate(lines):
            if line.startswith("p cnf "):
                t=line.split();t[3]=str(int(t[3])-1)
                lines[i]=" ".join(t)
                break
        removed=OUT/"removed_spoke.cnf"
        removed.write_text("\n".join(lines)+"\n")
        second=OUT/"bad_spoke.pbp"
        rc,_,_=run([sys.executable,GEN,"--cnf",removed,"--proof",second,
                      "--meta",OUT/"bad_spoke.json",
                      "--expected-sha256",hashlib.sha256(removed.read_bytes()).hexdigest()],15)
        if rc==0 or second.exists():errors.append("missing source spoke accepted")
    return errors

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    cases=inputs()
    rows=[attempt(c) for c in cases]
    errs=[r["name"]+" "+r["result"] for r in rows if r["result"].startswith("ERROR")]
    errs+=negative_source_tests(cases)
    yes=[r for r in rows if r["result"]=="PURE_CP_SOURCE_UNSAT_VERIFIED"]
    controls=[r for r in rows if r["kind"]!="ODD_WHEEL"]
    s={
        "status":"PASS" if not errs and len(yes)==9 else "FAIL",
        "source_cases":len(rows),"oddwheel_independent_source_CP_verified":len(yes),
        "rim_sizes_verified":sorted({r["rim"] for r in yes}),
        "pure_pol_steps":sorted({r["pol_steps"] for r in yes}),
        "rup_steps":sorted({r["rup_steps"] for r in yes}),
        "controls":len(controls),
        "controls_correct_unknown":sum(r["result"]=="UNKNOWN" for r in controls),
        "errors":errs,"proof_bytes":[r["proof_bytes"] for r in yes],
        "scope":"14 original-source VeriPB cutting-plane lines, zero RUP/DPLL/CDCL, for identified odd-wheel three-coloring graphs W5/W7/W9. This is NOT a new proof for original weighted Petersen PCMAX, nor general polynomial SAT.",
    }
    (OUT/"rows.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
    (OUT/"summary.json").write_text(json.dumps(s,sort_keys=True,indent=2)+"\n")
    print("IPG5D_PURE_PB_TOTAL "+json.dumps(s,sort_keys=True),flush=True)
    return 0 if not errs else 1
if __name__=="__main__":sys.exit(main())
