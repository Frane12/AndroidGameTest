#!/usr/bin/env python3
"""DRNAS C10a: structural context on C8D 19 + C9c 12 already measured SHA.

Retrospective EXPLORATORY analysis ONLY: cutoff rules are chosen after
observing C9c and C8D, so none of these comparisons may be called blind.
C10b tests frozen selected rule on newly source-frozen official 2026.
C8D cap15 and C9c cap60 are NEVER aggregated as one PAR2.
"""
from __future__ import annotations
import collections,hashlib,json,pathlib,statistics,time,math
ROOT=pathlib.Path("c10_out")
SRC8=pathlib.Path("c8d_s1_source/s1_router")
SRC9=pathlib.Path("c9c_official")
R8=pathlib.Path("c10_old_c8d/report.json")
R9=pathlib.Path("c10_old_c9c/c9c_out/report.json")
PROTO="DRNAS-C10A-31SHA-STRUCTURAL-RETROSPECTIVE-CAUSAL-CONTEXT-v1"
RULE="Kissat if nvars<=400 OR clauses/nvars>=200 OR (nvars>=25000 AND clauses/nvars<=2), else CaDiCaL"
def need(b,msg):
    if not b:raise RuntimeError("C10A_FAIL_CLOSED "+str(msg))
def digest(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()
def features(path):
    t=time.perf_counter()
    n=m=None;head=False
    lengths=collections.Counter()
    seen=set();duplicate=0;horn=0;xor_groups=collections.defaultdict(set)
    observed=0;words=0
    clause=[];binary=0;unit=0;three=0;long=0;positive=0
    with path.open("rt",errors="replace") as f:
        for ln in f:
            z=ln.strip()
            if not z or z.startswith("c"):continue
            if z.startswith("p "):
                parts=z.split()
                need(len(parts)==4 and parts[:2]==["p","cnf"],
                     "invalid original DIMACS header")
                n=int(parts[2]);m=int(parts[3]);head=True;continue
            need(head,"CNF header missing")
            for word in z.split():
                val=int(word)
                if val:
                    need(1<=abs(val)<=n,"invalid CNF literal")
                    clause.append(val)
                    continue
                observed+=1
                size=len(clause)
                lengths[size]+=1
                positive+=sum(x>0 for x in clause)
                if size==1:unit+=1
                if size==2:binary+=1
                if size==3:
                    three+=1
                    key=tuple(sorted(abs(x) for x in clause))
                    # Approximate complete XOR3 support among all sign patterns
                    # for a fixed three-variable support (only first 12k clauses).
                    if len(set(key))==3:
                        mask=sum(1<<i for i,v in enumerate(key)
                                 if (v in clause))
                        xor_groups[key].add(mask)
                if size>=10:long+=1
                k=tuple(sorted(set(clause)))
                if k in seen:duplicate+=1
                else:seen.add(k)
                clause=[]
                if observed>=12000:break
            if observed>=12000:break
    need(observed>=1 and n>0 and m>0 and not clause,"bad structural sample")
    xor_full=sum(len(s)>=4 for s in xor_groups.values())
    return dict(nvars=n,nclauses=m,clauses_per_var=round(m/n,6),
        sample_clauses=observed,sample_fraction=round(observed/m,6),
        binary_fraction=round(binary/observed,6),
        ternary_fraction=round(three/observed,6),
        horn_fraction=round(sum(1 for _ in ()) / max(1,observed),6), # set below
        unit_fraction=round(unit/observed,6),
        long_fraction=round(long/observed,6),
        mean_sample_clause_length=round(sum(k*v for k,v in lengths.items())/observed,6),
        sampled_duplicate_fraction=round(duplicate/observed,6),
        xor3_support_groups_with_4_or_more_sign_patterns=xor_full,
        scan_cost_s=round(time.perf_counter()-t,6),
        sampled_not_full_formula=True)
def feature_scan(path):
    # Separate Horn scan across exactly the same prefix; simple low-cost,
    # source-only and no solver feedback, never a proxy for an XOR certificate.
    f=features(path)
    count=0;horn=0;cls=[];head=False
    for line in path.open("rt",errors="replace"):
        x=line.strip()
        if not x or x.startswith("c") or x.startswith("p "):continue
        for z in x.split():
            l=int(z)
            if l:cls.append(l)
            else:
                count+=1
                if sum(v>0 for v in cls)<=1:horn+=1
                cls=[]
                if count>=f["sample_clauses"]:break
        if count>=f["sample_clauses"]:break
    need(count==f["sample_clauses"],"Horn same-prefix scan mismatch")
    f["horn_fraction"]=round(horn/count,6)
    return f
def route(f):
    n=f["nvars"];d=f["clauses_per_var"]
    return "kissat" if n<=400 or d>=200 or (n>=25000 and d<=2) else "cadical"
def load():
    a=json.loads(R8.read_text());b=json.loads(R9.read_text())
    need(a["protocol"]=="DRNAS-C8D-C7-BVE-EARLY-CDCL-19SHA-10ARM-2REP-15S-v1"
        and a["status"]=="C8D_E2E_AUDIT_PASS" and a["source_count"]==19,
        "invalid frozen C8D retrospective cohort")
    need(b["protocol"]=="DRNAS-C9C-OFFICIAL2026-12SHA-4ARM-2REP-60S-E2E-v1"
        and b["source_count"]==12 and b["full_trials"]==96 and
        b["original_source_lock"],"invalid frozen C9c retrospective cohort")
    j8=json.loads((SRC8/"manifest.json").read_text())
    j9=json.loads((SRC9/"manifest.json").read_text())
    lookup={x["sha256"]:x for x in j8["cases"]}
    lookup9={x["sha256"]:x for x in j9["cases"]}
    need(len(lookup)==20 and len(lookup9)==12,"source registry changed")
    data=[]
    for cohort,rows in (("C8D",a["per_source"]),("C9C",b["per_source"])):
        for x in rows:
            sha=x["sha256"]
            if cohort=="C8D":
                need(sha in lookup,"C8D score source not in original manifest")
                c=lookup[sha];p=SRC8/"sources"/c["name"];gbd=c["gbd"]
            else:
                need(sha in lookup9,"C9c score source not in frozen manifest")
                c=lookup9[sha];p=SRC9/c["filename"];gbd=c["gbd"]
            need(p.is_file() and digest(p)==sha,"original SHA mismatch "+sha)
            f=feature_scan(p)
            cap=15 if cohort=="C8D" else 60
            scores={z:x["by_mode"][z] for z in ("cadical","kissat")}
            for k,v in scores.items():
                need(0<v["PAR2_s"]<=4*cap+0.01 and 0<=v["solved"]<=2,
                    "invalid source backend PAR2")
            mode=route(f)
            data.append(dict(cohort=cohort,sha256=sha,gbd=gbd,
                original_source_verified=True,
                status_prior_reference=(x.get("reference_status") if cohort=="C9C"
                    else "source prior"),
                source_features=f,selected=mode,
                base_cadical=scores["cadical"],base_kissat=scores["kissat"],
                c10_retrospective=dict(solved=scores[mode]["solved"],
                    PAR2_s=scores[mode]["PAR2_s"]),
                exploratory_not_blind=True))
    need(len(data)==31 and len({x["sha256"] for x in data})==31,
         "not exactly 19+12 SHA-disjoint originals")
    return data
def report():
    data=load()
    outcome=[]
    for cohort in ("C8D","C9C"):
        cases=[c for c in data if c["cohort"]==cohort]
        scores={}
        for mode in ("cadical","kissat","c10_retrospective"):
            term=[c[{"cadical":"base_cadical","kissat":"base_kissat",
                     "c10_retrospective":"c10_retrospective"}[mode]]
                  for c in cases]
            scores[mode]=dict(
                solved=sum(x["solved"] for x in term),
                PAR2_s=round(sum(x["PAR2_s"] for x in term),6))
        for mode in scores:
            scores[mode]["PAR2_speedup_vs_Kissat_x"]=round(
                scores["kissat"]["PAR2_s"]/scores[mode]["PAR2_s"],6)
        gain_by_source=sorted([dict(sha=c["sha256"],gain_s=round(
            c["base_kissat"]["PAR2_s"]-c["c10_retrospective"]["PAR2_s"],6))
            for c in cases],key=lambda x:-x["gain_s"])
        total_gain=sum(x["gain_s"] for x in gain_by_source)
        outcome.append(dict(cohort=cohort,case_count=len(cases),
            cap_s=15 if cohort=="C8D" else 60,
            independent_seeds=False,combined_across_caps=False,
            modes=scores,rule_selected_Kissat=sum(c["selected"]=="kissat" for c in cases),
            rule_selected_CaDiCaL=sum(c["selected"]=="cadical" for c in cases),
            largest_gain_case=gain_by_source[0],
            aggregate_gain_excluding_largest_case=round(
                total_gain-gain_by_source[0]["gain_s"],6)))
    ROOT.mkdir(exist_ok=True)
    output=dict(protocol=PROTO,cases=31,source_sha_pinned=True,
        hypothesis_derived_posthoc=True,
        this_comparison_is_NOT_prospective=True,
        policy_string=RULE,clause_feature_window=12000,
        sample_XOR_groups_NOT_proof=True,
        no_auto_promotion=True,
        must_verify_on_new_official_SHA=True,
        separate_cohorts=outcome,all_cases=data)
    (ROOT/"report.json").write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("C10A_FINAL",json.dumps({k:v for k,v in output.items()
       if k!="all_cases"},sort_keys=True),flush=True)
if __name__=="__main__":report()
