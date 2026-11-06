#!/usr/bin/env python3
"""R180 SAT Shazam: source-only fingerprint routing, held-out replay audit.

This is NOT a live 256-conflict policy. Uses R179's actually measured paired
time data; no measurements from a held-out formula influence training.
Performance estimates are retrospective, NOT a live speedup claim.
"""
import argparse, collections, csv, hashlib, json, math, pathlib, statistics, time
ROOT = pathlib.Path("r180")
MODES = ("clean", "r174_b", "r177_onehop", "r177_twohop", "r179_selective")
def check(cond,msg):
    if not cond: raise AssertionError(msg)
def fingerprint(path):
    """Cheap syntactic fingerprint, no source metadata or benchmark labels."""
    start = time.perf_counter()
    n=0; declared=0; clauses=[]; occurrences=collections.Counter()
    for raw in pathlib.Path(path).read_text().splitlines():
        if not raw or raw.startswith("c"): continue
        if raw.startswith("p "):
            parts=raw.split();check(parts[:2]==["p","cnf"],"not DIMACS")
            n=int(parts[2]);declared=int(parts[3]);continue
        vals=[int(x) for x in raw.split()]
        check(vals and vals[-1]==0 and not any(x==0 for x in vals[:-1]),"bad clause")
        c=tuple(vals[:-1]); clauses.append(c)
        for x in set(map(abs,c)):occurrences[x]+=1
    check(n>0 and len(clauses)==declared,"DIMACS count wrong")
    hist=collections.Counter(map(len,clauses))
    # Syntactic XOR3 encoding: all four forbidden clauses on a triple.
    # This is a signal, NOT an equivalence proof or independent certificate.
    triples=collections.defaultdict(set)
    for c in clauses:
        if len(c)==3 and len(set(map(abs,c)))==3:
            vs=tuple(sorted(map(abs,c)))
            mask=tuple(x>0 for x in sorted(c,key=lambda x:abs(x)))
            triples[vs].add(mask)
    xor_triplets=sum(1 for masks in triples.values()
                     if len(masks)==4 and len(set(sum(m) % 2 for m in masks))==1)
    used=len(occurrences); degree=list(occurrences.values())
    vec=(math.log1p(n),math.log1p(declared),declared/max(1,n),
         hist[2]/max(1,declared),hist[3]/max(1,declared),
         sum(v>=4 for v in degree)/max(1,used),
         max(degree,default=0)/max(1,declared),
         xor_triplets/max(1,declared),
         xor_triplets/max(1,n),
         used/max(1,n))
    return tuple(round(x,8) for x in vec), time.perf_counter()-start, {
       "variables":n,"clauses":declared,"syntactic_xor3_groups":xor_triplets}
def split(id,sha,origin):
    # Four pre-existing real formulas are entirely holdout, no exceptions.
    if origin=="real_frozen": return "holdout"
    digest=hashlib.sha256(("R180-v1-frozen-split:"+sha).encode()).digest()
    return "train" if int.from_bytes(digest[:4],"big")%4 < 3 else "holdout"
def median(values):return statistics.median(values)
def cases_from_data(manifest,rows):
    by=collections.defaultdict(list)
    for row in rows:
        check(row["mode"] in MODES,"unknown mode")
        by[(row["id"],row["mode"])].append(row)
    cases=[]
    for c in manifest["cases"]:
        id=c["id"];sha=c["sha256"]
        times={}
        for mode in MODES:
            rs=by[(id,mode)]
            check(len(rs)==2,"missing paired repeated trials "+id+" "+mode)
            check(all(r["sha256"]==sha for r in rs),"source SHA mismatch")
            # PAR2 includes capped timeouts; same frozen instance and cap.
            times[mode]=median([float(r["par2"]) for r in rs])
        cases.append((c,times))
    check(len(cases)==100,"not R179 frozen 100")
    return cases
def route(v,training,scales):
    # 7 nearest training instances, source-only features. Training labels
    # are actual measured R179 PAR2 (never heldout PAR2).
    scored=[]
    for x,t in training:
        d=math.sqrt(sum(((a-b)/s)**2 for a,b,s in zip(v,x,scales)))
        scored.append((d,t))
    scored.sort(key=lambda z:z[0])
    neighbors=scored[:min(7,len(scored))]
    scores={}
    for mode in MODES:
        scores[mode]=sum(t[mode]/(0.1+d) for d,t in neighbors)/sum(
            1/(0.1+d) for d,_ in neighbors)
    chosen=min(MODES,key=lambda m:(scores[m],MODES.index(m)))
    # Abstain unless estimated improvement >= 5%; conservative unknown route.
    if chosen!="clean" and scores[chosen]>0.95*scores["clean"]:chosen="clean"
    return chosen,scores
