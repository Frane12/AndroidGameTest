#!/usr/bin/env python3
"""Paired one-CPU R153+LTM7 native integrated and selectively Gaussian-accelerated engine.
R153 is embedded; any fallback runs DRNAS CDCL IN-PROCESS, never Kissat.
Independent R153 original-source XOR/units UNSAT proofs replayed;
mixed formulas solved by native CDCL with proof-only Gaussian reduction.
Every SAT model is checked on the original CNF; remaining UNSAT unverified.
"""
import hashlib,json,os,pathlib,random,re,resource,subprocess,sys,time
sys.path.insert(0,"research")
import drnas_atlas13_generator as A
import drnas_atlas_wide500 as W

ROOT=pathlib.Path("r153_ltm7_gauss_results")
ROOT.mkdir(exist_ok=True)
CAP=7.0
REPS=2
ARMS=("LTM7_NATIVE","R153_LTM7_DIRECT","R153_LTM7_GAUSS","LTM9_NATIVE",
      "Kissat","CaDiCaL","CryptoMiniSat")
BIN={
 "LTM7_NATIVE":"./mre_atlas23/bin/drnas_r153_ltm7",
 "R153_LTM7_DIRECT":"./mre_atlas23/bin/drnas_r153_ltm7",
 "R153_LTM7_GAUSS":"./mre_atlas23/bin/drnas_r153_ltm7",
 "LTM9_NATIVE":"./mre_atlas23/bin/drnas_r153_ltm7",
 "Kissat":"./compiled/kissat",
 "CaDiCaL":"/usr/bin/cadical",
 "CryptoMiniSat":"/usr/bin/cryptominisat5",
}

def parity(variables,rhs):
    clauses=[]
    for bits in range(1<<len(variables)):
        if bits.bit_count()%2!=rhs:
            clauses.append([-x if (bits>>i)&1 else x for i,x in enumerate(variables)])
    return clauses

def extra_xor(kind,idx):
    rng=random.Random(1031991+idx*7537)
    n=56 if "large" not in kind else 76
    planted={v:int(rng.getrandbits(1)) for v in range(1,n+1)}
    clauses=[]
    used=set()
    width=4 if "4" in kind else 3
    for _ in range(n+14):
        support=tuple(sorted(rng.sample(range(1,n+1),width)))
        if support in used:continue
        used.add(support)
        rhs=sum(planted[v] for v in support)%2
        clauses.extend(parity(support,rhs))
    if kind.startswith("unit_xor_sat"):
        for v in (1,2,3,4):clauses.append([v if planted[v] else -v])
    elif kind=="unit_xor_unsat":
        clauses.extend(parity((1,2),0))
        clauses.extend([[1],[-2]])
    elif kind.startswith("xor_conflict"):
        clauses.extend(parity((1,2,3),0))
        clauses.extend(parity((1,2,3),1))
        if kind=="xor_conflict_mixed":
            clauses.extend([[1,-3,5],[-2,7,8],[6,-9,10]])
    elif kind=="pure_xor4_unsat":
        clauses.extend(parity((1,2,3,4),0))
        clauses.extend(parity((1,2,3,4),1))
    return n,clauses

EXTRA=("pure_xor3_sat","pure_xor4_sat","unit_xor_sat","unit_xor_unsat",
       "xor_conflict","xor_conflict_mixed","pure_xor4_unsat","unit_xor_sat_large")

def generate():
    cases=[]
    for fam in A.CATEGORIES:
        n,clauses,_=A.build(fam,72)
        cases.append(("ATLAS13",fam,72,n,clauses))
    for fam in W.SYNTH:
        n,clauses=W.synth_one(fam,22)
        cases.append(("WIDE500",fam,22,n,clauses))
    n,clauses,_=A.build("pigeonhole_unsat",64)
    cases.append(("ATLAS13","pigeonhole_unsat",64,n,clauses))
    for i,fam in enumerate(EXTRA):
        n,clauses=extra_xor(fam,i)
        cases.append(("GF2_FRESH",fam,i,n,clauses))
    assert len(cases)==34
    out=[]
    for origin,family,index,n,clauses in cases:
        raw=W.canonical(n,clauses)
        sha=hashlib.sha256(raw).hexdigest()
        path=ROOT/(sha+".cnf")
        path.write_bytes(raw)
        out.append(dict(origin=origin,family=family,index=index,
                        sha256=sha,vars=n,clauses=clauses,
                        nclauses=len(clauses),path=str(path.resolve())))
    assert len({c["sha256"] for c in out})==len(out)
    return out

