#!/usr/bin/env python3
"""Exercise verified persistent hits, fresh misses, policy isolation and corruption."""
import hashlib,json,os,sqlite3,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
import drnas_x5_memory_ab as M

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    a=SimpleNamespace(cap=3,model=ROOT/'experiments/drnas_x5/frozen_models/frozen_cost_model.txt',
        checker=ROOT/'build/drat-trim')
    a.model_sha=M.B.sha(a.model);a.binary_sha=M.B.sha(ROOT/'build/drnas-x5')
    count=0;hits=0;global_loads=0
    with tempfile.TemporaryDirectory() as tmp:
        td=Path(tmp);cnf=td/'case.cnf'
        for family in M.D.FAMILIES:
            s=M.D.source(family,14760001)
            cnf.write_text(s['content'])
            for arm in ('BASE','GLOBAL','CACHE','GLOBAL_CACHE'):
                cache=M.ResultCache(td/(family+arm+'.sqlite')) if 'CACHE' in arm else None
                first=M.run(arm,s,cnf,td,a,cache)
                assert first['accepted'] and not first['cache_hit'], (family,arm,first)
                global_loads+=first['probe'].get('learned_model',False)
                if cache:
                    path=cache.path;cache.close();cache=M.ResultCache(path)
                second=M.run(arm,s,cnf,td,a,cache)
                assert second['accepted'] and second['cache_hit']==bool(cache)
                assert first['status']==second['status']==s['expected_status']
                hits+=second['cache_hit'];count+=2
                if cache:
                    # Same CNF with a different global policy must miss.
                    other='GLOBAL_CACHE' if arm=='CACHE' else 'CACHE'
                    assert not M.run(other,s,cnf,td,a,cache)['cache_hit']
                    # Tamper with a cached proof or witness, including its envelope checksum.
                    key,status,output,proof=cache.db.execute('SELECT key,status,output,proof FROM results LIMIT 1').fetchone()
                    bad_output='s SATISFIABLE\nv 0\n' if status=='SAT' else output
                    bad_proof=b'' if status=='UNSAT' else proof
                    cache.db.execute('UPDATE results SET output=?,proof=?,payload_sha=? WHERE key=?',
                        (bad_output,bad_proof,M.digest(status.encode()+bad_output.encode()+bad_proof),key))
                    cache.db.commit()
                    # Direct payload corruption must always be detected too.
                    cache.db.execute("UPDATE results SET payload_sha='bad' WHERE key=?",(key,));cache.db.commit()
                    try:cache.get(key)
                    except AssertionError:pass
                    else:raise AssertionError('corrupt cache accepted')
                    cache.close()
        # Certificate checking, not merely a cache checksum, rejects a forged SAT hit.
        s=M.D.source('random3_sat',14760001);cnf.write_text(s['content'])
        cache=M.ResultCache(td/'forged.sqlite')
        assert M.run('CACHE',s,cnf,td,a,cache)['accepted']
        key,status,output,proof=cache.db.execute('SELECT key,status,output,proof FROM results').fetchone()
        output='s SATISFIABLE\nv 0\n'
        cache.db.execute('UPDATE results SET output=?,payload_sha=?',(output,M.digest(status.encode()+output.encode()+proof)));cache.db.commit()
        try:M.run('CACHE',s,cnf,td,a,cache)
        except AssertionError:pass
        else:raise AssertionError('forged witness accepted')
        cache.close()
        # Nontrivial UNSAT replay also requires a proof, not just a stored label.
        s=M.D.source('php_unsat',14760001);cnf.write_text(s['content'])
        cache=M.ResultCache(td/'forged_unsat.sqlite')
        assert M.run('CACHE',s,cnf,td,a,cache)['accepted']
        key,status,output,proof=cache.db.execute('SELECT key,status,output,proof FROM results').fetchone()
        assert status=='UNSAT' and proof
        cache.db.execute('UPDATE results SET proof=?,payload_sha=?',(b'',M.digest(status.encode()+output.encode())));cache.db.commit()
        try:M.run('CACHE',s,cnf,td,a,cache)
        except AssertionError:pass
        else:raise AssertionError('forged UNSAT certificate accepted')
        cache.close()
        # A different original source cannot reuse a certificate.
        cache=M.ResultCache(td/'fresh.sqlite')
        assert not M.run('CACHE',s,cnf,td,a,cache)['cache_hit']
        other=M.D.source('random3_sat',14760002);cnf.write_text(other['content'])
        assert not M.run('CACHE',other,cnf,td,a,cache)['cache_hit'];cache.close()
    assert hits==24 and global_loads==24
    print('X5_MEMORY_SELFTEST_PASS',json.dumps({'primary_runs':count,'persistent_hits':hits,
        'native_global_model_loads':global_loads,'families':12,'corruption_rejected':True,
        'forged_witness_rejected':True,'forged_unsat_rejected':True,'different_policy_and_source_miss':True}))
if __name__=='__main__':main()
