#!/usr/bin/env python3
"""Reproducible structure study of original SAT2024 PCMAX #44 and Worker #64.

Only analysis, exact source SHA, deterministic structural transformations.
All 584 added clauses must be one-step RUP from ORIGINAL input. Worker SAT model
is independently evaluated against every original clause. No UNSAT claim here.
"""
import collections,hashlib,itertools,json,os,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import drnas_structure_44_64 as S
import drnas_focus_44_64 as F
ROOT=pathlib.Path(__file__).resolve().parents[1]
DEST=ROOT/"pcmax_transition_audit"

def emit(tag,o):print(tag+" "+json.dumps(o,sort_keys=True),flush=True)
def groups_of(clauses):
    groups=[tuple(c) for c in clauses if len(c)>=5 and all(v>0 for v in c)]
    assert len({v for g in groups for v in g})==sum(map(len,groups)),"groups overlap"
    return groups
def choose_mutex(clauses,groups):
    choice={v:i for i,g in enumerate(groups) for v in g}
    forbidden={tuple(sorted((-c[0],-c[1]))) for c in clauses
              if len(c)==2 and all(l<0 for l in c)}
    in_groups=sum((min(x,y),max(x,y)) in forbidden
                  for g in groups for x,y in itertools.combinations(g,2))
    total=sum(len(g)*(len(g)-1)//2 for g in groups)
    return choice,{"group_count":len(groups),"positive_choices":len(choice),
                   "all_group_pairs":total,"forbidden_group_pairs":in_groups,
                   "complete_exactly_one":in_groups==total,
                   "group_sizes":list(map(len,groups))}
def pcmax(clauses,groups,choice):
    transition=collections.defaultdict(dict)
    for c in clauses:
        if len(c)!=3:continue
        aux=[l for l in c if abs(l) not in choice]
        cvars=[l for l in c if abs(l) in choice]
        if len(aux)!=2 or len(cvars)!=1 or sum(l>0 for l in aux)!=1:continue
        parent=-next(l for l in aux if l<0)
        head=next(l for l in aux if l>0)
        tested=cvars[0]
        role="positive" if tested>0 else "negative"
        key=(parent,abs(tested))
        assert role not in transition[key]
        transition[key][role]=head
    assert len(transition)==1250 and all(set(v)=={"positive","negative"} for v in transition.values())
    parents={p for p,x in transition}
    assert len(parents)==len(transition)
    # Weak components of the deterministic implication DAG, no external libs.
    adj=collections.defaultdict(set)
    internal_edges=0;layer_steps=collections.Counter()
    tested_group={p:choice[x] for p,x in transition}
    for (p,x),heads in transition.items():
        for h in heads.values():
            assert h>p,"non-forward transition"
            adj[p].add(h);adj[h].add(p)
            if h in parents:
                internal_edges+=1
                layer_steps[tested_group[h]-tested_group[p]]+=1
    remaining=set(adj);components=[]
    while remaining:
        seed=remaining.pop();component={seed};q=[seed]
        while q:
            v=q.pop()
            for w in adj[v]:
                if w in remaining:
                    remaining.remove(w);component.add(w);q.append(w)
        components.append(component)
    components.sort(key=lambda v:(min(v)))
    belongs={v:i for i,c in enumerate(components) for v in c}
    neg_triples=[c for c in clauses if len(c)==3 and all(l<0 for l in c)]
    coupling=collections.Counter()
    for c in neg_triples:
        aa=[-l for l in c if -l not in choice]
        cc=[-l for l in c if -l in choice]
        assert len(aa)==2 and len(cc)==1
        i,j=belongs[aa[0]],belongs[aa[1]]
        assert i!=j,"coupling must cross state machines"
        coupling[tuple(sorted((i,j)))]+=1
    assert len(components)==11 and len(coupling)==55 and internal_edges==1850
    assert dict(layer_steps)=={1:1850},"state transitions are not layer-by-layer"
    neg_units={-c[0] for c in clauses if len(c)==1 and c[0]<0}
    pos_units={c[0] for c in clauses if len(c)==1 and c[0]>0}
    original_set={tuple(sorted(c)) for c in clauses}
    derived=set();witnesses=[]
    for (p,x),heads in transition.items():
        if heads["positive"] in neg_units:
            clause=(-p,x)
            # (x OR -p OR forbiddenHead), (-forbiddenHead) => (-p OR x).
            assert tuple(sorted((x,-p,heads["positive"]))) in original_set
            assert (-heads["positive"],) in original_set
            derived.add(clause);witnesses.append([p,x,heads["positive"]])
        if heads["negative"] in neg_units:
            clause=(-p,-x)
            assert tuple(sorted((-x,-p,heads["negative"]))) in original_set
            assert (-heads["negative"],) in original_set
            derived.add(clause);witnesses.append([p,-x,heads["negative"]])
    assert len(derived)==584 and all(tuple(sorted(c)) not in original_set for c in derived)
    detail={"automata":len(components),"automaton_size_nodes":sorted(map(len,components)),
        "complete_coupling_graph":len(coupling)==len(components)*(len(components)-1)//2,
        "coupling_clauses":len(neg_triples),"coupling_pairs":len(coupling),
        "max_pair_coupling":max(coupling.values()),"transition_states":len(transition),
        "transition_implication_edges":2*len(transition),
        "internal_next_layer_edges":internal_edges,"state_ordered_next_layer":True,
        "positive_aux_roots":sum(v in belongs for v in pos_units),
        "negative_aux_terminals":sum(v in belongs for v in neg_units),
        "one_step_rup_binary_count":len(derived),
        "one_step_rup_direct_witnesses":len(witnesses)}
    return detail,sorted(derived),witnesses

def worker(clauses,groups,choice):
    assert len(clauses)==11934 and len(groups)==17
    assert all((len(c)==2 and all(v<0 for v in c))
          or (len(c)>=5 and all(v>0 for v in c)) for c in clauses)
    adjacency=collections.defaultdict(set)
    for a,b in (c for c in clauses if len(c)==2):
        adjacency[-a].add(-b);adjacency[-b].add(-a)
    outside=set(abs(l) for c in clauses for l in c)-set(choice)
    assert all(all(l<0 for c in clauses if abs(l) in c for l in c if abs(l) in outside)
               for _ in [0]),"nonchoice variables must occur only negatively"
    nodes=0;backtracks=0;started=time.perf_counter()
    def dfs(available,chosen):
        nonlocal nodes,backtracks
        nodes+=1
        if nodes>100000 or time.perf_counter()-started>5:return None
        if not available:return chosen
        group=min(available,key=lambda g:(len(available[g]),
                                -sum(len(adjacency[v]) for v in available[g])))
        others={g:list(vs) for g,vs in available.items() if g!=group}
        candidates=sorted(available[group],
              key=lambda v:sum(sum(w in adjacency[v] for w in vs) for vs in others.values()))
        for candidate in candidates:
            reduced={g:[v for v in vs if v not in adjacency[candidate]]
                     for g,vs in others.items()}
            if any(not v for v in reduced.values()):continue
            result=dfs(reduced,chosen+[candidate])
            if result is not None:return result
        backtracks+=1
        return None
    chosen=dfs({i:list(g) for i,g in enumerate(groups)},[])
    valid=chosen is not None and all(any((l>0)==(abs(l) in chosen) for l in c)
                                      for c in clauses)
    if chosen is not None:assert valid,"INVALID_MODEL"
    return {"group_count":len(groups),"group_choices":len(choice),
           "outside_pure_negative":len(outside),"search_nodes":nodes,
           "backtracks":backtracks,"sat_model_verified":valid,
           "chosen_true_lits":chosen,"search_only_elapsed_s":round(time.perf_counter()-started,7)}

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    sources=F.pick_sources();DEST.mkdir(exist_ok=True)
    result={"protocol":"PCMAX44-WORKER64-DOMAIN-EXACT-V1",
            "no_cdcl_change":True,"no_promotion":True,
            "sources":{}}
    for ident in (44,64):
        src=sources[ident]
        nv,clauses,normalization=S.parse(ROOT/src["path"],src["sha256"])
        assert normalization["tautological_clauses_omitted"]==0
        gs=groups_of(clauses)
        choice,mutex=choose_mutex(clauses,gs)
        detail={"family":src["normalized_name_family"],"sha256":src["sha256"],
                "nvars":nv,"clauses":len(clauses),"groups":mutex}
        if ident==44:
            automata,derived,witnesses=pcmax(clauses,gs,choice)
            detail["automata"]=automata
            detail["derived_rup_binary_sha256"]=hashlib.sha256(
                json.dumps(derived,separators=(",",":")).encode()).hexdigest()
            (DEST/"pcmax44_rup584.json").write_text(json.dumps(
                {"clauses":derived,"direct_witnesses":witnesses},indent=2)+"\n")
        else:detail["domain_solver"]=worker(clauses,gs,choice)
        result["sources"][str(ident)]=detail
        emit("DOMAIN_AUDIT_CASE",{"id":ident,**detail})
    (DEST/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    emit("DOMAIN_AUDIT_FINAL",{"status":"COMPLETE","summary":{
        "pcmax":result["sources"]["44"]["automata"],
        "worker":result["sources"]["64"]["domain_solver"]}})
if __name__=="__main__":main()
