#!/usr/bin/env python3
"""Aggregate checked COOP5 paired fixed-25ms vs adaptive-probe results."""
import collections,json,pathlib,random,sys
ARMS=("X5_FROZEN","ALGEBRA","DIRECT_ON","FIXED_SHADOW","FIXED_ON","DYNAMIC_SHADOW","DYNAMIC_ON")
ROOT=pathlib.Path(".")
def report(cohort):
    rows=[];manifests=[]
    for shard in range(3):
        path=ROOT/"coop5_downloads"/f"coop5-shard-{cohort}-{shard}"
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
             "feedback_good","feedback_bad","adaptive_cooldowns")}}
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
      "algebra_vs_fixed_on":("ALGEBRA","FIXED_ON"),
      "algebra_vs_dynamic_on":("ALGEBRA","DYNAMIC_ON"),
      "fixed_shadow_vs_fixed_on":("FIXED_SHADOW","FIXED_ON"),
      "dynamic_shadow_vs_dynamic_on":("DYNAMIC_SHADOW","DYNAMIC_ON"),
      "fixed_on_vs_dynamic_on":("FIXED_ON","DYNAMIC_ON"),
      "direct_on_vs_fixed_on":("DIRECT_ON","FIXED_ON"),
      "direct_on_vs_dynamic_on":("DIRECT_ON","DYNAMIC_ON")}
    d={"status":"COMPLETE","cohort":cohort,"sources":n,
       "trial_count":len(rows),"one_logical_cpu":True,
       "cap_s":manifests[0]["cap_s"],"arms":list(ARMS),"overall":stats,
       "comparisons":{name:bootstrap(*pair) for name,pair in pairs.items()},
       "promotion":False,"blind_holdout":False,
       "caveat":"fixed source protocol, retrospective originals and synthetic discovery only"}
    outfile=ROOT/f"coop5_{cohort}_final"
    outfile.mkdir(exist_ok=True)
    (outfile/"report.json").write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
    print("COOP5_"+cohort.upper()+"_FINAL "+json.dumps(d,sort_keys=True),flush=True)
    return d
if __name__=="__main__":
    a=report("synthetic")
    b=report("real")
    assert a["trial_count"]==21*2*len(ARMS)
    assert b["trial_count"]>0
