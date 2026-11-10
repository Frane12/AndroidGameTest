#!/usr/bin/env python3
"""DRNAS GF2-S1: exact CNF XOR proof-first, independently checked original CNF;
6 matched arms / 17 previously seen SHA / 2 reps / 8 s / one logical CPU.
No blind claim; algebraic proof is NOT LRAT and will be labelled separately.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,os,pathlib,random,subprocess,tempfile,time
import drnas_binary_scc2_e2e as s2
import drnas_equiv9_prospective_seed_holdout as e9

ROOT=pathlib.Path("mre_gf2_s1")
BIN=ROOT/"bin/gf2_exact"
PROTO="DRNAS-GF2-PROOF-FIRST-S1-17SHA-6ARM-2REP-8S-ONECPU-v1"
ARMS=("native_orig","native_probe","native_gf2","kissat_orig","kissat_probe","kissat_gf2")
CAP=8.0
REPS=2
SHARDS=6
NCASE=17
EXPECTED=NCASE*REPS*len(ARMS)
KNOWN_CERT_SHA="327bfcaa1933d1c2b293f90f5761bfb25448c577d4a6958b962d4a09a1c88b7a"

def need(ok,msg):
    if not ok:raise RuntimeError("GF2_S1_FAIL_CLOSED "+str(msg))
def save(path,o):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(o,sort_keys=True,indent=2)+"\n")
def cases():
    cs=s2.cases()
    need(len(cs)==NCASE and len({c["sha256"] for c in cs})==NCASE,
         "source roster drift")
    return cs

def original_path(case):
    p=e9.SOURCE/case["filename"]
    need(e9.digest(p)==case["sha256"],"source SHA mismatch")
    return p

def xor_equations_from_original(src):
    """Independent reconstruction from original clause literals, not C++ output.
    A complete parity encoding is an exact set of 2^(k-1) clauses for 2<=k<=4.
    Only those groups imply the XOR equation; unrelated CNF is untouched.
    """
    n,clauses=e9.x22.read_cnf(src)
    signatures=collections.defaultdict(set)
    for clause in clauses:
        if not 2<=len(clause)<=4:continue
        key=tuple(sorted(abs(x) for x in clause))
        if len(set(key))!=len(key):continue
        negative={abs(x) for x in clause if x<0}
        mask=sum(1<<i for i,v in enumerate(key) if v in negative)
        signatures[key].add(mask)
    eq=[]
    for key,seen in signatures.items():
        for parity in (0,1):
            required={m for m in range(1<<len(key)) if m.bit_count()%2==parity}
            if required<=seen:eq.append((key,1-parity))
    eq.sort()
    return n,len(clauses),eq

def verify_algebraic_certificate(src,record):
    need(record["xor_unsat"] and not record["abstained"],"no proof")
    n,k,eqs=xor_equations_from_original(src)
    need(record["vars"]==n and record["clauses"]==k and
         record["xor_equations"]==len(eqs),"equation count disagreement")
    ids=record["certificate_ids"]
    need(len(ids)>=1 and len(ids)<=len(eqs) and
         len(ids)==len(set(ids)) and all(type(i) is int and 0<=i<len(eqs) for i in ids),
         "illegal linear proof indices")
    acc=set();parity=0
    for i in ids:
        key,rhs=eqs[i]
        for v in key:
            if v in acc:acc.remove(v)
            else:acc.add(v)
        parity^=rhs
    need(not acc and parity==1,"linear proof does NOT yield 0=1")
    return dict(equations=len(eqs),terms=len(ids),remainder_vars=0,rhs_parity=1,
                verifier="independent_original_DIMACS_pattern_and_GF2_replay",
                original_SHA256=e9.digest(src),NOT_LRAT=True)

def scan(src):
    t=time.perf_counter()
    try:
        r=subprocess.run([str(BIN.resolve()),str(src.resolve())],
                         capture_output=True,text=True,timeout=1.5)
    except subprocess.TimeoutExpired:
        return dict(proved=False,abstained=True,probe_wall_s=round(time.perf_counter()-t,6),
                    reason="bounded_probe_timeout",proof=None,equations=0)
    if r.returncode!=0:
        return dict(proved=False,abstained=True,probe_wall_s=round(time.perf_counter()-t,6),
                    reason="safe_parser_abstention",proof=None,equations=0)
    lines=[line[len("GF2_S1_RESULT "):] for line in r.stdout.splitlines()
           if line.startswith("GF2_S1_RESULT ")]
    need(len(lines)==1,"C++ scanner result absent")
    record=json.loads(lines[0])
    proof=None
    if record["xor_unsat"]:
        proof=verify_algebraic_certificate(src,record)
    return dict(proved=proof is not None,abstained=record["abstained"],
                probe_wall_s=round(time.perf_counter()-t,6),
                reason="independent_GF2_proof" if proof else "no_exact_contradiction",
                proof=proof,equations=record["xor_equations"],
                scan_native_ms=record["scan_ms"])

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    cs=cases();need(BIN.is_file(),"C++ binary absent")
    for c in cs:original_path(c)
    m=dict(protocol=PROTO,cases=cs,arms=list(ARMS),cap_s=CAP,
           reps=REPS,shards=SHARDS,expected=EXPECTED,
           previously_observed_not_blind=True,no_auto_promotion=True,
           no_parallel_children=True,one_logical_CPU=True,
           original_CNFs_untouched=True,algebraic_proof_independently_verified=True,
           algebraic_proof_is_not_LRAT=True,
           predecessor_manifest_sha=e9.digest(s2.ROOT/"manifest.json"),
           binary_sha=e9.digest(BIN),
           native_sha=e9.digest(e9.NATIVE),kissat_sha=e9.digest(e9.KISSAT),
           script_sha=e9.digest(__file__),
           source_cpp_sha=e9.digest("research/drnas_gf2_proof_first_s1.cpp"))
    save(ROOT/"manifest.json",m);verify()
    print("GF2_S1_FROZEN "+json.dumps(dict(sha=NCASE,arms=len(ARMS),
        trials=EXPECTED,one_cpu=True,not_blind=True),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and m["cap_s"]==CAP and
         m["reps"]==REPS and m["shards"]==SHARDS and
         m["expected"]==EXPECTED and m["cases"]==cases(),"manifest drift")
    need(m["binary_sha"]==e9.digest(BIN) and
         m["script_sha"]==e9.digest(__file__) and
         m["source_cpp_sha"]==e9.digest("research/drnas_gf2_proof_first_s1.cpp") and
         m["native_sha"]==e9.digest(e9.NATIVE) and
         m["kissat_sha"]==e9.digest(e9.KISSAT) and
         m["predecessor_manifest_sha"]==e9.digest(s2.ROOT/"manifest.json"),
         "code/binary manifest mismatch")
    for c in m["cases"]:original_path(c)
    return m

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(BIN.is_file(),"native GF2 binary missing")
    with tempfile.TemporaryDirectory() as d:
        src=pathlib.Path(d)/"toy.cnf"
        # Two contradictory, complete XOR encodings have a proof on the original.
        for k in (2,3,4):
            clauses=[]
            for parity in (0,1):
                for mask in range(1<<k):
                    if mask.bit_count()%2==parity:
                        clauses.append([(-i-1 if mask&(1<<i) else i+1)
                                        for i in range(k)])
            src.write_text(f"p cnf {k} {len(clauses)}\n"+
                           "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            s=scan(src);need(s["proved"],"complete parity contradiction missed")
            # Drop one clause and brute-force verify that incomplete families
            # never result in a false-positive algebraic certificate.
            clauses.pop()
            src.write_text(f"p cnf {k} {len(clauses)}\n"+
                           "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            t=scan(src)
            for bits in itertools.product((0,1),repeat=k):
                if all(any((bits[abs(l)-1]==(l>0)) for l in c) for c in clauses):
                    need(not t["proved"],"reported UNSAT on SAT toy")
        source=next(c for c in cases() if c["sha256"]==KNOWN_CERT_SHA)
        p=original_path(source)
        result=scan(p)
        need(result["proved"] and result["proof"]["terms"]==196,
             "known original source full GF2 proof failed")
    print("GF2_S1_SELFTEST_PASS "+json.dumps(dict(
       complete_xor_parity_toys=3,incomplete_source_SAT_negative_controls=3,
       original_known_SHA_certificate_checked=True,
       certificate_terms=196,all_proofs_independently_replayed=True),
       sort_keys=True),flush=True)

def trial(case,rep,arm):
    need(arm in ARMS and rep in (0,1),"bad key")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    t=time.perf_counter();cpu_before=time.process_time();child_before=e9.x22.child_cpu()
    src=original_path(case)
    backend,mode=arm.split("_",1)
    probe=None
    if mode!="orig":
        probe=scan(src)
    certified=bool(probe and probe["proved"])
    status="TIMEOUT";witness=False;backend_status=None;used=False
    if certified and mode=="gf2":
        status="UNSAT"
    else:
        left=CAP-(time.perf_counter()-t)
        if left>0.09:
            used=True
            if backend=="native":
                r=e9.trial(case,rep,"native1",cap=left)
                status=r["status"];witness=r["SAT_original_witness_verified"]
            else:
                r=s2.trial(case,rep,"kissat_orig",cap=left)
                status=r["status"];witness=r["SAT_original_witness_verified"]
            backend_status=status
    wall=time.perf_counter()-t
    if wall>=CAP:status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"original SAT model not verified")
    need(e9.digest(src)==case["sha256"],"original CNF mutated")
    return dict(protocol=PROTO,sha256=case["sha256"],gbd=case["gbd"],
      arm=arm,rep=rep,cap_s=CAP,one_logical_cpu=cpu,
      original_SHA_checked=True,original_source_unchanged=True,
      one_solver_child_max=True,
      status=status,SAT_original_witness_verified=bool(witness if status=="SAT" else False),
      UNSAT_original_GF2_certificate_verified=bool(certified),
      UNSAT_independent_LRAT=False,certificate_terms=probe["proof"]["terms"] if certified else 0,
      xor_equations=probe["equations"] if probe else None,
      probe_E2E_s=probe["probe_wall_s"] if probe else 0,
      gate_reason=probe["reason"] if probe else "original_no_scan",
      backend_called=used,backend_status=backend_status,
      wall_E2E_s=round(wall,6),
      child_CPU_s=round(e9.x22.child_cpu()-child_before,6),
      parent_CPU_s=round(time.process_time()-cpu_before,6))

def shard(idx):
    need(idx in range(SHARDS),"bad shard")
    m=verify();cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx]
    rows=[]
    for c in cs:
        for rep in range(REPS):
            arms=list(ARMS);random.Random(c["sha256"]+str(rep)+"GF2S1").shuffle(arms)
            for a in arms:
                row=trial(c,rep,a);row["shard"]=idx
                need(row["wall_E2E_s"]<=CAP+.2,"cap overrun")
                rows.append(row)
                save(ROOT/f"shard-{idx}.json",rows)
                print("GF2_S1_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cs)*REPS*len(ARMS),"incomplete shard")
    print(f"GF2_S1_SHARD_PASS {idx} {len(rows)}",flush=True)

def audit():
    m=verify();rows=[]
    for idx in range(SHARDS):
        data=json.loads((ROOT/f"shard-{idx}.json").read_text())
        expected=len([c for i,c in enumerate(m["cases"]) if i%SHARDS==idx])*REPS*len(ARMS)
        need(len(data)==expected,"missing shard")
        rows.extend(data)
    expect={(c["sha256"],rep,a) for c in m["cases"] for rep in range(REPS) for a in ARMS}
    seen={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(seen)==len(expect) and seen==expect,"bad pairing")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["original_SHA_checked"] and
             r["original_source_unchanged"] and r["one_solver_child_max"] and
             r["cap_s"]==CAP and r["wall_E2E_s"]<=CAP+.2 and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]), "bad trial row")
        bysha[r["sha256"]].append(r)
    proof_shas={sha for sha,rr in bysha.items()
                if any(x["UNSAT_original_GF2_certificate_verified"] for x in rr)}
    agreed={sha for sha,rr in bysha.items()
            if any(x["arm"]=="native_orig" and x["status"]=="UNSAT" for x in rr)
            and any(x["arm"]=="kissat_orig" and x["status"]=="UNSAT" for x in rr)}
    for sha,rr in bysha.items():
        need(len({x["status"] for x in rr if x["status"]!="TIMEOUT"})<=1,
             "SAT/UNSAT disagreement on original SHA")
    def ok(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and
                                     r["sha256"] in (proof_shas|agreed))
    def par(r):return r["wall_E2E_s"] if ok(r) else 2*CAP
    def score(rs):
        return dict(attempts=len(rs),solved=sum(ok(x) for x in rs),
          SAT_verified=sum(x["status"]=="SAT" for x in rs),
          UNSAT_math_verified=sum(x["status"]=="UNSAT" and x["sha256"] in proof_shas for x in rs),
          UNSAT_reference_agreed_no_LRAT=sum(x["status"]=="UNSAT" and x["sha256"] in agreed-proof_shas for x in rs),
          UNSAT_unverified=sum(x["status"]=="UNSAT" and not ok(x) for x in rs),
          timeouts=sum(x["status"]=="TIMEOUT" for x in rs),
          PAR2_s=round(sum(par(x) for x in rs),6),
          actual_wall_s=round(sum(x["wall_E2E_s"] for x in rs),6),
          actual_CPU_s=round(sum(x["child_CPU_s"]+x["parent_CPU_s"] for x in rs),6),
          probe_E2E_s=round(sum(x["probe_E2E_s"] for x in rs),6))
    scores={a:score([x for x in rows if x["arm"]==a]) for a in ARMS}
    for backend in ("native","kissat"):
        b=scores[backend+"_orig"]["PAR2_s"]
        for mode in ("orig","probe","gf2"):
            scores[backend+"_"+mode]["PAR2_speedup_vs_original_x"]=round(
                b/scores[backend+"_"+mode]["PAR2_s"],6)
    bypair={}
    for backend in ("native","kissat"):
        for mode in ("probe","gf2"):
            dif=[]
            for sha,rr in bysha.items():
                for rep in range(REPS):
                    a=next(x for x in rr if x["arm"]==backend+"_"+mode and x["rep"]==rep)
                    b=next(x for x in rr if x["arm"]==backend+"_orig" and x["rep"]==rep)
                    dif.append(par(a)-par(b))
            bypair[backend+"_"+mode]=dict(wins=sum(v<-.02 for v in dif),
                losses=sum(v>.02 for v in dif),ties=sum(abs(v)<=.02 for v in dif),
                net_PAR2_benefit_s=round(-sum(dif),6),
                biggest_gain_s=round(min(dif),6),
                biggest_regression_s=round(max(dif),6))
    report=dict(protocol=PROTO,sources=len(m["cases"]),trials=EXPECTED,
      no_auto_promotion=True,not_blind=True,
      original_CNFs_SHA_locked=True,one_logical_CPU_per_solver=True,
      no_parallel_solver_children=True,GF2_algebraic_proof_not_LRAT=True,
      no_independent_LRAT_for_non_GF2_UNSAT=True,
      math_certified_source_SHA=sorted(proof_shas),other_reference_agreement=sorted(agreed-proof_shas),
      scores=scores,paired=bypair,
      per_shard={str(i):{a:score([r for r in rows if r["shard"]==i and r["arm"]==a])
                for a in ARMS} for i in range(SHARDS)},
      per_SHA={sha:{a:[dict(rep=x["rep"],status=x["status"],E2E_s=x["wall_E2E_s"],
                   proof=x["UNSAT_original_GF2_certificate_verified"])
                  for x in rr if x["arm"]==a] for a in ARMS} for sha,rr in bysha.items()})
    save(ROOT/"report.json",report)
    print("GF2_S1_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        globals()[a.action]()
        if a.action=="verify":print("GF2_S1_VERIFY_PASS",flush=True)
