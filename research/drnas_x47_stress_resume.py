#!/usr/bin/env python3
"""Resume the missing official stress cohort, reusing immutable solver/model bytes.

The 3072 completed synthetic sources are NOT rerun. No model retraining,
SQLite-to-model promotion, or test-label learning is performed. The expanded
archive eligibility envelope is recorded and selection never queries solvers.
"""
from __future__ import annotations
import argparse
from collections import Counter
import bz2
import gzip
import hashlib
import io
import json
import lzma
from pathlib import Path
import re
import subprocess
import tempfile
import time
from types import SimpleNamespace

MODEL_SHA = '234cb83b155bc5fe5ff5ec0337945480f4c09082f37fcfaacda6a1b7995cb4c4'
GUARD_SHA = '7647bf185d8c75a184cfff3e1f4f500434619bf6b553b0516b8c5a9150c223a7'
ARCHIVE = 'https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1'
MAX_RAW = 24 * 1024 * 1024
MAX_VARS = 100000
MAX_CLAUSES = 1000000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True)+'\n')


def family(name):
    value=Path(name).name.lower().replace('.sanitized','')
    value=re.sub(r'\.cnf(?:\.(?:xz|gz|bz2))?$','',value)
    return re.sub(r'[_\-.]+','-',re.sub(r'\d+','#',value)).strip('-')


def parse_cnf(raw):
    text=raw.decode('ascii')
    header=None; clauses=[]; pending=[]
    for line in text.splitlines():
        items=line.split()
        if not items or items[0] in ('c','%'):continue
        if items[0]=='p':
            if header is not None or len(items)!=4 or items[1]!='cnf':
                raise ValueError('invalid or repeated DIMACS header')
            n,m=map(int,items[2:])
            if not (1<=n<=MAX_VARS and 1<=m<=MAX_CLAUSES):
                raise ValueError('declared CNF exceeds bounded resource envelope')
            header=(n,m);continue
        if header is None:raise ValueError('clause before header')
        for token in items:
            if token in ('c','%'):break
            literal=int(token)
            if abs(literal)>header[0]:raise ValueError('out of range literal')
            if literal:pending.append(literal)
            else:
                clauses.append(tuple(pending));pending=[]
                if len(clauses)>header[1]:raise ValueError('too many clauses')
    if header is None or pending or len(clauses)!=header[1]:
        raise ValueError('incomplete original CNF')
    return text,header[0],clauses


def expand(entry, raw):
    source=io.BytesIO(raw)
    if entry.endswith('.xz'):reader=lzma.LZMAFile(source)
    elif entry.endswith('.gz'):reader=gzip.GzipFile(fileobj=source)
    elif entry.endswith('.bz2'):reader=bz2.BZ2File(source)
    else:reader=source
    with reader:
        decoded=reader.read(MAX_RAW+1)
    if len(decoded)>MAX_RAW:raise ValueError('raw CNF exceeds limit')
    return decoded


