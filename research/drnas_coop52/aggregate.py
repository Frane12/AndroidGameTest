#!/usr/bin/env python3
"""Aggregate quality-controlled COOP5.2 under 0.25/1/5/25ms probe budgets."""
import collections,json,pathlib,random,sys
ARMS=("X5_FROZEN","ALGEBRA","FIXED_ON","DYNAMIC_ON","HYBRID_ON","Q025_ON","Q1_ON","Q5_ON","Q25_ON","Q1_SHADOW")
ROOT=pathlib.Path(".")
def report(cohort):
    rows=[];manifests=[]
    for shard in range(3):
        path=ROOT/"coop52_downloads"/f"coop52-shard-{cohort}-{shard}"
        if not (path/"manifest.json").exists():
            path=path/f"coop52_shard_{cohort}_{shard}"
        m=json.loads((path/"manifest.json").read_text())
        rr=[json.loads(x) for x in (path/"trials.jsonl").read_text().splitlines() if x.strip()]
        assert m["cohort"]==cohort and m["shard"]==shard and m["shards"]==3
        assert m["arms"]==list(ARMS)
        assert len(rr)==len(m["selected_sha256"])*len(ARMS)*m["repeats"]
        assert {x["sha256"] for x in rr}==set(m["selected_sha256"])
        rows+=rr;manifests.append(m)
    assert len({json.dumps(m["binaries"],sort_keys=True) for m in manifests})==1
    n=manifests[0]["total_sources"]
    assert len({x["sha256"] for x in rows})==n
    assert len(rows)==n*manifests[0]["repeats"]*len(ARMS)
    assert len({(x["sha256"],x["rep"],x["arm"]) for x in rows})==len(rows)
    answers=collections.defaultdict(set)
    for x in rows:
        if x["certified"]:answers[x["sha256"]].add(x["status"])
    assert all(len(v)<=1 for v in answers.values())
    stats={}
    for arm in ARMS:
        vals=[x for x in rows if x["arm"]==arm]
        prob=[x["probe"] for x in vals]
        stats[arm]={
          "attempts":len(vals),"solved":sum(x["accepted"] for x in vals),
          "SAT":sum(x["accepted"] and x["status"]=="SAT" for x in vals),
          "UNSAT":sum(x["accepted"] and x["status"]=="UNSAT" for x in vals),
          "PAR2_s":round(sum(x["PAR2"] for x in vals),5),
          "distinct_solved":len({x["sha256"] for x in vals if x["accepted"]}),
          "probe_ms":round(sum(x.get("probe_wall_ms",0) for x in prob),5),
          **{k:sum(x.get(k,0) for x in prob) for k in
            ("attempted_pairs","completed_pairs","partial_pairs","would_override",
             "actually_overrode","shadow_recommend","depth96","depth320","depth900",
             "feedback_good","feedback_bad","adaptive_cooldowns",
             "hybrid_deep_pairs","hybrid_shallow_pairs","hybrid_deep_recommend",
             "quality_unmatched_rejected","quality_strong_rejected","quality_accepted")}}
        if arm.endswith("SHADOW"):assert stats[arm]["actually_overrode"]==0
        if arm=="ALGEBRA":assert stats[arm]["attempted_pairs"]==0
    fam=collections.defaultdict(lambda:collections.defaultdict(float))
    for r in rows:fam[r["family"]][r["arm"]]+=r["PAR2"]
    keys=sorted(fam)
    def bootstrap(base,alt,draws=2000):
        rng=random.Random(252513)
        def gain(selected):
            x=sum(fam[f][base] for f in selected)
            y=sum(fam[f][alt] for f in selected)
            return 100*(x-y)/x if x else 0
        samples=sorted(gain([rng.choice(keys) for _ in keys]) for _ in range(draws))
        return {"gain_pct":round(gain(keys),4),
                "family_CI95_pct":[round(samples[49],4),round(samples[1949],4)],
                "families":len(keys)}
    pairs={
      "algebra_vs_Q025":("ALGEBRA","Q025_ON"),
      "algebra_vs_Q1":("ALGEBRA","Q1_ON"),
      "algebra_vs_Q5":("ALGEBRA","Q5_ON"),
      "algebra_vs_Q25":("ALGEBRA","Q25_ON"),
      "Q025_vs_Q1":("Q025_ON","Q1_ON"),
      "Q1_vs_Q5":("Q1_ON","Q5_ON"),
      "Q1_vs_Q25":("Q1_ON","Q25_ON"),
      "Q5_vs_Q25":("Q5_ON","Q25_ON"),
      "Q1_shadow_vs_on":("Q1_SHADOW","Q1_ON"),
      "HYBRID_vs_Q1":("HYBRID_ON","Q1_ON"),
      "FIXED_vs_Q1":("FIXED_ON","Q1_ON"),
      "DYNAMIC_vs_Q1":("DYNAMIC_ON","Q1_ON")
    }
    # Paired, source-specific status changes; no post-hoc instance filtering.
    paired=collections.defaultdict(dict)
    for row in rows:paired[(row["sha256"],row["rep"])][row["arm"]]=row
    divergent=[]
    for (sha,rep),p in sorted(paired.items()):
        if len(p)!=len(ARMS):raise RuntimeError("missing source/rep arms")
        if len({p[name]["accepted"] for name in
               ("Q025_ON","Q1_ON","Q5_ON","Q25_ON")})>1 or
            p["ALGEBRA"]["accepted"]!=p["Q1_ON"]["accepted"]:
            divergent.append({"sha256":sha,"rep":rep,
              "id":p["Q1_ON"]["id"],"family":p["Q1_ON"]["family"],
              "result":{name:p[name]["status"] for name in
                 ("ALGEBRA","FIXED_ON","HYBRID_ON","Q025_ON","Q1_ON","Q5_ON","Q25_ON")},
              "accepted":{name:p[name]["accepted"] for name in
                 ("ALGEBRA","FIXED_ON","HYBRID_ON","Q025_ON","Q1_ON","Q5_ON","Q25_ON")}})
    d={"status":"COMPLETE","cohort":cohort,"sources":n,
       "trial_count":len(rows),"one_logical_cpu":True,
       "cap_s":manifests[0]["cap_s"],"arms":list(ARMS),"overall":stats,
       "comparisons":{name:bootstrap(*pair) for name,pair in pairs.items()},
       "source_outcome_differences":divergent,
       "promotion":False,"blind_holdout":False,
       "caveat":"fixed source protocol, retrospective originals and synthetic discovery only"}
    outfile=ROOT/f"coop52_{cohort}_final"
    outfile.mkdir(exist_ok=True)
    (outfile/"report.json").write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
    print("COOP52_"+cohort.upper()+"_FINAL "+json.dumps(d,sort_keys=True),flush=True)
    return d
if __name__=="__main__":
    a=report("synthetic")
    b=report("real")
    assert a["trial_count"]==21*2*len(ARMS)
    assert b["trial_count"]>0
