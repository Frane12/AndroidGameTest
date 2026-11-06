#!/usr/bin/env python3
"""R186 selective diverse SAT: 5 s paired, frozen-source, 3 arms, no outcome selection.
Known R182 synthetic reference-calibrated and R183 reused real sources are
separate cohorts; NEW deterministic synthetic families are not external/blind.
SAT original models checked; XOR contradictions/units traced to source CNF.
CaDiCaL UNSAT outside certified GF2 contradictions lacks independent LRAT.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,pathlib,random,statistics,subprocess,time
import r183_external_mixed as ext
import r182_mixed_engine as gf2
ROOT=pathlib.Path("r186")
FROZEN=ROOT/"frozen"
MODES=("clean","gf2_gate","r186_selective")
R186_PROTO="DRNAS-R186-SOURCE-ONLY-CHEAP-XOR-SCREEN-v1"
PROTO="DRNAS-R185-SHORT-DIVERSE-SOURCE-FROZEN-v1"
CAP=5.0
REPS=2
SHARDS=8
FAMILIES=("mixed_xor_unsat","mixed_xor_sat","planted_3sat","pigeonhole_unsat",
          "graph_3color_sat","graph_3color_unsat","two_sat_unsat","horn_sat")
SEED=185061106

def need(x,msg):
    if not x:raise RuntimeError("R185_FAIL_CLOSED "+msg)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def get(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):gf2.save(p,obj)

def generated(family,i):
    rnd=random.Random(SEED+1009*FAMILIES.index(family)+i*97)
    n=40+2*i; clauses=[]; expected="SAT"
    witness=[False]+[bool(rnd.getrandbits(1)) for _ in range(n)]
    def xor(vs,rhs):
        for bits in itertools.product((0,1),repeat=3):
            if (bits[0]^bits[1]^bits[2])!=rhs:
                clauses.append(tuple(v if bit==0 else -v for v,bit in zip(vs,bits)))
    def residual(count):
        for _ in range(count):
            vs=rnd.sample(range(1,n+1),3)
            cl=[v if rnd.getrandbits(1) else -v for v in vs]
            if not any((v>0)==witness[abs(v)] for v in cl):
                k=rnd.randrange(3);v=vs[k];cl[k]=v if witness[v] else -v
            clauses.append(tuple(cl))
    if family.startswith("mixed_xor_"):
        seen=set()
        for _ in range(12):
            while True:
                vs=tuple(sorted(rnd.sample(range(1,n//2+1),3)))
                if vs not in seen:seen.add(vs);break
            rhs=sum(witness[v] for v in vs)%2
            xor(vs,rhs)
            if len(seen)==1 and family=="mixed_xor_unsat":
                xor(vs,1-rhs)
        residual(3*n)
        if family=="mixed_xor_unsat":expected="UNSAT"
    elif family=="planted_3sat":
        residual(5*n)
    elif family=="pigeonhole_unsat":
        p=5+i%4;h=p-1;n=p*h;expected="UNSAT"
        var=lambda a,b:a*h+b+1
        for a in range(p):
            clauses.append(tuple(var(a,b) for b in range(h)))
        for b in range(h):
            for a in range(p):
                for c in range(a+1,p):
                    clauses.append((-var(a,b),-var(c,b)))
    elif family.startswith("graph_3color_"):
        v=12+i;n=3*v;var=lambda a,c:3*a+c+1
        colors=[rnd.randrange(3) for _ in range(v)]
        edges=set()
        if family=="graph_3color_unsat":
            expected="UNSAT"
            for a in range(4):
                for b in range(a+1,4):edges.add((a,b))
        for _ in range(v*5):
            a,b=sorted(rnd.sample(range(v),2))
            if family=="graph_3color_unsat" or colors[a]!=colors[b]:
                edges.add((a,b))
        for a in range(v):
            clauses.append(tuple(var(a,c) for c in range(3)))
            for c in range(3):
                for d in range(c+1,3):
                    clauses.append((-var(a,c),-var(a,d)))
        for a,b in sorted(edges):
            for c in range(3):
                clauses.append((-var(a,c),-var(b,c)))
    elif family=="two_sat_unsat":
        expected="UNSAT"
        clauses.extend(((1,2),(1,-2),(-1,3),(-1,-3)))
        for _ in range(n*3):
            a,b=rnd.sample(range(4,n+1),2)
            clauses.append((a if rnd.getrandbits(1) else -a,
                            b if rnd.getrandbits(1) else -b))
    elif family=="horn_sat":
        clauses.append((1,))
        for a in range(1,n):
            clauses.append((-a,a+1))
        for _ in range(n*2):
            a,b=rnd.sample(range(1,n+1),2)
            clauses.append((-a,b))
    else:raise RuntimeError("unknown family")
    clauses=list(dict.fromkeys(clauses))
    return n,clauses,expected

def freeze():
    FROZEN.mkdir(parents=True,exist_ok=True)
    r182=get("r179/r179-selected-freeze.json")
    known=r182["selected"]
    need(len(known)==53,"R182 frozen count mismatch")
    external=get(ROOT/"external/frozen/manifest.json")
    need(external["protocol"]=="DRNAS-R183-EXTERNAL-SHA-FROZEN-MIXED-v1","external original protocol drift")
    need(sha(ROOT/"external/frozen/manifest.json")==
         "102c8bdef78163aad8e08ab044c0ff7a123df4d67b0a714c50370b13447543c4",
         "R183 external manifest SHA mismatch")
    need(len(external["cases"])==12,"R183 original count drift")
    cases=[]
    for c in known:
        src=pathlib.Path("r179/frozen")/(c["id"]+".cnf")
        need(sha(src)==c["sha256"],"R182 source SHA drift")
        dst=FROZEN/("known-"+c["id"]+".cnf");dst.write_bytes(src.read_bytes())
        cases.append(dict(id="known-"+c["id"],family="known_r182_calibrated",
                          origin="known_generated_reference_calibrated",
                          expected=c["class"],sha256=sha(dst),original_sha=c["sha256"],
                          reused_split=c["split"]))
    for c in external["cases"]:
        src=ROOT/"external/frozen"/(c["id"]+".cnf")
        need(sha(src)==c["sha256"],"R183 external SHA drift")
        dst=FROZEN/("external-"+c["id"]+".cnf");dst.write_bytes(src.read_bytes())
        cases.append(dict(id="external-"+c["id"],family="external_"+c["cohort"],
                          origin="known_external_reused",expected="UNKNOWN",
                          sha256=sha(dst),original_sha=c["sha256"]))
    for family in FAMILIES:
        for i in range(8):
            n,clauses,truth=generated(family,i)
            raw=("c R185 precommitted deterministic generated family="+family+" index="+str(i)+"\n"+
                 f"p cnf {n} {len(clauses)}\n"+
                 "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses)).encode()
            id="new-"+family+"-"+str(i)
            dst=FROZEN/(id+".cnf");dst.write_bytes(raw)
            cases.append(dict(id=id,family=family,origin="new_synthetic",
                              expected=truth,sha256=sha(dst)))
    need(len(cases)==129 and len({x["sha256"] for x in cases})==129,
         "frozen count or unique SHA wrong")
    random.Random(PROTO).shuffle(cases)
    pin=get(ROOT/"external/build-pin.json")
    need(sha(ROOT/"external/r182-driver")==pin["binary_sha256"],"R183 binary drift")
    binary=ROOT/"r186-driver"
    binary.write_bytes((ROOT/"external/r182-driver").read_bytes())
    save(ROOT/"pin.json",dict(binary_sha256=sha(binary),
       original_external_manifest_sha256=sha(ROOT/"external/frozen/manifest.json"),
       original_r182_selected_sha256=sha("r179/r179-selected-freeze.json"),
       pinned_cadical=pin["cadical_commit"],source_count=129))
    save(ROOT/"manifest.json",dict(protocol=PROTO,cases=cases,cap_s=CAP,reps=REPS,
       synthetic_new=64,known_generated=53,reused_external=12,
       selected_by_solver_runtime=False,not_globally_blind=True,
       sha_original_preserved=True))
    verify()
    print("R186_FREEZE_PASS",json.dumps({"cases":len(cases),"new_synthetic":64,
         "known_generated":53,"known_external":12,"manifest_sha":sha(ROOT/"manifest.json")},
         sort_keys=True),flush=True)

def verify():
    m=get(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==129,"manifest drift")
    need(sha(ROOT/"r186-driver")==get(ROOT/"pin.json")["binary_sha256"],
         "binary SHA drift")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"source SHA drift "+c["id"])
    return m["cases"]


def cheap_gate(path):
    """Precommitted low-cost structural gate; never reads outcomes or source IDs.
    A small/trivially-easy CNF abstains; larger CNFs qualify only after at
    least two independent complete 4-clause XOR3 quartets in first 2048 clauses.
    A false negative costs performance only, never SAT correctness.
    """
    start=time.perf_counter()
    with open(path,encoding="ascii") as f:
        for line in f:
            if line.startswith("p cnf "):
                fields=line.split()
                need(len(fields)==4,"bad DIMACS header")
                n,m=int(fields[2]),int(fields[3])
                break
        else:raise RuntimeError("R186 source header absent")
        if n<55 or m<400:
            return False,"small_source",time.perf_counter()-start
        groups=collections.defaultdict(set)
        eligible=0
        scanned=0
        for line in f:
            line=line.strip()
            if not line or line.startswith("c"):continue
            scanned+=1
            if scanned>2048:break
            parts=line.split()
            if len(parts)!=4 or parts[-1]!="0":continue
            try:cl=[int(z) for z in parts[:3]]
            except ValueError:continue
            vs=tuple(sorted(abs(z) for z in cl))
            if len(set(vs))!=3:continue
            ordered=sorted(cl,key=lambda z:abs(z))
            mask=sum(1<<k for k,z in enumerate(ordered) if z<0)
            masks=groups[vs]
            if mask in masks:continue
            masks.add(mask)
            if len(masks)==4:
                # Exactly one parity half must be present, not four arbitrary signs.
                if all((x.bit_count()&1)==(mask.bit_count()&1) for x in masks):
                    eligible+=1
                    if eligible>=2:
                        return True,"two_certifiable_xor3_quartets",time.perf_counter()-start
        return False,"no_early_two_complete_xor3",time.perf_counter()-start

def trial(c,mode,rep,binary):
    path=FROZEN/(c["id"]+".cnf")
    need(sha(path)==c["sha256"],"trial source drift")
    if mode=="r186_selective":
        selected,reason,screen_s=cheap_gate(path)
        chosen="gf2_gate" if selected else "clean"
        r=trial(c,chosen,rep,binary)
        measured=r["elapsed_s"]+screen_s
        r.update(mode=mode,route=chosen,screen_selected=selected,
                 screen_reason=reason,screen_s=round(screen_s,6),
                 elapsed_s=round(measured,6),
                 status=("TIMEOUT" if measured>CAP else r["status"]))
        if r["status"]=="TIMEOUT":r["proof"]="CAP_REACHED"
        r["par2_s"]=round(2*CAP if r["status"]=="TIMEOUT" else measured,6)
        return r
    start=time.perf_counter()
    proof="NO_INDEPENDENT_UNSAT_LRAT";analysis=0.0
    row_count=0;unit_count=0;residual=0;conflict=False;status="TIMEOUT";model={}
    if mode!="clean":
        st=time.perf_counter()
        n,clauses,rows,gauss,info=ext.source_info(path,full=True)
        analysis=time.perf_counter()-st
        row_count=len(rows);unit_count=len(gauss["units"])
        residual=info["residual_clauses"];conflict=gauss["conflict"]
        if conflict:
            gf2.check_trace(rows,0,1,gauss["conflict_trace"])
            status="UNSAT";proof="SOURCE_CERTIFIED_GF2_CONTRADICTION"
        else:
            inp=path
            if mode=="gf2_units" and gauss["units"]:
                units=[v if rhs else -v for v,(rhs,trace) in sorted(gauss["units"].items())]
                for v,(rhs,trace) in gauss["units"].items():
                    gf2.check_trace(rows,1<<(v-1),rhs,trace)
                inp=ROOT/"derived"/(c["id"]+"-"+str(rep)+".cnf")
                inp.parent.mkdir(exist_ok=True)
                inp.write_text(f"p cnf {n} {len(clauses)+len(units)}\n"+
                    "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses)+
                    "".join(str(v)+" 0\n" for v in units))
            remaining=CAP-(time.perf_counter()-start)
            if remaining>0.12:
                status,_,model=ext.native(binary,inp,remaining)
    else:
        status,_,model=ext.native(binary,path,CAP)
    elapsed=time.perf_counter()-start
    if elapsed>CAP:status="TIMEOUT";proof="CAP_REACHED"
    if status=="SAT":
        _,orig=gf2.dimacs(path)
        gf2.sat_check(orig,model)
        proof="ORIGINAL_SAT_WITNESS_CHECKED"
    if c["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==c["expected"],"source truth discrepancy "+c["id"]+" "+mode)
    return dict(id=c["id"],sha256=c["sha256"],family=c["family"],
       origin=c["origin"],expected=c["expected"],mode=mode,repeat=rep,
       status=status,elapsed_s=round(elapsed,6),par2_s=round(2*CAP if status=="TIMEOUT" else elapsed,6),
       proof=proof,analysis_s=round(analysis,6),xor_rows=row_count,
       derived_units=unit_count,residual_clauses=residual,gf2_conflict=conflict)

def shard(idx,binary):
    cases=verify();need(0<=idx<SHARDS,"bad shard")
    out=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(R186_PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                rec=trial(c,mode,rep,binary);out.append(rec)
                save(ROOT/f"shard-{idx}.json",out)
                print("R186_TRIAL",json.dumps({k:rec[k] for k in (
                    "id","family","mode","repeat","status","elapsed_s","analysis_s",
                    "xor_rows","derived_units","gf2_conflict")}),flush=True)
    need(len(out)==len(cases[idx::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("R186_SHARD_PASS",idx,len(out),flush=True)

def audit():
    cases=verify();rows=[];seen=set()
    for i in range(SHARDS):
        shardrows=get(ROOT/f"shard-{i}.json")
        need(len(shardrows)==len(cases[i::SHARDS])*REPS*len(MODES),"shard incomplete")
        for r in shardrows:
            k=(r["sha256"],r["mode"],r["repeat"])
            need(k not in seen,"duplicated paired trial");seen.add(k);rows.append(r)
    need(len(rows)==129*REPS*len(MODES)==774,"expected 774 pairs")
    by_id={c["id"]:c for c in cases}
    for r in rows:
        need(r["sha256"]==by_id[r["id"]]["sha256"],"source SHA trial mismatch")
        need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"]))<1e-4,
             "PAR2 error")
    for c in cases:
        for rep in range(REPS):
            a=[r for r in rows if r["id"]==c["id"] and r["repeat"]==rep]
            need(len(a)==len(MODES) and {r["mode"] for r in a}==set(MODES),
                 "paired modes missing")
            truth={r["status"] for r in a if r["status"]!="TIMEOUT"}
            need(len(truth)<=1,"contradictory SAT/UNSAT answers")
    groups={"all":cases}
    for family in sorted(set(x["family"] for x in cases)):
        groups[family]=[c for c in cases if c["family"]==family]
    for origin in sorted(set(x["origin"] for x in cases)):
        groups["origin:"+origin]=[c for c in cases if c["origin"]==origin]
    stats={}
    for family,group in groups.items():
        d={}
        ids={c["id"] for c in group}
        for mode in MODES:
            rr=[r for r in rows if r["id"] in ids and r["mode"]==mode]
            d[mode]=dict(attempts=len(rr),solved=sum(r["status"]!="TIMEOUT" for r in rr),
               SAT=sum(r["status"]=="SAT" for r in rr),
               UNSAT=sum(r["status"]=="UNSAT" for r in rr),
               par2_s=round(sum(r["par2_s"] for r in rr),6),
               analysis_s=round(sum(r["analysis_s"] for r in rr),6),
               certified_conflicts=sum(r["proof"]=="SOURCE_CERTIFIED_GF2_CONTRADICTION" for r in rr))
        stats[family]=dict(formulas=len(group),modes=d,
          clean_to_gate_x=round(d["clean"]["par2_s"]/d["gf2_gate"]["par2_s"],5),
          clean_to_selective_x=round(d["clean"]["par2_s"]/d["r186_selective"]["par2_s"],5))
    proof=collections.Counter(r["proof"] for r in rows)
    report=dict(status="R186_PAIRED_AUDIT_PASS",protocol=PROTO,
       formulas=len(cases),attempts=len(rows),cap_s=CAP,repetitions=REPS,
       source_sha_verified=True,sat_witness_original_verified=True,
       gf2_source_traces_verified=True,independent_cdcl_unsat_LRAT=False,
       external_sources_reused_not_blind=True,new_synthetic_not_industrial=True,
       known_calibrated_results_separate=True,groups=stats,proof_counts=dict(proof))
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R186 cheap-source selective diverse 5-second paired benchmark\n\n")
        f.write("Same frozen R185 sources, 3 arms, 2 repeats, 774 trials. 64 generated + 53 known calibrated + 12 reused external. NOT blind external.\n\n")
        f.write("| Family | N | CaDiCaL solved | GF2 gate solved | R186 solved | Clean PAR2 | Gate PAR2 | R186 PAR2 | Speedup R186 |\n|---|---:|---:|---:|---:|---:|---:|\n")
        for family,s in stats.items():
            a=s["modes"]
            f.write(f'| {family} | {s["formulas"]} | {a["clean"]["solved"]} | {a["gf2_gate"]["solved"]} | {a["r186_selective"]["solved"]} | {a["clean"]["par2_s"]} | {a["gf2_gate"]["par2_s"]} | {a["r186_selective"]["par2_s"]} | {s["clean_to_selective_x"]}x |\n')
        f.write("\nCaDiCaL UNSAT without independent LRAT; no general SAT/world record claim.\n")
    print("R186_FINAL",json.dumps({k:report[k] for k in (
       "formulas","attempts","status","groups","proof_counts")},sort_keys=True),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for family in FAMILIES:
            n,clauses,status=generated(family,0)
            f=pathlib.Path(td)/(family+".cnf")
            f.write_text(f"p cnf {n} {len(clauses)}\n"+
                "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses))
            parsed=gf2.dimacs(f);need(parsed==(n,clauses),"DIMACS generation mismatch")
            if family=="mixed_xor_unsat":
                _,_,rows,g,features=ext.source_info(f,full=True)
                need(g["conflict"] and features["residual_clauses"]>0,
                     "XOR mixed UNSAT certified contradiction missing")
                gf2.check_trace(rows,0,1,g["conflict_trace"])
            if status=="SAT" and family in ("mixed_xor_sat","planted_3sat"):
                # Generator's construction guarantees a planted model.
                pass
    # Heuristics may abstain for any source, but SAT correctness must not change.
    with tempfile.TemporaryDirectory() as td:
        for family in FAMILIES:
            n,clauses,_=generated(family,0)
            f=pathlib.Path(td)/(family+".cnf")
            f.write_text(f"p cnf {n} {len(clauses)}\n"+
                "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses))
            selected,_,_=cheap_gate(f)
            need(not selected,"small generated source unexpectedly selected: "+family)
    print("R186_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r185/r185-driver")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":print("R186_VERIFY_PASS",len(verify()),flush=True)
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