def audit_memory(bundle, output):
    bundle=bundle.resolve()
    model=bundle/'model.txt';guard=bundle/'guard.txt';binary=bundle/'bin/drnas'
    if sha(model)!=MODEL_SHA or sha(guard)!=GUARD_SHA:
        raise AssertionError('persistent model/guard identity changed')
    observations=[]
    with tempfile.TemporaryDirectory(prefix='x46-restore-audit-') as d:
        root=Path(d);cnf=root/'audit.cnf'
        cnf.write_text('p cnf 4 2\n1 2 0\n3 4 0\n')
        cmd=[str(binary),str(cnf),'--mode','core','--time','2','--branch-at','1',
             '--stats','--x46-conflicts','8','--x46-model',str(model)]
        for cold_start in range(2):
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
            if p.returncode!=10:raise AssertionError('native restore audit failed: '+p.stderr[-800:])
            records=[json.loads(line[len('X46_PROBE '):]) for line in p.stderr.splitlines()
                     if line.startswith('X46_PROBE ')]
            if len(records)!=1 or not records[0].get('learned_model') or not records[0].get('triggered'):
                raise AssertionError('saved model was not loaded and used by native solver')
            values={}
            for line in p.stdout.splitlines():
                if line.startswith('v '):
                    for token in line[2:].split():
                        lit=int(token)
                        if lit:values[abs(lit)]=lit>0
            if not (any(values.get(v,False) for v in (1,2)) and
                    any(values.get(v,False) for v in (3,4))):
                raise AssertionError('restore audit SAT witness invalid')
            observations.append({'cold_start':cold_start+1,'learned_model':True,
                'probe_triggered':True,'pre_state_digest':records[0]['pre_state_digest'],
                'model_probability':records[0]['predicted_flip_probability']})
        bad=root/'corrupt.txt';bad.write_text('WRONG 12\n')
        p=subprocess.run(cmd[:-1]+[str(bad)],capture_output=True,text=True,timeout=4)
        if p.returncode in (0,10,20) or 'incompatible X46 learned model' not in p.stderr:
            raise AssertionError('invalid saved model was not rejected')
    if sha(model)!=MODEL_SHA or sha(guard)!=GUARD_SHA:
        raise AssertionError('inference changed persistent model')
    if observations[0]['pre_state_digest']!=observations[1]['pre_state_digest']:
        raise AssertionError('cold-start audit states differ')
    result={'status':'PASS','model_sha256':MODEL_SHA,'guard_sha256':GUARD_SHA,
        'source_run':43367322651,'native_sha256':sha(binary),'cold_starts':observations,
        'corrupt_model_rejected':True,'model_unchanged':True,
        'memory_mode':'restore frozen weights from disk; no test-time training',
        'global_database_consulted_by_native_solver':False}
    write_json(output,result);print('X46_PERSISTENT_RESTORE_PASS '+json.dumps(result),flush=True)


def select_sources(out,count=32):
    from remotezip import RemoteZip
    out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();selected=[];seen_sha=set();seen_families=set();skips=Counter()
    with RemoteZip(ARCHIVE,timeout=40) as archive:
        pool=[entry for entry in archive.infolist() if not entry.is_dir()
              and entry.filename.lower().endswith(('.cnf','.cnf.xz','.cnf.gz','.cnf.bz2'))
              and 4000<=entry.file_size<=2000000]
        # Immutable outcome-blind order. Permit alternate entries in a family
        # until a valid bounded representative has actually been selected.
        pool.sort(key=lambda e:hashlib.sha256(('X47-RESUME-V1|'+e.filename).encode()).hexdigest())
        for entry in pool[:512]:
            if len(selected)==count:break
            if time.monotonic()-started>600:raise TimeoutError('source selection exceeded budget')
            key=family(entry.filename)
            if key in seen_families:continue
            try:
                raw=expand(entry.filename,archive.read(entry))
                original_sha=hashlib.sha256(raw).hexdigest()
                if original_sha in seen_sha:skips['duplicate_original_sha']+=1;continue
                _,n,clauses=parse_cnf(raw)
            except (OSError,ValueError,EOFError,UnicodeError) as error:
                skips[type(error).__name__]+=1;continue
            index=len(selected);name=f'{index:02d}_{original_sha[:16]}.cnf.gz'
            (out/name).write_bytes(gzip.compress(raw,mtime=0))
            selected.append({'index':index,'family':key,'sha':original_sha,'n':n,
                'clauses':len(clauses),'archive_path':entry.filename,'stored_file':name,
                'raw_bytes':len(raw)})
            seen_sha.add(original_sha);seen_families.add(key)
            print('X47_RESUME_SOURCE '+json.dumps(selected[-1]),flush=True)
    manifest={'count':len(selected),'requested':count,'archive':ARCHIVE,'sources':selected,
        'selection':'fixed filename hash order; normalized family and decompressed-original SHA distinct',
        'expanded_bounds':{'archive_entry_bytes':[4000,2000000],'raw_bytes_max':MAX_RAW,
                           'vars_max':MAX_VARS,'clauses_max':MAX_CLAUSES},
        'outcome_based_selection':False,'retrospective_not_globally_blind':True,
        'rejections':dict(skips),'previous_failed_selection_count':25}
    write_json(out/'selection.json',manifest)
    if len(selected)!=count:raise RuntimeError(f'Only {len(selected)}/{count} bounded original sources available')
    print('X47_RESUME_SELECTION_PASS '+json.dumps({'sources':count,'families':len(seen_families)}),flush=True)


