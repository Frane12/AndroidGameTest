#!/usr/bin/env python3
"""DRNAS V10.1: graded confidence, identical 256-conflict prefix experiment.

Predeclared seven post-prefix policies: never/always/LBD/propagations/jump-
depth/all-three/original LBD+prop. Four known 2026 CNFs diagnostic; 8 archived 2025 CNFs disjoint from V9.8/V10.0, but not V7.2.1.
"""
import argparse, csv, hashlib, json, os, random, statistics, subprocess, time
from collections import defaultdict
from pathlib import Path
import official_shortlong_select as src
from official_shortlong_select import REV, SCORES_GIT_BLOB

src.RAW_CAP=96*1024*1024
src.CNF_CAP=96*1024*1024
src.VARIABLE_CAP=1_000_000
src.CLAUSE_CAP=4_000_000
SALT="DRNAS-v101-graded-confidence-identical-256-20261031-v1"
KNOWN_PREFIXES=("8117a2ac08","91860f79f0","8d0d8518a4","ee44c3f4")
POLICIES=("v100_late_plain_force","v100_late_phase_force",
          "v100_late_lbd_force","v100_late_prop_force",
          "v100_late_jump_force","v100_late_joint_force",
          "v100_late_legacy_force",
          "v100_late_confident_force","v100_late_soft_force")
ARMS=POLICIES+("v96_phase_force","ca_plain")
EARLY_KEYS=("stage1","v96_status64","v96_status128","v96_c64",
            "v96_c128","v96_lbd2_64","v96_lbd2_128","v96_lbd4_64",
            "v96_lbd4_128","v96_props64","v96_props128",
            "v96_jump64","v96_jump128","v96_learn64","v96_learn128",
            "v90_learned_256","v90_lbd2_256","v90_lbd4_256",
            "v90_lbd_sum_256","v90_props_256","v90_conflicts_256",
            "v90_jumpdepth_256","v90_jumps_256","v90_backtracks_256",
            "learned_delta","threshold","active_pre","active_256",
            "hints","vars","clauses")
CAP=18.0
REPEATS=2

