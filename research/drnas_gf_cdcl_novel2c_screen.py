#!/usr/bin/env python3
"""NOVEL2C source-only cross-cohort screening (no candidate solver timing).
MixAB4 source-frozen reference-easy six SHA + XORABC3 preexisting forty SHA.
No SAT labels or outcomes affect the GF2 structural screen.
"""
import collections, hashlib, json, pathlib, tempfile
import drnas_xorabc3_live_trail as abc3

OUT=pathlib.Path("mre_gf_cdcl_novel2c")
MIX=pathlib.Path("mre_mixab4")
def need(x,msg):
    if not x: raise RuntimeError("NOVEL2C_SCREEN_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def roster():
    frozen=abc3.verify()
    mix=json.loads((MIX/"manifest.json").read_text())
    cs=[]
    for c in frozen["cases"]:
        p=abc3.abc2.prev.source(c)
        cs.append(dict(cohort="xorabc3_seen40",sha256=c["sha256"],path=str(p),gbd=c.get("gbd")))
    need(len(cs)==40,"XORABC3 roster drift")
    mixes=mix["original_cases"]
    need(len(mixes)==6,"MIXAB4 six source-frozen SHA expected")
    for c in mixes:
        p=MIX/"cases"/c["filename"]
        need(p.is_file() and sha(p)==c["sha256"],"MIXAB4 source SHA drift")
        cs.append(dict(cohort="mixab4_reference_easy6",sha256=c["sha256"],path=str(p),gbd=c.get("gbd"),
                       independent_lrat=c.get("independent_lrat_proof_file"),
                       independent_drat=c.get("independent_drat_proof_file")))
    need(len({c["sha256"] for c in cs})==46,"46 disjoint originals required")
    return cs
def source_rows(src):
    with tempfile.TemporaryDirectory(dir=OUT) as td:
        tsv=pathlib.Path(td)/"verified_rows.tsv"
        meta,_=abc3.export_native(pathlib.Path(src),tsv)
        rows=[]
        for line in tsv.read_text().splitlines():
            parts=list(map(int,line.split()))
            need(len(parts)==parts[0]+2,"bad row")
            rows.append((tuple(sorted(parts[2:])),parts[1]))
        need(len(rows)==meta["rows"] and meta["verified"],"source row verification failed")
        return rows,meta
def profile(rows):
    known=set(rows);pairs=set();units=set();rejected_disjoint=0
    for i,(a,pa) in enumerate(rows):
        for b,pb in rows[i+1:]:
            diff=tuple(sorted(set(a)^set(b))); rhs=pa^pb
            if len(diff)>=max(len(a),len(b)):rejected_disjoint+=1;continue
            if (diff,rhs) in known:continue
            if len(diff)==1:units.add((diff,rhs))
            elif 2<=len(diff)<=6:pairs.add((diff,rhs))
    return dict(source_rows=len(rows),short_reductions=len(pairs),
                binary_reductions=sum(len(v)==2 for v,_ in pairs),
                unit_reductions=len(units),rejected_nonreducing=rejected_disjoint)
def main():
    OUT.mkdir(exist_ok=True)
    cases=roster();reports=[]
    for c in cases:
        rows,meta=source_rows(c["path"])
        reports.append(dict(**c,**profile(rows),source_equations=meta["equations"]))
    eligible=[r for r in reports if r["short_reductions"]]
    easy=[r for r in eligible if r["cohort"]=="mixab4_reference_easy6"]
    summary=dict(protocol="GFCDCL-NOVEL2C-SOURCE-SCREEN-v1",
                 cohort_sizes=dict(collections.Counter(r["cohort"] for r in reports)),
                 eligible_by_cohort=dict(collections.Counter(r["cohort"] for r in eligible)),
                 easy_with_reductions=len(easy),total_eligible=len(eligible),
                 no_candidate_timing_used=True, original_sha_verified=True,
                 cases=reports)
    (OUT/"screen.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("NOVEL2C_SCREEN_SUMMARY "+json.dumps({k:v for k,v in summary.items() if k!="cases"},sort_keys=True),flush=True)
    for row in sorted(eligible,key=lambda r:(r["cohort"]!="mixab4_reference_easy6",-r["binary_reductions"],-r["short_reductions"],r["sha256"])):
        print("NOVEL2C_ELIGIBLE "+json.dumps({k:v for k,v in row.items() if k!="path"},sort_keys=True),flush=True)
    print("NOVEL2C_SCREEN_PASS 46",flush=True)
if __name__=="__main__":main()
