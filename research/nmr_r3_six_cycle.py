#!/usr/bin/env python3
"""DRNAS Neural R3: six successive TRAIN-only epochs; paired held-out learning curve.

R2's same frozen SHA-disjoint 34/40 split, never uses held-out test data for
training. One controlled neural change: confidently correct updates abstain
and SGD decays with lifetime updates. A pre-registered <=3s budget guard is
evaluated as a separate ablation arm, not hidden inside the neural arm.

Seven frozen snapshots (0 through 6 epochs) evaluated against fresh clean
CaDiCaL per paired case+rep. This is a REUSED nonblind R2 holdout, not a
prospective external benchmark. Native UNSAT has no independent LRAT.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,pathlib,random,shutil,statistics
import nmr_r3_policy as policy
import nmr_r2_benchmark as r2

ROOT=pathlib.Path("nmr_r3")
FROZEN=pathlib.Path("new_horizon/frozen")
SPLIT=pathlib.Path("nmr_r2/split.json")
NATIVE=pathlib.Path("nmr_r2/nmr-driver")
CLEAN=pathlib.Path("new_horizon/r190-driver")
START=pathlib.Path("nmr_r2/model.sqlite")
R2_CHECKPOINT_SHA="50b262503e2e2d770fbed6da0688e9c2f7206ee5fe53bda36f469a805e35211b"
PROTO="DRNAS-NEURAL-R3-SIX-CYCLE-SELECTIVE-SGD-20261107-v1"
EPOCHS=tuple(range(7))
MODES=("clean","neural_live","neural_guarded")
REPS=2
SHARDS=4
GUARD_CAP=3.0

def need(flag,reason):
    if not flag: raise RuntimeError("NMR_R3_FAIL_CLOSED "+str(reason))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text())
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def checkpoint(epoch):return ROOT/"checkpoints"/f"epoch-{epoch:02d}.sqlite"

def verify_sources():
    d=r2.verify()
    need(len(d["training"])==34 and len(d["testing"])==40,
         "expected R2 34/40 disjoint split")
    need(tuple(d["modes"])==r2.MODES,"R2 benchmark split changed")
    need({c["sha256"] for c in d["training"]}.isdisjoint(
         {c["sha256"] for c in d["testing"]}),"train/test leak")
    need(sha(START)==R2_CHECKPOINT_SHA,"starting R2 checkpoint changed")
    need(sha(START)==pathlib.Path("nmr_r2/model.sha256").read_text().strip(),
         "R2 memory sidecar drift")
    pin=read("nmr_r2/build-pin.json")
    for name in ("nmr_r2/nmr-driver","new_horizon/r190-driver","nmr_r2/split.json"):
        need(sha(name)==pin[name],"native/split binary SHA drift "+name)
    need(pin["cadical_commit"]=="31f9aae44947c673dc6190c9beb399acb9ffec6a",
         "CaDiCaL pin changed")
    return d

def selftest():
    policy.selftest()
    x=[0.]*policy.INPUTS
    p=policy.NeuralPolicy()
    p.b2=6.0
    b=p.updates
    p.update(x,1)
    need(p.updates==b,"confident-correct SGD must abstain")
    p.b2=0.0
    p.update(x,1)
    need(p.updates==b+1,"uncertain SGD must update")
    need(len(EPOCHS)==7 and len(MODES)==3 and GUARD_CAP==3.,
         "R3 matrix drift")
    print("NMR_R3_SELFTEST_PASS",flush=True)

def prepare():
    d=verify_sources()
    need(not checkpoint(0).exists(),"checkpoint already exists before new training")
    ROOT.mkdir(exist_ok=True)
    shutil.copy2(START,checkpoint(0)) if checkpoint(0).parent.mkdir(parents=True,exist_ok=True) is None else None
    need(sha(checkpoint(0))==R2_CHECKPOINT_SHA,"R2 checkpoint copy drift")
    manifest=dict(protocol=PROTO,source_manifest_sha256=sha(FROZEN/"manifest.json"),
        source_split_sha256=sha(SPLIT),r2_initial_checkpoint_sha256=R2_CHECKPOINT_SHA,
        cadical_commit="31f9aae44947c673dc6190c9beb399acb9ffec6a",
        clean_binary_sha256=sha(CLEAN),nmr_binary_sha256=sha(NATIVE),
        train_cases=34,test_cases=40,training_epochs=6,
        snapshot_epochs=list(EPOCHS),repetitions=REPS,methods=list(MODES),
        guard_rule="if user-supplied case runtime cap <= 3.0s then pure clean CaDiCaL",
        source_disjoint=True,known_family_and_seen_R2_holdout=True,
        holdout_never_trains_weights=True,independent_unsat_LRAT=False)
    save(ROOT/"protocol.json",manifest)
    print("NMR_R3_PREPARE_PASS",json.dumps(manifest,sort_keys=True),flush=True)

def train():
    d=verify_sources()
    p=read(ROOT/"protocol.json")
    need(p["source_split_sha256"]==sha(SPLIT),"R3 frozen split drift")
    need(sha(checkpoint(0))==R2_CHECKPOINT_SHA,"starting checkpoint mismatch")
    shutil.copy2(checkpoint(0),ROOT/"model.sqlite")
    rows=[]
    ordered=sorted(d["training"],key=lambda c:c["sha256"])
    for epoch in range(1,7):
        source_rows=[]
        mem=policy.PersistentMemory(ROOT/"model.sqlite",True)
        beginning=mem.policy.updates
        start_weights=mem.policy.dump()
        try:
            cases=ordered[:]
            random.Random(PROTO+"TRAIN_EPOCH"+str(epoch)).shuffle(cases)
            for c in cases:
                fp=FROZEN/(c["id"]+".cnf")
                need(sha(fp)==c["sha256"],"training source SHA changed")
                out=policy.run_case(fp,NATIVE,CLEAN,float(c["cap_s"]),"train",mem)
                if c.get("expected") in ("SAT","UNSAT") and out["status"]!="TIMEOUT":
                    need(out["status"]==c["expected"],"wrong train answer")
                source_rows.append(dict(source_sha256=c["sha256"],status=out["status"],
                    cap_s=c["cap_s"],elapsed_s=round(out["elapsed_s"],7),
                    updates=out["updates"],pairs=out["pairs"],periods=out["recurrence_hits"]))
            end_weights=mem.policy.dump()
            end_updates=mem.policy.updates
        finally:
            mem.close()
        shutil.copy2(ROOT/"model.sqlite",checkpoint(epoch))
        start_vector=[x for row in start_weights["w1"] for x in row]+start_weights["b1"]+start_weights["w2"]+[start_weights["b2"]]
        end_vector=[x for row in end_weights["w1"] for x in row]+end_weights["b1"]+end_weights["w2"]+[end_weights["b2"]]
        drift=math.sqrt(sum((a-b)**2 for a,b in zip(end_vector,start_vector)))
        row=dict(epoch=epoch,instances=len(source_rows),lifetime_updates=end_updates,
            new_updates=end_updates-beginning,weight_l2_drift=round(drift,9),
            solved=sum(x["status"]!="TIMEOUT" for x in source_rows),
            elapsed_s=round(sum(x["elapsed_s"] for x in source_rows),6),
            checkpoint_sha256=sha(checkpoint(epoch)))
        rows.append(row)
        save(ROOT/"training-epochs.json",rows)
        save(ROOT/f"train-epoch-{epoch:02d}.json",source_rows)
        print("NMR_R3_TRAIN_EPOCH",json.dumps(row,sort_keys=True),flush=True)
    print("NMR_R3_TRAIN_PASS",len(rows),flush=True)

def verify_checkpoints():
    d=verify_sources()
    rows=read(ROOT/"training-epochs.json")
    need(len(rows)==6 and [x["epoch"] for x in rows]==list(range(1,7)),
         "incomplete six-cycle training history")
    need(sha(checkpoint(0))==R2_CHECKPOINT_SHA,"initial model changed")
    for r in rows:need(sha(checkpoint(r["epoch"]))==r["checkpoint_sha256"],
                       "checkpoint changed at "+str(r["epoch"]))
    return d

def trial(c,epoch,mode,rep,mem):
    path=FROZEN/(c["id"]+".cnf")
    need(sha(path)==c["sha256"],"test source SHA drift")
    cap=float(c["cap_s"])
    skip=(mode=="neural_guarded" and cap<=GUARD_CAP)
    actual="clean" if mode=="clean" or skip else "live"
    result=policy.run_case(path,NATIVE,CLEAN,cap,actual,mem)
    need(result["source_sha"]==c["sha256"],"result source drift")
    need(result["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
    if c.get("expected") in ("SAT","UNSAT") and result["status"]!="TIMEOUT":
        need(result["status"]==c["expected"],"known status differs")
    if result["status"]=="SAT":
        need(result["proof"]=="SAT_WITNESS_VERIFIED_ORIGINAL_CNF"
             or result["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL_SHA",
             "unverified SAT")
    wall=min(cap,float(result["elapsed_s"]))
    return dict(id=c["id"],source_sha256=c["sha256"],origin=c["origin"],
        epoch=epoch,mode=mode,rep=rep,status=result["status"],cap_s=cap,
        wall_s=round(wall,7),par2_s=round(2*cap if result["status"]=="TIMEOUT" else wall,7),
        profile=result["profile"],guard_abstained=skip,
        neural_updates=result["updates"],probe_pairs=result["pairs"],
        recurrence_hits=result["recurrence_hits"],scan_s=round(result["structural_scan_s"],7),
        proof=result["proof"])

def shard(idx):
    d=verify_checkpoints()
    need(0<=idx<SHARDS,"invalid shard")
    byepoch={}
    for epoch in EPOCHS:byepoch[epoch]=policy.PersistentMemory(checkpoint(epoch),False)
    rows=[]
    try:
        for c in d["testing"][idx::SHARDS]:
            for epoch in EPOCHS:
                for rep in range(REPS):
                    arms=list(MODES)
                    random.Random(PROTO+c["sha256"]+str(epoch)+str(rep)).shuffle(arms)
                    for arm in arms:
                        r=trial(c,epoch,arm,rep,byepoch[epoch])
                        rows.append(r)
                        save(ROOT/f"shard-{idx}.json",rows)
                        print("NMR_R3_TRIAL",json.dumps({k:r[k] for k in
                            ("id","epoch","mode","rep","status","wall_s",
                             "guard_abstained","neural_updates","profile")},sort_keys=True),flush=True)
        need(len(rows)==len(d["testing"][idx::SHARDS])*len(EPOCHS)*REPS*len(MODES),
             "incomplete R3 shard")
        print("NMR_R3_SHARD_PASS",idx,len(rows),flush=True)
    finally:
        for mem in byepoch.values():mem.close()

def audit():
    d=verify_checkpoints()
    rows=[]
    for idx in range(SHARDS):
        p=read(ROOT/f"shard-{idx}.json")
        need(len(p)==len(d["testing"][idx::SHARDS])*len(EPOCHS)*REPS*len(MODES),
             "missing paired shard")
        rows.extend(p)
    need(len(rows)==len(d["testing"])*len(EPOCHS)*REPS*len(MODES)==1680,
         "R3 missing paired attempts")
    orig={c["sha256"]:c for c in d["testing"]}
    pairs=collections.defaultdict(dict)
    for x in rows:
        need(x["source_sha256"] in orig and x["id"]==orig[x["source_sha256"]]["id"],
             "source SHA mismatch")
        key=x["source_sha256"],x["epoch"],x["rep"]
        need(x["mode"] not in pairs[key],"duplicate method")
        pairs[key][x["mode"]]=x
        expected=(2*x["cap_s"] if x["status"]=="TIMEOUT" else x["wall_s"])
        need(abs(expected-x["par2_s"])<1e-5,"PAR-2 drift")
        if x["status"]=="SAT":
            need(x["proof"].startswith("SAT_WITNESS_"),"SAT proof missing")
        need(x["mode"] in MODES and x["epoch"] in EPOCHS and x["rep"] in range(REPS),
             "wrong method/epoch/rep")
    for key,group in pairs.items():
        need(set(group)==set(MODES),"not paired")
        need(len({v["status"] for v in group.values() if v["status"]!="TIMEOUT"})<=1,
             "contradictory solver answers")
    epochs={}
    for epoch in EPOCHS:
        groups={}
        for mode in MODES:
            z=[x for x in rows if x["epoch"]==epoch and x["mode"]==mode]
            groups[mode]=dict(attempts=len(z),solved=sum(x["status"]!="TIMEOUT" for x in z),
                sat=sum(x["status"]=="SAT" for x in z),unsat=sum(x["status"]=="UNSAT" for x in z),
                par2_s=round(sum(x["par2_s"] for x in z),6),
                total_wall_s=round(sum(x["wall_s"] for x in z),6),
                updates=sum(x["neural_updates"] for x in z),
                guard_abstentions=sum(x["guard_abstained"] for x in z),
                recurrence_hits=sum(x["recurrence_hits"] for x in z))
        vs={}
        for mode in MODES[1:]:
            wins=losses=ties=0
            for (source,e,rep),m in pairs.items():
                if e!=epoch:continue
                a,b=m["clean"],m[mode]
                if b["par2_s"]<a["par2_s"]*.995:wins+=1
                elif b["par2_s"]>a["par2_s"]*1.005:losses+=1
                else:ties+=1
            vs[mode]=dict(paired_wins=wins,paired_losses=losses,paired_ties=ties,
                speedup=round(groups["clean"]["par2_s"]/groups[mode]["par2_s"],6))
        epochs[str(epoch)]=dict(groups=groups,paired=vs)
    report=dict(protocol=PROTO,status="NMR_R3_CURVE_AUDIT_PASS",
        known_R2_holdout_not_blind=True,source_split_SHA=sha(SPLIT),
        original_manifest_SHA=sha(FROZEN/"manifest.json"),
        R2_initial_checkpoint_SHA=R2_CHECKPOINT_SHA,
        training_only_checkpoint_epochs=6,
        test_sources=len(d["testing"]),train_sources=len(d["training"]),
        test_attempts=len(rows),repetitions=REPS,
        neural_changes="selective confident proxy abstention + update annealing",
        budget_guard_cap_s=GUARD_CAP,
        native_UNSAT_independent_LRAT=False,
        comparison="exact source SHA, paired cap and repetition; fresh clean run per epoch",
        training_curve=read(ROOT/"training-epochs.json"),epochs=epochs)
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# DRNAS Neural R3: six-cycle learning curve on reused R2 SHA-disjoint split\n\n")
        f.write("All 34 training sources separate from 40 reused R2 test sources. "
                "Tests are NOT a new blind holdout. Checkpoint from R2 at epoch 0. "
                "Six TRAIN-only epochs; test network copies never persist updates. "
                "Same pinned CaDiCaL and native sources; UNSAT lacks independent LRAT.\n\n")
        f.write("| Epoch | Method | Solved | PAR-2 s | vs clean | Neural updates | Guard abstentions |\n"
                "|---:|---|---:|---:|---:|---:|---:|\n")
        for epoch in EPOCHS:
            e=epochs[str(epoch)]
            for mode in MODES:
                v=e["groups"][mode]
                speed=e["paired"].get(mode,{}).get("speedup","—")
                f.write(f'| {epoch} | {mode} | {v["solved"]}/{v["attempts"]} | {v["par2_s"]} | {speed} | {v["updates"]} | {v["guard_abstentions"]} |\n')
        f.write("\nTraining drift (per epoch):\n\n")
        for x in report["training_curve"]:
            f.write(f'- Epoch {x["epoch"]}: {x["new_updates"]} updates, weight L2 drift {x["weight_l2_drift"]}, source SHA frozen\n')
        f.write("\nDo not tune selected epoch on held-out trials then call it blind. "
                "Do not interpret the short-clause/time proxy as eventual SAT runtime.\n")
    print("NMR_R3_FINAL",json.dumps({"attempts":len(rows),"epochs":epochs,
          "training_curve":report["training_curve"]},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("selftest","prepare","verify","train","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.command=="selftest":selftest()
    elif args.command=="prepare":prepare()
    elif args.command=="verify":print("NMR_R3_VERIFY_PASS",len(verify_sources()["testing"]),flush=True)
    elif args.command=="train":train()
    elif args.command=="shard":shard(args.shard)
    else:audit()
