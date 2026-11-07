#!/usr/bin/env python3
"""DRNAS New Horizon R6: real R5 SHA-pinned 2026 originals dual-live replay.

The R5 originals are already SEEN. This is a causal paired ablation with
existing CaDiCaL 2.1 configurations, NOT independent blind SAT validation.

Seven policies: native default, native UNSAT, dual keep default,
dual keep UNSAT, pilot faster, pilot short-clause rate, dual interleave.
The selected solver retains in-process learned state: no restart.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random,re,statistics,subprocess,time
import new_horizon_sat as sat
import r182_mixed_engine as exact

ROOT=pathlib.Path("new_horizon_r6")
FROZEN=ROOT/"frozen"
SOURCE_SHA="8931f7f544c04336cc9469039d5677915e999c5cd8f4070a4e103d2be8e346a7"
PROTO="DRNAS_NH_R6_R5_REAL_16_DUAL_DEFAULT_UNSAT_PRESERVED_v1"
REPS=2
SHARDS=8
CAP_S=12.0
ARMS=("default","unsat","dual_keep_default","dual_keep_unsat",
      "dual_fast","dual_learning","dual_interleave")
TARGET_SAT="65ee6b49612eccb7d213e4d950f23677"
TARGET_UNSAT="12cd0c3196589ac8105653cbfe613fc6"

def need(x,msg):
    if not x:raise AssertionError("NH_R6_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def verify():
    need(sha(FROZEN/"manifest.json")==SOURCE_SHA,"R5 original manifest SHA drift")
    raw=load(FROZEN/"manifest.json")
    need(raw["protocol"]=="DRNAS-NH-R5-PROSPECTIVE-EXTERNAL-MAIN2026-NATIVE6-v2",
         "wrong original R5 freeze protocol")
    cases=raw["cases"]
    need(len(cases)==16,"R5 original cohort count changed")
    need({TARGET_SAT,TARGET_UNSAT}<={c["id"] for c in cases},
         "complementary original test cases not pinned")
    for c in cases:
        p=FROZEN/(c["id"]+".cnf")
        need(p.is_file() and sha(p)==c["source_sha256"],
             "immutable original SAT2026 CNF drift")
    need(len({c["source_sha256"] for c in cases})==len(cases),
         "original hashes not unique")
    return cases

def source_pin(binary):
    pin=load(ROOT/"pin.json")
    need(sha(binary)==pin["driver_sha256"],
         "new dual-live native binary SHA drift")
    need(pin["R5_manifest_sha256"]==SOURCE_SHA,
         "original R5 source manifest pin mismatch")
    need(pin["cadical_commit"]=="31f9aae44947c673dc6190c9beb399acb9ffec6a",
         "CaDiCaL solver commit mismatch")
    return pin

def native(binary,source,cap,mode,order):
    started=time.perf_counter()
    args=[str(pathlib.Path(binary).resolve()),str(pathlib.Path(source).resolve()),
          str(cap),mode,str(order)]
    try:
        result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              timeout=cap+4,check=False)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",elapsed_s=time.perf_counter()-started,
                    model={},choice=None,reason="watchdog",
                    pilot_s=0,pilot_default_s=0,pilot_unsat_s=0,
                    offers_default=0,offers_unsat=0,
                    windows_default=0,windows_unsat=0,
                    source_preserved=mode.startswith("dual_"),
                    watchdog=True)
    need(result.returncode==0,
         "native R6 solver error "+result.stderr.decode(errors="replace")[-800:])
    raw=result.stdout.decode(errors="replace")
    m=re.search(r"^R182_STATUS status=(SAT|UNSAT|UNKNOWN) solver_s=([0-9.]+) variables=(\d+)$",raw,re.M)
    need(m,"R6 native status missing")
    status="TIMEOUT" if m[1]=="UNKNOWN" else m[1]
    effective=re.search(r"^NH_R6_MODE (\w+) profile=(default|unsat)$",raw,re.M)
    need(effective is not None and effective[1]==mode,
         "incorrect source solver mode")
    pilots=[]
    pattern=(r"^NH_R6_PILOT profile=(default|unsat) round=(\d+) "
       r"time_s=([0-9.]+) offers=(\d+) short3=(\d+) status=(SAT|UNSAT|UNKNOWN)$")
    for x in re.finditer(pattern,raw,re.M):
        need(int(x[5])<=int(x[4]),"invalid IPASIR short-offer telemetry")
        pilots.append(dict(profile=x[1],round=int(x[2]),time_s=float(x[3]),
                           offers=int(x[4]),short3=int(x[5]),status=x[6]))
    choice=None;reason="fixed_profile";pilot_default=pilot_unsat=0.
    offers_default=offers_unsat=0
    windows_default=windows_unsat=0
    dual=re.search(r"^NH_R6_DUAL selected=(default|unsat) reason=(\w+) "
        r"default_pilot_s=([0-9.]+) unsat_pilot_s=([0-9.]+) "
        r"offers_default=(\d+) offers_unsat=(\d+) "
        r"short_default=(\d+) short_unsat=(\d+) "
        r"windows_default=(\d+) windows_unsat=(\d+) "
        r"preserved=(\d+) source_original=(\d+)$",raw,re.M)
    if mode.startswith("dual_"):
        need(dual is not None,"dual telemetry missing")
        choice=dual[1];reason=dual[2]
        pilot_default=float(dual[3]);pilot_unsat=float(dual[4])
        offers_default=int(dual[5]);offers_unsat=int(dual[6])
        windows_default=int(dual[9]);windows_unsat=int(dual[10])
        need(dual[11]=="1" and dual[12]=="1",
             "original source / selected in-process state not preserved")
        need(1<=len(pilots)<=4,"missing pilots")
        need(len([p for p in pilots if p["profile"]=="default"])==windows_default,
             "default pilot counts disagree")
        need(len([p for p in pilots if p["profile"]=="unsat"])==windows_unsat,
             "unsat pilot counts disagree")
        need(abs(sum(p["time_s"] for p in pilots if p["profile"]=="default")-
                 pilot_default)<1e-4,
             "default measured pilot time inconsistent")
        need(abs(sum(p["time_s"] for p in pilots if p["profile"]=="unsat")-
                 pilot_unsat)<1e-4,
             "unsat measured pilot time inconsistent")
    else:
        need(dual is None and not pilots,"baseline unexpectedly dual")
    model={}
    if status=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                for token in line[2:].split():
                    lit=int(token)
                    if not lit:continue
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "native witness internally contradictory")
                    model[abs(lit)]=lit>0
    return dict(status=status,elapsed_s=time.perf_counter()-started,
                model=model,choice=choice,reason=reason,
                pilot_s=pilot_default+pilot_unsat,
                pilot_default_s=pilot_default,pilot_unsat_s=pilot_unsat,
                offers_default=offers_default,offers_unsat=offers_unsat,
                windows_default=windows_default,windows_unsat=windows_unsat,
                source_preserved=bool(dual),watchdog=False)

def selftest():
    need(REPS==2 and SHARDS==8 and CAP_S==12.0 and len(ARMS)==7,
         "unregistered experiment parameters")
    need(len(set(ARMS))==len(ARMS),"duplicated method")
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        p=pathlib.Path(root)/"test.cnf"
        p.write_text("p cnf 2 2\n1 0\n-1 2 0\n")
        n,clauses=exact.dimacs(p)
        need(n==2 and len(clauses)==2,"source test invalid")
    print("NH_R6_SELFTEST_PASS",flush=True)

def trial(c,mode,rep,binary):
    p=FROZEN/(c["id"]+".cnf")
    need(sha(p)==c["source_sha256"],"timed original SHA changed")
    order=rep%2
    start=time.perf_counter()
    x=native(binary,p,CAP_S,mode,order)
    status=x["status"]
    elapsed=time.perf_counter()-start
    if elapsed>=CAP_S:status="TIMEOUT"
    if status=="SAT":
        sat.verify_model(p,x["model"])
        proof="ORIGINAL_CNF_SAT_MODEL_CHECKED"
    elif status=="UNSAT":proof="NATIVE_UNSAT_NO_INDEPENDENT_LRAT"
    else:proof="CAP"
    expected=c["expected_from_GBD_if_published"].upper()
    if status!="TIMEOUT" and expected in ("SAT","UNSAT"):
        need(status==expected,
             "source original conflicts with GBD published answer")
    need(status in ("SAT","UNSAT","TIMEOUT"),"invalid R6 status")
    elapsed=time.perf_counter()-start # witness checking included
    if elapsed>=CAP_S:status="TIMEOUT"
    return dict(id=c["id"],source_sha256=c["source_sha256"],
         family=c["family"],mode=mode,rep=rep,order=order,
         cap_s=CAP_S,status=status,elapsed_s=round(elapsed,6),
         par2_s=round(2*CAP_S if status=="TIMEOUT" else elapsed,6),
         proof=proof,chosen=x["choice"],reason=x["reason"],
         pilot_s=round(x["pilot_s"],6),
         pilot_default_s=round(x["pilot_default_s"],6),
         pilot_unsat_s=round(x["pilot_unsat_s"],6),
         offers_default=x["offers_default"],offers_unsat=x["offers_unsat"],
         windows_default=x["windows_default"],
         windows_unsat=x["windows_unsat"],
         same_live_solver_preserved=x["source_preserved"],
         watchdog=x["watchdog"])

def shard(index,binary):
    cases=verify()
    source_pin(binary)
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),
         "invalid R6 shard/binary")
    rows=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(PROTO+c["source_sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                row=trial(c,arm,rep,binary)
                rows.append(row)
                save(ROOT/f"shard-{index}.json",rows)
                print("NH_R6_TRIAL",json.dumps({k:row[k] for k in (
                    "id","mode","rep","status","elapsed_s","pilot_s","chosen")}),
                    flush=True)
    need(len(rows)==len(cases[index::SHARDS])*REPS*len(ARMS),
         "missing R6 trial in shard")
    print("NH_R6_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=verify()
    source_pin(ROOT/"r6-driver")
    source_map={c["source_sha256"]:c for c in cases}
    rows=[]
    for idx in range(SHARDS):
        a=load(ROOT/f"shard-{idx}.json")
        need(len(a)==len(cases[idx::SHARDS])*REPS*len(ARMS),
             "missing shard "+str(idx))
        rows+=a
    need(len(rows)==len(cases)*REPS*len(ARMS),
         "missing 224 source-paired trials")
    groups=collections.defaultdict(list)
    for row in rows:
        c=source_map.get(row["source_sha256"])
        need(c is not None and c["id"]==row["id"],
             "source SHA not matched")
        want=2*CAP_S if row["status"]=="TIMEOUT" else row["elapsed_s"]
        need(abs(row["par2_s"]-want)<.00001,"incorrect PAR2")
        if row["mode"].startswith("dual_"):
            need(row["same_live_solver_preserved"] or row["watchdog"],
                 "dual-lifecycle lost model state")
        groups[row["source_sha256"],row["rep"]].append(row)
    for c in cases:
        for rep in range(REPS):
            g=groups[c["source_sha256"],rep]
            need(len(g)==len(ARMS) and {r["mode"] for r in g}==set(ARMS),
                 "unpaired formula/repeat")
            need(len({r["status"] for r in g if r["status"]!="TIMEOUT"})<=1,
                 "opposing native SAT/UNSAT outcomes")
    cohorts=dict(all=cases,
                 R5_lightsout_SAT=[c for c in cases if c["id"]==TARGET_SAT],
                 R5_hardware_UNSAT=[c for c in cases if c["id"]==TARGET_UNSAT])
    cohorts.update({family:[c for c in cases if c["family"]==family]
                    for family in sorted({c["family"] for c in cases})})
    report={}
    for cohort,subset in cohorts.items():
        accepted={c["source_sha256"] for c in subset}
        report[cohort]={}
        for arm in ARMS:
            arr=[r for r in rows if r["mode"]==arm and r["source_sha256"] in accepted]
            report[cohort][arm]=dict(n=len(arr),
                solved=sum(r["status"]!="TIMEOUT" for r in arr),
                par2_s=round(sum(r["par2_s"] for r in arr),6),
                elapsed_s=round(sum(r["elapsed_s"] for r in arr),6),
                pilot_s=round(sum(r["pilot_s"] for r in arr),6),
                statuses=dict(collections.Counter(r["status"] for r in arr)),
                selected=dict(collections.Counter(r["chosen"] for r in arr
                    if r["chosen"] is not None)),
                choices=dict(collections.Counter(r["reason"] for r in arr)))
    result=dict(protocol=PROTO,
        status="NH_R6_DUAL_LIVE_REPLAY_AUDIT_PASS_NOT_BLIND",
        sources=len(cases),trials=len(rows),repeats=REPS,cap_s=CAP_S,
        R5_manifest_sha256=SOURCE_SHA,
        source_original_byte_for_byte_reused=True,
        real_external_R5_replay_not_new_blind=True,
        same_CaDiCaL_2_1_binary_for_all_arms=True,
        selected_live_CaDiCaL_state_retained=True,
        original_SAT_witness_verified=True,
        native_UNSAT_independent_LRAT_absent=True,
        all_losing_pilot_work_charged=True,
        summary=report)
    save(ROOT/"report.json",result)
    save(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    md=["# DRNAS New Horizon SAT R6 — true in-process dual live default/UNSAT","",
        f"**{len(cases)} R5 reused real 2026 originals; {len(rows)} SHA matched runs;",
        f"{len(ARMS)} arms × {REPS} repeats; {CAP_S}s cap.**",
        "Not independent blind holdout. All loser pilot CPU and 2× source parses count.",
        "","| Cohort | Mode | Solved | PAR2 seconds | Pilot seconds |",
        "|---|---|---:|---:|---:|"]
    for group,v in report.items():
        for m,x in v.items():
            md.append(f"| {group} | {m} | {x['solved']}/{x['n']} | "+
                      f"{x['par2_s']:.6f} | {x['pilot_s']:.6f} |")
    md.extend(["","## Interpretation",
      "Only source-identical existing CaDiCaL profile choice; NOT a new SAT algorithm.",
      "Original SAT models independently checked; no LRAT/FRAT for UNSAT.",
      "Comparison to R5 8s PAR2 is invalid because R6 uses 12s caps.",
      "Within-R6 controls isolate pilot overhead and survivor state reuse.",
      "Any winner needs truly unseen originals and multiple seeds/hardware reruns."])
    (ROOT/"summary.md").write_text("\n".join(md)+"\n")
    print("NH_R6_FINAL",json.dumps({k:report[k] for k in
         ("all","R5_lightsout_SAT","R5_hardware_UNSAT")},sort_keys=True),
         flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cmd",choices=("selftest","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="new_horizon_r6/r6-driver")
    a=p.parse_args()
    if a.cmd=="selftest":selftest()
    elif a.cmd=="verify":
        print("NH_R6_R5_SOURCE_VERIFIED",len(verify()),SOURCE_SHA)
    elif a.cmd=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