def save(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def hash_order(txt):
    return hashlib.sha256((SALT+"/"+txt).encode()).hexdigest()

def label_from_score(status):
    if status=="sat-verified":return "SAT"
    if status=="unsat-verified":return "UNSAT"
    return None

def parse_trace(line):
    return dict(part.split("=",1) for part in line.split("\t")[1:])

def gates(t):
    l=int(t["v90_learned_256"])
    c=int(t["v90_conflicts_256"])
    p=int(t["v90_props_256"])
    j=int(t["v90_jumps_256"])
    d=int(t["v90_jumpdepth_256"])
    lbd=l>=20 and c>0 and 100*int(t["v90_lbd2_256"])>=6*l
    prop=c>=32 and p>=32*c
    jump=j>=20 and d>=2*j
    active=int(t["stage1"])==0
    return {
      "v100_late_plain_force":False,
      "v100_late_phase_force":active,
      "v100_late_lbd_force":active and lbd,
      "v100_late_prop_force":active and prop,
      "v100_late_jump_force":active and jump,
      "v100_late_joint_force":active and lbd and prop and jump,
      "v100_late_legacy_force":active and lbd and prop,
      "v100_late_confident_force":active and lbd and (prop or int(t["v90_lbd2_256"])>=64),
      "v100_late_soft_force":active and lbd and (prop or jump),
    }

def freeze(args):
    old=json.loads(Path(args.v100).read_text())
    oldv98=json.loads(Path(args.v98).read_text())
    src25=json.loads(Path(args.source2025).read_text())
    assert len(old["known"])==4 and len(old["holdout"])==8
    assert len(oldv98["new"])==6 and len(src25["holdout"])==32
    known=[dict(x) for x in old["known"]]
    excluded={c["id"] for c in old["holdout"]+oldv98["new"]}
    assert len(excluded)==14
    ranked=sorted(src25["holdout"],
                  key=lambda c:hash_order(c["url"].rstrip("/").split("/")[-1]))
    chosen=[];attempts=[]
    for c in ranked:
        ident=c["url"].rstrip("/").split("/")[-1]
        if ident in excluded:
            attempts.append({"id":ident,"status":"excluded_prior"});continue
        if len(chosen)>=8:break
        try:
            info=src.download_and_features(ident)
            if info["sha256"]!=c["sha256"]:
                raise RuntimeError("Source 2025 SHA256 mismatch")
            assert c["status"] in ("SAT","UNSAT")
            chosen.append({**info,"group":"archived_2025_new_to_v101",
                           "official_label":c["status"],"source_family":c["family"]})
            attempts.append({"id":ident,"status":"accepted"})
            print("V101_ACCEPT",ident,c["family"],flush=True)
        except Exception as e:
            attempts.append({"id":ident,"status":"reject","error":str(e)[:240]})
            print("V101_REJECT",ident,str(e)[:100],flush=True)
    if len(chosen)!=8:raise RuntimeError("Insufficient disjoint 2025 archived CNFs")
    assert len({x["id"] for x in known+chosen})==12
    save(args.out,dict(protocol=SALT,known=known,holdout=chosen,
        cases=known+chosen,arms=ARMS,cap=CAP,repeats=REPEATS,
        prior_excluded_2025_ids=sorted(excluded),attempts=attempts,
        source2025_title=src25["title"],source2025_commit=src25["source_commit"],
        predeclared_gates={
          "lbd":"learned>=20 and LBD2>=6% learned",
          "prop":"conflicts>=32 and propagations>=32/conflict",
          "jump":"jumps>=20 and average jump-depth>=2",
          "legacy":"lbd and prop",
          "soft":"lbd and (prop or jump)",
          "confident":"lbd and (prop or LBD2>=64)"},
        limitations=[
          "V10.1 gates chosen after observing V10 diagnostic runs, known 4 CNFs are not blind",
          "Eight 2025 CNFs disjoint from V9.8/V10, all previously in V7.2.1 work",
          "No V10.1 solution timing used to adjust gates or case order",
          "2 repeats 18s cap: not official competition measurement",
          "SAT models checked locally, UNSAT certificates not independently verified"]))
    print("V101_FROZEN",len(known),len(chosen),flush=True)

def run(args):
    manifest=json.loads(Path(args.manifest).read_text())
    assert manifest["protocol"]==SALT and 0<=args.shard<6
    cases=manifest["cases"][2*args.shard:2*args.shard+2]
    assert len(cases)==2
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    core=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    rows=[]
    exe=str(Path(args.exe).resolve())
    for c in cases:
        fn=out/(c["id"]+".cnf")
        chk=src.download_and_features(c["id"],fn)
        assert chk["sha256"]==c["sha256"]
        assert chk["features"]==c["features"]
        for rep in range(REPEATS):
            seed=(100101+829*rep+int(c["sha256"][:8],16))%(2**32)
            shuffled=list(ARMS);random.Random(seed^9961).shuffle(shuffled)
            for mode in shuffled:
                t0=time.monotonic();early={};final={};err=""
                try:
                    p=subprocess.run([exe,mode,str(fn),str(seed)],
                         capture_output=True,text=True,timeout=CAP,check=False)
                    sec=time.monotonic()-t0
                    if p.returncode:
                        raise RuntimeError("process exit="+str(p.returncode)+
                                           " "+p.stderr[-280:])
                    es=[x for x in p.stdout.splitlines()
                        if x.startswith("DRNAS_EARLY\t")]
                    fs=[x for x in p.stdout.splitlines()
                        if x.startswith("DRNAS_CAUSAL\t")]
                    if len(fs)!=1:raise RuntimeError("No unique DRNAS_CAUSAL final")
                    final=parse_trace(fs[0])
                    early=parse_trace(es[0]) if len(es)==1 else {}
                    status=final["answer"]
                    if final["mode"]!=mode or status!=c["official_label"]:
                        raise RuntimeError("Wrong mode or incorrect SAT/UNSAT")
                except subprocess.TimeoutExpired as exc:
                    status="TIMEOUT";sec=CAP
                    stdout=exc.stdout or b""
                    if isinstance(stdout,bytes):stdout=stdout.decode("utf8","replace")
                    es=[x for x in stdout.splitlines() if x.startswith("DRNAS_EARLY\t")]
                    early=parse_trace(es[-1]) if es else {}
                except Exception as exc:
                    err=str(exc);status="ERROR";sec=time.monotonic()-t0
                if mode in POLICIES and not early:
                    raise RuntimeError("Missing checkpoint trace "+c["id"]+" "+mode)
                if status=="ERROR":
                    raise RuntimeError(c["id"]+" "+mode+" "+err)
                if early and early.get("mode")!=mode:
                    raise RuntimeError("Checkpoint label mismatch")
                row=dict(id=c["id"],group=c["group"],sha256=c["sha256"],
                    seed=seed,rep=rep,cap=CAP,mode=mode,status=status,
                    wall_s=round(sec,6),early=early,final=final,error=err)
                rows.append(row)
                print("V101_TRIAL",c["id"][:10],rep,mode,status,
                    round(sec,3),"LBD2",early.get("v90_lbd2_256","NA"),
                    "PROP",early.get("v90_props_256","NA"),
                    "JUMP",early.get("v90_jumpdepth_256","NA"),flush=True)
        fn.unlink(missing_ok=True)
    assert len(rows)==len(cases)*len(ARMS)*REPEATS==44
    save(out/"raw.json",rows)
    save(out/"meta.json",{"shard":args.shard,"cases":[c["id"] for c in cases],
                           "rows":len(rows),"core":core})
    print("V101_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    m=json.loads(Path(args.manifest).read_text())
    assert m["protocol"]==SALT and m["arms"]==list(ARMS)
    rows=[]
    for shard in range(6):
        base=Path(args.combined)/("v101-shard-"+str(shard))/"results"
        meta=json.loads((base/"meta.json").read_text())
        assert meta["shard"]==shard and meta["rows"]==44
        assert meta["cases"]==[c["id"] for c in m["cases"][2*shard:2*shard+2]]
        rows.extend(json.loads((base/"raw.json").read_text()))
    assert len(rows)==264,len(rows)
    ids={c["id"]:c for c in m["cases"]}
    assert len(ids)==12
    seen=set();by_pair=defaultdict(dict)
    for r in rows:
        key=(r["id"],r["rep"],r["mode"])
        assert key not in seen and r["id"] in ids
        seen.add(key)
        c=ids[r["id"]]
        assert r["sha256"]==c["sha256"] and r["group"]==c["group"]
        assert r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"]
        if r["status"]!="TIMEOUT":
            assert r["status"]==c["official_label"]
        assert r["cap"]==CAP
        by_pair[(r["id"],r["rep"])][r["mode"]]=r
    same_prefix=0
    activation={x:0 for x in POLICIES}
    signal_examples=[]
    for c in m["cases"]:
        for rep in range(REPEATS):
            rr=by_pair[(c["id"],rep)]
            assert set(rr)==set(ARMS)
            traces=[rr[name]["early"] for name in POLICIES]
            assert all(x and all(k in x for k in EARLY_KEYS) for x in traces)
            first=traces[0]
            for t in traces[1:]:
                assert all(t[k]==first[k] for k in EARLY_KEYS),\
                    ("Not identical 256-conflict prefix",c["id"],rep)
                same_prefix+=1
            gate=gates(first)
            for name in POLICIES:
                row=rr[name]
                expected=gate[name]
                actual=bool(int(row["early"]["v100_will_apply"]))
                assert actual==expected,("Incorrect predeclared early gate",c["id"],name)
                activation[name]+=actual
                if row["status"]!="TIMEOUT":
                    assert bool(int(row["final"]["v91_phase_applied"]))==actual
                    assert bool(int(row["final"]["v100_will_apply"]))==actual
            signal_examples.append(dict(id=c["id"],rep=rep,group=c["group"],
                learned=int(first["v90_learned_256"]),
                lbd2=int(first["v90_lbd2_256"]),
                propagations=int(first["v90_props_256"]),
                conflicts=int(first["v90_conflicts_256"]),
                jumps=int(first["v90_jumps_256"]),
                jump_depth_sum=int(first["v90_jumpdepth_256"]),
                activations={k:int(v) for k,v in gate.items()}))
    cohorts={}
    for group in ("known_2026_diagnostic","archived_2025_new_to_v101","all"):
        records=[r for r in rows if group=="all" or r["group"]==group]
        by_arm={}
        for mode in ARMS:
            part=[r for r in records if r["mode"]==mode]
            scores=[2*CAP if r["status"]=="TIMEOUT" else r["wall_s"] for r in part]
            by_arm[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in part),
                n=len(part),mean_PAR2_s=statistics.mean(scores))
        cohorts[group]=by_arm
    cases=[]
    for c in m["cases"]:
        rr=[r for r in rows if r["id"]==c["id"]]
        stats={}
        for mode in ARMS:
            part=[r for r in rr if r["mode"]==mode]
            stats[mode]=statistics.mean(
                2*CAP if r["status"]=="TIMEOUT" else r["wall_s"] for r in part)
        oracle=min(stats["v100_late_plain_force"],stats["v100_late_phase_force"])
        cases.append(dict(id=c["id"],group=c["group"],PAR2=stats,
            late_phase_benefit_s=stats["v100_late_plain_force"]-
                                 stats["v100_late_phase_force"],
            oracle_plain_vs_always=oracle))
    report=dict(protocol=SALT,trials=len(rows),cases=cases,cohorts=cohorts,
                identical_prefix_pairs=same_prefix,gate_activations=activation,
                early_signals=signal_examples,limitations=m["limitations"])
    save(args.out,report)
    lines=["# DRNAS V10.1 — Graded confidence, matched prefix","",
        "264 scheduled matched attempts = 12 CNFs × 11 arms × 2 repeats.",
        "All nine V10/V10.1 late-phase arms share exactly the same FIRST 256 conflicts.",
        "Predeclared before benchmark: LBD, propagation rate, mean jump depth,",
        "their AND combination and original LBD+propagation joint rule.",
        "Verified equal early traces: "+str(same_prefix)+" independent pairwise checks.",
        "No historical or official leaderboard claim.","",
        "## Gate activation counts (of 24 case/repeat pairs)",""]
    for name,n in activation.items():lines.append("- "+name+": "+str(n)+"/24")
    for group in ("known_2026_diagnostic","archived_2025_new_to_v101","all"):
        lines.extend(["","## "+group,"",
            "| Method | Solved | Mean PAR2 s (lower is better) |",
            "|---|---:|---:|"])
        for mode,v in cohorts[group].items():
            lines.append("| "+mode+" | "+str(v["solved"])+"/"+str(v["n"])+
                         " | "+format(v["mean_PAR2_s"],".4f")+" |")
    lines.extend(["","## Per-instance performance: positive phase benefit means late phases help"])
    for c in cases:
        lines.append("- "+c["id"][:12]+" "+c["group"]+
            " phase benefit: "+format(c["late_phase_benefit_s"],"+.3f")+
            " s; LBD gate: "+format(c["PAR2"]["v100_late_lbd_force"],".3f")+
            ", prop gate: "+format(c["PAR2"]["v100_late_prop_force"],".3f")+
            ", jump gate: "+format(c["PAR2"]["v100_late_jump_force"],".3f")+
            ", joint: "+format(c["PAR2"]["v100_late_joint_force"],".3f"))
    lines.extend(["","Eight archived 2025 CNFs exclude V9.8 and V10.0, but were seen in earlier V7.2.1 work.",
        "SAT/UNSAT labels come from archived official 2025 and 2026 source metadata;",
        "UNSAT proofs were not independently checked."])
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    for mode,params in (("freeze",("v100","v98","source2025","out")),
                        ("run",("manifest","exe","out")),
                        ("audit",("manifest","combined","out","md"))):
        a=sub.add_parser(mode)
        for name in params:a.add_argument("--"+name,required=True)
        if mode=="run":a.add_argument("--shard",type=int,required=True)
    args=p.parse_args()
    {"freeze":freeze,"run":run,"audit":audit}[args.cmd](args)