def checked_model(c,out):
    model={}
    for line in out.splitlines():
        if not line.startswith("v "):continue
        for item in line.split()[1:]:
            lit=int(item)
            if not lit:continue
            v=abs(lit)
            if v<1 or v>c["vars"] or (v in model and model[v]!=(lit>0)):
                return False
            model[v]=lit>0
    return all(any(model.get(abs(lit))==(lit>0) for lit in cl)
               for cl in c["clauses"])

def verify_gf2_unsat(c,out):
    eq={}
    for m in re.finditer(r"^c R28_EQ id=(\d+) rhs=(\d+) vars=([\d,]+)\s*$",out,re.M):
        idx,rhs,vs=int(m[1]),int(m[2]),tuple(int(t) for t in m[3].split(","))
        if idx in eq or rhs not in (0,1) or len(vs)>6 or not vs or len(set(vs))!=len(vs):
            return False
        if any(v<1 or v>c["vars"] for v in vs):return False
        eq[idx]=(vs,rhs)
    match=re.search(r"^c R28_UNSAT_CERT ids=([\d,]+)\s*$",out,re.M)
    if not match or not eq:return False
    ids=[int(x) for x in match[1].split(",")]
    if not ids or len(set(ids))!=len(ids) or any(i not in eq for i in ids):return False
    original={tuple(sorted(cl)) for cl in c["clauses"]}
    support=set();rhs=0
    for idx in ids:
        vs,p=eq[idx]
        # Independent original-source implication check: every assignment
        # violating the XOR must be blocked by a complete source CNF clause.
        if len(vs)==1:
            if (vs[0] if p else -vs[0],) not in original:return False
        else:
            for bits in range(1<<len(vs)):
                if bits.bit_count()%2==p:continue
                blocking=tuple(sorted(-v if ((bits>>j)&1) else v
                                      for j,v in enumerate(vs)))
                if blocking not in original:return False
        rhs^=p
        for v in vs:
            if v in support:support.remove(v)
            else:support.add(v)
    return not support and rhs==1

def metrics(stdout):
    result={}
    for line in stdout.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            result=dict(x.split("=",1) for x in line.split()[1:] if "=" in x)
    keys=("conflicts","decisions","ltm9_lbd_le2","ltm9_lbd_3to6",
        "ltm9_lbd_ge7","atlas15_deleted","atlas36_effective_quota",
        "gauss_rows","gauss_rank","gauss_units","gauss_binaries","gauss_clauses",
        "gauss_conflict","ltm6_gate","ltm7_gate_off")
    return {k:int(float(result[k])) for k in keys if k in result}

def run(c,arm,rep):
    assert hashlib.sha256(pathlib.Path(c["path"]).read_bytes()).hexdigest()==c["sha256"]
    exe=BIN[arm]
    if arm in ("LTM7_NATIVE","R153_LTM7_DIRECT","R153_LTM7_GAUSS","LTM9_NATIVE"):
        mode={"LTM7_NATIVE":"LTM7_SELECT","LTM9_NATIVE":"LTM8_KEEP50"}.get(arm,arm)
        cmd=[exe,c["path"],"--mode",mode,"--time",str(CAP),
             "--seed",str(rep+1),"--policy","1.0,0.85"]
    else:
        cmd=[exe,c["path"]]
    def limited():
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(int(CAP)+2,int(CAP)+3))
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+.15,
                         preexec_fn=limited)
        rc,out,err=p.returncode,p.stdout,p.stderr
    except subprocess.TimeoutExpired as e:
        rc,out,err=124,e.stdout or "",e.stderr or ""
        if isinstance(out,bytes):out=out.decode("utf-8","replace")
        if isinstance(err,bytes):err=err.decode("utf-8","replace")
    elapsed=min(CAP,time.monotonic()-start)
    gate=("R153_VERIFIED" if "R153_LTM7_GATE route=R153_VERIFIED" in out
          else "CDCL_FALLBACK" if "R153_LTM7_GATE route=CDCL_FALLBACK" in out
          else "NOT_APPLICABLE")
    if arm.startswith("R153_LTM7_") and gate=="NOT_APPLICABLE" and rc in (10,20):
        raise RuntimeError(f"Missing integrated fastpath marker {arm} {c['sha256']}")
    if rc==10:
        if not checked_model(c,out):
            raise RuntimeError(f"INVALID SAT original witness for {arm} {c['sha256']}")
        status="SAT_VERIFIED"
    elif rc==20:
        if gate=="R153_VERIFIED":
            if not verify_gf2_unsat(c,out):
                raise RuntimeError(f"INVALID GF2 source cert: {arm} {c['sha256']}")
            status="UNSAT_GF2_VERIFIED"
        else:
            status="UNSAT_UNVERIFIED"
    elif rc in (0,124,-24,-9,-15):
        status="UNKNOWN"
    else:
        raise RuntimeError(f"Unexpected exit={rc} arm={arm} case={c['sha256']} stderr={err[-400:]}")
    certified=status in ("SAT_VERIFIED","UNSAT_GF2_VERIFIED")
    reported=certified or status=="UNSAT_UNVERIFIED"
    native=arm not in ("Kissat","CaDiCaL","CryptoMiniSat")
    stats=metrics(out) if native else {}
    return dict(arm=arm,origin=c["origin"],family=c["family"],
                index=c["index"],rep=rep,sha256=c["sha256"],
                status=status,e2e_s=round(elapsed,6),
                PAR2_verified_s=round(elapsed if certified else 2*CAP,6),
                PAR2_reported_s=round(elapsed if reported else 2*CAP,6),
                standalone_native=native,
                independent_GF2_UNSAT=bool(status=="UNSAT_GF2_VERIFIED"),
                r153_gate=gate,
                gauss_rows=stats.get("gauss_rows",0),
                gauss_rank=stats.get("gauss_rank",0),
                gauss_derived_clauses=stats.get("gauss_clauses",0),
                stats=stats)

