#!/usr/bin/env python3
"""DRNAS COMBO4: ORIGINAL-CNF proof-carrying GF(2) implied-unit prepass.
Two pre-frozen SAT24/25 cohorts: SEARCH5 12 + SEARCH6 12 disjoint SHA.
5 arms x 2 reps x 24 SHA = 240 1CPU, 8s E2E, each source hash-locked.
Paired CMS raw, CMS placebo (same scanner), GF2-unit-augmented CMS,
cheap source-gated GF2-unit CMS, Kissat raw. NO parallel solver portfolio.
Each injected unit is replayed from independently reconstructed COMPLETE
CNF 2..4 XOR clauses; never trust C++ unit output without this verification.
UNSAT backend is NOT accepted as a certified original proof merely because
the augmented CNF is UNSAT. Two previously CMS-XLRUP+CakeML-certified original
SHA are labelled externally certified, others need original reference agreement.
This is a previously used frozen cohort, NOT globally blind.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,shutil,subprocess,tempfile,time
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_binary_scc2_e2e as s2
import drnas_gf2_proof_first_s1 as s1

ROOT=pathlib.Path("mre_combo4")
ORIGINAL=e9.SOURCE
BIN=ROOT/"bin/combo4_units"
CMS=pathlib.Path("mre_equiv12/bin/cryptominisat5")
SEARCH5=pathlib.Path("mre_search5")
SEARCH6=pathlib.Path("mre_search6")
CERT=pathlib.Path("prior_combo2proof/report.json")
PROTO="DRNAS-COMBO4-GF2-RREF-UNIT-ORIGINAL-24SHA-5ARM-2REP-8S-ONECPU-v1"
ARMS=("cms_plain","cms_placebo","cms_derived_units","cms_source_gate","kissat_plain")
N=24
REPS=2
SHARDS=6
CAP=8.
MAX_SCAN_S=.45
MAX_UNITS=32
EXPECTED=N*len(ARMS)*REPS

def need(v,msg):
    if not v:raise RuntimeError("COMBO4_FAIL_CLOSED "+str(msg))
def sha(p):return e9.digest(p)
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,o):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(o,indent=2,sort_keys=True)+"\n")

def old_originals():
    a=read(SEARCH5/"manifest.json")["original_cases"]
    b=read(SEARCH6/"manifest.json")["original_SHA_sources"]
    need(len(a)==len(b)==12,"frozen 12+12 source count mismatch")
    cs=[dict(x,source_cohort="search5") for x in a]+[
        dict(x,source_cohort="search6") for x in b]
    need(len({c["sha256"] for c in cs})==N and
         len({c["gbd"] for c in cs})==N,"duplicate frozen SHA or GBD")
    return sorted(cs,key=lambda c:c["sha256"])

def src(c):
    p=ORIGINAL/c["filename"]
    need(p.is_file() and sha(p)==c["sha256"],"original DIMACS source SHA mismatch")
    return p

def certified_originals():
    p=read(CERT)
    need(p["protocol"]=="DRNAS-COMBO2-2ORIGINAL-SHA-PINNED-CMS17-CAKEML-BINARY-XLRUP-v1" and
         p["independent_XLRUP_CakeML_verified_count"]==2,"prior CMS XLRUP audited evidence absent")
    confirmed=set()
    for k,v in p["certificates"].items():
        if (v["independent_verified"] and
            v["certification_status"]=="CERTIFIED_ORIGINAL_UNSAT_BY_CMS_XLRUP_CAKEML"):
            confirmed.add(k)
    need(len(confirmed)==2,"source-original independent certificates drift")
    return confirmed

def hashes():
    return dict(script=sha(__file__),
      cpp=sha("research/drnas_combo4_certified_units.cpp"),
      cpp_bin=sha(BIN),cms=sha(CMS),kissat=sha(e9.KISSAT),
      search5=sha(SEARCH5/"manifest.json"),
      search6=sha(SEARCH6/"manifest.json"),proof_record=sha(CERT),
      old_xor_checker=sha("research/drnas_gf2_proof_first_s1.py"))

def source_gate(c):
    f=c.get("source_signals") or c.get("original_source_signals") or {}
    # Only previous SOURCE-ONLY 3-variable parity pattern counts; unchanged
    # regardless of any earlier solving outcomes. Gate is not part of correctness.
    return bool(int(f.get("xor3_complete_patterns",0))>0
        and c.get("bytes",0)<=6*1024*1024
        and int(f.get("clauses",0))<=65000)

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True);ORIGINAL.mkdir(parents=True,exist_ok=True)
    need(BIN.is_file() and CMS.is_file() and e9.KISSAT.is_file(),"missing pinned executables")
    cases=old_originals()
    for c in cases:
        p=(SEARCH5 if c["source_cohort"]=="search5" else SEARCH6)/"cases"/c["filename"]
        need(p.is_file() and sha(p)==c["sha256"],"frozen original CNF bytes missing")
        dst=ORIGINAL/c["filename"]
        if dst.exists():need(sha(dst)==c["sha256"],"source original SHA conflicting")
        else:shutil.copyfile(p,dst)
        src(c)
    proofset=certified_originals()
    need(proofset<={c["sha256"] for c in cases},"certified CNF not in frozen cohort")
    m=dict(protocol=PROTO,cases=cases,source_count=N,arms=list(ARMS),reps=REPS,
        shards=SHARDS,cap_s=CAP,max_scan_s=MAX_SCAN_S,max_units=MAX_UNITS,
        expected_trials=EXPECTED,one_logical_CPU=True,
        no_parallel_children=True,SAT_original_witness_verified=True,
        independent_GF2_derived_unit_proofs_replayed_on_original_CNF=True,
        independent_UNSAT_LRAT_for_newly_augmented_backend=False,
        prior_independent_CMS_XLRUP_original_CERT_SHA=sorted(proofset),
        no_automatic_promotion=True,
        source_only_gate=True,previously_tested_source_set=True,
        globally_blind=False,original_SHA_untouched=True,
        code_binary_manifest_digests=hashes())
    save(ROOT/"manifest.json",m);verify()
    print("COMBO4_FROZEN "+json.dumps(dict(sources=N,trials=EXPECTED,
        arms=len(ARMS),previously_tested=True,certified_sources=len(proofset)),
        sort_keys=True),flush=True)

def verify():
    m=read(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["cases"]==old_originals()
         and m["source_count"]==N and m["arms"]==list(ARMS)
         and m["reps"]==REPS and m["shards"]==SHARDS
         and m["cap_s"]==CAP and m["expected_trials"]==EXPECTED
         and m["max_scan_s"]==MAX_SCAN_S and m["max_units"]==MAX_UNITS
         and m["code_binary_manifest_digests"]==hashes(),"manifest/code/binary drift")
    for c in m["cases"]:src(c)
    need(set(m["prior_independent_CMS_XLRUP_original_CERT_SHA"])==certified_originals(),
         "archived cert SHA drift")
    return m

def certified_units_from_record(original,record):
    n,k,eq=s1.xor_equations_from_original(original)
    need(record["vars"]==n and record["clauses"]==k and
         record["xor_equations"]==len(eq) and not record["abstained"],
         "C++/independent complete-XOR enumeration mismatch")
    if record["xor_unsat"]:
        original_cert=s1.verify_algebraic_certificate(original,record)
        return [],original_cert
    units=record.get("derived_units",[])
    need(isinstance(units,list) and len(units)<=MAX_UNITS and
         len({abs(u["literal"]) for u in units})==len(units),
         "bad unique unit list")
    approved=[]
    for u in units:
        lit=u["literal"];indices=u["certificate_ids"]
        need(type(lit) is int and 1<=abs(lit)<=n,
             "bad implied original literal")
        need(isinstance(indices,list) and 1<=len(indices)<=len(eq)
             and len(set(indices))==len(indices)
             and all(type(i) is int and 0<=i<len(eq) for i in indices),
             "missing or illegal GF2 derivation equation IDs")
        combined=set();parity=0
        for i in indices:
            vs,rhs=eq[i]
            combined.symmetric_difference_update(vs);parity^=rhs
        need(combined=={abs(lit)} and parity==int(lit>0),
             "GF2 unit source-original proof does not entail literal")
        approved.append(lit)
    return approved,None

def scan(original):
    t=time.perf_counter()
    try:
        r=subprocess.run([str(BIN.resolve()),str(original.resolve())],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,timeout=MAX_SCAN_S)
    except subprocess.TimeoutExpired:
        return dict(verified_units=[],math_unsat=False,probe_s=round(time.perf_counter()-t,6),
                    reason="bounded_scanner_timeout",xor_count=0,proof_terms=0)
    if r.returncode!=0:
        return dict(verified_units=[],math_unsat=False,probe_s=round(time.perf_counter()-t,6),
                    reason="fail_closed_scanner_rc",xor_count=0,proof_terms=0)
    lines=[x[len("GF2_S1_RESULT "):] for x in r.stdout.splitlines()
           if x.startswith("GF2_S1_RESULT ")]
    need(len(lines)==1,"scanner emitted no unambiguous JSON")
    record=json.loads(lines[0])
    if record["abstained"]:
        return dict(verified_units=[],math_unsat=False,probe_s=round(time.perf_counter()-t,6),
                    reason="bounded_equation_abstention",xor_count=0,proof_terms=0)
    verified,unsat=certified_units_from_record(original,record)
    return dict(verified_units=verified,math_unsat=bool(unsat),
                probe_s=round(time.perf_counter()-t,6),
                reason="independent_GF2_UNSAT" if unsat else
                       "derived_units" if verified else "no_GF2_implied_units",
                xor_count=record["xor_equations"],
                proof_terms=unsat["terms"] if unsat else 0,
                unit_budget_abstained=record.get("unit_budget_abstained",False))

def toy_test():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(BIN.is_file(),"C++ native GF2 detector not built")
    with tempfile.TemporaryDirectory(prefix="combo4-toy-") as temp:
        d=pathlib.Path(temp)
        # Exact XOR x ^ y = 0, x ^ y ^ z = 1 entails z=1.
        # Both complete encodings are generated independently as original CNF.
        def parity(variables,rhs):
            ret=[]
            for mask in range(1<<len(variables)):
                if mask.bit_count()%2==1-rhs:
                    ret.append([(-v if mask&(1<<i) else v)
                                 for i,v in enumerate(variables)])
            return ret
        clauses=parity((1,2),0)+parity((1,2,3),1)
        f=d/"unit.cnf"
        def write(cs):
            f.write_text("p cnf 3 %d\n"%len(cs)+
                 "".join(" ".join(map(str,cl))+" 0\n" for cl in cs))
        write(clauses)
        proof=scan(f)
        need(proof["verified_units"]==[3] and not proof["math_unsat"],
             "two-row GF2 implication z=1 was not source-certified")
        # Remove one clause, making XOR3 incomplete; no longer implies z=1.
        write(clauses[:-1])
        q=scan(f)
        need(3 not in q["verified_units"] and not q["math_unsat"],
             "unsafe conclusion from incomplete XOR3 clause set")
        # Contradictory exact two-variable XOR subsets imply 0=1.
        write(parity((1,2),0)+parity((1,2),1))
        u=scan(f)
        need(u["math_unsat"] and u["proof_terms"]==2,
             "failed original CNF independent algebraic contradiction replay")
    print("COMBO4_SELFTEST_PASS "+json.dumps(dict(
        derived_unit_z_true_original_CNF_independently_verified=True,
        incomplete_parity_negative_control=True,
        contradictory_XOR_CNF_independently_proved_UNSAT=True,
        no_unverified_unit_injection=True),sort_keys=True),flush=True)

def write_augmented(original,output,units):
    # Original SAT models of strengthened CNF also satisfy untouched original.
    # No stronger UNSAT claim is made without ORIGINAL CNF proof evidence.
    n,clauses=e9.x22.read_cnf(original)
    need(len(units)<=MAX_UNITS and all(0<abs(x)<=n for x in units),
         "bad original-space unit")
    with open(output,"w") as f:
        f.write("p cnf %d %d\n"%(n,len(clauses)+len(units)))
        for clause in clauses:f.write(" ".join(map(str,clause))+" 0\n")
        for x in units:f.write(str(x)+" 0\n")

def backend_cms(original,augmented,cap):
    n,original_clauses=e9.x22.read_cnf(original)
    need(n>0 and bool(original_clauses),"source DIMACS parse error")
    cpu=min(os.sched_getaffinity(0));start=time.perf_counter()
    status="TIMEOUT";witness=False
    with tempfile.TemporaryDirectory(dir=ROOT) as d:
        proc=e9.x22.launch("cms",
            [str(CMS),"--verb","0","-t","1",str(augmented)],cpu,d)
        try:
            while proc["p"].poll() is None and time.perf_counter()-start < cap-.018:
                time.sleep(.004)
            if proc["p"].poll() is not None:
                stdout,stderr=e9.x22.read_output(proc)
                status,witness=e9.x22.solver_result("cms",
                    proc["p"].returncode,stdout,original_clauses,{})
        finally:e9.x22.cleanup([proc])
    wall=time.perf_counter()-start
    if wall>=cap:status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"CMS SAT witness invalid on ORIGINAL CNF")
    return status,bool(witness)

def one(c,rep,arm):
    need(arm in ARMS and rep in range(REPS),"bad trial key")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    t=time.perf_counter();pcpu=time.process_time();ccpu=e9.x22.child_cpu()
    original=src(c)
    state=None
    gated=arm=="cms_source_gate"
    do_scan=arm in ("cms_placebo","cms_derived_units","cms_source_gate")
    if do_scan and (not gated or source_gate(c)):
        state=scan(original)
    units=state["verified_units"] if state else []
    math_proof=bool(state and state["math_unsat"])
    # A proven original GF2 contradiction can be accepted immediately,
    # including in the gated arm. Placebo must never short-circuit.
    shortcut=math_proof and arm!="cms_placebo"
    inject=bool(units and arm in ("cms_derived_units","cms_source_gate"))
    status="UNSAT" if shortcut else "TIMEOUT";witness=False
    backend_called=False
    if not shortcut:
        left=CAP-(time.perf_counter()-t)
        if left>.1:
            backend_called=True
            if arm=="kissat_plain":
                s2.ROOT.mkdir(parents=True,exist_ok=True)
                r=s2.trial(dict(c,cohort="holdout"),rep,"kissat_orig",cap=left)
                status=r["status"];witness=r["SAT_original_witness_verified"]
            elif inject:
                with tempfile.TemporaryDirectory(dir=ROOT) as d:
                    augmented=pathlib.Path(d)/"implied-units.cnf"
                    write_augmented(original,augmented,units)
                    left=CAP-(time.perf_counter()-t)
                    if left>.1:status,witness=backend_cms(original,augmented,left)
            else:
                status,witness=backend_cms(original,original,left)
    wall=time.perf_counter()-t
    if wall>=CAP:status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"original SAT witness not verified")
    need(sha(original)==c["sha256"],"original source changed")
    row=dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
       source_cohort=c["source_cohort"],arm=arm,rep=rep,cap_s=CAP,
       original_SHA_checked=True,one_logical_CPU=cpu,one_backend_child_max=True,
       source_only_gate_decision=source_gate(c),source_gate_used=gated,
       scanner_executed=state is not None,
       scanner_E2E_s=state["probe_s"] if state else 0,
       xor_equations=state["xor_count"] if state else None,
       independent_GF2_original_UNSAT=math_proof,
       independent_GF2_unit_certificates_count=len(units),
       injected_original_source_entailed_units=len(units) if inject else 0,
       proof_terms=state["proof_terms"] if state else 0,
       scanner_reason=state["reason"] if state else "gate_skip" if do_scan else "baseline",
       status=status,SAT_original_witness_verified=bool(witness if status=="SAT" else False),
       UNSAT_independent_original_LRAT=False,
       prior_original_independent_XLRUP_available=c["sha256"] in certified_originals(),
       backend_called=backend_called,
       wall_E2E_s=round(wall,6),
       parent_CPU_s=round(time.process_time()-pcpu,6),
       child_CPU_s=round(e9.x22.child_cpu()-ccpu,6))
    return row

def shard(index):
    m=verify();need(index in range(SHARDS),"wrong shard")
    cases=[c for i,c in enumerate(m["cases"]) if i%SHARDS==index]
    rows=[]
    for c in cases:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+str(rep)+"COMBO4").shuffle(arms)
            for arm in arms:
                row=one(c,rep,arm);row["shard"]=index
                need(row["wall_E2E_s"]<=CAP+.2,"trial exceeded wall cap")
                rows.append(row);save(ROOT/f"shard-{index}.json",rows)
                print("COMBO4_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cases)*REPS*len(ARMS),"incomplete shard")
    print("COMBO4_SHARD_PASS %d %d"%(index,len(rows)),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        rr=read(ROOT/f"shard-{i}.json")
        need(len(rr)==len([c for j,c in enumerate(m["cases"]) if j%SHARDS==i])*REPS*len(ARMS),
             "missing shard or incomplete paired source")
        rows.extend(rr)
    expected={(c["sha256"],rep,arm) for c in m["cases"]
          for rep in range(REPS) for arm in ARMS}
    seen={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(seen)==len(expected) and seen==expected,
         "pairing or SHA set mismatch")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["original_SHA_checked"] and
             r["one_backend_child_max"] and r["cap_s"]==CAP
             and r["status"] in ("SAT","UNSAT","TIMEOUT")
             and (r["status"]!="SAT" or r["SAT_original_witness_verified"])
             and r["wall_E2E_s"]<=CAP+.2,"unverified raw trial")
        bysha[r["sha256"]].append(r)
    prior=certified_originals()
    independent=prior | {sha for sha,rr in bysha.items()
          if any(x["independent_GF2_original_UNSAT"] for x in rr)}
    reference_agreed={sha for sha,rr in bysha.items()
            if any(x["arm"]=="kissat_plain" and x["status"]=="UNSAT" for x in rr)
            and any(x["arm"]=="cms_plain" and x["status"]=="UNSAT" for x in rr)}
    for sha,rr in bysha.items():
        need(len({x["status"] for x in rr if x["status"]!="TIMEOUT"})<=1,
             "solver SAT/UNSAT disagreement")
    def accepted(r):
        return r["status"]=="SAT" and r["SAT_original_witness_verified"] or (
             r["status"]=="UNSAT" and r["sha256"] in (independent|reference_agreed))
    def penalty(r):return r["wall_E2E_s"] if accepted(r) else 2*CAP
    def score(rr):
        return dict(trials=len(rr),solved=sum(accepted(r) for r in rr),
           SAT_original_verified=sum(r["status"]=="SAT" for r in rr),
           UNSAT_independent_original_SHA=sum(r["status"]=="UNSAT"
               and r["sha256"] in independent for r in rr),
           UNSAT_reference_agreed_no_independent_proof=sum(r["status"]=="UNSAT"
               and r["sha256"] in reference_agreed-independent for r in rr),
           UNSAT_unverified=sum(r["status"]=="UNSAT" and not accepted(r) for r in rr),
           timeouts=sum(r["status"]=="TIMEOUT" for r in rr),
           derived_unit_repetitions=sum(r["independent_GF2_unit_certificates_count"]>0 for r in rr),
           total_derived_units=sum(r["independent_GF2_unit_certificates_count"] for r in rr),
           total_units_injected=sum(r["injected_original_source_entailed_units"] for r in rr),
           total_scan_wall_s=round(sum(r["scanner_E2E_s"] for r in rr),6),
           total_wall_s=round(sum(r["wall_E2E_s"] for r in rr),6),
           total_CPU_s=round(sum(r["child_CPU_s"]+r["parent_CPU_s"] for r in rr),6),
           PAR2_s=round(sum(penalty(r) for r in rr),6))
    scores={arm:score([r for r in rows if r["arm"]==arm]) for arm in ARMS}
    for arm in ARMS:
        scores[arm]["speedup_vs_CMS_PAR2_x"]=round(
           scores["cms_plain"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
    paired={}
    for arm in ARMS:
        if arm=="cms_plain":continue
        dif=[]
        for sha,rr in bysha.items():
            for rep in range(REPS):
                a=next(r for r in rr if r["arm"]==arm and r["rep"]==rep)
                b=next(r for r in rr if r["arm"]=="cms_plain" and r["rep"]==rep)
                dif.append(penalty(a)-penalty(b))
        paired[arm]=dict(wins=sum(d<-.02 for d in dif),
          losses=sum(d>.02 for d in dif),ties=sum(abs(d)<=.02 for d in dif),
          net_PAR2_gain_s=round(-sum(dif),6),
          max_gain_s=round(-min(dif),6),max_regression_s=round(max(dif),6))
    report=dict(protocol=PROTO,trials=EXPECTED,sources=N,one_logical_CPU=True,
      source_SHA_disjoint_cohorts=True,
      previously_frozen_not_blind=True,
      GF2_derived_units_independently_verified_on_original_CNF=True,
      not_native_original_UNSAT_LRAT_proof=True,
      prior_external_CMS_CakeML_original_SHA=sorted(prior),
      source_math_cert_SHA=sorted(independent-prior),
      reference_agreed_without_standard_proof_SHA=sorted(reference_agreed-independent),
      no_automatic_promotion=True,
      scores=scores,paired=paired,
      per_shard={str(i):{arm:score([r for r in rows if r["shard"]==i and r["arm"]==arm])
                  for arm in ARMS} for i in range(SHARDS)},
      per_SHA={sha:{arm:[dict(rep=r["rep"],status=r["status"],E2E_s=r["wall_E2E_s"],
                  derived_units=r["independent_GF2_unit_certificates_count"],
                  injected=r["injected_original_source_entailed_units"],
                  XOR=r["xor_equations"],scan_E2E_s=r["scanner_E2E_s"])
                  for r in rr if r["arm"]==arm] for arm in ARMS} for sha,rr in bysha.items()})
    save(ROOT/"report.json",report)
    print("COMBO4_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":toy_test()
    elif a.action=="shard":shard(a.shard)
    else:
        globals()[a.action]()
        if a.action=="verify":print("COMBO4_VERIFY_PASS",flush=True)
