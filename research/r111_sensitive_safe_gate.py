#!/usr/bin/env python3
"""R111 experimental sensitivity selector. Never modifies original CNF or V15.3.1.
The only permitted intervention is a separately verified R107C UNSAT certificate.
All other cases fall back to the unchanged input, with bounded profiling cost.
"""
import argparse,hashlib,json,pathlib,subprocess,tempfile,time
from collections import Counter

def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def profile(path, byte_cap=24*1024*1024, clause_cap=1500000):
    p=pathlib.Path(path)
    if p.stat().st_size>byte_cap:return dict(eligible=False,reason="size_cap")
    widths=Counter();vars_seen=Counter();count=0;header=None;clause=[]
    with p.open() as f:
        for line in f:
            if line.startswith("c") or not line.strip():continue
            if line.startswith("p "):
                if header is not None: return dict(eligible=False,reason="duplicate_header")
                t=line.split()
                if len(t)!=4 or t[1]!="cnf":return dict(eligible=False,reason="header")
                header=(int(t[2]),int(t[3]));continue
            if header is None:return dict(eligible=False,reason="missing_header")
            for token in line.split():
                lit=int(token)
                if lit:
                    if abs(lit)>header[0]:return dict(eligible=False,reason="bad_literal")
                    clause.append(lit)
                    if len(clause)>100000:return dict(eligible=False,reason="long_clause")
                else:
                    count+=1; widths[len(clause)]+=1
                    if 2<=len(clause)<=6:
                        for v in set(map(abs,clause)):vars_seen[v]+=1
                    clause=[]
                    if count>clause_cap:return dict(eligible=False,reason="clause_cap")
    if header is None or count!=header[1] or clause:return dict(eligible=False,reason="truncated")
    short=sum(widths[k] for k in range(2,7))
    density=short/max(1,count)
    repeated=sum(v>=3 for v in vars_seen.values())
    score=round(0.65*density+0.35*min(1,repeated/max(1,header[0])),6)
    return dict(eligible=True,variables=header[0],clauses=count,short_fraction=round(density,6),
                repeated_variables=repeated,score=score,sha256=digest(p))

def decide(source,native,threshold=0.15,budget_s=1.0):
    start=time.monotonic(); features=profile(source)
    result=dict(protocol="R111-SAFE-SENSITIVITY",features=features,decision="fallback",
                reason="not_selected",original_sha256=digest(source))
    if not features.get("eligible"):result["reason"]=features["reason"];return result
    if features["score"]<threshold:result["reason"]="low_structural_score";return result
    # Native output remains isolated. Fail closed on timeout, nonzero or absent proof.
    with tempfile.TemporaryDirectory() as td:
        target=pathlib.Path(td)/"derived.cnf";evidence=pathlib.Path(td)/"evidence.json"
        try:
            cp=subprocess.run([native,str(source),str(target),str(evidence)],
                              capture_output=True,text=True,timeout=budget_s)
            if cp.returncode:raise ValueError("native_rejected")
            cert=json.loads(evidence.read_text())
            if not cert.get("gf2_unsat"):result["reason"]="no_verified_contradiction";return result
            if not cert.get("proof_row_ids"):raise ValueError("missing_proof_ancestry")
            # Native R107C independently replays proof against original source before
            # it emits the extra empty clause. Do not accept any unexpected output.
            if not target.is_file():raise ValueError("missing_derived")
            original=pathlib.Path(source).read_bytes()
            derived=target.read_bytes()
            if not derived.endswith(b"0\\n"):raise ValueError("missing_empty_clause")
            if digest(source)!=result["original_sha256"]:raise ValueError("source_changed")
            result["decision"]="certified_unsat";result["reason"]="native_independent_replay"
            result["proof_length"]=len(cert["proof_row_ids"])
        except (subprocess.TimeoutExpired,ValueError,OSError,KeyError,json.JSONDecodeError) as exc:
            result["reason"]="fail_closed_"+type(exc).__name__
    result["probe_s"]=round(time.monotonic()-start,6)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("cnf");p.add_argument("--native",required=True)
    p.add_argument("--threshold",type=float,default=.15);p.add_argument("--budget",type=float,default=1.)
    p.add_argument("--out",required=True);a=p.parse_args()
    if not 0<=a.threshold<=1 or not 0<a.budget<=10:raise SystemExit("invalid bounds")
    r=decide(a.cnf,a.native,a.threshold,a.budget)
    pathlib.Path(a.out).write_text(json.dumps(r,indent=2)+"\\n")
    print("R111_SAFE_GATE",json.dumps(r,sort_keys=True))
if __name__=="__main__":main()