def report(rows):
    total={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        total[arm]=dict(trials=len(subset),
          SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in subset),
          UNSAT_GF2_verified=sum(r["status"]=="UNSAT_GF2_VERIFIED" for r in subset),
          UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in subset),
          r153_fast_solved=sum(r["r153_gate"]=="R153_VERIFIED" for r in subset),\n          gauss_fired=sum(r["gauss_rows"]>0 for r in subset),\n          gauss_clauses=sum(r["gauss_derived_clauses"] for r in subset),
          timeout_unknown=sum(r["status"]=="UNKNOWN" for r in subset),
          PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in subset),6),
          PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in subset),6),
          E2E_s=round(sum(r["e2e_s"] for r in subset),6))
    if any(len([r for r in rows if r["arm"]==a])!=len(rows)//len(ARMS) for a in ARMS):
        raise RuntimeError("Unequal trial counts")
    return total

def main():
    cases=generate()
    manifest=[{k:v for k,v in case.items() if k not in ("clauses","path")}
              for case in cases]
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print("R153_LTM7_MANIFEST "+json.dumps(dict(
        cases=len(cases),reps=REPS,arms=ARMS,
        trials=len(cases)*REPS*len(ARMS),cap_s=CAP,
        source="synthetic_SHA_pinned",one_cpu=True,
        r153_kissat_fallback="ABSENT_NATIVE_IN_PROCESS",
        GF2_UNSAT_independently_verified=True,
        other_UNSAT_independently_verified=False)),flush=True)
    rows=[]
    for c in cases:
        for rep in range(REPS):
            order=ARMS if rep==0 else tuple(reversed(ARMS))
            statuses=set()
            for arm in order:
                row=run(c,arm,rep);rows.append(row);statuses.add(row["status"])
                print("R153_LTM7_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
                (ROOT/"results.json").write_text(json.dumps(rows,indent=2))
            if "SAT_VERIFIED" in statuses and (
                "UNSAT_GF2_VERIFIED" in statuses or "UNSAT_UNVERIFIED" in statuses):
                raise RuntimeError("CONTRADICTORY SAT and UNSAT on original source")
    summary=report(rows)
    print("R153_LTM7_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
    groups={}
    for origin in sorted(set(c["origin"] for c in cases)):
        sub=[r for r in rows if r["origin"]==origin]
        groups[origin]=report(sub)
    print("R153_LTM7_GROUPS "+json.dumps(groups,sort_keys=True),flush=True)
    (ROOT/"summary.json").write_text(json.dumps(dict(total=summary,groups=groups),indent=2))
    print("R153_LTM7_AUDIT original_sha=true model_verified=true "
          "r153_in_process_cdcl_only=true r153_unit_XOR_proof_replayed=true "
          "selective_Gaussian_source_certified=true single_cpu=true "
          "paired=true synthetic=true unverified_UNSAT_separate=true",flush=True)
if __name__=="__main__":
    main()
