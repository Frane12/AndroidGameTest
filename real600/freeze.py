#!/usr/bin/env python3
"""Source-only, deterministic 600-CNF freeze; no solver is executed."""
import bz2, concurrent.futures, gzip, hashlib, io, json, lzma, os, random, re, shutil, urllib.request
from pathlib import Path

ROOT=Path.cwd(); OUT=ROOT/'real600_inputs'; TARGET=600
CATALOGS={
 'SAT2025': 'https://raw.githubusercontent.com/satcompetition/2025/1de9acf01846f96fd3d6a460bc2238ce3bb4e3a6/downloads/SC2025.uri',
 'SAT2026': 'https://raw.githubusercontent.com/satcompetition/2026/d2f8f186dacc48b9bab7e4374aef0a3f46b96582/downloads/track_main_2026.uri',
}
MAX_COMPRESSED=20*1024*1024; MAX_CNF=65*1024*1024
def digest(b): return hashlib.sha256(b).hexdigest()
def get(url, limit, timeout=25):
    req=urllib.request.Request(url,headers={'User-Agent':'DRNAS-REAL600-source-freeze/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as f:
        data=f.read(limit+1); dest=f.geturl(); name=f.headers.get('Content-Disposition','')
    if len(data)>limit: raise ValueError('size limit')
    return data,dest,name
def check(data):
    n=m=None; count=0; open_clause=False
    for line in data.splitlines():
        z=line.split()
        if not z or z[0] in (b'c', b'%'): continue
        if z[0]==b'p':
            if n is not None or len(z)!=4 or z[1]!=b'cnf': raise ValueError('header')
            n,m=map(int,z[2:]);
            if n<=0 or m<=0 or n>2000000 or m>5000000: raise ValueError('dimensions')
            continue
        if n is None: raise ValueError('missing header')
        for token in z:
            x=int(token)
            if abs(x)>n: raise ValueError('literal')
            if x: open_clause=True
            else: count+=1; open_clause=False
    if n is None or open_clause or count!=m: raise ValueError('clause count or terminator')
    return n,m
def download(item):
    year,url=item; row={'catalog':year,'url':url}
    try:
        raw,dest,name=get(url,MAX_COMPRESSED)
        if raw.startswith(b'\xfd7zXZ\x00'): f=lzma.LZMAFile(io.BytesIO(raw)); compression='xz'
        elif raw.startswith(b'\x1f\x8b'): f=gzip.GzipFile(fileobj=io.BytesIO(raw)); compression='gzip'
        elif raw.startswith(b'BZh'): f=bz2.BZ2File(io.BytesIO(raw)); compression='bzip2'
        else: f=io.BytesIO(raw); compression='plain'
        with f: data=f.read(MAX_CNF+1)
        if len(data)>MAX_CNF: raise ValueError('expanded size limit')
        n,m=check(data)
        row.update(status='READY',sha256=digest(data),compressed_sha256=digest(raw),bytes=len(data),vars=n,clauses=m,compression=compression,redirect=dest,content_disposition=name)
        return row,data
    except Exception as e:
        row.update(status='EXCLUDED',reason=(type(e).__name__+': '+str(e))[:180]); return row,None
def main():
    OUT.mkdir(exist_ok=False); (OUT/'cnf').mkdir(); sources=[]; attempts=[]; seen=set()
    def add(data,origin,**meta):
        h=digest(data)
        if h in seen: return False
        n,m=check(data); i=len(sources); p=OUT/'cnf'/f'{i:03d}-{h[:16]}.cnf'; p.write_bytes(data)
        sources.append(dict(id=i,path=str(p.relative_to(ROOT)),sha256=h,bytes=len(data),vars=n,clauses=m,origin=origin,**meta)); seen.add(h); return True
    core=json.loads((ROOT/'unified_realblind100_inputs/manifest.json').read_text())
    cf=json.loads((ROOT/'cf7/manifest.json').read_text())
    for s in core['sources']:
        data=(ROOT/s['path']).read_bytes(); assert digest(data)==s['sha256']; add(data,'CORE2 development original',original=s)
    for s in cf['sources']:
        data=(ROOT/s['path']).read_bytes(); assert digest(data)==s['sha256']; add(data,'CF7 development original',original=s)
    print('REAL600_PRIOR '+json.dumps({'unique':len(sources)}),flush=True)
    candidates=[]; catalog_meta={}
    for year,url in CATALOGS.items():
        data,_,_=get(url,200000); lines=[x.strip() for x in data.decode().splitlines() if x.strip()]
        assert len(lines)==400 and all(re.fullmatch(r'https?://benchmark-database\.de/file/[a-f0-9]{32}',x) for x in lines)
        lines=[x.replace('http://','https://') for x in lines]
        catalog_meta[year]={'url':url,'sha256':digest(data),'count':len(lines)}
        random.Random('DRNAS-REAL600-20261115-'+year).shuffle(lines)
        candidates.append([(year,x) for x in lines])
    # Interleave years. Deterministic source-only exclusions, never solver outcomes.
    candidates=[x for pair in zip(*candidates) for x in pair]
    for start in range(0,len(candidates),12):
        if len(sources)>=TARGET: break
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            batch=list(pool.map(download,candidates[start:start+12]))
        for row,data in batch:
            if data is not None:
                if len(sources)>=TARGET: row['status']='NOT_NEEDED'
                elif row['sha256'] in seen: row['status']='EXCLUDED_DUPLICATE'
                else: add(data,row['catalog'],original_url=row['url'],content_disposition=row['content_disposition'])
            attempts.append(row)
        print('REAL600_SOURCE '+json.dumps({'attempted':len(attempts),'selected':len(sources),'excluded':sum(r['status'].startswith('EXCLUDED') for r in attempts)}),flush=True)
    manifest={'protocol':'REAL600 source-only v1','target':TARGET,'selected':len(sources),'sources':sources,'catalogs':catalog_meta,'attempts':attempts,'retrospective':True,'blind_holdout':False,'history_disjoint':False,'selection':'frozen old sources then deterministic year-interleaved source-only acquisition, SHA dedup; no solver outcomes','limits':{'compressed_bytes':MAX_COMPRESSED,'cnf_bytes':MAX_CNF},'solver_executed':False,'commit':os.getenv('GITHUB_SHA')}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print('REAL600_FREEZE '+json.dumps({'target':TARGET,'selected':len(sources),'manifest_sha256':digest((OUT/'manifest.json').read_bytes())}),flush=True)
    if len(sources)!=TARGET: raise SystemExit('600 unique eligible original CNFs not available; no benchmark started')
if __name__=='__main__': main()
