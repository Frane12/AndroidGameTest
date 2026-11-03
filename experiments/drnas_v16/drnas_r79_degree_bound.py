#!/usr/bin/env python3
"""DRNAS R79 stronger LOWER BOUND, unchanged shared-route TSP search.

Two arms, each using exactly four CPU-pinned workers:
  independent: isolated first-hop partitions; only local upper bound per worker.
  shared: publish each better complete tour to a shared upper bound immediately.

The benchmark retains R79 route sharing, DFS ordering, process layout and MST bound.
The ONLY new search intervention is max(old_MST_bound, degree-2_remaining_bound).
The new admissible bound is checked only if the old one cannot prune.
No soft deferral; no learned or heuristic permanent branch discards.
"""
from __future__ import annotations
import argparse, functools, hashlib, itertools, json, math, multiprocessing as mp
import os, random, time
from multiprocessing.connection import wait
from pathlib import Path

PROTO = "DRNAS-R79-COOPERATIVE-TSP-EXACT-20261103-v1"
SEED = 7411032026
MODES = ("independent", "shared")
COUNTS = ((16,"uniform"), (18,"cluster"), (20,"uniform"), (22,"cluster"))
SHARDS = 4
WORKERS = 4
REPS = 2
CAP = 7.0
METRICS = ("nodes","pruned","shared_only","complete_tours","improved",
           "peer_events","degree_checked","degree_extra_pruned")

