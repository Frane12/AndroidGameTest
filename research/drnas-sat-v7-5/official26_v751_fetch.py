#!/usr/bin/env python3
"""Fetch EXACT same 20 official SAT Competition 2026 CNFs as prior DRNAS
run #41204322891. No resampling, substitutions or training. All selected
files are authenticated with previous per-source DIMACS SHA256.
"""
import argparse,bz2,csv,gzip,hashlib,json,lzma,urllib.request
from pathlib import Path
OFFICIAL_PREVIOUS_RUN=41204322891
LIMIT_RAW=18*1024*1024
LIMIT_CNF=32*1024*1024

def unpack(data):
    if data.startswith(b'\xfd7zXZ\x00'):return lzma.decompress(data)
    if data.startswith(b'\x1f\x8b'):return gzip.decompress(data)
    if data.startswith(b'BZh'):return bz2.decompress(data)
    return data

def download(uri):
    req=urllib.request.Request(uri,headers={
        'User-Agent':'DRNAS-SAT-v7.5.1-2026-official-repeat/1.0',
        'Accept':'application/octet-stream'})
    with urllib.request.urlopen(req,timeout=60) as resp:
        data=resp.read(LIMIT_RAW+1)
        if len(data)>LIMIT_RAW:raise RuntimeError('Exceeded original raw file cap')
        return data,resp.geturl()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--previous',required=True)
    p.add_argument('--outdir',required=True)
    p.add_argument('--shard',type=int,required=True)
    p.add_argument('--shards',type=int,default=10)
    a=p.parse_args()
    if a.shards!=10 or not 0<=a.shard<10:raise RuntimeError('Require 10 predefined shards')
    with open(a.previous,newline='',encoding='utf-8') as f:
        source=list(csv.DictReader(f))
    assert len(source)==24,(len(source),'must be EXACT 24 preselected v1.0 originals')
    ready=sorted((row for row in source if row['status']=='READY'),
                 key=lambda row:int(row['index']))
    assert len(ready)==20,(len(ready),'must be EXACT original 20 ready CNFs')
    assert len({row['gbd_id'] for row in ready})==20
    chosen=ready[a.shard*2:a.shard*2+2]
    assert len(chosen)==2
    destination=Path(a.outdir);destination.mkdir(parents=True,exist_ok=True)
    accepted=[]
    for item in chosen:
        hashid=item['gbd_id']
        url='https://benchmark-database.de/file/'+hashid
        data,redirect=download(url)
        cnf=unpack(data)
        if len(cnf)>LIMIT_CNF:raise RuntimeError('Exceeded old 32MB normalized file cap '+hashid)
        digest=hashlib.sha256(cnf).hexdigest()
        if digest!=item['dimacs_sha256']:
            raise RuntimeError('OFFICIAL DIMACS SHA256 mismatch '+hashid+' '+digest+
                               ' vs frozen '+item['dimacs_sha256'])
        path=destination/(hashid+'.cnf')
        path.write_bytes(cnf)
        accepted.append(dict(id=hashid,source_index=int(item['index']),
                  path=str(path.resolve()),original_url=url,redirect=redirect,
                  sha256=digest,raw_sha256=hashlib.sha256(data).hexdigest(),
                  cnf_bytes=len(cnf),n=int(item['variables']),m=int(item['clauses']),
                  official_source='SAT Competition 2026 Main 400-hash GBD URI list',
                  previously_tested_run=OFFICIAL_PREVIOUS_RUN))
        print('PINNED READY',hashid, len(cnf),'bytes; sha256',digest,flush=True)
    (destination/'selected.json').write_text(json.dumps(accepted,indent=2))
    print('PASS: same two official 2026 CNFs for shard',a.shard,flush=True)

if __name__=='__main__':main()