def run_selected(args):
    import drnas_x47_stress as B
    manifest=json.loads((args.sources/'selection.json').read_text())
    if manifest['count']!=32 or not 0<=args.shard<4:raise ValueError('bad selection/shard')
    if sha(args.bundle/'model.txt')!=MODEL_SHA or sha(args.bundle/'guard.txt')!=GUARD_SHA:
        raise AssertionError('resumed test is not using the stored X46 weights')
    def originals():
        for info in manifest['sources']:
            if info['index']%4!=args.shard:continue
            with gzip.open(args.sources/info['stored_file'],'rb') as f:raw=f.read(MAX_RAW+1)
            if len(raw)>MAX_RAW or hashlib.sha256(raw).hexdigest()!=info['sha']:
                raise AssertionError('original source corrupted after selection')
            text,n,clauses=parse_cnf(raw)
            yield {'family':info['family'],'index':info['index'],'tier':3,'cap':15.,'n':n,
                   'clauses':clauses,'text':text,'sha':info['sha'],'cert':None,'truth':'UNKNOWN',
                   'cohort':'official_retrospective','archive_path':info['archive_path']}
    original_trial=B.run_trial
    def audited_trial(conf,source,arm,rep,root):
        row=original_trial(conf,source,arm,rep,root)
        if arm=='X46_LEARNED_8':
            records=[json.loads(line[len('X46_PROBE '):])
                     for line in (root/'stderr.txt').read_text(errors='replace').splitlines()
                     if line.startswith('X46_PROBE ')]
            loaded=records[0].get('learned_model') if len(records)==1 else None
            row['persistent_model_loaded']=loaded
            row['model_sha256']=MODEL_SHA
            # A killed run may not flush its final telemetry. Never invent
            # a success flag for that case; record unavailable observation.
            if row['status'] not in ('TIMEOUT','RESOURCE_OR_PROCESS_FAILURE') and loaded is not True:
                raise AssertionError('completed learned run lacks model-load evidence')
        return row
    B.run_trial=audited_trial
    config=SimpleNamespace(out=args.out,shard=args.shard,memory_mb=1536,
        bin_dir=args.bundle/'bin',model=args.bundle/'model.txt',guard=args.bundle/'guard.txt')
    B.run_sources(config,originals())
    result=json.loads((args.out/'summary.json').read_text())
    if result['sources']!=8 or result['runs']!=112:raise AssertionError('incomplete official shard')


def selftest():
    data=b'c sample\np cnf 3 2\n1 -2\n0 3 0\n'
    text,n,cs=parse_cnf(data);assert n==3 and cs==[(1,-2),(3,)]
    assert expand('a.cnf.gz',gzip.compress(data))==data
    assert expand('a.cnf.xz',lzma.compress(data))==data
    assert expand('a.cnf.bz2',bz2.compress(data))==data
    for bad in (b'p cnf 2 1\n3 0\n',b'p cnf 2 1\n1\n',b'p cnf 2 2\n1 0\n'):
        try:parse_cnf(bad)
        except ValueError:pass
        else:raise AssertionError('invalid DIMACS accepted')
    print('X47_RESUME_SELFTEST_PASS',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('selftest','audit','select','run'))
    p.add_argument('--bundle',type=Path,default=Path('bundle'))
    p.add_argument('--sources',type=Path,default=Path('selection/resumed_sources'))
    p.add_argument('--out',type=Path,default=Path('memory-restore.json'))
    p.add_argument('--shard',type=int,default=0);a=p.parse_args()
    if a.command=='selftest':selftest()
    elif a.command=='audit':audit_memory(a.bundle,a.out)
    elif a.command=='select':select_sources(a.out)
    else:run_selected(a)

if __name__=='__main__':main()
