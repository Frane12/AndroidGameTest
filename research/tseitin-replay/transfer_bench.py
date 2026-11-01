"""Prospective eight-slot transfer test, with no solver timing during selection."""
import csv
import hashlib
import io
import json
import os
import random
import resource
import shutil
import statistics
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from official_family import history, pinned
import official_shortlong_select as source
from xor4_benchmark import validate, dimacs

# Identified from the competition catalogue before any new timing.
CATALOGUE = [
    ('0297c2a35f116ffd5382aea5b421e6df','Urquhart-s3-b3','Tseitin','UNSAT'),
    ('fff3f8c76467cdf9d92689969fd94281','mod2c-rand3bip-240-2','random-graph-xorsat','SAT'),
    ('073c28dfd3204f4c51e03c297ac841c1','mod2c-rand3bip-120-3','random-graph-xorsat','UNSAT'),
    ('07e851c74295f7ddf472820c0f0164e8','x2_72','xor-chain','UNSAT')]
FAMILIES = ['minimum-disagreement-parity','cryptography','hardware-miter','scheduling']
SOLVERS = ['v142_xor4','v142_fastgate','kissat_solver','cryptominisat5']
LIMIT = 8
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, obj):
    Path(p).write_text(json.dumps(obj,indent=2))
def freeze():
    folder = Path('frozen')
    folder.mkdir()
    ids, shas = history()
    extra = json.loads(next(Path('prior-v146').rglob('v146_new30_source.json')).read_text())['cases']
    ids.update(c['id'] for c in extra)
    shas.update(c['sha256'] for c in extra)
    other = json.loads(next(Path('prior-grid').rglob('external_manifest.json')).read_text())
    ids.update(c['id'] for c in other)
    shas.update(c['sha256'] for c in other)
    ids.update(['c69c5163c9087ffe770743bd4cdafcc9','0fa8623240b5c14c1308f863a6dc88ab','aa39c6d885d283a085d033ab7b89f8c8'])
    meta = pinned('meta.csv','c8703ab84f28b4369c96bbdfd3d6cc0f00b0b5212bc58cd2d5d7eca48cafc0ce')
    archive = pinned('detailed_results.zip','dfdf1d515fc95e95d3b76f907a2ce67932af1f8905f90c3dd7f743ea6c2b751a')
    detail = zipfile.ZipFile(io.BytesIO(archive)).read('detailed_main.csv').decode()
    labels = {r['hash']:r['vresult'].upper() for r in csv.DictReader(io.StringIO(detail))}
    pool = [(v[0],v[1],v[2],labels[v[0]]) for line in meta.decode().splitlines()[1:] if (v:=line.split())]
    groups = [[case] for case in CATALOGUE]
    for family in FAMILIES:
        eligible = [v for v in pool if v[2]==family and v[3] in ('SAT','UNSAT')]
        groups.append(sorted(eligible,key=lambda x:hashlib.sha256(('outside-grid-v1/'+x[0]).encode()).digest()))
    cases, skipped = [], []
    historic = len(ids)
    for slot, options in enumerate(groups):
        obj = None
        for ident, name, family, label in options:
            if ident in ids:
                skipped.append([ident,'seen id'])
                continue
            p = folder/(ident+'.cnf')
            try:
                summary = source.download_and_features(ident,p)
            except ValueError as e:
                skipped.append([ident,str(e)])
                continue
            sha = digest(p)
            assert sha==summary['sha256']
            if sha in shas or p.stat().st_size>12*1024**2:
                skipped.append([ident,'seen digest or >12 MiB'])
                p.unlink()
                continue
            obj = dict(slot=slot,id=ident,name=name,family=family,label=label,sha256=sha,
                       variables=summary['variables'],clauses=summary['clauses'])
            shas.add(sha)
            ids.add(ident)
            break
        cases.append(obj)
    assert sum(bool(c) for c in cases)>=2
    save(folder/'manifest.json',dict(cases=cases,excluded_ids=historic,skipped=skipped))

