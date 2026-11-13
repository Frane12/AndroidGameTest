#!/usr/bin/env python3
"""X4.1 manifest, generator family isolation, and completed-target audit."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
import drnas_x41_dataset as D
import drnas_x41_evaluate as E

def main():
    with TemporaryDirectory() as td:
        root=Path(td)
        cases=[D.generate(f,i,root) for split,fs in D.FAMILIES.items() for f in fs for i in range(48)]
        assert len(cases)==384
        assert len({c['sha256'] for c in cases})==384,'duplicate CNF source'
        bysplit={sp:{c['family'] for c in cases if c['split']==sp} for sp in D.FAMILIES}
        assert not bysplit['train']&bysplit['validation']
        assert not bysplit['train']&bysplit['holdout']
        assert not bysplit['validation']&bysplit['holdout']
        for c in cases:
            assert c['nvars']>0
            if c['oracle'].startswith('SAT_BY_'):
                assert c['family'] not in ('synthetic:pigeonhole_unsat','synthetic:graph_k4_unsat')
            else:assert c['oracle'] in ('UNSAT_BY_PHP_THEOREM','UNSAT_BY_K4_SUBGRAPH')
        print('X41_GENERATOR_AUDIT_PASS '+json.dumps({'sources':len(cases),'source_sha_distinct':True,
              'train_families':len(bysplit['train']),'validation_families':len(bysplit['validation']),
              'holdout_families':len(bysplit['holdout'])}),flush=True)

if __name__=='__main__':main()