#!/usr/bin/env python3
"""DRNAS TURN2: source-structural, bijective representation experiment.

Primary preregistered contrast: Kissat structural-both vs plain Kissat.
Ablations: signed degree-labeling and clause order independently.
TURN1 random both and CMS plain are frozen reference arms.
No SAT outcome, filename/ID, benchmark time, or source SHA is used in the
transformation. A separate post-audit diagnosis uses a fixed conflict cap.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import lzma
import os
import pathlib
import random
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

import drnas_turn1_representation as t1

ROOT = pathlib.Path("turn2")
SOURCE = ROOT / "sources"
CAP, REPS, NCASES = 60.0, 3, 12
PROTO = "DRNAS-TURN2-NEW12-STRUCTURAL-BIJECTION-6ARMS-3REPS-60S-v1"
MODES = (
    "kissat_plain", "kissat_turn1_both",
    "kissat_struct_signed", "kissat_struct_order",
    "kissat_struct_both", "cms_plain"
)
KISSAT = os.environ.get("TURN2_KISSAT", "built/bin/kissat_4_0_4")
CMS = os.environ.get("TURN2_CMS", "cryptominisat5")
EXCLUSIONS = t1.EXCLUSIONS + ("turn1/manifest.json",)
REPS_DIAG = 1
DIAG_CAP = 8.0


def need(condition, explanation):
    if not condition:
        raise RuntimeError("TURN2_FAIL_CLOSED " + str(explanation))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def save(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def known():
    hashes, ids = t1.known()
    p = pathlib.Path("turn1/manifest.json")
    need(p.is_file(), "missing TURN1 source exclusion")
    for c in json.loads(p.read_text())["cases"]:
        hashes.add(c["sha256"])
        ids.add(c["id"].split("-")[0])
    return hashes, ids


def fetch():
    previous, ids = known()
    q = json.loads(pathlib.Path("ta3_2026/preregistration.json").read_text())
    need(len(q["source_queue"]) == 400, "official 400-source frozen queue")
    SOURCE.mkdir(parents=True, exist_ok=True)
    cases = []
    skipped = []
    for url in q["source_queue"]:
        if len(cases) >= NCASES:
            break
        identifier = url.rsplit("/", 1)[-1]
        need(re.fullmatch(r"https://benchmark-database\.de/file/[0-9a-f]{32}", url),
             "source domain")
        if identifier in ids:
            continue
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "DRNAS-TURN2-SOURCE-FROZEN-v1"})
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read(q["max_compressed_bytes"] + 1)
            need(0 < len(data) <= q["max_compressed_bytes"], "compressed limit")
            decoder = lzma.LZMADecompressor()
            raw = decoder.decompress(data, max_length=q["max_original_bytes"] + 1)
            need(decoder.eof and 0 < len(raw) <= q["max_original_bytes"], "raw limit")
            header = re.search(rb"(?m)^p\s+cnf\s+(\d+)\s+(\d+)\s*$", raw[:8192])
            need(header is not None, "invalid CNF header")
            n, m = map(int, header.groups())
            need(0 < n <= 150000 and 0 < m <= 160000, "formula size eligibility")
            h = hashlib.sha256(raw).hexdigest()
            need(h not in previous and h not in {c["sha256"] for c in cases},
                 "source overlap")
            p = SOURCE / (identifier + ".cnf")
            p.write_bytes(raw)
            t1.parse(p)
            cases.append(dict(id=identifier, sha256=h, url=url,
                              variables=n, clauses=m, bytes=len(raw)))
            print("TURN2_NEW_SOURCE", identifier, h, flush=True)
        except Exception as exc:
            skipped.append(dict(id=identifier, reason=str(exc)[:160]))
            print("TURN2_SOURCE_SKIP", identifier, str(exc)[:160], flush=True)
    need(len(cases) == NCASES, "not enough SHA-disjoint originals")
    save(ROOT / "manifest.json",
         dict(protocol=PROTO, cases=cases, skipped=skipped,
              selected_without_runtime=True, known_manifest_disjoint=True,
              globally_blind=False))
    print("TURN2_SOURCE_FROZEN", NCASES, sha(ROOT / "manifest.json"), flush=True)


def verify():
    data = json.loads((ROOT / "manifest.json").read_text())
    need(data["protocol"] == PROTO, "wrong protocol")
    cases = data["cases"]
    need(len(cases) == NCASES and len({c["sha256"] for c in cases}) == NCASES,
         "wrong number of unique sources")
    known_hashes, _ = known()
    need(not known_hashes.intersection(c["sha256"] for c in cases),
         "source overlap with old manifest")
    for p, digest in json.loads((ROOT / "pins.json").read_text()).items():
        need(sha(p) == digest, "pin drift " + p)
    for c in cases:
        need(sha(SOURCE / (c["id"] + ".cnf")) == c["sha256"],
             "original CNF changed")
    return sorted(cases, key=lambda c: c["sha256"])


def degree_profile(n, clauses):
    occ = [0] * (n + 1)
    pos = [0] * (n + 1)
    neg = [0] * (n + 1)
    binary = horn = long = xor3 = 0
    for c in clauses:
        binary += len(c) == 2
        horn += sum(lit > 0 for lit in c) <= 1
        long += len(c) >= 5
        for lit in c:
            v = abs(lit)
            occ[v] += 1
            if lit > 0:
                pos[v] += 1
            else:
                neg[v] += 1
    nonzero = sorted((occ[i] for i in range(1, n + 1) if occ[i] > 0))
    median = nonzero[len(nonzero) // 2] if nonzero else 0
    p90 = nonzero[min(len(nonzero)-1, int(.9 * len(nonzero)))] if nonzero else 0
    avg_bias = sum(abs(pos[i]-neg[i])/occ[i]
                   for i in range(1, n + 1) if occ[i]) / max(1, len(nonzero))
    features = {
        "variables": n, "clauses": len(clauses),
        "literals": sum(occ),
        "active_variables": len(nonzero),
        "binary_fraction": round(binary / max(1, len(clauses)), 7),
        "horn_fraction": round(horn / max(1, len(clauses)), 7),
        "long_fraction": round(long / max(1, len(clauses)), 7),
        "p90_over_median_occ": round(p90 / max(1, median), 7),
        "mean_polarity_bias": round(avg_bias, 7),
        "negative_majority_fraction": round(
            sum(neg[i] > pos[i] for i in range(1, n+1))
            / max(1, len(nonzero)), 7),
    }
    return occ, pos, neg, features


def structural_mapping(n, occ, pos, neg, variant):
    # The same deterministic map for both signed and full variants.
    # Variable IDs and clause positions affect only tie-breaking; outcomes
    # and source SHA are never inputs to this mapping.
    mp = [0] * (n + 1)
    rank = sorted(range(1, n + 1), key=lambda i: (-occ[i], -pos[i], i))
    for label, old in enumerate(rank, start=1):
        polarity = -1 if neg[old] > pos[old] else 1
        mp[old] = label * (polarity if variant in ("struct_signed","struct_both") else 1)
    if variant == "struct_order":
        mp = list(range(n + 1))
    return mp


def transformation(n, clauses, mode):
    if mode == "kissat_turn1_both":
        return t1.transform(n, clauses, "both")
    if mode in ("kissat_plain", "cms_plain"):
        return clauses, list(range(n+1))
    variant = mode.partition("_")[2]
    need(variant in ("struct_signed", "struct_order", "struct_both"),
         "bad representation mode")
    occ, pos, neg, _ = degree_profile(n, clauses)
    mp = structural_mapping(n, occ, pos, neg, variant)
    out = [[mp[abs(v)] if v > 0 else -mp[abs(v)] for v in c] for c in clauses]
    if variant in ("struct_order", "struct_both"):
        # Prioritize short clauses and high-degree literals deterministically.
        # This is a bijective reorder; it neither learns nor inserts clauses.
        label_degree = {abs(mp[i]):occ[i] for i in range(1,n+1)}
        for c in out:
            c.sort(key=lambda lit: (-label_degree[abs(lit)],
                                   abs(lit), lit < 0))
        out.sort(key=lambda c: (len(c), -sum(label_degree[abs(v)] for v in c),
                                tuple(abs(v) for v in c)))
    inverse = {abs(mp[i]): (i if mp[i] > 0 else -i) for i in range(1, n+1)}
    restored = [
        tuple(sorted(inverse[abs(v)] if v > 0 else -inverse[abs(v)] for v in c))
        for c in out
    ]
    need(len({abs(mp[i]) for i in range(1, n+1)}) == n, "mapping not a permutation")
    need(collections.Counter(restored) ==
         collections.Counter(tuple(sorted(c)) for c in clauses),
         "full clause multiset changed")
    return out, mp


def worker(source, mode, directory):
    start = time.perf_counter()
    n, original = t1.parse(source)
    clauses, mp = transformation(n, original, mode)
    path = pathlib.Path(source)
    if mode not in ("kissat_plain", "cms_plain"):
        path = pathlib.Path(directory) / "transformed.cnf"
        t1.write_cnf(path, n, clauses)
    prep = time.perf_counter() - start
    command = ([CMS, "--threads", "1", "--verb", "0", str(path)]
               if mode.startswith("cms") else [KISSAT, str(path)])
    print(json.dumps(dict(event="solver_start", command=command, prep_s=prep,
                          transformed_sha256=sha(path))), flush=True)
    started_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    finished_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    pathlib.Path(directory, "solver.log").write_text(result.stdout)
    verdicts = re.findall(r"^s (SATISFIABLE|UNSATISFIABLE)\s*$",
                          result.stdout, re.M)
    need(len(verdicts) == 1, "missing / ambiguous solver verdict")
    status = "SAT" if verdicts[0] == "SATISFIABLE" else "UNSAT"
    need(result.returncode == (10 if status == "SAT" else 20),
         "exit status and verdict mismatch")
    model = {}
    for line in result.stdout.splitlines():
        if line.startswith("v "):
            for token in line[2:].split():
                lit = int(token)
                if lit:
                    need(abs(lit) not in model or model[abs(lit)] == (lit > 0),
                         "conflicting SAT model")
                    model[abs(lit)] = lit > 0
    if status == "SAT":
        model = t1.inverse_model(model, mp)
        need(t1.satisfies(original, model), "reconstructed SAT model invalid")
        save(pathlib.Path(directory) / "model.json", model)
    print(json.dumps(dict(event="result", status=status, prep_s=prep,
                          transformed_sha256=sha(path),
                          cpu_user_s=round(finished_cpu.ru_utime-started_cpu.ru_utime, 6),
                          cpu_system_s=round(finished_cpu.ru_stime-started_cpu.ru_stime, 6),
                          peak_rss_kib=finished_cpu.ru_maxrss,
                          proof=("SAT_ORIGINAL_MODEL_VERIFIED" if status == "SAT"
                                 else "NO_INDEPENDENT_UNSAT_PROOF"))), flush=True)


def trial(case, mode, rep, shard):
    source = SOURCE / (case["id"] + ".cnf")
    need(sha(source) == case["sha256"], "source SHA drift")
    directory = ROOT / "raw" / str(shard) / (str(rep) + "-" + mode)
    directory.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, __file__, "worker",
               "--source", str(source), "--mode", mode,
               "--directory", str(directory)]
    began = time.perf_counter()
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, start_new_session=True)
    timed_out = False
    try:
        output, _ = p.communicate(timeout=max(.001, CAP-(time.perf_counter()-began)))
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = p.communicate()
    elapsed = time.perf_counter()-began
    (directory / "worker.log").write_text(output)
    events = []
    for line in output.splitlines():
        try:
            events.append(json.loads(line))
        except (ValueError, TypeError):
            pass
    ended = [e for e in events if e.get("event") == "result"]
    status, proof, prep, transformed, cpu_user, cpu_sys, rss = (
        "TIMEOUT","WALL_CAP_TIMEOUT",None,None,None,None,None)
    if not timed_out and elapsed < CAP:
        need(p.returncode == 0 and len(ended) == 1,
             "worker failed " + output[-1800:])
        e=ended[0];status=e["status"];proof=e["proof"];prep=e["prep_s"]
        transformed=e["transformed_sha256"];cpu_user=e["cpu_user_s"]
        cpu_sys=e["cpu_system_s"];rss=e["peak_rss_kib"]
    if status=="SAT":
        model = {int(k):v for k,v in json.loads((directory/"model.json").read_text()).items()}
        need(t1.satisfies(t1.parse(source)[1], model), "independent parent model recheck")
    row = dict(protocol=PROTO, id=case["id"], sha256=case["sha256"],
               mode=mode, rep=rep, shard=shard,
               elapsed_s=round(min(CAP,elapsed),6),
               par2_s=round(2*CAP if status=="TIMEOUT" else elapsed,6),
               status=status,proof=proof,prep_s=prep,
               transformed_sha256=transformed,
               cpu_user_s=cpu_user,cpu_system_s=cpu_sys,peak_rss_kib=rss,
               single_solver=True)
    print("TURN2_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row


def shard(index):
    cases=verify()
    need(0<=index<NCASES,"bad shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    c=cases[index]
    n,clauses=t1.parse(SOURCE/(c["id"]+".cnf"))
    _,_,_,features=degree_profile(n,clauses)
    save(ROOT / ("features-%d.json"%index),
         dict(source_sha256=c["sha256"], features=features, diagnostic_only=True))
    rows=[]
    for rep in range(REPS):
        order=list(MODES)
        random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
        for mode in order:
            rows.append(trial(c,mode,rep,index))
            save(ROOT/("shard-%d.json"%index),rows)
    need(len(rows)==REPS*len(MODES),"incomplete shard")
    print("TURN2_SHARD_PASS",index,len(rows),flush=True)


def audit():
    cases=verify(); rows=[]; seen=set()
    for i,c in enumerate(cases):
        subset=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(subset)==REPS*len(MODES),"incomplete paired shard")
        features=json.loads((ROOT/("features-%d.json"%i)).read_text())
        need(features["source_sha256"]==c["sha256"],"feature source drift")
        for r in subset:
            key=(r["sha256"],r["rep"],r["mode"])
            need(key not in seen,"duplicate trial")
            seen.add(key)
            need(r["sha256"]==c["sha256"] and r["shard"]==i
                 and r["id"]==c["id"] and r["protocol"]==PROTO,"source mismatch")
            need(r["mode"] in MODES and 0<=r["rep"]<REPS,"unregistered run")
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad status")
            need(0<=r["elapsed_s"]<=CAP,"out of cap")
            need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT"
                                else r["elapsed_s"]))<.00002, "PAR2 wrong")
            need(r["status"]!="SAT" or r["proof"]=="SAT_ORIGINAL_MODEL_VERIFIED",
                 "unverified SAT")
            rows.append(r)
        statuses={r["status"] for r in subset if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"contradictory solver SAT/UNSAT verdicts")
    expected={(c["sha256"],rep,mode) for c in cases
              for rep in range(REPS) for mode in MODES}
    need(seen==expected and len(rows)==NCASES*REPS*len(MODES),
         "wrong count/coverage")
    metrics={}
    bykey={(r["sha256"],r["rep"],r["mode"]):r for r in rows}
    for mode in MODES:
        r=[x for x in rows if x["mode"]==mode]
        metrics[mode]=dict(attempts=len(r),solved=sum(x["status"]!="TIMEOUT" for x in r),
                           SAT=sum(x["status"]=="SAT" for x in r),
                           UNSAT=sum(x["status"]=="UNSAT" for x in r),
                           PAR2_s=round(sum(x["par2_s"] for x in r),6))
    comparisons={}
    for mode in ("kissat_turn1_both","kissat_struct_signed",
                 "kissat_struct_order","kissat_struct_both"):
        pairs=[]
        for c in cases:
            base=sum(bykey[c["sha256"],rep,"kissat_plain"]["par2_s"] for rep in range(REPS))
            alt=sum(bykey[c["sha256"],rep,mode]["par2_s"] for rep in range(REPS))
            pairs.append((c["id"],base,alt))
        rng=random.Random(20261107)
        dist=[]
        for _ in range(5000):
            sampled=rng.choices(pairs,k=NCASES)
            dist.append(sum(x[1] for x in sampled)/max(1e-12,sum(x[2] for x in sampled)))
        dist.sort()
        comparisons[mode]=dict(base="kissat_plain",
             ratio=metrics["kissat_plain"]["PAR2_s"]/metrics[mode]["PAR2_s"],
             bootstrap95=[round(dist[125],6),round(dist[4875],6)],
             wins=sum(x[2]+.005 < x[1] for x in pairs),
             losses=sum(x[2] > x[1]+.005 for x in pairs),
             ties=sum(abs(x[2]-x[1])<=.005 for x in pairs),
             regressions_over_10pct=sum(x[2]>1.1*x[1] for x in pairs),
             new_solved_sources=sum(x[1]==2*CAP*REPS and x[2]<x[1] for x in pairs),
             paired_formula_delta_s=[
                 {"id":x[0],"base_PAR2":round(x[1],6),"variant_PAR2":round(x[2],6),
                  "gain_s":round(x[1]-x[2],6)}
                 for x in pairs if abs(x[1]-x[2])>.005])
    primary=comparisons["kissat_struct_both"]
    signal=(primary["ratio"]>1.05 and primary["bootstrap95"][0]>1 and
            primary["regressions_over_10pct"]<=1 and
            metrics["kissat_struct_both"]["solved"]>=metrics["kissat_plain"]["solved"])
    result=dict(status="TURN2_AUDIT_PASS",protocol=PROTO,attempts=len(rows),
        sources=NCASES,cap_s=CAP,repetitions=REPS,one_solver_one_cpu=True,
        source_manifest_exclusions_including_TURN1=True,
        known_manifest_SHA_disjoint=True,globally_blind=False,
        independent_UNSAT_proof=False,promotion_allowed=False,
        primary_signal=signal,primary="kissat_struct_both vs kissat_plain",
        modes=metrics,comparisons=comparisons,
        note="Telemetry is a separate AFTER-AUDIT exploratory job and is NOT a performance arm")
    save(ROOT/"report.json",result)
    save(ROOT/"all-trials.json",rows)
    report=["# TURN2 prospective structural representation","",
      "A green audit is not proof of a performance win. UNSAT has no independent certificate.","",
      "| Mode | Solved | PAR2 s |","|---|---:|---:|"]
    for mode,v in metrics.items():
        report.append("| %s | %d / %d | %.6f |"%(mode,v["solved"],v["attempts"],v["PAR2_s"]))
    report.extend(["","Primary: "+json.dumps(primary,sort_keys=True),
                   "Primary signal: "+str(signal),"Promotion allowed: False"])
    (ROOT/"report.md").write_text("\n".join(report)+"\n")
    print("TURN2_FINAL",json.dumps(result,sort_keys=True),flush=True)


def diagnose():
    """Separate post-audit exploratory 5000-conflict telemetry, NOT benchmark."""
    cases=verify()
    results=[]
    for c in cases:
        source=SOURCE/(c["id"]+".cnf")
        n,clauses=t1.parse(source)
        for mode in ("kissat_plain","kissat_turn1_both","kissat_struct_both"):
            with tempfile.TemporaryDirectory() as tmp:
                transformed,_=transformation(n,clauses,mode)
                p=source
                if mode!="kissat_plain":
                    p=pathlib.Path(tmp)/"representation.cnf"
                    t1.write_cnf(p,n,transformed)
                cmd=[KISSAT,"--conflicts=5000","--statistics",str(p)]
                started=time.perf_counter()
                try:
                    out=subprocess.run(cmd,stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,text=True,timeout=DIAG_CAP)
                    status="FINISHED"; output=out.stdout;code=out.returncode
                except subprocess.TimeoutExpired as exc:
                    status="DIAG_TIMEOUT"
                    output=(exc.stdout or b"")
                    if isinstance(output,bytes): output=output.decode("utf-8","replace")
                    code=None
                elapsed=time.perf_counter()-started
                # Do NOT invent numeric counters when output is incomplete or unparseable.
                interesting=[l[:240] for l in output.splitlines()
                            if re.search(r"\b(conflicts|propagations|restarts|decisions)\b",l,re.I)]
                numeric={}
                for field in ("conflicts","propagations","restarts","decisions"):
                    pat=re.compile(r"^c\s+([0-9][0-9,]*)\s+"+field+r"\b",re.I)
                    hits=[int(m.group(1).replace(",","")) for l in interesting
                          if (m:=pat.search(l))]
                    numeric[field]=hits[-1] if len(hits)==1 else None
                r=dict(id=c["id"],sha256=c["sha256"],mode=mode,code=code,
                       status=status,wall_s=round(elapsed,6),
                       conflict_cap=5000,statistics=numeric,
                       raw_counter_lines=interesting[:36],
                       exploratory_after_audit=True)
                results.append(r)
                print("TURN2_DIAG",json.dumps(r,sort_keys=True),flush=True)
    save(ROOT/"diagnostics.json",dict(protocol=PROTO,events=results,
         measured_after_audit=True,not_used_for_primary_benchmark=True,
         warning="Solver statistics are available only if emitted and parsed unambiguously."))
    print("TURN2_DIAG_PASS",len(results),flush=True)


def selftest():
    rng=random.Random(20261107)
    for _ in range(35):
        n=5
        clauses=[[rng.choice((-1,1))*rng.randint(1,n)
                  for _ in range(rng.randrange(5))] for _ in range(rng.randrange(12))]
        for mode in MODES:
            transformed,mp=transformation(n,clauses,mode)
            for bits in itertools.product((False,True),repeat=n):
                model=dict(enumerate(bits,1))
                original=t1.inverse_model(model,mp)
                need(t1.satisfies(clauses,original)==
                     t1.satisfies(transformed,model),"exhaustive truth equivalence")
    print("TURN2_SELFTEST_PASS",35*len(MODES)*2**5,flush=True)


def smoke():
    selftest()
    with tempfile.TemporaryDirectory() as tmp:
        for name,clauses,verdict in (
            ("sat",[[1],[-1,2]],"SAT"),
            ("unsat",[[1],[-1]],"UNSAT")):
            p=pathlib.Path(tmp)/(name+".cnf")
            t1.write_cnf(p,3,clauses)
            for mode in MODES:
                dest=pathlib.Path(tmp)/(name+"-"+mode)
                dest.mkdir()
                r=subprocess.run([sys.executable,__file__,"worker","--source",
                   str(p),"--mode",mode,"--directory",str(dest)],
                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=20)
                need(r.returncode==0,"worker smoke: "+mode+" "+r.stdout[-500:]+r.stderr[-500:])
                result=json.loads(r.stdout.splitlines()[-1])
                need(result["status"]==verdict,"wrong smoke verdict")
    print("TURN2_SMOKE_PASS",2*len(MODES),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("fetch","selftest","smoke","shard","audit",
                                         "worker","diagnose"))
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--source")
    parser.add_argument("--mode",choices=MODES)
    parser.add_argument("--directory")
    args=parser.parse_args()
    if args.action=="worker":
        worker(args.source,args.mode,args.directory)
    elif args.action=="shard":
        shard(args.shard)
    else:
        globals()[args.action]()
