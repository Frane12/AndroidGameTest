#!/usr/bin/env python3
"""R32g: proof-checked cooperative SAT portfolio versus independent race.

Two native Kissat workers normally race (OFF and R32e). In cooperative mode,
the active worker STREAMS its mathematically proven original-source root
GF(2) literals through a coordinator. If the other worker remains active
past a frozen 20ms guard, the coordinator independently certifies the signed
literals, stops that worker and restarts it on the original CNF plus only
those entailed unit clauses. The producer continues solving in parallel.
One restart maximum; no exchange of unverified learnt clauses. This is a
limited root-clause relay, NOT live in-process CDCL clause sharing.

Timing: timestamp the candidate's terminal status BEFORE the expensive
offline source-proof/witness audit. Verify all verdicts after timing, and
include launch, relay, restarting and polling in wall clock; include total
children CPU time. Compare clean, native OFF, R32e, independent race, relay.
"""
from __future__ import annotations
import argparse,collections,functools,json,os,random,re,resource,statistics
import subprocess,tempfile,time
from pathlib import Path
import r31_consistent_gf2_test as r31
import r32b_native_shadow_benchmark as b
import r32f_safe_portfolio_benchmark as f

PROTO="DRNAS-R32G-COOPERATIVE-VERIFIED-UNIT-RELAY-20261103-v1"
MODES=("clean","native_off","r32e_active","independent_race","cooperative_relay")
BASE_FAMILIES=("consistent_visible","consistent_hidden","consistent_mixed",
               "root_unsat","xor_decoy","planted_random3")
STRESS_FAMILIES=("consistent_visible","consistent_hidden","consistent_mixed")
CAP=8.0
REPEATS=3
SHARDS=4
RELAY_START_S=0.020
POLL_S=0.0005

# Cache independent original-CNF proofs; benchmarking includes the actual
# native GF2 producer calculation but excludes repeated scientific audit.
r31.structure=functools.lru_cache(maxsize=128)(r31.structure)
b.r30.parse_dimacs=functools.lru_cache(maxsize=128)(b.r30.parse_dimacs)

def check(ok,why):
    if not ok:raise RuntimeError("R32G_AUDIT_FAILURE "+str(why))
