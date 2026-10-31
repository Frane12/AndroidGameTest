#!/usr/bin/env python3
"""DRNAS v9.6: frozen zero-conflict CNF-only predictor; prospective SATLIB holdout.
Training coefficients fitted ONLY to the 22 previously measured selected SATLIB
cases. No holdout outcome used for selection. Evaluation includes Python feature
and routing overhead. This is not a fully external blind competition.
"""
import argparse,collections,csv,hashlib,io,json,math,os,random,statistics,subprocess,tarfile,time,zipfile
from pathlib import Path

SALT="drnas-v96-satlib-unscreened-20261031-precommitted"
FAMILIES=["uf225-960","uuf225-960","uf250-1065","uuf250-1065"]
MODES=["ca_plain","v92_sparse","v92_structural","v96_predict"]
FEATURES=["strong_ratio","broad_ratio","weak_ratio","strong_coverage","broad_coverage",
          "weak_only_cover","strong_falsified","broad_falsified","strong_unit",
          "broad_unit","weak_disagreement","degree_std","strong_pair_reuse",
          "weak_pair_reuse"]
MEANS=[0.2734141414141414,0.5836363636363635,0.3102222222222222,0.4733354673495518,0.7647113743064448,0.4727539479300042,0.0005828531796841656,0.00597057725138711,0.011722417840375587,0.044622279129321374,0.0735070692353381,0.27286793663401576,0.04366100666953896,0.0548766487571726]
SCALES=[0.023661145602944723,0.038407733126041635,0.030289882669691195,0.03217023668132457,0.030065697916737494,0.04114680615565504,0.0007588368489181644,0.0022784301803773607,0.003838239341892884,0.004698345340910474,0.014671725271920203,0.012234569732905855,0.016916340157173172,0.01774541333502453]
COEF=[0.05827290058032338,0.03479877061740383,-0.0013952411374526619,0.03456660321515323,-0.03828178568490732,-0.05816942294282486,-0.11994248467977782,-0.06362318420877713,0.0031449537490401054,-0.0715970183606697,-0.07024596546837919,-0.061053175450459594,0.03611413374929445,-0.08689817354790298]
INTERCEPT=0.06065629402047778
CUTOFF=math.log(1.30)
CAP=4.0
REPEATS=3

def cnf_clean(raw):
    lines=[]
    for line in raw.splitlines(keepends=True):
        if line.strip()==b"%":break
        lines.append(line)
    return b"".join(lines)

def parse_cnf(raw):
    n=0; clauses=[];cl=[]
    for line in raw.decode("ascii").splitlines():
        if not line or line.startswith("c") or line.startswith("%"):continue
        if line.startswith("p"):
            bits=line.split()
            assert bits[:2]==["p","cnf"]
            n=int(bits[2]);expected=int(bits[3]);continue
        for part in line.split():
            lit=int(part)
            if lit==0:clauses.append(cl);cl=[]
            else:cl.append(lit)
    assert not cl and n>0 and len(clauses)==expected
    return n,clauses

def get_features(raw):
    n,clauses=parse_cnf(raw)
    pos=[0]*(n+1);neg=[0]*(n+1)
    for c in clauses:
        for lit in c:
            if lit>0:pos[lit]+=1
            else:neg[-lit]+=1
    strong={v:(1 if pos[v]>neg[v] else -1) for v in range(1,n+1)
            if pos[v]+neg[v]>=8 and 100*abs(pos[v]-neg[v])>=30*(pos[v]+neg[v]) and pos[v]!=neg[v]}
    broad={v:(1 if pos[v]>neg[v] else -1) for v in range(1,n+1)
           if pos[v]+neg[v]>=6 and 100*abs(pos[v]-neg[v])>=15*(pos[v]+neg[v]) and pos[v]!=neg[v]}
    weak={v:s for v,s in broad.items() if v not in strong}
    assert all(broad.get(v)==s for v,s in strong.items())
    def probe(assign):
        covered=falsified=units=0;pairs=set();pair_count=0
        for c in clauses:
            true=sum(abs(x) in assign and assign[abs(x)]==(1 if x>0 else -1) for x in c)
            false=sum(abs(x) in assign and assign[abs(x)]!=(1 if x>0 else -1) for x in c)
            covered+=bool(true);falsified+=false==len(c);units+=false==len(c)-1 and true==0
            vs=sorted(abs(x) for x in c if abs(x) in assign)
            for i in range(len(vs)):
                for j in range(i+1,len(vs)):
                    pairs.add((vs[i],vs[j]));pair_count+=1
        return covered/len(clauses),falsified/len(clauses),units/len(clauses),(pair_count-len(pairs))/max(1,pair_count)
    sc,sf,su,sp=probe(strong)
    bc,bf,bu,bp=probe(broad)
    wc,_,_,wp=probe(weak)
    mismatch=denom=0
    for c in clauses:
        strong_lits=[x for x in c if abs(x) in strong]
        weak_lits=[x for x in c if abs(x) in weak]
        if strong_lits and weak_lits:
            denom+=1
            ss=sum(strong[abs(x)]==(1 if x>0 else -1) for x in strong_lits)
            ww=sum(weak[abs(x)]==(1 if x>0 else -1) for x in weak_lits)
            mismatch+=(ss==0 and ww==0)
    deg=[pos[v]+neg[v] for v in range(1,n+1)]
    return [len(strong)/n,len(broad)/n,len(weak)/n,sc,bc,wc,sf,bf,su,bu,
            mismatch/max(1,denom),statistics.pstdev(deg)/max(1,statistics.mean(deg)),sp,wp]

