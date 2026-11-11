"""Recheck retained original CNFs, certificates and paired PAR2 after the run."""
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path

from experiment import ROOT,OUT,independently_audit_inferences
from design import source_parity_unsat,satisfies
from probe import parse_dimacs


def audit(report_path=None):
    report=json.loads(Path(report_path or ROOT/'MI_LTM3_FINAL.json').read_text())
    cap=report['cap_s'];rows=report['trials']
    assert report['version']=='relational-audit-v2'
    source={};splits=defaultdict(set)
    for item in report['manifest']:
        sha=item['sha256'];raw=(OUT/'sources'/(sha+'.cnf')).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==sha,('source SHA',sha)
        source[sha]=parse_dimacs(raw.decode())
        splits[item['split']].add(sha)
    assert splits['train'].isdisjoint(splits['holdout'])
    seen=set();counts=Counter();stats=defaultdict(lambda:dict(trials=0,solved=0,sat=0,unsat=0,par2_s=0.0))
    for row in rows:
        key=(row['sha256'],row['rep'],row['arm'])
        assert key not in seen,('duplicate trial',key)
        seen.add(key)
        assert row['sha256'] in splits[row['split']]
        digest=row['certificate_sha256']
        encoded=(OUT/'certificates'/(digest+'.json')).read_text().rstrip('\n')
        assert hashlib.sha256(encoded.encode()).hexdigest()==digest
        cert=json.loads(encoded)
        assert cert['original_sha256']==row['sha256'] and cert['arm']==row['arm'] and cert['rep']==row['rep']
        cs=source[row['sha256']]
        if 'equations' in cert:
            independently_audit_inferences(cs,dict(xor_equations=cert['equations'],consequences=cert['consequences']))
        candidate=cert['status']
        if candidate=='SAT_ORIGINAL_VERIFIED':
            model={int(k):v for k,v in cert['model'].items()}
            assert satisfies(cs,model),('bad original SAT witness',key)
        elif candidate=='UNSAT_SOURCE_GF2_VERIFIED':
            assert source_parity_unsat(cs)[0],('unproved source UNSAT',key)
        else:
            assert candidate=='UNKNOWN'
        assert row['within_budget']==cert['within_budget']
        # Rows are rounded to 1e-7 s; eligibility itself was tested unrounded.
        if row['solved']:
            assert row['within_budget'] and row['e2e_s']<=cap+1e-7
            assert row['status']==candidate and candidate!='UNKNOWN'
            assert abs(row['par2_s']-row['e2e_s'])<1e-6
        else:
            assert row['status']=='UNKNOWN' and row['par2_s']==2*cap
        counts[(row['split'],row['sha256'],row['rep'])]+=1
        s=stats[row['split']+'/'+row['arm']]
        s['trials']+=1;s['solved']+=row['solved'];s['par2_s']+=row['par2_s']
        s['sat']+=row['status']=='SAT_ORIGINAL_VERIFIED'
        s['unsat']+=row['status']=='UNSAT_SOURCE_GF2_VERIFIED'
    for (split,sha,rep),n in counts.items():
        assert n==(3 if split=='train' else 4)
    for split in ('train','holdout'):
        assert len({(sha,rep) for sp,sha,rep in counts if sp==split})==len(splits[split])*report['repeats']
    for key,s in stats.items():
        s['par2_s']=round(s['par2_s'],6)
        split,arm=key.split('/')
        assert abs(s['par2_s']-report['summary'][split][arm]['PAR2_s'])<1e-6
    result=dict(shard=0,trials=len(rows),original_cnf=len(source),
                training_sha=len(splits['train']),holdout_sha=len(splits['holdout']),
                verified_certificates=len(rows),stats=dict(stats),
                independent_LRAT=False,source_GF2_rechecked=True,
                note='One benchmark job/shard; source GF2 certificates are not CDCL proof traces.')
    (ROOT/'MI_LTM3_AUDIT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print('MI_LTM3_ARTIFACT_AUDIT '+json.dumps(result,sort_keys=True),flush=True)
    return result


if __name__=='__main__':audit()
