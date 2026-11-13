#!/usr/bin/env python3
"""Original SAT Competition 2024 crypto-related CNFs, paired diagnostic."""
import bz2,gzip,hashlib,json,lzma,os,pathlib,random,re
from remotezip import RemoteZip
import drnas_hybrid_bench_helpers as B

ARCHIVE='https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1'
ROOT=pathlib.Path('real_crypto_xor'); (ROOT/'cases').mkdir(parents=True,exist_ok=True)
B.CAP=10.0
B.ARMS=('R153_NATIVE','LTM9_NATIVE','DRNAS_HYBRID','DRNAS_GATED','Kissat','CaDiCaL','CryptoMiniSat')
LIMIT=64*1024*1024

def unpack(name,data):
    if name.endswith('.xz'):
        d=lzma.LZMADecompressor(); out=d.decompress(data,max_length=LIMIT+1)
        if not d.eof: raise ValueError('over size limit or truncated')
    elif name.endswith('.gz'):
        out=gzip.decompress(data)
    elif name.endswith('.bz2'):
        out=bz2.decompress(data)
    else: out=data
    if len(out)>LIMIT: raise ValueError('over size limit')
    return out

def parse(raw):
    n=None; declared=None; clauses=[]; pending=[]
    for line in raw.splitlines():
        line=line.strip()
        if not line or line.startswith(b'c'): continue
        if line.startswith(b'p '):
            parts=line.split()
            if len(parts)!=4 or parts[1]!=b'cnf' or n is not None: raise ValueError('bad header')
            n=int(parts[2]); declared=int(parts[3]); continue
        if line.startswith(b'%'): break
        if n is None: raise ValueError('missing header')
        for w in line.split():
            lit=int(w)
            if lit:
                if abs(lit)>n:raise ValueError('literal outside header')
                pending.append(lit)
            else: clauses.append(pending); pending=[]
    if pending or n is None or len(clauses)!=declared: raise ValueError('DIMACS clause count mismatch')
    return n,clauses

def collect():
    selected=[]; seen=set(); cap=2
    groups=('ascon','simon','sha','md5','aes')
    with RemoteZip(ARCHIVE,timeout=90) as z:
        entries=[x for x in z.infolist() if not x.is_dir() and x.filename.lower().endswith(('.cnf','.cnf.xz','.cnf.gz','.cnf.bz2')) and x.file_size<=4*1024*1024]
        for family in groups:
            candidates=sorted((e for e in entries if family in pathlib.PurePosixPath(e.filename).name.lower()),key=lambda e:(e.file_size,e.filename))
            print('REAL_CRYPTO_CANDIDATES '+json.dumps({'family':family,'eligible':len(candidates)}),flush=True)
            added=0
            for entry in candidates:
                try:
                    raw=unpack(entry.filename.lower(),z.read(entry)); n,clauses=parse(raw)
                except (ValueError,EOFError,lzma.LZMAError,OSError) as e:
                    print('REAL_CRYPTO_SKIP '+json.dumps({'source':entry.filename,'reason':str(e)}),flush=True);continue
                sha=hashlib.sha256(raw).hexdigest()
                if sha in seen:continue
                seen.add(sha)
                path=ROOT/'cases'/(sha+'.cnf');path.write_bytes(raw)
                case={'origin':'SAT2024_original_crypto','family':family,'index':len(selected),'sha256':sha,'vars':n,'clauses':clauses,'nclauses':len(clauses),'path':str(path.resolve()),'source_file':entry.filename,'bytes':len(raw),'archive_bytes':entry.file_size}
                selected.append(case);added+=1
                print('REAL_CRYPTO_SOURCE '+json.dumps({k:v for k,v in case.items() if k not in ('clauses','path')}),flush=True)
                if added==cap: break
    if not selected: raise RuntimeError('No crypto candidate CNFs found in source archive')
    return selected

def main():
    cases=collect()
    manifest={'archive':ARCHIVE,'selection':'first two smallest eligible files by compressed size per keyword; no outcome filtering','family_keywords':['ascon','simon','sha','md5','aes'],'source':'SAT Competition 2024 Main','known_blind':False,'source_preserved':True,'cap_s':B.CAP,'repetitions':2,'arms':B.ARMS,'cases':[{k:v for k,v in c.items() if k not in ('clauses','path')} for c in cases]}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rows=[]
    print('REAL_CRYPTO_START '+json.dumps({'cases':len(cases),'arms':B.ARMS,'repetitions':2,'cap_s':B.CAP,'trials':len(cases)*len(B.ARMS)*2,'generic_unsat_proof':'not checked','real_xor':'must inspect route'}),flush=True)
    for c in cases:
        for rep in range(2):
            order=list(B.ARMS);random.Random(c['sha256']+str(rep)).shuffle(order)
            statuses=set()
            for arm in order:
                row=B.run(c,arm,rep);rows.append(row);statuses.add(row['status'])
                print('REAL_CRYPTO_TRIAL '+json.dumps(row,sort_keys=True),flush=True)
                (ROOT/'results.json').write_text(json.dumps(rows,indent=2))
            if 'SAT_VERIFIED' in statuses and ('UNSAT_GF2_VERIFIED' in statuses or 'UNSAT_UNVERIFIED' in statuses):
                raise RuntimeError('SAT/UNSAT contradiction across arms')
    summary={f:B.report([r for r in rows if r['family']==f]) for f in sorted({c['family'] for c in cases})}
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2))
    print('REAL_CRYPTO_FINAL '+json.dumps(summary,sort_keys=True),flush=True)
if __name__=='__main__':main()
