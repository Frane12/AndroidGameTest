#!/usr/bin/env python3
"""DRNAS CRR1-B5 — discrimination-only study, NOT a solver benchmark.

Test whether 54 GF(2)-certified binary clauses can be distinguished by
measuring their additional *exact CNF unit-propagation* effects under
deterministic two- and three-literal, CNF-neighborhood partial assignments.

The study deliberately uses previously examined W4 SAT2026 originals.
No outcome-based training, no claim of blind validation, no CDCL claims.
All prospective clauses are independently certified from original CNF
complete parity blocks before any usefulness measurement. No CNF is changed.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

import drnas_crr1a_shadow as a
import drnas_crr1b_active as b
import drnas_crr1b2_telemetry as b2
import drnas_crr1b4_value as b4

ROOT=Path("crr1b5")
PROTO="DRNAS-CRR1B5-FOCUS4-3SEEDS-DISCRIMINATION-ONLY-v1"
FOCUS_IDS=b2.FOCUS_IDS
SHARDS=4
SEEDS=(101,202,303)
BUDGET_S=8.0
MAX_CONTEXTS=12
MAX_NEIGHBORS=8

def need(x,msg):
    if not x:raise RuntimeError("CRR1B5_FAIL_CLOSED "+msg)

def save(p,o):a.save(p,o)

def hash_num(seed,*v):
    s="|".join(map(str,(seed,)+v))
    return int.from_bytes(hashlib.sha256(s.encode()).digest()[:8],"big")

def adjacency(original,candidate_vars,deadline):
    """Only collect CNF-neighborhood literals for variables in proposed rows.

    No external solver outcomes or arbitrary metadata enter ranking.
    """
    neigh=collections.defaultdict(collections.Counter)
    for i,c in enumerate(original):
        if i%512==0 and time.perf_counter()>deadline:
            raise TimeoutError("neighbor build budget")
        if not 2<=len(c)<=7:continue
        focused=[lit for lit in c if abs(lit) in candidate_vars]
        for lit in focused:
            for other in c:
                if abs(other)!=abs(lit):
                    neigh[abs(lit)][other]+=1
    return neigh

def contexts(clause,neigh,seed):
    """Deterministic candidate-specific partial assignments.

    Each binary clause (p OR q) is probed with -p or -q plus 0, 1 or 2
    locally adjacent, falsified CNF literals. This avoids merely repeating
    B4's two single-assumption probes.
    """
    if len(clause)==1:
        return [(),(-clause[0],)]
    p,q=clause
    out=[]
    for k,antecedent in enumerate((-p,-q)):
        out.append((antecedent,))
        # Use neighbors of both clause variables; rotate deterministic seeds.
        combined=collections.Counter()
        for lit in clause:
            combined.update(neigh.get(abs(lit),{}))
        candidates=[lit for lit in combined
                    if abs(lit) not in {abs(p),abs(q)}]
        candidates.sort(key=lambda lit:(-combined[lit],
                         hash_num(seed,k,abs(lit),lit),abs(lit),lit))
        picked=[]
        used={abs(p),abs(q)}
        for lit in candidates:
            if abs(lit) in used:continue
            picked.append(-lit)
            used.add(abs(lit))
            if len(picked)>=MAX_NEIGHBORS:break
        # Four two-assumption probes plus a three-assumption probe per side.
        for extra in picked[:4]:
            out.append((antecedent,extra))
        if len(picked)>=2:
            out.append((antecedent,picked[0],picked[1]))
    need(len(out)<=MAX_CONTEXTS,"context cap")
    # Remove any duplicated assumption set, but never bias by outcomes.
    return list(dict.fromkeys(out))

def profile(oracle,clause,tests,deadline):
    """Compare exact original/selected BCP vs propagation with ONE clause.

    BCP under original + candidate is evaluated exactly by starting
    from the original fixpoint, then forcing the newly unit literal
    and running original BCP again. If both clause literals are false,
    the candidate immediately gives a conflict not found by original BCP.
    """
    conflicts=0;downstream=0;activations=0;unit_forces=0
    tried=0;valid=0;ignored_conflicting=0
    for assumps in tests:
        if time.perf_counter()>deadline:raise TimeoutError("probe budget")
        baseline=oracle.run(assumps,deadline,max_literal_visits=135000)
        tried+=1
        if baseline["conflict"]:
            ignored_conflicting+=1;continue
        valid+=1
        vals=baseline["fixed"]
        if len(clause)==1:
            lit=clause[0]
            v=vals.get(abs(lit))
            if v==(lit>0):continue
            if v is not None:
                conflicts+=1;activations+=1;continue
            forced=lit
        else:
            p,q=clause
            x=vals.get(abs(p));y=vals.get(abs(q))
            xp=x==(p>0);yp=y==(q>0)
            if xp or yp:continue
            xf=x is not None and not xp
            yf=y is not None and not yp
            if xf and yf:
                conflicts+=1;activations+=1;continue
            if xf and y is None:forced=q
            elif yf and x is None:forced=p
            else:continue
        activations+=1;unit_forces+=1
        aug=oracle.run(tuple(assumps)+(forced,),deadline,
                       max_literal_visits=135000)
        if aug["conflict"]:
            conflicts+=1
        else:
            newvars=set(aug["fixed"])-set(vals)
            # Exclude the immediate candidate-enforced literal to measure
            # *additional* downstream propagation induced in original CNF.
            downstream+=max(0,len(newvars)-1)
    return {"conflicts":conflicts,"downstream":downstream,
            "activations":activations,"unit_forces":unit_forces,
            "contexts":tried,"consistent_contexts":valid,
            "original_bcp_conflicts":ignored_conflicting}

def order_score(x):
    # No arbitrary weighted sum: compare independent effects in priority order.
    return (x["conflicts"],x["downstream"],x["activations"])

def discriminate(original,candidates,certs,seed,deadline):
    start=time.perf_counter()
    need(len(candidates)==len(certs),"input proof pair cardinality")
    if not candidates:
        return {"status":"NO_CANDIDATES","candidate_count":0,
                "unique_b4_scores":0,"unique_b5_profiles":0,
                "strict_discrimination":False,"elapsed_s":0.0,
                "sample_count":0,"top8_overlap":None,"top16_overlap":None,
                "candidates":[]}
    # Fail closed before probing any uncertified source-derived clause.
    validated=b.certify_added(original,certs)
    need(validated=={tuple(sorted(c)) for c in candidates},
         "original source GF2 entailment certificate invalid")
    orig_short={tuple(sorted(c)) for c in original if len(c)<=2}
    original_units={c[0] for c in original if len(c)==1}
    filtered=[];seen=set()
    for c,cert in zip(candidates,certs):
        c=tuple(sorted(c))
        if c in seen or c in orig_short:continue
        if len(c)==2 and any(lit in original_units for lit in c):continue
        seen.add(c);filtered.append((c,cert))
    if not filtered:return {"status":"NO_NOVEL_CANDIDATES","candidate_count":0,
                 "unique_b4_scores":0,"unique_b5_profiles":0,
                 "strict_discrimination":False,"elapsed_s":0.0,
                 "sample_count":0,"top8_overlap":None,"top16_overlap":None,
                 "candidates":[]}
    target={abs(lit) for c,_ in filtered for lit in c}
    t=time.perf_counter()
    neigh=adjacency(original,target,deadline)
    oracle=b4.PropagationOracle(original,deadline)
    graph,_=b.graph_from_original(original,deadline)
    need(graph is not None,"graph too large to check implied clauses")
    build_s=time.perf_counter()-t
    rows=[];total=0
    for i,(c,cert) in enumerate(filtered):
        if time.perf_counter()>deadline:raise TimeoutError("candidate loop time")
        # Original bin graph may reject provably redundant candidates.
        if len(c)==2 and b.graph_implies(graph,c,deadline):
            continue
        old,probes=b4.propagation_gain(oracle,c,deadline)
        tests=contexts(c,neigh,seed)
        score=profile(oracle,c,tests,deadline)
        total+=len(tests)
        support=sum(len(oracle.occ.get(v,()))+
                    len(oracle.occ.get(-v,())) for v in c)
        rows.append({"clause":list(c),"b4_score":old,
                     "b4_support":support,
                     "profile":score,"profile_vector":list(order_score(score))})
    b4_rank=sorted(rows,key=lambda r:(-r["b4_score"],-r["b4_support"],
                                     r["clause"]))
    b5_rank=sorted(rows,key=lambda r:(tuple(-v for v in r["profile_vector"]),
                                     -r["b4_support"],r["clause"]))
    def overlap(k):
        one={tuple(r["clause"]) for r in b4_rank[:k]}
        two={tuple(r["clause"]) for r in b5_rank[:k]}
        return len(one&two)
    unique_b4=len({r["b4_score"] for r in rows})
    unique_b5=len({tuple(r["profile_vector"]) for r in rows})
    def compact_top(rank):
        return [{"clause":r["clause"],"b4":r["b4_score"],
                 "profile":r["profile_vector"]} for r in rank[:16]]
    return {"status":"OK","seed":seed,"candidate_count":len(rows),
        "unique_b4_scores":unique_b4,"unique_b5_profiles":unique_b5,
        "strict_discrimination":unique_b5>unique_b4,
        "unique_multi_context_profiles":unique_b5,
        "total_contexts":total,
        "median_original_B4_score":statistics.median(r["b4_score"] for r in rows),
        "top8_overlap":overlap(8),"top16_overlap":overlap(16),
        "top8_changes":min(8,len(rows))-overlap(8),
        "top16_changes":min(16,len(rows))-overlap(16),
        "total_b5_conflicts":sum(r["profile"]["conflicts"] for r in rows),
        "total_b5_downstream":sum(r["profile"]["downstream"] for r in rows),
        "total_b5_activations":sum(r["profile"]["activations"] for r in rows),
        "build_s":round(build_s,6),
        "elapsed_s":round(time.perf_counter()-start,6),
        "b4_top16":compact_top(b4_rank),
        "b5_top16":compact_top(b5_rank),
        "all_candidates":rows}

def selftest():
    # Original B4 and GF2 source replay calibrations remain mandatory.
    b4.selftest()
    deadline=time.perf_counter()+3
    example=[(-2,5),(-5,6),(-1,7)]
    o=b4.PropagationOracle(example,deadline)
    pr1=profile(o,(1,2),[(-1,),(-2,)],deadline)
    pr2=profile(o,(8,9),[(-8,),(-9,)],deadline)
    need(pr1["downstream"]>=2 and pr2["downstream"]==0,
         "B5 downstream discrimination must separate identical B4=2 scores")
    need(b4.propagation_gain(o,(1,2),deadline)[0]==2 and
         b4.propagation_gain(o,(8,9),deadline)[0]==2,
         "B4 baseline scores must genuinely tie in separation fixture")
    # BCP propagation profile under assumptions is deterministic.
    need(pr1==profile(o,(1,2),[(-1,),(-2,)],deadline),
         "B5 deterministic probing fixture failed")
    print("CRR1B5_SELFTEST_PASS",flush=True)

def focused():
    cc=b2.cases()
    need(len(cc)==SHARDS,"focus case count")
    return cc

def prepare():
    selftest()
    cc=focused()
    for c in cc:
        need(a.sha(a.SOURCE/(c["id"]+".cnf"))==c["sha256"],
             "SHA-frozen original source invalid")
    ROOT.mkdir(exist_ok=True)
    manifest={"protocol":PROTO,"case_sha256":[c["sha256"] for c in cc],
       "source_manifest_sha":a.sha("history/w4sources/manifest.json"),
       "source_set":"posthoc 4 SAT2026 W4 originals","blind":False,
       "promotion_allowed":False,"shards":SHARDS,"seeds":list(SEEDS),
       "main_question":"can multi-context exact BCP distinguish B4=2 candidates",
       "source_replay":"all candidate GF2 reasons independently replayed from original",
       "No_solver_runs":True,"no_claim_of_CDCL_progress":True,
       "probe_budget_per_seed_s":BUDGET_S,
       "context_selection":"deterministic CNF neighborhood, 1-3 literal assumptions"}
    save(ROOT/"manifest.json",manifest)
    files=["research/drnas_crr1b5_discrimination.py",
           "research/drnas_crr1b4_value.py",
           "research/drnas_crr1b2_telemetry.py",
           "research/drnas_crr1b_active.py",
           "research/drnas_crr1a_shadow.py",
           ".github/workflows/drnas-crr1b5-discrimination.yml",
           "history/w4sources/manifest.json",
           "crr1b5/manifest.json"]
    save(ROOT/"pins.json",{p:a.sha(p) for p in files})
    verify()
    print("CRR1B5_PREP_PASS",a.sha(ROOT/"manifest.json"),flush=True)

def verify():
    cc=focused()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["case_sha256"]==[c["sha256"] for c in cc]
         and m["source_manifest_sha"]==a.sha("history/w4sources/manifest.json"),
         "manifest drift")
    for p,v in json.loads((ROOT/"pins.json").read_text()).items():
        need(a.sha(p)==v,"code pin mismatch "+p)
    for c in cc:
        need(a.sha(a.SOURCE/(c["id"]+".cnf"))==c["sha256"],
             "source drift")
    return cc

def shard(i):
    cc=verify()
    need(0<=i<SHARDS,"bad shard number")
    case=cc[i]
    n,original=a.parse(a.SOURCE/(case["id"]+".cnf"))
    rows=[]
    for seed in SEEDS:
        t=time.perf_counter()
        try:
            c,cert,discovery=b2.make_bridge(n,original)
            if c:
                result=discriminate(original,c,cert,seed,t+BUDGET_S)
            else:
                result={"status":"NO_CANDIDATES","candidate_count":0,
                  "unique_b4_scores":0,"unique_b5_profiles":0,
                  "strict_discrimination":False,"top8_overlap":None,
                  "top16_overlap":None,"total_contexts":0,"all_candidates":[]}
        except TimeoutError as exc:
            result={"status":"BUDGET_CUTOFF","reason":str(exc),
               "candidate_count":None,"unique_b4_scores":None,
               "unique_b5_profiles":None,"strict_discrimination":False,
               "top8_overlap":None,"top16_overlap":None,"all_candidates":[]}
            discovery={"status":"CUTOFF"}
        row={"protocol":PROTO,"id":case["id"],"sha256":case["sha256"],
             "shard":i,"seed":seed,"source_variables":n,
             "source_clauses":len(original),
             "discovery":{"added":discovery["added"] if "added" in discovery else None,
                          "complete_xor_equations":discovery.get("complete_xor_equations"),
                          "status":discovery["status"]},
             "result":result,
             "wall_s":round(time.perf_counter()-t,6)}
        rows.append(row)
        save(ROOT/("shard-%d.json"%i),rows)
        slim={k:v for k,v in result.items()
              if k not in ("all_candidates","b4_top16","b5_top16")}
        print("CRR1B5_TRIAL",json.dumps({**{k:v for k,v in row.items() if k!="result"},
                                      "result":slim},sort_keys=True),flush=True)
    need(len(rows)==len(SEEDS),"incomplete shard")
    print("CRR1B5_SHARD_PASS",i,len(rows),flush=True)

def audit():
    cc=verify()
    rows=[];seen=set()
    for i,c in enumerate(cc):
        rr=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(rr)==len(SEEDS),"missing study replications")
        for r in rr:
            key=(r["sha256"],r["seed"])
            need(key not in seen and r["sha256"]==c["sha256"]
                 and r["id"]==c["id"] and r["shard"]==i
                 and r["protocol"]==PROTO and r["seed"] in SEEDS,
                 "source or seed mismatch")
            seen.add(key)
            result=r["result"]
            need(result["status"] in ("NO_CANDIDATES","OK","BUDGET_CUTOFF"),
                 "invalid result status")
            if result["status"]=="OK":
                candidates=result["all_candidates"]
                need(len(candidates)==result["candidate_count"]
                     and len(candidates)>0,"candidate provenance mismatch")
                need(len({tuple(x["clause"]) for x in candidates})==
                     len(candidates),"normalized duplicates in analyzed candidates")
                need(len({tuple(x["profile_vector"]) for x in candidates})==
                     result["unique_b5_profiles"],"profile count mismatch")
                need(len({x["b4_score"] for x in candidates})==
                     result["unique_b4_scores"],"B4 baseline mismatch")
            rows.append(r)
    expected={(c["sha256"],seed) for c in cc for seed in SEEDS}
    need(seen==expected and len(rows)==SHARDS*len(SEEDS),"incomplete 12 trials")
    focus=cc[0]["id"]
    subset=[r for r in rows if r["id"]==focus]
    complete=[r for r in subset if r["result"]["status"]=="OK"]
    report={"status":"CRR1B5_AUDIT_PASS","protocol":PROTO,
       "attempts":len(rows),"formulas":SHARDS,"seeds":list(SEEDS),
       "focus_source":focus,
       "focus_complete":len(complete),
       "focus_discriminates":len(complete)==len(SEEDS) and
                 all(r["result"]["strict_discrimination"] for r in complete),
       "focus_unique_b4_scores":[r["result"]["unique_b4_scores"] for r in complete],
       "focus_unique_b5_profiles":[r["result"]["unique_b5_profiles"] for r in complete],
       "focus_top8_changes":[r["result"]["top8_changes"] for r in complete],
       "focus_top16_changes":[r["result"]["top16_changes"] for r in complete],
       "focus_runtime_s":[r["wall_s"] for r in subset],
       "rows_summary":[{"id":r["id"],"seed":r["seed"],
             "status":r["result"]["status"],
             "candidates":r["result"]["candidate_count"],
             "b4_unique":r["result"]["unique_b4_scores"],
             "b5_unique":r["result"]["unique_b5_profiles"],
             "changed_top8":r["result"].get("top8_changes"),
             "conflict_gain":r["result"].get("total_b5_conflicts"),
             "downstream_gain":r["result"].get("total_b5_downstream"),
             "wall_s":r["wall_s"]} for r in rows],
       "posthoc_development":True,"promotion_allowed":False,
       "no_solver_benchmark":True}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    print("CRR1B5_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("prepare","selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