def ck(ok,msg):
    if not ok:raise RuntimeError("R79_FAIL_CLOSED "+str(msg))

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def make_graph(n,kind):
    rng=random.Random(SEED+n*113+sum(map(ord,kind)))
    coords=[]
    for i in range(n):
        if kind=="cluster":
            anchors=((170,160),(810,200),(220,790),(790,800))
            cx,cy=anchors[i%4]
            x=max(1,min(999,cx+rng.randrange(-120,121)))
            y=max(1,min(999,cy+rng.randrange(-120,121)))
        else:x,y=rng.randrange(1,1000),rng.randrange(1,1000)
        coords.append((x,y))
    ck(len(set(coords))==n,"coordinate collision")
    dist=[[0 if i==j else max(1,math.isqrt(
        (coords[i][0]-coords[j][0])**2+
        (coords[i][1]-coords[j][1])**2)//10) for j in range(n)]for i in range(n)]
    ck(all(dist[i][j]==dist[j][i] and (i==j or dist[i][j]>0)
           for i in range(n) for j in range(n)),"not symmetric metric graph")
    return coords,dist

def nearest_neighbor(d):
    n=len(d);visited={0};tour=[0]
    while len(tour)<n:
        last=tour[-1]
        v=min((v for v in range(1,n) if v not in visited),
              key=lambda v:(d[last][v],v))
        tour.append(v);visited.add(v)
    tour.append(0)
    return tour,route_cost(d,tour)

def route_cost(d,tour):
    return sum(d[a][b] for a,b in zip(tour,tour[1:]))

def validate(d,tour,cost):
    n=len(d)
    ck(tour[0]==tour[-1]==0 and len(tour)==n+1 and
       set(tour[:-1])==set(range(n)),"invalid full TSP tour")
    ck(route_cost(d,tour)==cost,"claimed cost mismatch")

def freeze(folder):
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    cases=[]
    for n,kind in COUNTS:
        coords,d=make_graph(n,kind);initial,upper=nearest_neighbor(d)
        item=dict(protocol=PROTO,n=n,kind=kind,coords=coords,dist=d,
                  initial_tour=initial,initial_upper=upper)
        p=root/f"r79_{n}_{kind}.json"
        p.write_text(json.dumps(item,sort_keys=True,separators=(',',':'))+"\n")
        data=dict(name=p.name,sha256=sha(p),n=n,kind=kind,initial_upper=upper)
        cases.append(data)
        print("R79_SOURCE_FROZEN",n,kind,"nearest_neighbor",upper,flush=True)
    m=dict(protocol=PROTO,methods=list(MODES),cases=cases,repeats=REPS,
           workers=WORKERS,shards=SHARDS,cap_s=CAP,seed=SEED,
           notes=[
             "Fresh deterministic synthetic coordinate TSP, NOT TSPLIB/official",
             "Dedicated exact MST branch-and-bound prototype, NOT SAT/Kissat",
             "All methods use four separately pinned CPUs and identical partition",
             "Independent workers combine answers only at end",
             "Shared workers publish strictly improving complete-route UB",
             "Timeout may leave optimum UNPROVEN; correct upper-bound tour verified",
             "R79 changes only exact lower-bound pruning; extra bound is max(MST,degree-2)",
             "No claim of solver superiority from one seed/four sizes"
           ])
    (root/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
    (root/"source.sha256").write_text(''.join(c["sha256"]+"  "+c["name"]+"\n" for c in cases))
    print("R79_FREEZE_PASS",sha(root/"manifest.json"),flush=True)

def degree_completion_bound(d,ordered,last,unseen,vals,last_min,home_min):
    """Admissible cost LB for Hamiltonian LAST -> all unseen -> 0.

    In every valid remaining path, last and home have degree one; each
    unseen vertex has degree exactly two, among the unseen vertices
    and those two endpoints. Counting the minimum incident edge sum at
    each vertex counts every actual path edge twice. Ceil of half yields
    a safe integer LB. This bound never discards on statistical guesses.
    """
    ck(last!=0 and unseen and len(vals)>=1,"invalid residual degree problem")
    allowed=unseen|(1<<last)|1
    degree_sum=last_min+home_min
    for city in vals:
        found=0
        for other in ordered[city]:
            if allowed & (1<<other):
                degree_sum+=d[city][other]
                found+=1
                if found==2:break
        ck(found==2,"not enough distinct degree neighbors")
    return (degree_sum+1)//2


def worker(wid,d,mode,initial_best,shared_best,shared_updates,lock,
           start_event,base_time,progress,finished,bests,conn,cpuid):
    """Only this worker writes its own progress and done flag."""
    try:
        os.sched_setaffinity(0,{cpuid})
        n=len(d);allbits=(1<<n)-1
        counts=[0]*len(METRICS)
        local=initial_best;seen_update=0
        bests[wid]=local
        @functools.lru_cache(maxsize=100000)
        def mst(mask):
            if not mask or mask.bit_count()==1:return 0
            vs=[i for i in range(1,n) if (mask>>i)&1]
            taken={vs[0]}
            price={j:d[vs[0]][j] for j in vs[1:]}
            total=0
            while len(taken)<len(vs):
                j=min(price,key=lambda v:(price[v],v))
                total+=price.pop(j);taken.add(j)
                for k in price:
                    if d[j][k]<price[k]:price[k]=d[j][k]
            return total

        # Pre-sort distances once per worker. No change to DFS or sharing.
        ordered=tuple(tuple(sorted((j for j in range(n) if j!=i),
                       key=lambda j:(d[i][j],j))) for i in range(n))
        def lb(last,unseen,cost,upper):
            if not unseen:return cost+d[last][0]
            vals=[j for j in range(1,n) if (unseen>>j)&1]
            last_min=min(d[last][j] for j in vals)
            home_min=min(d[0][j] for j in vals)
            old_bound=cost+mst(unseen)+last_min+home_min
            if old_bound>=upper:return old_bound
            counts[6]+=1
            degree=cost+degree_completion_bound(
                d,ordered,last,unseen,vals,last_min,home_min)
            if degree>=upper:
                counts[7]+=1
            return max(old_bound,degree)

        ready=[(v,(1|(1<<v)),d[0][v],(0,v))
               for v in range(1,n) if (v-1)%WORKERS==wid]
        # Same deterministic DFS from smaller first-hop distances.
        ready.sort(key=lambda z:(d[0][z[0]],z[0]),reverse=True)
        stack=ready
        first=0.0
        def publish():
            offset=wid*len(METRICS)
            for i,x in enumerate(counts):progress[offset+i]=x
            bests[wid]=local

        start_event.wait()
        while stack:
            last,visited,cost,path=stack.pop()
            counts[0]+=1
            if mode!="independent" and shared_updates.value!=seen_update:
                seen_update=shared_updates.value
                counts[5]+=1
            upper=min(local,shared_best.value) if mode!="independent" else local
            unseen=allbits^visited
            bound=lb(last,unseen,cost,upper)
            if bound>=upper:
                counts[1]+=1
                if mode!="independent" and upper<local and bound<local:
                    counts[2]+=1
                if counts[0]%256==0:publish()
                continue
            if not unseen:
                total=bound
                counts[3]+=1
                if total<local:
                    local=total;counts[4]+=1
                    if first==0:first=time.monotonic()-base_time.value
                    completed=path+(0,)
                    validate(d,completed,total)
                    conn.send(("improvement",wid,total,completed,
                               round(time.monotonic()-base_time.value,6)))
                    if mode!="independent":
                        with lock:
                            if total<shared_best.value:
                                shared_best.value=total
                                shared_updates.value+=1
                if counts[0]%256==0:publish()
                continue
            choices=[v for v in range(1,n) if (unseen>>v)&1]
            choices.sort(key=lambda v:(d[last][v],d[v][0],v),reverse=True)
            for v in choices:
                stack.append((v,visited|(1<<v),cost+d[last][v],
                              path+(v,)))
            if counts[0]%256==0:publish()
        publish()
        finished[wid]=1
        conn.send(("finished",wid,list(counts),local,round(time.monotonic()-base_time.value,6)))
    except BaseException as exc:
        try:conn.send(("error",wid,repr(exc)))
        except Exception:pass
    finally:
        conn.close()

def trial(d,mode,cpus,cap):
    ck(mode in MODES,"mode")
    ck(len(cpus)>=WORKERS,"need four distinct CPUs")
    initial,initial_upper=nearest_neighbor(d)
    ctx=mp.get_context("fork")
    best=ctx.RawValue("q",initial_upper)
    updates=ctx.RawValue("i",0)
    lock=ctx.Lock()
    start=ctx.Event()
    base_time=ctx.RawValue("d",0.)
    progress=ctx.RawArray("q",WORKERS*len(METRICS))
    finished=ctx.RawArray("i",WORKERS)
    bests=ctx.RawArray("q",[initial_upper]*WORKERS)
    procs=[];readers=[]
    original_started=time.monotonic()
    try:
        for wid in range(WORKERS):
            recv,send=ctx.Pipe(duplex=False)
            p=ctx.Process(target=worker,args=(
                wid,d,mode,initial_upper,best,updates,lock,
                start,base_time,progress,finished,bests,send,cpus[wid]))
            p.start();send.close()
            procs.append(p);readers.append(recv)
        setup_time=time.monotonic()-original_started
        ck(setup_time<min(4,cap/2),"worker startup exceeded budget")
        base_time.value=time.monotonic()
        start.set()
        deadline=base_time.value+cap
        candidates=[dict(cost=initial_upper,tour=initial,time_s=0.0)]
        errors=[];last_done={}
        messages=0
        while time.monotonic()<deadline:
            active=[c for c in readers if not c.closed]
            if not active:break
            avail=wait(active,timeout=.025)
            for pipe in avail:
                try:rec=pipe.recv()
                except EOFError:pipe.close();continue
                if rec[0]=="improvement":
                    _,wid,cost,tour,at=rec
                    validate(d,tour,cost)
                    candidates.append(dict(cost=cost,tour=tour,time_s=at,worker=wid))
                    messages+=1
                elif rec[0]=="finished":
                    last_done[rec[1]]=rec
                else:errors.append(rec)
            ck(not errors,"worker error "+repr(errors))
            if len(last_done)==WORKERS:break
        elapsed=min(cap,time.monotonic()-base_time.value)
        for p in procs:
            if p.is_alive():p.terminate()
        for p in procs:p.join(timeout=2)
        for c in readers:
            if c.closed:continue
            while c.poll():
                try:rec=c.recv()
                except EOFError:break
                if rec[0]=="improvement":
                    _,wid,cost,tour,at=rec
                    validate(d,tour,cost)
                    candidates.append(dict(cost=cost,tour=tour,time_s=at,worker=wid))
                elif rec[0]=="finished":last_done[rec[1]]=rec
                elif rec[0]=="error":errors.append(rec)
            c.close()
        ck(not errors,"worker error "+repr(errors))
        # Every reported best MUST have a complete witnessed Hamiltonian tour.
        winner=min(candidates,key=lambda c:(c["cost"],c["time_s"]))
        counts={key:int(sum(progress[w*len(METRICS)+i] for w in range(WORKERS)))
                for i,key in enumerate(METRICS)}
        # Final packet contains exact counters even if <256 updates were pending.
        for wid,rec in last_done.items():
            for i,key in enumerate(METRICS):
                old=int(progress[wid*len(METRICS)+i])
                counts[key]+=rec[2][i]-old
        complete=len(last_done)==WORKERS
        ck(not complete or all(finished),"finished flag conflict")
        return dict(mode=mode,n=len(d),best=winner["cost"],tour=winner["tour"],
                    initial_upper=initial_upper,improvement=initial_upper-winner["cost"],
                    first_improve_s=round(min((c["time_s"] for c in candidates
                         if c["cost"]<initial_upper),default=cap),6),
                    elapsed_s=round(elapsed,6),setup_s=round(setup_time,6),
                    proven_optimum=complete,finished_workers=len(last_done),
                    signals_sent=updates.value if mode!="independent" else 0,
                    proposals=messages,**counts)
    finally:
        for p in procs:
            if p.is_alive():p.terminate()
            p.join(timeout=1)
        for c in readers:
            if not c.closed:c.close()

def selftest():
    # New degree lower bound must NEVER exceed a real completion.
    for n in (5,6,7):
        _,d=make_graph(n,"uniform")
        ordered=tuple(tuple(sorted((j for j in range(n) if j!=i),
                      key=lambda j:(d[i][j],j))) for i in range(n))
        rng=random.Random(n*9149)
        for _ in range(25):
            seq=list(range(1,n));rng.shuffle(seq)
            visited_count=rng.randrange(1,n-1)
            path=[0]+seq[:visited_count]
            last=path[-1]
            unseen=seq[visited_count:]
            mask=sum(1<<v for v in unseen)
            endpoint=min(d[last][v] for v in unseen)
            home=min(d[0][v] for v in unseen)
            bound=degree_completion_bound(d,ordered,last,mask,unseen,endpoint,home)
            exact=min(sum(d[x][y] for x,y in zip(
                          (last,)+order,order+(0,)))
                      for order in itertools.permutations(unseen))
            ck(bound<=exact,"degree bound inadmissible, would prune optimum")
    print("R79_DEGREE_BOUND_EXHAUSTIVE_SUFFIX_SELFTEST_PASS",flush=True)
    # Baseline MST is admissible: for 6/7/8 cities both modes must
    # return the exact brute-force minimum and prove completion.
    cpus=sorted(os.sched_getaffinity(0))
    ck(len(cpus)>=WORKERS,"requires four CPUs")
    for n in (6,7,8):
        d=make_graph(n,"uniform")[1]
        true=min(route_cost(d,(0,)+p+(0,)) for p in itertools.permutations(range(1,n)))
        for mode in MODES:
            x=trial(d,mode,cpus,cap=3.0)
            ck(x["proven_optimum"] and x["best"]==true,
               "exact small-case / MST admissibility failure "+str((n,mode,x)))
    print("R79_EXACT_FOUR_WORKER_SELFTEST_PASS",flush=True)

def measure(a):
    root=Path(a.sources);m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and m["methods"]==list(MODES)
       and len(m["cases"])==SHARDS and m["cap_s"]==CAP,"protocol drift")
    ck(0<=a.shard<SHARDS,"shard")
    cpus=sorted(os.sched_getaffinity(0))
    ck(len(cpus)>=WORKERS,"cannot compare 4 worker processes on <4 cores")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(protocol=PROTO,
        shard=a.shard,manifest_sha=sha(root/"manifest.json"),cpus=cpus[:4],
        runner=os.getenv("RUNNER_NAME","local")),indent=2)+"\n")
    rows=[]
    for c in m["cases"][a.shard::SHARDS]:
        source=root/c["name"]
        ck(sha(source)==c["sha256"],"source drift")
        spec=json.loads(source.read_text())
        ck(spec["protocol"]==PROTO and spec["n"]==c["n"],"source mismatch")
        d=spec["dist"]
        route,upper=nearest_neighbor(d)
        ck(upper==spec["initial_upper"] and route==spec["initial_tour"],
           "initial upper drift")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(hashlib.sha256((c["sha256"]+":"+str(rep)+":"+PROTO)
                .encode()).hexdigest(),16)).shuffle(order)
            for mode in order:
                z=trial(d,mode,cpus,CAP)
                validate(d,z["tour"],z["best"])
                if z["proven_optimum"] and c["n"]<=16:
                    import drnas_r72_tsp_sat as r72
                    optimum,_=r72.held_karp(d)
                    ck(z["best"]==optimum,"incorrect exact optimum")
                row=dict(case=c["name"],case_sha=c["sha256"],rep=rep,**z)
                rows.append(row)
                (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                print("R79_TRIAL",c["name"],rep,mode,
                  "cost",z["best"],"complete",z["proven_optimum"],
                  "wall",z["elapsed_s"],"nodes",z["nodes"],
                  "pruned",z["pruned"],"shared-only",z["shared_only"],
                  "signals",z["signals_sent"],flush=True)
    ck(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),"missing trials")