def predict(raw):
    f=get_features(raw)
    score=INTERCEPT+sum(w*(v-m)/sd for v,m,sd,w in zip(f,MEANS,SCALES,COEF))
    return ("v92_sparse" if score>CUTOFF else "v92_structural"),score

def select_from_archive(root,shard):
    fam=FAMILIES[shard];part=root/("shard-"+str(shard))
    meta=json.loads((part/"manifest.json").read_text())
    screen=json.loads((part/"screen.json").read_text())
    assert meta["group"]==fam and len(screen)==20 and len(meta["cases"])>=4
    archive=(part/(fam+".tar.gz")).read_bytes()
    assert hashlib.sha256(archive).hexdigest()==meta["archive_sha256"]
    seen={x["source_member"] for x in screen}
    with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as tar:
        members={m.name:m for m in tar if m.isfile() and m.name.endswith(".cnf")}
        possible=sorted((m for m in members if m not in seen),
                        key=lambda s:hashlib.sha256((SALT+"/"+s).encode()).hexdigest())
        assert len(possible)>=6
        chosen=possible[:6]
        cases=[]
        for i,member in enumerate(chosen):
            original=tar.extractfile(members[member]).read()
            clean=cnf_clean(original)
            n,clauses=parse_cnf(clean)
            digest=hashlib.sha256(clean).hexdigest()
            cases.append(dict(id=fam+"-"+str(i),family=fam,source_member=member,
                              original_sha256=hashlib.sha256(original).hexdigest(),
                              sha256=digest,truth=("SAT" if fam.startswith("uf") else "UNSAT"),
                              vars=n,clauses=len(clauses),body=clean))
    assert len(cases)==6
    return cases

def bench(args):
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    core=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{core})
    cases=select_from_archive(Path(args.source),args.shard)
    manifest=[{k:v for k,v in c.items() if k!="body"} for c in cases]
    (root/"manifest.json").write_text(json.dumps(dict(salt=SALT,shard=args.shard,cases=manifest,core=core,cap=CAP,repeats=REPEATS),indent=2))
    exe=str(Path(args.exe).resolve())
    fields=["id","family","sha256","truth","rep","mode","routed","status","wall_s","score","hint_count","stage1","stage2","learned_delta","error"]
    with (root/"raw.csv").open("w",newline="") as file:
        wr=csv.DictWriter(file,fieldnames=fields);wr.writeheader()
        for case in cases:
            cnf=root/(case["id"]+".cnf");cnf.write_bytes(case["body"])
            for rep in range(REPEATS):
                order=list(MODES);random.Random(int(case["sha256"][:8],16)+rep*971).shuffle(order)
                for mode in order:
                    start=time.monotonic(); routed=mode;score=""
                    status="ERROR";error="";attrs={}
                    try:
                        if mode=="v96_predict":
                            routed,score=predict(case["body"])
                        used=time.monotonic()-start
                        if used>=CAP:
                            status="TIMEOUT";elapsed=CAP
                        else:
                            seed=(830031+rep*527+int(case["sha256"][:8],16))%(2**32)
                            p=subprocess.run([exe,routed,str(cnf),str(seed)],
                                capture_output=True,text=True,timeout=CAP-used,check=False)
                            elapsed=time.monotonic()-start
                            if elapsed>=CAP:
                                status="TIMEOUT";elapsed=CAP
                            else:
                                assert p.returncode==0,("exit "+str(p.returncode)+" "+p.stderr[-200:])
                                found=[s for s in p.stdout.splitlines() if s.startswith("DRNAS_CAUSAL\t")]
                                assert len(found)==1
                                attrs=dict(x.split("=",1) for x in found[0].split("\t")[1:])
                                assert attrs["mode"]==routed and attrs["answer"]==case["truth"]
                                status=attrs["answer"]
                    except subprocess.TimeoutExpired:
                        status="TIMEOUT";elapsed=CAP
                    except Exception as e:
                        error=str(e);elapsed=time.monotonic()-start;status="ERROR"
                    row=dict(id=case["id"],family=case["family"],sha256=case["sha256"],truth=case["truth"],
                             rep=rep,mode=mode,routed=routed,status=status,wall_s=round(min(CAP,elapsed),6),
                             score=score,hint_count=attrs.get("hints",""),stage1=attrs.get("stage1",""),
                             stage2=attrs.get("stage2",""),learned_delta=attrs.get("learned_delta",""),error=error)
                    wr.writerow(row);file.flush()
                    print("V96_TRIAL",case["id"],rep,mode,"=>",routed,status,row["wall_s"],flush=True)
                    if error:raise RuntimeError(str(row))
            cnf.unlink(missing_ok=True)
    print("V96_SHARD_OK",args.shard,flush=True)

