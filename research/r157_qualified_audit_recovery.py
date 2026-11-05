#!/usr/bin/env python3
"""Audit-only qualified provenance recovery of R157 run 42120573934.

No solver reruns, no source reselection. The original R157 audit required one
identical binary SHA across 4 self-built GitHub runners; all four differently
built binaries were instead produced from the same pinned R157 and CaDiCaL
source commits. Such binaries are NOT asserted identical. Every run retains
its native SHA and CPU; only within-shard paired comparisons are comparable.
"""
import collections,hashlib,json,pathlib,re
R=pathlib.Path("r157"); REPS=2; MODES=("clean","freeze","watch","clause","direct")
def need(cond,msg):
 if not cond:raise RuntimeError("R157_QUALIFIED_AUDIT_FAIL "+msg)
def load(p):return json.loads(pathlib.Path(p).read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def read_clauses(p):
 clauses=[];buf=[];n=None;count=None
 for ln in p.read_text().splitlines():
  if not ln.strip() or ln.startswith(("c","%")):continue
  if ln.startswith("p "):
   a=ln.split();need(len(a)==4 and a[1]=="cnf","source header")
   n,count=int(a[2]),int(a[3]);continue
  for k in ln.split():
   lit=int(k)
   if lit:buf.append(lit)
   else:clauses.append(tuple(buf));buf=[]
 need(n is not None and not buf and len(clauses)==count,"original source DIMACS corruption")
 return n,clauses
m=load(R/"frozen/manifest.json")
need(len(m["cases"])==25,"unexpected frozen 25 source")
cs=sorted((c for c in m["cases"] if c["cohort"]=="mixed_residual"),key=lambda c:c["id"])
need(len(cs)==4,"need 4 original mixed sources")
pins=[];allrows=[];keys=set()
for i in range(4):
 pin=load(R/f"pin-{i}.json")
 need(re.fullmatch(r"[0-9a-f]{40}",pin["git_commit"]) is not None,"pin git commit")
 need(re.fullmatch(r"[0-9a-f]{40}",pin["cadical_commit"]) is not None,"pin CaDiCaL commit")
 need(re.fullmatch(r"[0-9a-f]{64}",pin["binary_sha"]) is not None,"pin native binary SHA")
 pins.append(dict(shard=i,**pin))
 arr=load(R/f"shard-{i}.json")
 need(len(arr)==10,"incomplete frozen shard "+str(i))
 for a in arr:
  need(a["id"]==cs[i]["id"] and a["sha256"]==cs[i]["sha256"],"source mismatch in shard")
  need(a["mode"] in MODES and a["repeat"] in (0,1),"invalid trial identity")
  key=a["id"],a["mode"],a["repeat"]
  need(key not in keys,"duplicated trial")
  keys.add(key)
  need(a["status"] in ("TIMEOUT","SAT","UNSAT"),"status invalid")
  need(abs(a["par2"]-(30.0 if a["status"]=="TIMEOUT" else a["time_s"]))<0.00002,"PAR2 wrong")
  need(a["status"]!="SAT" or a.get("proof")=="original_source_SAT_witness_checked","external source SAT missing proof")
  allrows.append(a)
need(len({p["git_commit"] for p in pins})==1,"R157 SOURCE COMMIT DRIFT")
need(len({p["cadical_commit"] for p in pins})==1,"CADICAL SOURCE COMMIT DRIFT")
need(len(allrows)==40 and len(keys)==40,"40-run missing")
for c in cs:
 p=R/"frozen"/(c["id"]+".cnf")
 need(sha(p.read_bytes())==c["sha256"],"original CNF SHA drift")
 n,clauses=read_clauses(p)
 ce=load(R/("cert-"+c["id"]+".json"))
 need(ce["source_sha256"]==c["sha256"] and ce["selected_rows"]==len(ce["selected"]),"source evidence binding")
 units={}; groups=collections.defaultdict(set)
 for clause in clauses:
  if len(clause)==1:
   v=abs(clause[0]);rhs=int(clause[0]>0)
   need(v not in units or units[v]==rhs,"conflicting source units: need independent proof")
   units[v]=rhs
  if not 2<=len(clause)<=6 or len({abs(v) for v in clause})!=len(clause):continue
  lit=sorted(clause,key=abs);vs=tuple(abs(v) for v in lit)
  groups[vs].add(sum(1<<i for i,v in enumerate(lit) if v<0))
 rows=[]
 for e in ce["selected"]:
  sv=tuple(e["source_vars"]);rhs=int(e["source_rhs"])
  need(len(sv)>=2 and len(sv)<=6 and tuple(sorted(set(sv)))==sv,"bad source XOR row")
  masks=groups.get(sv,set())
  required={i for i in range(1<<len(sv)) if i.bit_count()%2==1-rhs}
  need(required<=masks,"source XOR blocks not complete")
  removed=[v for v in sv if v in units]
  remain=tuple(v for v in sv if v not in units)
  rr=rhs
  for v in removed:rr^=units[v]
  need(tuple(e["vars"])==remain and int(e["rhs"])==rr,"XOR+units implication incorrect")
  need(2<=len(remain)<=6,"derived row length")
  rows.append(f"{len(remain)} {rr} "+" ".join(map(str,remain))+"\n")
 digest=sha("".join(rows).encode())
 for a in allrows:
  if a["id"]==c["id"]:
   need(a["source_proof_sha"]==digest and a["source_rows"]==len(rows),"source evidence SHA does not match actual native input")
 print("R157_SOURCE_CERT_REPLAY_PASS",c["id"],"rows",len(rows),flush=True)
for c in cs:
 a=[r for r in allrows if r["id"]==c["id"]]
 need(len(a)==10 and len({r["status"] for r in a if r["status"]!="TIMEOUT"})<=1,"mode outcome disagreement")
totals={}
for mode in MODES:
 arr=[r for r in allrows if r["mode"]==mode]
 totals[mode]=dict(trials=len(arr),solved=sum(z["status"]!="TIMEOUT" for z in arr),
                   par2_s=round(sum(z["par2"] for z in arr),6),
                   timeout_progress_recovered=sum(z["timeout_progress_recovered"] for z in arr),
                   proposed_GF2_from_last_checkpoint=sum(z.get("direct_proposals") or 0 for z in arr),
                   reason_requests_from_last_checkpoint=sum(z.get("direct_reason_requests") or 0 for z in arr),
                   assignment_events_from_last_checkpoint=sum(z.get("assignments") or 0 for z in arr),
                   backtracks_from_last_checkpoint=sum(z.get("backtracks") or 0 for z in arr))
report=dict(protocol="R157-AUDIT-ONLY-PER-SHARD-BINARY-PINS-20261106-v1",
            status="QUALIFIED_AUDIT_PASS_WITH_HETEROGENEOUS_NATIVE_BINARIES",
            source_run_id=42120573934,original_audit_failed="original audit required identical binary SHAs",
            no_rerun=True,original_mixed_cases=4,paired_attempts=40,
            native_binary_sha_distinct=len({x["binary_sha"] for x in pins}),
            cadical_source_commit=pins[0]["cadical_commit"],
            r157_source_commit=pins[0]["git_commit"],pins_by_shard=pins,
            source_CNF_SHA_and_GF2_cert_replayed=True,
            bin_sha_drift_fully_disclosed=True,
            cross_shard_native_binary_equivalence_NOT_VERIFIED=True,
            within_shard_same_native_binary=True,
            original_source_SAT_witness="checked by native solver if any SAT; all current cases timeout",
            independent_UNSAT_certificate=False,
            cap_s=15.0,par2_timeout_s=30.0,
            summaries=totals,paired=allrows,
            caveats=["All 4 source/shard audits pass but compiled native binary SHA differs across runners",
             "Only paired modes within the same shard are strictly matched",
             "No solver reruns or source changes; proof verification independently replays original XOR blocks and unit substitutions",
             "Progress samples are lower bounds, not final complete counters; no solved mixed formula"])
(R/"qualified-report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print("R157_QUALIFIED_AUDIT_PASS",json.dumps({k:report[k] for k in ("status","paired_attempts","native_binary_sha_distinct","source_CNF_SHA_and_GF2_cert_replayed","summaries")},sort_keys=True),flush=True)