def audit(a):
    root=Path(a.sources);m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO,"wrong protocol")
    rows=[];seen=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r79-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        ck(meta["shard"]==shard and meta["protocol"]==PROTO and
           meta["manifest_sha"]==sha(root/"manifest.json"),"mixed manifest")
        ck(len(meta["cpus"])==WORKERS,"not four CPUs")
        part=json.loads((folder/"rows.json").read_text())
        ck(len(part)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),"partial")
        for z in part:
            k=(z["case"],z["rep"],z["mode"])
            ck(k not in seen,"duplicate row");seen.add(k)
            c=next(x for x in m["cases"] if x["name"]==z["case"])
            ck(z["case_sha"]==c["sha256"],"case SHA differs")
            d=json.loads((root/c["name"]).read_text())["dist"]
            validate(d,z["tour"],z["best"])
            ck(z["mode"] in MODES and
               z["best"]<=z["initial_upper"],"invalid cost or mode")
        rows.extend(part)
    ck(len(rows)==len(m["cases"])*REPS*len(MODES),"incomplete benchmark")
    summary={}
    for mode in MODES:
        v=[z for z in rows if z["mode"]==mode]
        summary[mode]=dict(attempts=len(v),
          proven=sum(z["proven_optimum"] for z in v),
          total_best_cost=sum(z["best"] for z in v),
          total_wall_s=round(sum(z["elapsed_s"] for z in v),4),
          total_nodes=sum(z["nodes"] for z in v),
          total_pruned=sum(z["pruned"] for z in v),
          shared_only_prunes=sum(z["shared_only"] for z in v),
          signals=sum(z["signals_sent"] for z in v))
    for c in m["cases"]:
        for rep in range(REPS):
            z=[x for x in rows if x["case"]==c["name"] and x["rep"]==rep]
            proven={x["best"] for x in z if x["proven_optimum"]}
            ck(len(proven)<=1,"two modes disagree on PROVEN optimum")
            if proven:ck(all(x["best"]>=next(iter(proven)) for x in z),
                         "candidate beats proven global optimum")
    report=dict(protocol=PROTO,summary=summary,rows=rows,
                limitations=m["notes"])
    Path(a.json).write_text(json.dumps(report,indent=2)+"\n")
    lines=[
      "# R79: four real-time cooperative TSP searchers",
      "Independent vs live shared best-route upper bound.",
      "Synthetic weighted Euclidean TSP, four CPU-pinned worker processes for EVERY mode.",
      "Only mathematically justified lower-bound pruning; no heuristic deferral.",
      "All claimed routes checked against original distance matrices. Proof only when every worker finishes.",
      "| Arm | Proven / 8 | Total best route lengths | Total wall s | Nodes | Pruned | Shared-only prunes | Signals |",
      "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        x=summary[mode]
        lines.append(f"| {mode} | {x['proven']}/8 | {x['total_best_cost']} | {x['total_wall_s']:.3f} | {x['total_nodes']} | {x['total_pruned']} | {x['shared_only_prunes']} | {x['signals']} |")
    lines+=["","| Cities | Kind | Rep | Independent cost / time | Shared cost / time |",
            "|---:|---|---:|---|---|"]
    for case in m["cases"]:
        for rep in range(REPS):
            rr={z["mode"]:z for z in rows if z["case"]==case["name"] and z["rep"]==rep}
            def fmt(mode):
                z=rr[mode];status="PROVEN" if z["proven_optimum"] else "unproven"
                return f"{z['best']} / {z['elapsed_s']:.3f}s ({status})"
            lines.append(f"| {case['n']} | {case['kind']} | {rep} | "+
                         " | ".join(fmt(k) for k in MODES)+" |")
    lines+=["","## Caveats"]+["- "+n for n in m["notes"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R79_FINAL_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="task",required=True)
    sub.add_parser("selftest")
    x=sub.add_parser("freeze");x.add_argument("--out",required=True)
    x=sub.add_parser("measure")
    for flag in ("sources","out"):x.add_argument("--"+flag,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sub.add_parser("audit")
    for flag in ("sources","combined","json","md"):x.add_argument("--"+flag,required=True)
    a=p.parse_args()
    {"selftest":lambda:selftest(),"freeze":lambda:freeze(a.out),
     "measure":lambda:measure(a),"audit":lambda:audit(a)}[a.task]()
if __name__=="__main__":main()