def sha(x):return b.sha(x)
def freeze(dest):
    out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    def add(family,index,cohort,n,clauses,expected):
        raw=r31.encode(n,clauses)
        name=f"r32g_{cohort}_{family}_{index:02d}.cnf"
        (out/name).write_bytes(raw)
        cases.append(dict(name=name,family=family,expected=expected,
                          cohort=cohort,sha256=sha(raw)))
    for family in BASE_FAMILIES:
        for idx in range(80,83):
            n,clauses,label,_=r31.make_case(family,idx)
            add(family,idx,"base",n,clauses,label)
    for family in STRESS_FAMILIES:
        for idx in range(90,96):
            n,clauses,label,truth=r31.make_case(family,idx)
            rng=random.Random(int(sha((PROTO+"/"+family+"/"+str(idx)).encode()),16))
            extra=380+40*(idx%2)
            bg=list(range(n+1,n+extra+1))
            for v in bg:truth[v]=rng.getrandbits(1)
            n+=extra
            clauses += [r31.planted_clause(rng,bg,truth) for _ in range(int(extra*4.23))]
            copies=8+4*(idx%2)
            for j in range(290):
                bridge=4*(j%copies+1)
                others=rng.sample(bg,2)
                cl=[-bridge]+[v if rng.getrandbits(1) else -v for v in others]
                if not any((lit>0)==bool(truth[abs(lit)]) for lit in cl):
                    cl[1]*=-1
                clauses.append(cl)
            rng.shuffle(clauses)
            check(all(any((lit>0)==bool(truth[abs(lit)]) for lit in cl)
                          for cl in clauses),"Invalid stress SAT witness")
            add(family,idx,"coupled_stress",n,clauses,label)
    check(len(cases)==36 and len({c["sha256"] for c in cases})==36,
          "Need 36 SHA-distinct source formulas")
    manifest=dict(protocol=PROTO,modes=MODES,repeats=REPEATS,shards=SHARDS,
       cap_seconds=CAP,relay_delay_s=RELAY_START_S,
       total_trials=len(cases)*REPEATS*len(MODES),cases=cases,
       upstream_pin="8af8e56f174b778aef3aa45af9f739b2a5f492c2",
       warnings=[
          "All source formulas are new generated SYNTHETIC inputs, not official instances",
          "Relay shares independently verified original-CNF root units only",
          "No sharing of learnt clauses or in-process restart state",
          "Relay kills and restarts the OFF worker at most once after 20ms",
          "Elapsed wall excludes slow Python audit but includes spawning, polling, relay and restart",
          "Child CPU includes all attempted solvers, not Python parent",
          "SAT models checked on original CNF; UNSAT correctness follows generator label, no LRAT",
          "8s timeout, PAR2=16s. Performance is not general SAT ranking"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(
        f'{c["sha256"]}  {c["name"]}\n' for c in cases))
    print("R32G_FROZEN",len(cases),"trials",manifest["total_trials"],
          "SHA",sha(out/"manifest.json"),flush=True)

def make_augmented(original,units,target):
    lines=Path(original).read_text().splitlines()
    head=lines[0].split()
    check(len(head)==4 and head[:2]==["p","cnf"],"Cannot safely alter DIMACS header")
    orig=int(head[3])
    actual=sum(1 for line in lines[1:] if line.strip() and not line.startswith("c"))
    check(actual==orig,"Untrusted DIMACS clause count")
    check(len(set(map(abs,units)))==len(units) and
          all(1<=abs(v)<=int(head[2]) for v in units),"Malformed root unit")
    lines[0]=f"p cnf {head[2]} {orig+len(units)}"
    Path(target).write_text("\n".join(lines+[str(u)+" 0" for u in units])+"\n")

def start(binary,source,mode,core,outpath):
    out=open(outpath,"w")
    env=os.environ.copy()
    env["R32B_MODE"]="r32e" if mode=="r32e_active" else "off"
    def affinity():os.sched_setaffinity(0,{core})
    p=subprocess.Popen([str(binary),str(source)],stdout=out,
        stderr=subprocess.DEVNULL,env=env,preexec_fn=affinity)
    out.close()
    return p

def reap(p):
    if p is None:return
    if p.poll() is None:p.kill()
    p.wait()

def audit_status(case,original,output,returncode,mode):
    # Audits are intentionally AFTER the measured terminal timestamp.
    status,verification,final=f.verify(case,original,output,returncode,mode)
    return status,verification,final

def solo(case,source,mode,bins,core):
    starting_cpu=f.cpu_usage()
    start_s=time.monotonic()
    binpath=bins["clean"] if mode=="clean" else bins["native"]
    with tempfile.TemporaryDirectory(prefix="r32g-") as temp:
        output=Path(temp)/"single.log"
        p=start(binpath,source,mode,core,output)
        try:p.wait(timeout=CAP)
        except subprocess.TimeoutExpired:
            reap(p)
            return dict(status="TIMEOUT",wall_s=time.monotonic()-start_s,
                        par2=CAP*2,cpu_s=f.cpu_usage()-starting_cpu,
                        winner=None,conflicts=None,relayed=False,relayed_units=0)
        end_s=time.monotonic()
        code=p.returncode
        reap(p)
        used_cpu=f.cpu_usage()-starting_cpu
        status,verification,final=audit_status(case,source,output.read_text(),code,mode)
        return dict(status=status,wall_s=round(end_s-start_s,6),
                    par2=round(end_s-start_s,6),cpu_s=round(used_cpu,6),
                    winner=mode,conflicts=final["conflicts"] if final else None,
                    relayed=False,relayed_units=0)

def parallel(case,source,mode,bins,cores,proof_literals):
    startcpu=f.cpu_usage();started=time.monotonic()
    relay=mode=="cooperative_relay"
    processes={};output_files={};pending=None;relayed=False;count=0
    with tempfile.TemporaryDirectory(prefix="r32g-") as tmp:
        directory=Path(tmp)
        output_files["native_off"]=directory/"native_off.log"
        output_files["r32e_active"]=directory/"r32e.log"
        processes["native_off"]=start(bins["native"],source,"native_off",
                                       cores[0],output_files["native_off"])
        processes["r32e_active"]=start(bins["native"],source,"r32e_active",
                                         cores[1],output_files["r32e_active"])
        read_fd=open(output_files["r32e_active"],"r") if relay else None
        buffered=""
        winner=None
        verdict=None
        wall=None
        try:
            while time.monotonic()-started<CAP:
                for which in ("native_off","r32e_active"):
                    if processes[which].poll() is not None:
                        winner=which
                        wall=time.monotonic()-started
                        code=processes[which].returncode
                        # Kill the still-running competitor and keep source file.
                        for alt,p in processes.items():
                            if alt!=winner:reap(p)
                        status,verified,final=audit_status(
                            case,source,output_files[which].read_text(),
                            code,which)
                        verdict=(status,final)
                        break
                if winner is not None:break
                if relay:
                    extra=read_fd.read()
                    if extra:
                        buffered+=extra
                        while "\n" in buffered:
                            line,buffered=buffered.split("\n",1)
                            if line.startswith("c R32C_INJECTED_LITS "):
                                match=re.fullmatch(
                                    r"c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)",line)
                                check(match is not None,"Malformed sender root message")
                                sent=[int(x) for x in match.group(2).split(",")]
                                check(int(match.group(1))==len(sent) and
                                      0<len(sent)<=12 and
                                      len(set(sent))==len(sent) and
                                      set(sent).issubset(proof_literals),
                                      "Sender transmitted uncertified XOR literal")
                                pending=sent
                    if (pending and not relayed and
                        time.monotonic()-started>=RELAY_START_S and
                        processes["native_off"].poll() is None):
                        # This is the actual one-way communication:
                        # sender -> verified root unit message -> receiver restart.
                        reap(processes["native_off"])
                        aug=directory/"relayed.cnf"
                        make_augmented(source,pending,aug)
                        output_files["native_off"]=directory/"relayed.log"
                        processes["native_off"]=start(bins["native"],aug,
                                 "native_off",cores[0],output_files["native_off"])
                        relayed=True;count=len(pending)
                time.sleep(0.0005)
            if winner is None:
                wall=time.monotonic()-started
                for p in processes.values():reap(p)
                return dict(status="TIMEOUT",wall_s=round(wall,6),par2=CAP*2,
                    cpu_s=round(f.cpu_usage()-startcpu,6),winner=None,
                    conflicts=None,relayed=relayed,relayed_units=count,
                    root_message_seen=bool(pending))
            usedcpu=f.cpu_usage()-startcpu
            status,final=verdict
            return dict(status=status,wall_s=round(wall,6),par2=round(wall,6),
                cpu_s=round(usedcpu,6),winner=winner,
                conflicts=final["conflicts"] if final else None,
                relayed=relayed,relayed_units=count,
                root_message_seen=bool(pending))
        finally:
            if read_fd:read_fd.close()
            for p in processes.values():
                if p.poll() is None:reap(p)

def measure(a):
    directory=Path(a.inputs)
    manifest=json.loads((directory/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and len(manifest["cases"])==36,
          "Wrong R32g frozen protocol")
    check(0<=a.shard<SHARDS,"Shard out of range")
    cores=sorted(os.sched_getaffinity(0))
    check(len(cores)>=2,"At least two CPU cores required")
    cores=cores[:2]
    bins={k:Path(getattr(a,k)).resolve() for k in ("clean","native")}
    check(all(v.is_file() for v in bins.values()),"Missing binary pair")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
          shard=a.shard,manifest_sha256=sha(directory/"manifest.json"),
          binaries={k:sha(v) for k,v in bins.items()},cores=cores),indent=2))
    rows=[]
    for case in manifest["cases"][a.shard::SHARDS]:
        source=directory/case["name"]
        check(sha(source)==case["sha256"],"Source CNF modified")
        independent,ctx=r31.structure(source)
        proof_literals={int(u["literal"]) for u in independent["units"]}
        if independent["signal"]!="CONSISTENT_EXTRA_UNITS":
            check(not proof_literals,"Unsafe root unit source state")
        for rep in range(REPEATS):
            modes=list(MODES)
            rng=random.Random(int(sha((case["sha256"]+str(rep)+":R32G").encode()),16))
            rng.shuffle(modes)
            for mode in modes:
                if mode in ("independent_race","cooperative_relay"):
                    row=parallel(case,source,mode,bins,cores,proof_literals)
                else:
                    row=solo(case,source,mode,bins,cores[0])
                rows.append(dict(case=case["name"],cohort=case["cohort"],
                         family=case["family"],repeat=rep,mode=mode,**row))
                print("R32G_TRIAL",a.shard,case["name"],rep,mode,
                      row["status"],row["wall_s"],"winner",row["winner"],
                      "relay",row["relayed"],"cpu",row["cpu_s"],flush=True)
        (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32G_SHARD_PASS",a.shard,len(rows),flush=True)

def aggregate(a):
    root=Path(a.inputs);manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO,"Wrong frozen benchmark source")
    rows=[];fingerprints=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r32g-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["shard"]==shard and
              meta["manifest_sha256"]==sha(root/"manifest.json"),"Manifest SHA drift")
        fingerprints.add(json.dumps(meta["binaries"],sort_keys=True))
        part=json.loads((folder/"rows.json").read_text())
        check(len(part)==len(manifest["cases"][shard::SHARDS])*REPEATS*len(MODES),
              "Incomplete paired shard")
        rows.extend(part)
    check(len(rows)==manifest["total_trials"]==540 and len(fingerprints)==1,
          "Require 540 trials on frozen binary fingerprints")
    groups={"ALL":manifest["cases"]}
    for cohort in ("base","coupled_stress"):
        groups[cohort]=[c for c in manifest["cases"] if c["cohort"]==cohort]
    for fam in BASE_FAMILIES:
        groups[fam]=[c for c in manifest["cases"] if c["family"]==fam]
    summary={}
    for group,cases in groups.items():
        names={c["name"] for c in cases}
        score={}
        for mode in MODES:
            seq=[r for r in rows if r["mode"]==mode and r["case"] in names]
            score[mode]=dict(par2_s=round(sum(r["par2"] for r in seq),6),
                            cpu_s=round(sum(r["cpu_s"] for r in seq),6),
                            timeouts=sum(r["status"]=="TIMEOUT" for r in seq),
                            n=len(seq))
        for mode in ("independent_race","cooperative_relay"):
            d=score[mode];baseline=score["native_off"]
            d["change_vs_off_pct"]=round(100*(d["par2_s"]-
                         baseline["par2_s"])/baseline["par2_s"],4)
            d["CPU_vs_off_pct"]=round(100*(d["cpu_s"]-
                         baseline["cpu_s"])/baseline["cpu_s"],4)
            seq=[r for r in rows if r["mode"]==mode and r["case"] in names]
            d["winners"]=dict(collections.Counter(r["winner"] for r in seq))
            d["actually_relayed_trials"]=sum(r["relayed"] for r in seq)
            d["relay_msgs"]=sum(r["root_message_seen"] for r in seq
                                  if "root_message_seen" in r)
        summary[group]=score
        print("R32G_SUMMARY",group,json.dumps(score,sort_keys=True),flush=True)
    bycase={case["name"]:[r for r in rows if r["case"]==case["name"]]
            for case in manifest["cases"]}
    percase=[]
    for case in manifest["cases"]:
        seq=bycase[case["name"]]
        for rep in range(REPEATS):
            check(len([r for r in seq if r["repeat"]==rep])==len(MODES),
                  "Incomplete matched modes")
            found={r["status"] for r in seq if r["repeat"]==rep}-{"TIMEOUT"}
            check(len(found)<=1,"SAT/UNSAT disagreement between solvers")
        med={mode:statistics.median(r["par2"] for r in seq if r["mode"]==mode)
             for mode in MODES}
        percase.append(dict(name=case["name"],family=case["family"],
             cohort=case["cohort"],median_par2=med,
             relay_count=sum(r["relayed"] for r in seq
                             if r["mode"]=="cooperative_relay")))
    rng=random.Random(32026)
    draws=[]
    for _ in range(2500):
        sample=[rng.choice(percase) for _ in percase]
        orig=sum(c["median_par2"]["native_off"] for c in sample)
        linked=sum(c["median_par2"]["cooperative_relay"] for c in sample)
        draws.append(100*(linked-orig)/orig)
    draws.sort()
    summary["ALL"]["bootstrap_median_95_pct"]=[round(draws[62],3),round(draws[2437],3)]
    output=dict(protocol=PROTO,summary=summary,percase=percase,
                rows=rows,warnings=manifest["warnings"],
                source_manifest_sha256=sha(root/"manifest.json"))
    Path(a.output).write_text(json.dumps(output,indent=2)+"\n")
    md=["# DRNAS R32g cooperative certified root-clause relay",
        "36 fresh synthetic originals, 3 repeats x 5 modes = 540 attempts.",
        "Real producer->coordinator->receiver communication via signed GF2 units.",
        "At most one OFF restart when active worker sends valid source units.",
        "Wall is marked on solver status BEFORE slow independent validation.",
        "Original-CNF SAT witness audited in every completed trial.",
        "No external industrial SAT or true in-process learned-clause sharing.",
        f'Case-bootstrap 95% interval on relay vs native OFF: {summary["ALL"]["bootstrap_median_95_pct"]}%.',
        "","| Group | Clean s | Native OFF s | R32e s | Independent race s | Cooperative relay s | Relay vs OFF | Relay CPU vs OFF | Actual restarts |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for group,score in summary.items():
        c=score["cooperative_relay"]
        md.append(f'| {group} | {score["clean"]["par2_s"]:.5f} | {score["native_off"]["par2_s"]:.5f} | {score["r32e_active"]["par2_s"]:.5f} | {score["independent_race"]["par2_s"]:.5f} | {c["par2_s"]:.5f} | {c["change_vs_off_pct"]:+.3f}% | {c["CPU_vs_off_pct"]:+.2f}% | {c["actually_relayed_trials"]} |')
    md+=["","| Formula | Cohort | Native OFF median s | Active median s | Race median s | Relay median s | Restarts (of 3) |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for p in percase:
        m=p["median_par2"]
        md.append(f'| {p["name"]} | {p["cohort"]} | {m["native_off"]:.6f} | {m["r32e_active"]:.6f} | {m["independent_race"]:.6f} | {m["cooperative_relay"]:.6f} | {p["relay_count"]} |')
    Path(a.report).write_text("\n".join(md)+"\n")
    print("R32G_AUDIT_PASS",len(rows),"trials",len(percase),"originals",flush=True)

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="task",required=True)
    q=sub.add_parser("freeze");q.add_argument("--dest",required=True)
    q=sub.add_parser("measure")
    for n in ("inputs","clean","native","outdir"):q.add_argument("--"+n,required=True)
    q.add_argument("--shard",required=True,type=int)
    q=sub.add_parser("aggregate")
    for n in ("inputs","combined","output","report"):q.add_argument("--"+n,required=True)
    a=ap.parse_args()
    if a.task=="freeze":freeze(a.dest)
    elif a.task=="measure":measure(a)
    else:aggregate(a)

if __name__=="__main__":
    main()
