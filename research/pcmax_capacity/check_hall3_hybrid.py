#!/usr/bin/env python3
"""Independent original-clause HALL3 checker: no native code, LP or SAT solver.

Positive-weight source ALO groups require at least one true literal each.
Every demanded option belongs to exactly one BDD resource or one source-mutex
clique. Independently computed integer maxima bound their total weight.
"""
import argparse
import hashlib
import json
from pathlib import Path
from check_capacity import parse_cnf

class InvalidCertificate(ValueError):
    pass

def require(ok, why):
    if not ok: raise InvalidCertificate(why)

def verify(raw, certificate):
    require(type(certificate) is dict and certificate.get('format')=='pcmax-hall3-hybrid-v1', 'format')
    require(certificate.get('source_sha256')==hashlib.sha256(raw).hexdigest(),'source hash')
    variables, clauses=parse_cnf(raw)
    groups=certificate.get('selected_groups')
    weights=certificate.get('group_weights')
    machines=certificate.get('machines')
    cliques=certificate.get('resource_cliques')
    caps=certificate.get('resource_capacities')
    require(all(type(z) is list for z in (groups,weights,machines,cliques,caps)), 'invalid collections')
    require(0<len(groups)<=128 and len(weights)==len(groups), 'invalid group count')
    require(0<len(machines)<=128 and len(cliques)<=128 and len(caps)==len(cliques), 'invalid resource count')
    selected_weight={}
    for group,weight in zip(groups,weights):
        require(type(weight) is int and 0<weight<=1000000, 'invalid weight')
        require(1<len(group)<=128 and all(type(v) is int and 0<v<=variables for v in group), 'invalid group')
        require(len(set(group))==len(group), 'repeated group option')
        require(frozenset(group) in clauses, 'original ALO missing')
        for v in group:
            require(v not in selected_weight, 'duplicate ALO option')
            selected_weight[v]=weight
    required=sum(weights)
    occupied=set()
    states=set()
    capacities=[]
    for machine in machines:
        require(type(machine) is dict, 'invalid machine')
        order=machine.get('variable_order')
        transitions=machine.get('transitions')
        require(type(order) is list and 0<len(order)<=128 and type(transitions) is list
                and 0<len(transitions)<=60000,'invalid BDD data')
        require(all(type(v) is int and 0<v<=variables for v in order),'invalid BDD selector')
        require(not occupied.intersection(order) and len(set(order))==len(order),'duplicate BDD selector')
        occupied.update(order)
        ranks={v:i for i,v in enumerate(order)}
        prefix=[0]
        for v in order:prefix.append(prefix[-1]+selected_weight.get(v,0))
        nodes={}
        for edge in transitions:
            require(type(edge) is list and len(edge)==4 and all(type(x) is int and 0<x<=variables for x in edge), 'bad BDD edge')
            p,x,lo,hi=edge
            require(p not in nodes and x in ranks, 'duplicate state or invalid selector')
            require(len({p,x,lo})==3 and len({p,x,hi})==3, 'BDD alias')
            require(frozenset((-p,x,lo)) in clauses, 'missing false BDD implication')
            require(frozenset((-p,-x,hi)) in clauses, 'missing true BDD implication')
            nodes[p]=(x,lo,hi)
        root,t,f=[machine.get(key) for key in ('root','true_terminal','false_terminal')]
        require(all(type(v) is int and 0<v<=variables for v in (root,t,f)), 'invalid BDD terminals')
        require(root in nodes and t!=f and t not in nodes and f not in nodes,'invalid BDD root/terminal')
        require(all(frozenset(c) in clauses for c in ((root,),(t,),(-f,))),'missing BDD unit')
        local_states=set(nodes)|{t,f}
        require(not states.intersection(local_states),'state shared between machines')
        states.update(local_states)
        node_rank={p:ranks[x] for p,(x,_,_) in nodes.items()}
        node_rank[t]=node_rank[f]=len(order)
        for p,(x,lo,hi) in nodes.items():
            require(lo in local_states and hi in local_states,'BDD child outside machine')
            require(node_rank[lo]>ranks[x] and node_rank[hi]>ranks[x],'not an ordered DAG')
        best={t:0,f:None}
        for p in sorted(nodes,key=node_rank.__getitem__,reverse=True):
            x,lo,hi=nodes[p]
            idx=ranks[x]
            options=[]
            for child,value in ((lo,0),(hi,selected_weight.get(x,0))):
                if best[child] is not None:
                    skipped=prefix[node_rank[child]]-prefix[idx+1]
                    options.append(best[child]+skipped+value)
            best[p]=max(options) if options else None
        require(best[root] is not None,'BDD has no accepting path')
        actual=prefix[node_rank[root]]+best[root]
        require(type(machine.get('capacity')) is int and machine['capacity']==actual,'BDD capacity mismatch')
        capacities.append(actual)
    for clique,cap in zip(cliques,caps):
        require(type(clique) is list and 0<len(clique)<=512,'invalid resource clique')
        require(all(type(v) is int and 0<v<=variables for v in clique),'invalid clique literal')
        require(len(set(clique))==len(clique) and not occupied.intersection(clique),'overlapping resources')
        occupied.update(clique)
        for i,v in enumerate(clique):
            for old in clique[:i]:
                require(frozenset((-v,-old)) in clauses,'clique mutex missing in source')
        actual=max(selected_weight.get(v,0) for v in clique)
        require(type(cap) is int and cap==actual,'clique capacity mismatch')
        capacities.append(actual)
    require(not states.intersection(occupied),'BDD states overlap selectors')
    require(set(selected_weight).issubset(occupied),'uncovered positive group option')
    total=sum(capacities)
    require(type(certificate.get('required')) is int and required==certificate['required'],'wrong demand')
    require(type(certificate.get('capacity_sum')) is int and total==certificate['capacity_sum'],'wrong total capacity')
    require(required>total,'not a strict contradiction')
    return {'status':'UNSAT_HALL3_INDEPENDENTLY_VERIFIED',
            'source_sha256':certificate['source_sha256'],
            'selected_groups':len(groups),'bdd_machines':len(machines),
            'mutex_cliques':len(cliques),'required':required,'capacity':total,
            'deficit':required-total}

def main():
    a=argparse.ArgumentParser()
    a.add_argument('cnf',type=Path)
    a.add_argument('certificate',type=Path)
    args=a.parse_args()
    try:print(json.dumps(verify(args.cnf.read_bytes(),json.loads(args.certificate.read_text())),sort_keys=True))
    except (InvalidCertificate,ValueError,TypeError,KeyError,IndexError) as exc:
        print('INVALID_HALL3_CERTIFICATE '+str(exc))
        raise SystemExit(1)

if __name__=='__main__':main()