def evaluation(root):
    manifest=json.loads((root/"frozen"/"manifest.json").read_text())
    check(manifest["protocol"]=="DRNAS-R179-FROZEN-100-MIXED-SPECTRUM-v1","wrong benchmark")
    rows=[]
    for i in range(10):
        rs=json.loads((root/f"shard-{i}.json").read_text())
        rows.extend(rs)
    check(len(rows)==1000,"incomplete R179 paired result data")
    cases=cases_from_data(manifest,rows)
    data=[];counts=collections.Counter()
    for c,times in cases:
        path=root/"frozen"/(c["id"]+".cnf")
        check(hashlib.sha256(path.read_bytes()).hexdigest()==c["sha256"],
              "CNF source SHA changed")
        features,overhead,details=fingerprint(path)
        side=split(c["id"],c["sha256"],c["origin"])
        counts[side]+=1
        data.append(dict(id=c["id"],sha256=c["sha256"],origin=c["origin"],
                         split=side,vec=features,overhead=overhead,details=details,
                         times=times))
    train=[z for z in data if z["split"]=="train"]
    test=[z for z in data if z["split"]=="holdout"]
    check(len(train)>=50 and len(test)>=10,"insufficient split")
    check(all(z["origin"]!="real_frozen" for z in train),"real source leakage")
    scales=[]
    for j in range(len(train[0]["vec"])):
        vals=[z["vec"][j] for z in train]
        scales.append(max(0.1,statistics.pstdev(vals)))
    training=[(z["vec"],z["times"]) for z in train]
    output=[]
    for z in test:
        start=time.perf_counter()
        selected,pred=route(z["vec"],training,scales)
        predict_s=time.perf_counter()-start
        # Retrospective conservative upper-bound charge for classifier and
        # measured feature extraction, added to already charged arm times.
        cost=z["overhead"]+predict_s
        selected_par2=z["times"][selected]+cost
        clean=z["times"]["clean"]
        output.append(dict(id=z["id"],origin=z["origin"],
             route=selected,measured_selected_par2=z["times"][selected],
             classifier_charged_s=round(cost,7),
             replay_par2_s=round(selected_par2,7),
             clean_par2_s=clean,oracle_par2_s=min(z["times"].values()),
             predicted=pred,details=z["details"]))
    total=lambda k:sum(x[k] for x in output)
    aggregate={"holdout":len(test),"train":len(train),
        "real_holdout":sum(x["origin"]=="real_frozen" for x in output),
        "clean_par2_total":round(total("clean_par2_s"),6),
        "routed_replay_par2_total":round(total("replay_par2_s"),6),
        "oracle_par2_total":round(total("oracle_par2_s"),6),
        "ratio_clean_to_routed":round(total("clean_par2_s")/total("replay_par2_s"),5),
        "chosen_modes":dict(collections.Counter(x["route"] for x in output)),
        "method":"source-only syntactic kNN 7; 75/25 SHA split; real 4 all heldout",
        "warning":"Retrospective routing replay, not live solver run; no 256-conflict sampling",
        "dataset":"R179 4 known originals + 96 synthetic SAT; NOT BLIND"}
    ROOT.mkdir(exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps({"summary":aggregate,"holdout":output},indent=2))
    with (ROOT/"holdout.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["id","origin","route","measured_selected_par2",
           "classifier_charged_s","replay_par2_s","clean_par2_s","oracle_par2_s"])
        w.writeheader()
        for x in output:w.writerow({k:x[k] for k in w.fieldnames})
    (ROOT/"summary.md").write_text("# R180 SAT Shazam offline source-fingerprint prototype\n\n"+
      "No CDCL conflict probe yet. Strict train/holdout SHA isolation.\n\n"+
      "| metric | result |\n|---|---:|\n"+
      "".join(f"| {k} | {v} |\n" for k,v in aggregate.items()))
    print("R180_SHazam_REPLAY_PASS",json.dumps(aggregate,sort_keys=True))
def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"tiny.cnf"
        p.write_text("p cnf 3 4\n1 2 3 0\n1 -2 -3 0\n-1 2 -3 0\n-1 -2 3 0\n")
        v,seconds,d=fingerprint(p)
        check(d["syntactic_xor3_groups"]==1 and len(v)==10,"fingerprint test")
        dummy=[(v,{m:(1.0 if m=="r174_b" else 2.0) for m in MODES})]
        chosen,_=route(v,dummy,[1]*len(v))
        check(chosen=="r174_b","router selftest")
    print("R180_SHAZAM_SELFTEST_PASS")
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=["selftest","evaluate"])
    ap.add_argument("--root",default="r179")
    a=ap.parse_args()
    if a.action=="selftest":selftest()
    else:evaluation(pathlib.Path(a.root))
