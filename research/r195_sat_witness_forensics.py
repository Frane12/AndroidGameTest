#!/usr/bin/env python3
"""R195 SAT witness failure forensics. No benchmark totals or source mutation.

Replays exact R195 failing official-2026 SAT source and seed, with progressively
more source-certified pairwise XORs given to CMS. Results never enter R195
performance report; invalid witnesses stay flagged, not accepted as SAT.
"""
import hashlib, json, pathlib, subprocess, sys, time
sys.path.insert(0,"research")
import r195_native_cms_benchmark as b
SRC=b.FROZEN/"official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf"
ROW=pathlib.Path("r195/forensics-source.tsv")
DER=pathlib.Path("r195/forensics-derived.tsv")
META=pathlib.Path("r195/forensics-evidence.json")
BIN=pathlib.Path("r195/r195_native").resolve()

def test(k,rep,source_file,source_rows,derived):
    seed=int(b.sha_text(b.PROTO+b.digest(SRC)+str(rep))[:8],16)
    partial=pathlib.Path("r195/forensics-subset.tsv")
    partial.write_text("".join(derived[:k]))
    started=time.perf_counter()
    try:
        p=subprocess.run([str(BIN),str(SRC.resolve()),str(ROW.resolve()),
            str(partial.resolve()),"derived_active",str(seed)],
            timeout=25,capture_output=True,text=True)
    except subprocess.TimeoutExpired:
        return {"rows":k,"rep":rep,"outcome":"TIMEOUT","seconds":25}
    raw=p.stdout
    result={"rows":k,"rep":rep,"returncode":p.returncode,"seconds":round(time.perf_counter()-started,5)}
    if p.returncode:
        result.update(outcome="NATIVE_FAIL",stderr=p.stderr[-900:])
        return result
    status,model,stats=b.parsed_native(raw)
    result.update(outcome=status,source_rows=stats["source_rows"],
                  derived_rows=stats["derived_rows"],conflicts=stats["conflicts"],
                  decisions=stats["decisions"],propagations=stats["propagations"])
    if status=="SAT":
        n,clauses=b.exact.parse_dimacs(SRC)
        failures=[(i,c) for i,c in enumerate(clauses) if not any(
            model.get(abs(x),False)==(x>0) for x in c)]
        source_bad=[]
        for i,row in enumerate(source_rows):
            parts=list(map(int,row.split()))
            rhs=parts[1];vs=parts[2:]
            if sum(bool(model.get(v,False)) for v in vs)%2!=rhs:
                source_bad.append(i)
        derived_bad=[]
        for i,row in enumerate(derived[:k]):
            parts=list(map(int,row.split()))
            rhs=parts[1];vs=parts[2:]
            if sum(bool(model.get(v,False)) for v in vs)%2!=rhs:
                derived_bad.append(i)
        result.update(valid_original=(not failures),
           violated_original_count=len(failures),
           first_violated_original_clause=failures[0] if failures else None,
           violated_source_xor_rows=source_bad[:15],
           violated_derived_xor_rows=derived_bad[:15])
    return result

def main():
    old=b.cases()
    c=next(c for c in old if c["name"]==SRC.name)
    assert c["expected"]=="SAT"
    META.parent.mkdir(parents=True,exist_ok=True)
    evidence=b.prep(SRC,ROW,DER,META,True)
    print("R195_FORENSICS_PROOF",json.dumps(evidence,sort_keys=True),flush=True)
    source_rows=ROW.read_text().splitlines(True)
    derived=DER.read_text().splitlines(True)
    assert len(source_rows)==evidence["source_rows_imported"]
    assert len(derived)==evidence["derived_rows_proven"]
    results=[]
    for rep in (0,):
        for k in (0,1,2,4,8,16,24,32,48):
            res=test(k,rep,ROW,source_rows,derived)
            results.append(res)
            print("R195_FORENSICS_TRIAL",json.dumps(res,sort_keys=True),flush=True)
    pathlib.Path("r195/forensics-report.json").write_text(
        json.dumps({"source":str(SRC),"original_sha":b.digest(SRC),
            "results":results},indent=2,sort_keys=True))
    assert any(x.get("valid_original") is False for x in results),(
        "INVALID SAT model not reproduced: still record all valid runs")
    print("R195_FORENSICS_FINISH",len(results),flush=True)

if __name__=="__main__":
    main()
