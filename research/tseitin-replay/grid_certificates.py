"""Emit compact certificates and verify them directly against both original grid CNFs."""
import collections,copy,hashlib,itertools,json,sys
from pathlib import Path
from proofcheck import dimacs
sys.path.insert(0,'research/drnas-sat-v7-8')
from official_shortlong_select import download_and_features
targets={
 'grid6x200':('35789168b67a74985804902008251269','d0c3805e55d90cfaefa253b7e6836496ab07d3779ab3b0703a1d0483c50df39a'),
 'grid11x20':('36dbc206c7d9773bebb03f752070cee9','6d194d2f8a49b0a3eecf25f21445bc4e5ff0e4b13825b34c1180fde74b0a53fb')}

def make(clauses):
    groups=collections.defaultdict(list)
    for i,c in enumerate(clauses):groups[tuple(sorted(map(abs,c)))].append(i)
    cert=[]
    for support,indices in sorted(groups.items()):
        # The falsifying assignment sets precisely the negative literals to true.
        falsified_parity=sum(lit<0 for lit in clauses[indices[0]])%2
        cert.append(dict(variables=list(support),clause_indices=indices,rhs=1-falsified_parity))
    return cert

def replay(clauses,cert):
    remaining=set();rhs=0
    for row in cert:
        vs,ids,bit=row['variables'],row['clause_indices'],row['rhs']
        assert 1<=len(vs)<=6 and len(set(vs))==len(vs)
        assert bit in (0,1) and ids and all(0<=i<len(clauses) for i in ids)
        cs=[clauses[i] for i in ids]
        assert all(set(map(abs,c))==set(vs) for c in cs)
        for bits in itertools.product((0,1),repeat=len(vs)):
            assignment=dict(zip(vs,bits))
            ok=all(any(bool(assignment[abs(l)])==(l>0) for l in c) for c in cs)
            assert ok==(sum(bits)%2==bit)
        remaining.symmetric_difference_update(vs);rhs^=bit
    assert not remaining and rhs==1

def main():
    folder=Path('grid-proofs');folder.mkdir(exist_ok=True)
    for name,(ident,sha) in targets.items():
        p=Path(name+'.cnf');download_and_features(ident,p)
        assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
        n,cs=dimacs(p);cert=make(cs);replay(cs,cert)
        for mutation in ('drop','flip'):
            bad=copy.deepcopy(cert)
            if mutation=='drop': bad.pop()
            else: bad[0]['rhs']^=1
            try:replay(cs,bad)
            except AssertionError:pass
            else:raise AssertionError('tamper accepted')
        meta=dict(case=ident,sha256=sha,variables=n,clauses=len(cs),equations=len(cert),
                  widths=dict(collections.Counter(len(e['variables']) for e in cert)),
                  xor_left=0,xor_right=1,corrupted_proofs_rejected=2)
        print(meta);(folder/(name+'.json')).write_text(json.dumps(dict(summary=meta,rows=cert),separators=(',',':')))
if __name__=='__main__':main()