def audit(args):
    root=Path(args.source);rows=[]; cases=[]
    for shard in range(4):
        folder=root/("v96-shard-"+str(shard))
        m=json.loads((folder/"manifest.json").read_text())
        assert m["salt"]==SALT and m["shard"]==shard and m["cap"]==CAP and m["repeats"]==REPEATS
        cases.extend(m["cases"])
        rows.extend(list(csv.DictReader((folder/"raw.csv").open())))
    assert len(cases)==24 and len({c["sha256"] for c in cases})==24
    assert len({c["source_member"] for c in cases})==24
    assert len(rows)==24*3*4,len(rows)
    observed={(r["sha256"],int(r["rep"]),r["mode"]) for r in rows}
    expected={(c["sha256"],rep,mode) for c in cases for rep in range(3) for mode in MODES}
    assert observed==expected and len(observed)==len(rows)
    assert all(r["status"] in ("SAT","UNSAT","TIMEOUT") and r["status"] in (r["truth"],"TIMEOUT") and not r["error"] for r in rows)
    stats={}
    for mode in MODES:
        selected=[r for r in rows if r["mode"]==mode]
        stats[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in selected),
                         mean_PAR2=statistics.mean(float(r["wall_s"]) if r["status"]!="TIMEOUT" else 2*CAP for r in selected))
    choices=collections.Counter(r["routed"] for r in rows if r["mode"]=="v96_predict")
    details=[]
    for c in cases:
        d={"id":c["id"],"truth":c["truth"]}
        for mode in MODES:
            rr=[r for r in rows if r["sha256"]==c["sha256"] and r["mode"]==mode]
            d[mode]=statistics.mean(float(r["wall_s"]) if r["status"]!="TIMEOUT" else 2*CAP for r in rr)
        details.append(d)
    report=dict(protocol=SALT,holdout_cases=24,attempts=len(rows),cutoff=CAP,
                training_cases=22,selection="SHA-256 salted rank of unscreened SATLIB archive members",
                metrics=stats,choices=choices,per_case=details,
                limitations=["Same public SATLIB archives as training but disjoint formulas, not external competition",
                    "16+ structural features could overfit 22 historical training cases",
                    "Features measured in Python for v96 only, included in wall time",
                    "UNSAT verified by SATLIB labels and solver agreement only; no independent DRAT/LRAT"])
    Path(args.out).mkdir(parents=True,exist_ok=True)
    (Path(args.out)/"v96_report.json").write_text(json.dumps(report,indent=2))
    lines=["# DRNAS V9.6 prospective 24-instance SATLIB holdout","",
           "24 unscreened archived CNFs, 4 SAT/UNSAT families, three repeats, 4 s cap, PAR2 timeout=8s.",
           "Prediction frozen from 22 earlier selected cases; feature overhead counted. No retraining on holdout.","",
           "| Mode | Solved/72 | Mean PAR2 (s; lower better) |","|---|---:|---:|"]
    for mode in MODES:
        lines.append("| %s | %d/72 | %.6f |"%(mode,stats[mode]["solved"],stats[mode]["mean_PAR2"]))
    lines+=["","Prediction choices: "+str(dict(choices)),
            "Missing/incorrect answers: 0",
            "This is disjoint-from-training but not evidence of a world record or P=NP."]
    md="\n".join(lines)+"\n"
    (Path(args.out)/"v96_report.md").write_text(md)
    print(md,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("command",choices=("bench","audit"))
    p.add_argument("--source",required=True);p.add_argument("--out",required=True)
    p.add_argument("--shard",type=int,default=0);p.add_argument("--exe",default="./v92_probe")
    args=p.parse_args()
    if args.command=="bench":bench(args)
    else:audit(args)
