#!/usr/bin/env python3
"""R178 spectrum-100: immutable SHA-matched 4 known ORIGINAL source residual
mixed formulas + 96 newly deterministic planted SAT mixed XOR/AND/OR formulas.

No claims that generated instances are external or blind. No selection of
formulas by benchmark performance. Groups by CaDiCaL runtime are post-hoc.
Compare clean CaDiCaL, R174-B, R177-OneHop, R177-TwoHop at identical source
SHA and cap, with full preprocessing and router charges for DRNAS modes.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,os,pathlib,random,statistics,subprocess,time
import r177_xor_cnf_resolution_benchmark as r177

ROOT=pathlib.Path("r178")
r177.ROOT=ROOT
r177.prior.ROOT=ROOT
r177.prior.base174.ROOT=ROOT
r177.prior.base174.base.ROOT=ROOT
r177.prior.base174.base.FROZEN=ROOT/"frozen"
base=r177.base174
need=r177.need
sha=r177.sha
save=r177.save
rd=r177.rd
PROTO="DRNAS-R178-FROZEN-100-MIXED-SPECTRUM-v1"
MODES=("clean","r174_b","r177_onehop","r177_twohop")
NATIVE={"r174_b":"gauss_feedback",
        "r177_onehop":"gauss_resolve1",
        "r177_twohop":"gauss_resolve2"}
SHARDS=10
REPS=2
REAL_IDS=(
 "3e912cd2a499b8f956246b866e2f9f64",
 "99718c1729a8de3347a9946f1836421d",
 "b76b9699c2deb74dd9b4a99a05179acd",
 "c0e828fb967fc4f0935cf06c6a6b1055",
)
def sig(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def cap_for(c):return 45.0 if c["origin"]=="real_frozen" else 30.0
def normalize(clause):
    x=tuple(sorted(clause,key=lambda z:(abs(z),z)))
    need(len({abs(v) for v in x})==len(x),"tautology or duplicate variables")
    return x
def generate(i):
    band=i//32
    j=i%32
    if band==0:
        n=38+2*(j%16);density=3.5+0.06*(j%7);xors=max(12,n//3)
    elif band==1:
        n=80+4*(j%16);density=4.05+0.045*(j%7);xors=max(14,n//5)
    else:
        n=160+9*(j%16);density=4.15+0.065*(j%7);xors=max(18,n//6)
    rng=random.Random(178000012+i*113)
    witness=[0]+[rng.getrandbits(1) for _ in range(n)]
    xorpool=list(range(1,max(16,int(n*0.65))+1))
    nonxorpool=list(range(max(xorpool)+1,n+1))
    need(len(nonxorpool)>=8,"generator CNF outside parity block missing")
    rows=set();clauses=set()
    # Every 3-variable XOR is encoded by its four forbidden assignments.
    for _ in range(xors*10):
        if len(rows)>=xors:break
        vs=tuple(sorted(rng.sample(xorpool,3)))
        if vs in rows:continue
        rows.add(vs)
        rhs=witness[vs[0]]^witness[vs[1]]^witness[vs[2]]
        for bits in itertools.product((0,1),repeat=3):
            if (bits[0]^bits[1]^bits[2])==rhs:continue
            clauses.add(normalize([(-v if b else v) for v,b in zip(vs,bits)]))
    need(len(rows)==xors,"generator short parity quota")
    # Residual AND/OR CNF crosses the XOR and non-XOR variable boundary.
    target=int(n*density)
    attempts=0
    while len(clauses)<target+4*xors and attempts<target*40:
        attempts+=1
        if attempts%5==0:
            vs=rng.sample(range(1,n+1),3)
        else:
            vs=[rng.choice(xorpool),*rng.sample(nonxorpool,2)]
        bits=[rng.randrange(2) for _ in vs]
        if not any(bits[k]==witness[v] for k,v in enumerate(vs)):
            # Enforce one satisfied residual literal under the planted model.
            k=rng.randrange(3)
            bits[k]=witness[vs[k]]
        clause=normalize([v if b else -v for v,b in zip(vs,bits)])
        clauses.add(clause)
    need(attempts<target*40,"generator residual clause quota")
    # Check that the source model satisfies every original CNF clause.
    for cl in clauses:
        need(any((lit>0)==bool(witness[abs(lit)]) for lit in cl),
             "original planted SAT witness invalid")
    ordered=sorted(clauses,key=lambda cl:(len(cl),cl))
    return n,ordered,len(rows),band
def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    frozen=ROOT/"frozen";frozen.mkdir(exist_ok=True)
    srcroot=ROOT/"input"/"frozen"
    source=rd(srcroot/"manifest.json")
    known={c["id"]:c for c in source["cases"]}
    cases=[]
    for id in REAL_IDS:
        need(id in known and known[id]["cohort"]=="mixed_residual",
             "missing previous original mixed source in immutable artifact")
        src=srcroot/(id+".cnf")
        need(sig(src)==known[id]["sha256"],"original source SHA failed")
        dst=frozen/(id+".cnf");dst.write_bytes(src.read_bytes())
        cases.append({"id":id,"sha256":sig(dst),"origin":"real_frozen","cohort":"mixed_residual",
            "nominal_band":"original_hard","original_provenance":"r155_original25",
            "source_family":known[id].get("family","unknown"),"expected":"unknown",
            "cap_s":45.0})
    for i in range(96):
        n,cl,xorrows,band=generate(i)
        raw=(f"c R178 deterministic planted SAT seed_index={i}\n"
             f"p cnf {n} {len(cl)}\n"+
             "".join(" ".join(map(str,c))+" 0\n" for c in cl)).encode()
        digest=hashlib.sha256(raw).hexdigest()
        id="s"+digest[:31]
        (frozen/(id+".cnf")).write_bytes(raw)
        cases.append({"id":id,"sha256":digest,"origin":"synthetic_planted","cohort":"mixed_residual",
           "nominal_band":("easy","medium","hard")[band],
           "original_provenance":"R178_local_deterministic_generator",
           "source_family":"generated_xor3_and_or3",
           "expected":"SAT","variables":n,"clauses":len(cl),
           "xor_rows":xorrows,"seed_index":i,"cap_s":30.0})
    cases.sort(key=lambda c:c["id"])
    need(len(cases)==100 and len({x["sha256"] for x in cases})==100,
         "100 source formula hashes must be unique")
    data={"protocol":PROTO,"formulas":100,
          "originals":4,"generated":96,"not_blind":True,
          "source_artifact_run_id":42112755104,
          "cases":cases}
    save(frozen/"manifest.json",data)
    verify()
    print("R178_FROZEN_100_PASS",json.dumps(
      {"originals":4,"generated":96,
       "origin_counts":dict(collections.Counter(x["origin"] for x in cases)),
       "manifest_sha256":sig(frozen/"manifest.json")},sort_keys=True),flush=True)
def verify():
    m=rd(ROOT/"frozen"/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==100,
         "frozen source count/protocol drift")
    need(sum(c["origin"]=="real_frozen" for c in m["cases"])==4,
         "not 4 original formulas")
    need(sum(c["origin"]=="synthetic_planted" for c in m["cases"])==96,
         "not 96 generated formulas")
    for c in m["cases"]:
        need(sig(ROOT/"frozen"/(c["id"]+".cnf"))==c["sha256"],
             "one original SHA drift "+c["id"])
        need(c["cap_s"]==cap_for(c),"source cap policy changed")
    return m["cases"]

def run_one(c,mode,rep,prep,binary):
    cap=cap_for(c)
    src=ROOT/"frozen"/(c["id"]+".cnf")
    need(sig(src)==c["sha256"],"source drift before trial")
    screen_s=0.0
    if mode=="clean":
        result=base.capped_native(c,"clean",cap,binary,prep,0.0)
        result.update(route="clean_CaDiCaL",eligible=False,
                      r177_onehop=0,r177_twohop=0,r177_proof_checks=0)
    else:
        t=time.perf_counter()
        exact=base.exact.solve(src)
        screen_s=time.perf_counter()-t
        need(exact["source_sha256"]==c["sha256"] and
             exact["status"]=="NOT_PURE" and not exact["pure_exact"],
             "source is not residual mixed CNF")
        eligible=(prep["full_rows"]>=8 and prep["boundary_rows"]>=4
           and prep["diverse_boundary_vars"]>=12 and
           prep["preprocessing_s"]<=min(1.5,0.07*cap))
        if eligible:
            result=r177.capped_native(c,NATIVE[mode],cap,binary,prep,screen_s)
            result["route"]=mode+"_certified_gauss"
        else:
            # Safe no-structure fallback: charge source extraction and
            # exact screening, never give a free preprocessing advantage.
            result=base.capped_native(c,"clean",cap,binary,prep,
                                      screen_s+prep["preprocessing_s"])
            result.update(r177_onehop=0,r177_twohop=0,r177_proof_checks=0)
            result["route"]="clean_with_abstention_cost"
        if mode in ("r177_onehop","r177_twohop"):
            need(result["r177_proof_checks"]==
                 result["r177_onehop"]+result["r177_twohop"],
                 "unverified R177 mixed clauses")
            if mode=="r177_onehop":
                need(result["r177_twohop"]==0,"leaked second-hop clause")
        result["eligible"]=eligible
    if result["status"]!="TIMEOUT" and result["elapsed"]>cap:
        result["status"]="TIMEOUT"
    need(result["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid answer")
    result.update(id=c["id"],sha256=c["sha256"],mode=mode,repeat=rep,
      origin=c["origin"],nominal_band=c["nominal_band"],
      cap_s=cap,router_s=round(screen_s,6),
      proof=("ORIGINAL_SAT_WITNESS_VERIFIED" if result["status"]=="SAT"
         else "NATIVE_UNSAT_WITHOUT_INDEPENDENT_LRAT" if result["status"]=="UNSAT"
         else "TIMEOUT"),
      par2=round(2*cap if result["status"]=="TIMEOUT"
                 else min(cap,result["elapsed"]),6))
    return result

def shard(index,binary):
    need(0<=index<SHARDS,"bad shard index")
    pin=rd(ROOT/"build-pin.json")
    need(sig(binary)==pin["binary_sha256"],"native SHA changed")
    need(pin["source_commit"]==os.environ.get("GITHUB_SHA",pin["source_commit"]),
         "unfrozen binary commit drift")
    if hasattr(os,"sched_getaffinity"):
        available=os.sched_getaffinity(0)
        if available:os.sched_setaffinity(0,{min(available)})
    cases=verify()
    (ROOT/"empty-rows.tsv").write_text("")
    rows=[]
    for i,c in enumerate(cases):
        if i%SHARDS!=index:continue
        prep=base.base.prepare(c)
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                r=run_one(c,mode,rep,prep,binary)
                rows.append(r)
                save(ROOT/f"shard-{index}.json",rows)
                print("R178_TRIAL",json.dumps({k:r.get(k) for k in (
                  "id","origin","nominal_band","mode","repeat","status",
                  "elapsed","par2","cap_s","route","eligible","conflicts",
                  "decisions","r177_onehop","r177_twohop","r177_proof_checks")},
                  sort_keys=True),flush=True)
    need(len(rows)==len(cases[index::SHARDS])*REPS*len(MODES),
         "incomplete benchmark shard")
    print("R178_SHARD_PASS",index,len(rows),flush=True)

def baseline_band(rows,case):
    a=[r for r in rows if r["id"]==case["id"] and r["mode"]=="clean"]
    need(len(a)==2,"baseline repetitions incomplete")
    if all(x["status"]=="TIMEOUT" for x in a):return "timeout"
    t=statistics.median(x["elapsed"] if x["status"]!="TIMEOUT"
                        else x["cap_s"] for x in a)
    if t<0.1:return "lt_0_1s"
    if t<1:return "0_1_to_1s"
    if t<10:return "1_to_10s"
    if t<=30:return "10_to_30s"
    return "30_to_45s"

def audit():
    cases=verify()
    manifest_sha=sig(ROOT/"frozen"/"manifest.json")
    allrows=[];seen=set()
    for i in range(SHARDS):
        rr=rd(ROOT/f"shard-{i}.json")
        need(len(rr)==len(cases[i::SHARDS])*REPS*len(MODES),
             "shard length mismatch")
        for r in rr:
            key=(r["sha256"],r["repeat"],r["mode"])
            need(key not in seen,"duplicate SHA/rep/mode")
            seen.add(key);allrows.append(r)
    need(len(allrows)==100*REPS*len(MODES)==800,"800 trials missing")
    original={c["sha256"]:c for c in cases}
    for r in allrows:
        c=original.get(r["sha256"])
        need(c is not None and c["id"]==r["id"],"source mismatch")
        need(r["mode"] in MODES and r["repeat"] in (0,1),"invalid mode")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
        need(abs(r["par2"]-(2*r["cap_s"] if r["status"]=="TIMEOUT"
                else min(r["cap_s"],r["elapsed"])))<1e-4,"PAR2 mismatch")
        if r["status"]=="SAT":
            need(r["proof"]=="ORIGINAL_SAT_WITNESS_VERIFIED",
                 "no verified original CNF SAT witness")
        if r["mode"] in ("r177_onehop","r177_twohop"):
            need(r["r177_proof_checks"]==r["r177_onehop"]+r["r177_twohop"],
                 "bad native resolution trace")
        if c["origin"]=="synthetic_planted":
            need(r["status"]!="UNSAT","generated planted SAT marked UNSAT")
    # Replay source XOR independently once per selected formula, as well
    # as every Gaussian proof generated by the per-shard prep.
    from r166x_certified_gauss import replay
    for c in cases:
        src=ROOT/"frozen"/(c["id"]+".cnf")
        prep=rd(ROOT/("prep-"+c["id"]+".json"))
        cert=rd(ROOT/("cert-"+c["id"]+".json"))
        base.base.independent_cert(c,cert)
        d=ROOT/("gauss-"+c["id"])
        need(sig(d/"gauss-cert.json")==prep["gauss_certificate_sha"],
             "cert SHA mismatch")
        need(replay(src,cert,d/"gauss-cert.json",
                    d/"gauss.tsv",d/"gauss-units.tsv"),"Gaussian source proof invalid")
        for rep in range(REPS):
            answers={r["status"] for r in allrows if r["id"]==c["id"]
                    and r["repeat"]==rep and r["status"]!="TIMEOUT"}
            need(len(answers)<=1,"contradictory paired SAT/UNSAT answers")
    summary={}
    by_band=collections.defaultdict(lambda:collections.defaultdict(list))
    by_origin=collections.defaultdict(lambda:collections.defaultdict(list))
    for c in cases:
        b=baseline_band(allrows,c)
        for r in allrows:
            if r["id"]!=c["id"]:continue
            by_band[b][r["mode"]].append(r)
            by_origin[c["origin"]][r["mode"]].append(r)
    def summarise(rr):
        times=[x["elapsed"] for x in rr if x["status"]!="TIMEOUT"]
        return dict(trials=len(rr),solved=len(times),
            sat=sum(x["status"]=="SAT" for x in rr),
            unsat=sum(x["status"]=="UNSAT" for x in rr),
            par2_s=round(sum(x["par2"] for x in rr),6),
            median_solved_s=round(statistics.median(times),6) if times else None,
            clauses_1hop=sum(x.get("r177_onehop",0) for x in rr),
            clauses_2hop=sum(x.get("r177_twohop",0) for x in rr),
            eligible=sum(x.get("eligible",False) for x in rr))
    for mode in MODES:summary[mode]=summarise([r for r in allrows if r["mode"]==mode])
    bands={b:{mode:summarise(v.get(mode,[])) for mode in MODES}
          for b,v in sorted(by_band.items())}
    origins={b:{mode:summarise(v.get(mode,[])) for mode in MODES}
          for b,v in sorted(by_origin.items())}
    paired=[]
    for c in cases:
        for rep in range(REPS):
            arms={x["mode"]:x for x in allrows
                  if x["id"]==c["id"] and x["repeat"]==rep}
            for mode in MODES[1:]:
                a,b=arms["clean"],arms[mode]
                paired.append(dict(id=c["id"],origin=c["origin"],repeat=rep,
                    mode=mode,baseline_band=baseline_band(allrows,c),
                    clean_status=a["status"],variant_status=b["status"],
                    delta_par2_s=round(a["par2"]-b["par2"],6),
                    speedup_both_solved=round(a["elapsed"]/b["elapsed"],6)
                         if a["status"]!="TIMEOUT" and b["status"]!="TIMEOUT"
                         and b["elapsed"]>0 else None))
    report=dict(protocol=PROTO,status="R178_SPECTRUM_100_AUDIT_PASS_NOT_BLIND",
       formulas=100,originals=4,generated=96,attempts=len(allrows),
       repetitions=REPS,not_blind=True,
       original_sources_known_development=True,
       newly_generated_sources_not_external=True,
       selection_by_benchmark_results=False,
       difficulty_bands_posthoc_reference_calibration=True,
       manifest_sha256=manifest_sha,sha_checked=True,
       original_SAT_witnesses_checked=True,
       independent_source_Gaussian_certificates_replayed=True,
       independent_UNSAT_LRAT=False,
       summary=summary,bands=bands,origins=origins,paired=paired,
       caveats=["4 original reused, 96 newly generated planted SAT",
       "0.1-30s is a calibrated analysis band, not a promised quota",
       "Do not compare performance across capped original 45s vs generated 30s without paired per-case analysis",
       "UNSAT results are not independent LRAT certified",
       "Original formulas not blind; generated data are deterministic and not external"])
    save(ROOT/"report.json",report)
    import csv
    with (ROOT/"paired.csv").open("w",newline="") as f:
        cols=list(paired[0])
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(paired)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R178 100 original + synthetic mixed XOR-CNF source SHA pairs\n\n")
        f.write("4 known real original CNFs + 96 deterministic planted SAT CNFs; NOT BLIND.\n\n")
        f.write("| Arm | Solved/200 | PAR2 s | One-hop clauses | Two-hop clauses |\n|---|---:|---:|---:|---:|\n")
        for mode,v in summary.items():
            f.write(f'| {mode} | {v["solved"]}/{v["trials"]} | {v["par2_s"]} | {v["clauses_1hop"]} | {v["clauses_2hop"]} |\n')
        f.write("\n## CaDiCaL baseline-calibrated bands\n\n")
        for band,group in bands.items():
            f.write("### "+band+"\n")
            for mode,v in group.items():
                f.write(f'- {mode}: {v["solved"]}/{v["trials"]} PAR2={v["par2_s"]}\n')
        f.write("\nNo claim of world ranking or independent UNSAT LRAT.\n")
    print("R178_FINAL",json.dumps({"formulas":100,"attempts":len(allrows),
      "summary":summary,"bands":{b:{mode:{"solved":v["solved"],
       "trials":v["trials"],"par2_s":v["par2_s"]}
       for mode,v in group.items()} for b,group in bands.items()}},
       sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r178/r178-native")
    a=p.parse_args()
    if a.action=="freeze":freeze()
    elif a.action=="verify":
        print("R178_SOURCE_VERIFIED",len(verify()),flush=True)
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