def solve(exe, path):
    if exe=='cryptominisat5':
        cmd=[shutil.which(exe),'--threads=1',str(path)]
    else:
        cmd=[str(Path('bin',exe).resolve()),str(path)]
        if exe.startswith('v142'):
            cmd.extend([str(Path('bin/kissat_solver').resolve()),'0'])
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,timeout=LIMIT,text=True,capture_output=True)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT',LIMIT,'timeout',{}
    elapsed=time.perf_counter()-start
    if elapsed>LIMIT:
        return 'TIMEOUT',LIMIT,'timeout',{}
    lines=p.stdout.splitlines()
    tags=[line.split('\t',1)[1] for line in lines if line.startswith('DRNAS_HYBRID_RESULT\t')]
    if tags:
        assert len(tags)==1 and p.returncode==0
        answer=json.loads(tags[0])
        return answer['status'],elapsed,answer['path'],answer
    status={10:'SAT',20:'UNSAT'}.get(p.returncode)
    expected={'SAT':'s SATISFIABLE','UNSAT':'s UNSATISFIABLE'}
    if not status or expected[status] not in lines:
        raise RuntimeError(str((p.returncode,lines[-4:],p.stderr[-300:])))
    model=[int(x) for line in lines if line.startswith('v ') for x in line.split()[1:] if int(x)]
    return status,elapsed,('Kissat fallback' if exe.startswith('v142') else exe),{'model':model}

def run(slot):
    data=json.loads(Path('frozen/manifest.json').read_text())
    c=data['cases'][slot]
    out=Path('out');out.mkdir()
    if c is None:
        save(out/'results.json',dict(slot=slot,case=None,trials=[]))
        return
    path=Path('frozen',c['id']+'.cnf')
    assert digest(path)==c['sha256']
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    version=subprocess.check_output(['dpkg-query','-W','-f=${Version}','cryptominisat'],text=True)
    machine=next(s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name'))
    rng=random.Random(420711+slot)
    trials=[]
    for rep in range(3):
        order=SOLVERS.copy()
        rng.shuffle(order)
        for exe in order:
            status,seconds,route,answer=solve(exe,path)
            check='timeout'
            if status!='TIMEOUT':
                assert status==c['label'], (c,exe,status)
                if status=='SAT':
                    # Some solvers legally omit don't-care variables.
                    _,clauses=dimacs(path)
                    model={int(v) for v in answer['model'] if int(v)}
                    assert not any(-v in model for v in model)
                    assert all(any(lit in model for lit in clause) for clause in clauses)
                    check='model checked'
                elif route in ('affine_exact','affine_exact_xor4'):
                    proof=validate(path,status,answer)
                    assert proof
                    check='XOR certificate replayed'
                    if rep==0:save(out/(exe+'-certificate.json'),dict(input_sha=c['sha256'],answer=answer,equations=proof))
                else:
                    check='published label matched'
            trials.append(dict(rep=rep,solver=exe,status=status,seconds=seconds,route=route,check=check))
    save(out/'results.json',dict(slot=slot,case=c,cap=LIMIT,repeats=3,cpu=machine,cms=version,
                                checksums={s:digest(Path(shutil.which(s)) if s=='cryptominisat5' else Path('bin',s)) for s in SOLVERS},trials=trials))
def aggregate():
    manifest=json.loads(Path('frozen/manifest.json').read_text())
    rows=[json.loads(p.read_text()) for p in sorted(Path('all').glob('*/results.json'))]
    assert len(rows)==8 and sorted(r['slot'] for r in rows)==list(range(8))
    for r in rows:
        assert r['case']==manifest['cases'][r['slot']]
        if r['case']:
            assert len({(t['solver'],t['rep']) for t in r['trials']})==12
    save('transfer-audit.json',dict(manifest=manifest,reports=rows))
if __name__=='__main__':
    if sys.argv[1]=='freeze':freeze()
    elif sys.argv[1]=='run':run(int(sys.argv[2]))
    elif sys.argv[1]=='aggregate':aggregate()
