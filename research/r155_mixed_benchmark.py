#!/usr/bin/env python3
"""DRNAS R155: certified GF2-to-residual-CNF bridge vs real reference solvers.

Development rematch of the ORIGINAL SHA-FROZEN R154 25 CNFs, NOT a blind test.
R155 appends only independently verified XOR-span-implied clauses, in a
temporary unlinked DIMACS FD. SAT witnesses checked against ORIGINAL CNF.
Pure GF2 UNSAT contradictions independently replayed; fallback UNSAT
still lacks independent LRAT certification. Six real solvers, 15s cap,
two paired repetitions, SHA/binary pinning and no automatic promotion.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,math,os,pathlib,random,re,statistics,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r154_unseen_benchmark as old
ROOT=pathlib.Path("r155")
INPUT=ROOT/"frozen"
PROTO="DRNAS-R155-MIXED-XOR-ENTAILED-CNF-DEV-25-20261105-v1"
FROZEN_PROTO=old.PROTO
SHARDS=8;REPS=2;CAP=15.
MODES=("r155","r153","r28","kissat","cadical","cryptominisat")
BINS={"r155":ROOT/"r155","r153":ROOT/"r153","r28":ROOT/"r28",
      "kissat":pathlib.Path("built/bin/kissat_4_0_4"),
      "cadical":pathlib.Path("built/bin/cadical_3_0_1"),
      "cryptominisat":pathlib.Path("/usr/bin/cryptominisat5")}
old.ROOT=ROOT
def need(ok,message):
    if not ok:raise RuntimeError("R155_AUDIT_REFUSED "+str(message))
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()
def load(path):return json.loads(pathlib.Path(path).read_text())
def write(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+".partial")
    temp.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    os.replace(temp,p)
def cases():
    m=old.manifest()
    need(m["protocol"]==FROZEN_PROTO,"R154 original freeze changed")
    need(len(m["cases"])==25 and sum(m["cohort_counts"].values())==25,
         "expected original 25 R154 cases")
    need(set(m["cohort_counts"])=={"complete_xor","xor_plus_units","mixed_residual","nonxor_control"},
         "original cohort composition drift")
    return m["cases"],m
def implied_short_proofs(src,stdout):
    """Full independent check of each new encoded GF2 equality as entailed.
    Reconstruct complete XOR patterns and *original* units; no trusting R155
    annotations or a solver-supplied linear-combination proof.
    """
    text=stdout.decode("utf-8",errors="replace")
    marker=re.findall(r"^c R155_ROUTE augmented_gf2_short consequence_eq=(\d+) added_clauses=(\d+) original_clauses=(\d+) detector_us=(\d+)$",text,re.M)
    derived=re.findall(r"^c R155_DERIVED_EQ rhs=([01]) vars=([0-9,]+)$",text,re.M)
    if not marker:
        need(not derived,"derived equations without augmented route")
        return 0
    need(len(marker)==1 and bool(derived),"missing/duplicate augmented route")
    n,clauses=old.orig.parse_clauses(src)
    groups=collections.defaultdict(set)
    original_eq=[]
    for c in clauses:
        if len(c)==1:
            original_eq.append(((abs(c[0]),),int(c[0]>0)))
        if len(c)<2 or len(c)>6 or len(set(abs(x) for x in c))!=len(c):
            continue
        lits=sorted(c,key=lambda v:abs(v))
        v=tuple(abs(x) for x in lits)
        signmask=sum(1<<i for i,x in enumerate(lits) if x<0)
        groups[v].add(signmask)
    for variables,masks in groups.items():
        k=len(variables)
        even={i for i in range(1<<k) if i.bit_count()%2==0}
        odd={i for i in range(1<<k) if i.bit_count()%2==1}
        if even<=masks:original_eq.append((variables,1))
        if odd<=masks:original_eq.append((variables,0))
    need(bool(original_eq),"no independently certified source XOR equation")
    def bits(vs,rhs):
        val=0
        for v in vs:val^=1<<(v-1)
        return val|((rhs&1)<<n)
    basis={}
    for vs,rhs in original_eq:
        val=bits(vs,rhs)
        while val:
            p=val.bit_length()-1
            if p not in basis:
                basis[p]=val;break
            val^=basis[p]
    total=0
    for rhs_str,vs_str in derived:
        vs=tuple(map(int,vs_str.split(",")));rhs=int(rhs_str)
        need(1<=len(vs)<=4 and tuple(sorted(set(vs)))==vs
             and all(1<=x<=n for x in vs),"invalid derived short parity row")
        val=bits(vs,rhs)
        while val:
            p=val.bit_length()-1
            need(p in basis,"R155 injected XOR consequence NOT implied by source")
            val^=basis[p]
        total+=1<<(len(vs)-1)
    declared=tuple(map(int,marker[0]))
    need(len(derived)<=128 and total<=384,"R155 consequence budgets violated")
    need(declared[0]==len(derived) and declared[1]==total
         and declared[2]==len(clauses),"R155 augmented DIMACS metadata mismatch")
    return len(derived)
def smoke():
    cases()
    need(all(x.is_file() for x in BINS.values()),"binary missing")
    target=ROOT/"selftest";target.mkdir(exist_ok=True)
    samples=[
      ("mixed_sat",b"p cnf 3 5\n1 -2 0\n-1 2 0\n1 0\n-2 3 0\n3 0\n",10,"augmented_gf2_short"),
      ("mixed_unsat",b"p cnf 3 5\n1 -2 0\n-1 2 0\n1 0\n-2 3 0\n-3 0\n",20,"augmented_gf2_short"),
      ("full_xor",b"p cnf 2 2\n1 -2 0\n-1 2 0\n",10,"certified_pure_xor_sat"),
      ("no_xor",b"p cnf 3 2\n1 2 0\n-3 0\n",10,"fallback"),
    ]
    for name,plain,expected,route in samples:
        src=target/(name+".cnf");src.write_bytes(plain)
        p=subprocess.run([str(BINS["r155"].resolve()),str(src.resolve()),str(BINS["kissat"].resolve())],
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        need(p.returncode==expected,"R155 native selftest wrong SAT answer "+
             name+" rc="+str(p.returncode)+" "+p.stderr[-300:].decode(errors="replace"))
        need(route.encode() in p.stdout,"R155 selftest missing requested route "+name)
        if route=="augmented_gf2_short":
            need(implied_short_proofs(src,p.stdout)>0,"R155 short proof not verified")
        if expected==10:
            old.orig.sat_model_check(src,p.stdout)
        elif route=="certified_xor_contradiction":
            old.replay_xor_unsat(src,p.stdout)
        print("R155_SELFTEST_PASS",name,route,flush=True)
    return True
def trial(c,mode,rep):
    src=INPUT/(c["id"]+".cnf")
    need(sha(src)==c["sha256"],"frozen original SHA drift")
    args=[str(BINS[mode].resolve()),str(src.resolve())]
    if mode in ("r155","r153","r28"):args.append(str(BINS["kissat"].resolve()))
    start=time.perf_counter()
    status="TIMEOUT";sec=CAP;route="timeout";proof="timeout";short_eq=0
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
        sec=min(CAP,time.perf_counter()-start)
        need(p.returncode in (10,20),"backend failure: "+mode+" rc="+str(p.returncode)+
             " stderr="+p.stderr[-400:].decode(errors="replace"))
        status="SAT" if p.returncode==10 else "UNSAT"
        output=p.stdout
        if mode=="r155" and b"R155_ROUTE augmented_gf2_short" in output:
            short_eq=implied_short_proofs(src,output)
            need(short_eq>0,"R155 augmented original GF2 proofs missing")
            route="augmented"
        elif mode in ("r155","r153","r28"):
            route=("gf2_sat" if b"R28_ROUTE certified_pure_xor_sat" in output else
                   "gf2_unsat" if b"R28_ROUTE certified_xor_contradiction" in output else
                   "fallback")
        else:route="plain"
        if status=="SAT":
            old.orig.sat_model_check(src,output)
            proof="original_CNF_SAT_witness_verified"
        elif route=="gf2_unsat":
            old.replay_xor_unsat(src,output)
            proof="source_XOR_UNSAT_independently_replayed"
        else:
            proof="UNSAT_no_independent_LRAT"
    except subprocess.TimeoutExpired:
        sec=CAP
    sec=min(CAP,sec)
    return dict(id=c["id"],cohort=c["cohort"],sha256=c["sha256"],
        mode=mode,rep=rep,route=route,status=status,
        seconds=round(sec,6),par2=round(2*CAP if status=="TIMEOUT" else sec,6),
        short_entailed_equations=short_eq,proof=proof)
def run(shard):
    need(0<=shard<SHARDS,"shard outside range")
    cs,m=cases()
    smoke()
    if hasattr(os,"sched_getaffinity"):
        aff=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(aff)})
    cpu=next((line for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines()
              if line.startswith("model name")),"unknown")
    pinned={mode:sha(path) for mode,path in BINS.items()}
    manuscript=sha(INPUT/"manifest.json")
    rows=[]
    for idx,c in enumerate(cs):
        if idx%SHARDS!=shard:continue
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(order)
            answers=set()
            for mode in order:
                row=dict(protocol=PROTO,original_manifest_sha256=manuscript,
                    shard=shard,**trial(c,mode,rep))
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    answers.add(row["status"])
                    need(len(answers)<=1,"SAT/UNSAT contradiction on original SHA "+c["sha256"])
                print("R155_PAIRED",json.dumps(row,sort_keys=True),flush=True)
                write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,
                    original_manifest_sha256=manuscript,cpu=cpu,pins=pinned,rows=rows))
    need(len(rows)==len(cs[shard::SHARDS])*REPS*len(MODES),
         "incomplete paired measurements")
    print("R155_SHARD_PASS",shard,len(rows),flush=True)
def confidence(per,mode,baseline):
    rng=random.Random(15520261105)
    grouped=collections.defaultdict(list)
    for row in per:grouped[row["cohort"]].append(row)
    out=[]
    for _ in range(3000):
        sample=[rng.choice(group) for key,group in sorted(grouped.items()) for i in group]
        d=sum(x[baseline] for x in sample)
        out.append(100*(d-sum(x[mode] for x in sample))/d)
    out.sort()
    return [round(out[74],5),round(out[2924],5)]
def audit():
    cs,m=cases()
    shards=[load(ROOT/f"shard-{i}.json") for i in range(SHARDS)]
    manifest_hash=sha(INPUT/"manifest.json")
    need(all(s["protocol"]==PROTO and
             s["original_manifest_sha256"]==manifest_hash for s in shards),
         "source provenance mismatch")
    need(len(set(json.dumps(s["pins"],sort_keys=True) for s in shards))==1,
         "solver SHA or package changed across shards")
    rows=[r for shard in shards for r in shard["rows"]]
    need(len(rows)==len(cs)*REPS*len(MODES),"incomplete 6-solver matrix")
    indexed={c["sha256"]:c for c in cs}
    seen={}
    for row in rows:
        cc=indexed.get(row["sha256"])
        need(cc and cc["cohort"]==row["cohort"] and cc["id"]==row["id"],
             "wrong original CNF identifier")
        need(row["mode"] in MODES and row["rep"] in (0,1),
             "invalid solver name or repetition")
        need(row["status"] in ("SAT","UNSAT","TIMEOUT"),"bad status")
        need(0<=row["seconds"]<=CAP+1e-5,"invalid runtime")
        need(abs(row["par2"]-(2*CAP if row["status"]=="TIMEOUT" else row["seconds"]))<1e-4,
             "PAR2 penalty wrong")
        if row["status"]=="SAT":
            need(row["proof"]=="original_CNF_SAT_witness_verified","SAT witness invalid")
        if row["route"]=="gf2_unsat":
            need(row["proof"]=="source_XOR_UNSAT_independently_replayed","fake proof")
        if row["route"]=="augmented":
            need(row["mode"]=="r155" and row["short_entailed_equations"]>0,
                 "unsafe XOR route")
        key=(row["sha256"],row["rep"],row["mode"])
        need(key not in seen,"duplicate paired record")
        seen[key]=row
    for c in cs:
        for rep in range(REPS):
            answers={seen[c["sha256"],rep,mode]["status"] for mode in MODES}-{"TIMEOUT"}
            need(len(answers)<=1,"solver answer contradiction")
    sums={}
    for mode in MODES:
        rr=[row for row in rows if row["mode"]==mode]
        time=[r["seconds"] for r in rr if r["status"]!="TIMEOUT"]
        sums[mode]=dict(attempts=len(rr),solved=len(time),
            SAT=sum(r["status"]=="SAT" for r in rr),
            UNSAT_unverified=sum(r["status"]=="UNSAT" and
                                  r["proof"]=="UNSAT_no_independent_LRAT" for r in rr),
            UNSAT_independent_XOR=sum(r["proof"]=="source_XOR_UNSAT_independently_replayed" for r in rr),
            timeouts=len(rr)-len(time),
            PAR2_s=round(sum(r["par2"] for r in rr),6),
            median_solved_s=round(statistics.median(time),6) if time else None)
    grouped=[]
    for c in cs:
        h=c["sha256"]
        bymode={mode:sum(seen[h,rep,mode]["par2"] for rep in range(REPS)) for mode in MODES}
        grouped.append(dict(id=c["id"],cohort=c["cohort"],sha256=h,**bymode,
            r155_entailed_eq=sum(seen[h,rep,"r155"]["short_entailed_equations"] for rep in range(REPS)),
            **{mode+"_solved":sum(seen[h,rep,mode]["status"]!="TIMEOUT" for rep in range(REPS)) for mode in MODES}))
    compar={}
    for mode in MODES:
        if mode=="r155":continue
        compar[mode]=dict(
            r155_PAR2_gain_pct=round(100*(sums[mode]["PAR2_s"]-sums["r155"]["PAR2_s"])/sums[mode]["PAR2_s"],6),
            bootstrap95_pct=confidence(grouped,"r155",mode),
            formula_wins=sum(r["r155"]<r[mode]-1e-5 for r in grouped),
            formula_losses=sum(r["r155"]>r[mode]+1e-5 for r in grouped),
            formula_regressions_2x=sum(r["r155"]>=2*max(.001,r[mode]) for r in grouped))
    bycohort={co:dict(formulas=sum(c["cohort"]==co for c in cs),
        PAR2_s={mode:round(sum(r["par2"] for r in rows if r["cohort"]==co and r["mode"]==mode),6)
                for mode in MODES},
        solved={mode:sum(r["status"]!="TIMEOUT" for r in rows if r["cohort"]==co and r["mode"]==mode)
                for mode in MODES},
        r155_entailed_eq=sum(r["short_entailed_equations"] for r in rows
                             if r["cohort"]==co and r["mode"]=="r155"))
        for co in sorted(set(c["cohort"] for c in cs))}
    report=dict(protocol=PROTO,status="AUDIT_PASS_RESEARCH_ONLY",
        cohort_is_development_not_blind=True,source_run=42107642696,
        formulas=len(cs),trials=len(rows),CAP_s=CAP,repetitions=REPS,
        original_manifest_sha256=manifest_hash,original_SHA_verified=True,
        pinned=shards[0]["pins"],CPU_models=[shard["cpu"] for shard in shards],
        summary=sums,by_cohort=bycohort,comparisons=compar,
        top_formula_regressions=sorted(grouped,key=lambda r:r["r155"]-r["r153"],reverse=True)[:8],
        entailed_equation_trials=sum(r["short_entailed_equations"]>0 for r in rows if r["mode"]=="r155"),
        UNSAT_independent_LRAT_available=False,
        caveats=["Development reuses exposed R154 original CNFs, NOT new blind validation",
                 "R155 augments CNF only with independently verified GF2-implied 1..4-var equations",
                 "SAT model verified against original CNF, GF2 UNSAT reconstructed; other UNSAT lacks LRAT",
                 "Only 4 mixed-residual formulas in reused R154; conclusions may not generalize",
                 "Cost including scanning/injection is in measured elapsed time",
                 "Github shard CPU models can vary; each CNF's solver modes paired within same shard",
                 "No world-ranking or automatic version promotion"])
    write(ROOT/"audit.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        keys=sorted({key for row in rows for key in row})
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
    with (ROOT/"per_formula.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(grouped[0]));w.writeheader();w.writerows(grouped)
    print("R155_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("step",choices=("smoke","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    {"smoke":smoke,"run":lambda:run(a.shard),"audit":audit}[a.step]()
