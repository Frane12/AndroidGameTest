#!/usr/bin/env python3
"""SAT Competition 2026 Main: OFFICIAL original selected hashes only.

The immutable URI list is shipped by SAT Competition 2026 organizers:
https://github.com/satcompetition/2026/blob/main/downloads/track_main_2026.uri

Predeclare a uniform deterministic subset of 24 out of 400 BEFORE requests.
Download exact GBD file/<hash> links; do NOT replace an unavailable selected
instance with a convenient/easy alternative. Each original source and status
is independently logged. No training or policy changes from this benchmark.
"""
from __future__ import annotations
import bz2,csv,gzip,hashlib,json,lzma,random,re,time,urllib.error,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEST=ROOT/'satcomp26_official'
LIST_SOURCE_REPO='satcompetition/2026'
LIST_COMMIT='3e2dee7cf5aa643c77bf946280a3c1c520756ef9'
LIST_URL=(f'https://raw.githubusercontent.com/{LIST_SOURCE_REPO}/'
          f'{LIST_COMMIT}/downloads/track_main_2026.uri')
SEED=20261031
SAMPLE=24
MAX_DOWNLOAD_BYTES=18*1024*1024
MAX_CNFSIZE_BYTES=32*1024*1024
EXPECTED_LIST_ENTRIES=400

def request_data(url,limit,timeout=28):
    req=urllib.request.Request(url,headers={'User-Agent':'DRNAS-SATCOMP26-official-independent-benchmark/0.1',
       'Accept':'application/octet-stream'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        answer=r.read(limit+1)
        if len(answer)>limit:raise ValueError('too-large-source')
        return answer,r.geturl()

def header_check(path):
    """Low-cost first header check; real native C++ parser does full validation."""
    with path.open('rt',encoding='ascii',errors='strict') as f:
        for _ in range(10000):
            line=f.readline()
            if not line:break
            line=line.strip()
            if not line or line.startswith('c'):continue
            m=re.fullmatch(r'p\s+cnf\s+(\d+)\s+(\d+)',line)
            if not m:raise ValueError('not-DIMACS-header')
            n,cls=map(int,m.groups())
            if n<1 or cls<1:raise ValueError('empty DIMACS instance')
            if n>3000000 or cls>5000000:raise ValueError('too-large-n-or-clauses')
            return n,cls
    raise ValueError('missing-DIMACS-header')

def unpack(raw):
    if raw.startswith(b'\xfd7zXZ\x00'):return lzma.decompress(raw)
    if raw.startswith(b'\x1f\x8b'):return gzip.decompress(raw)
    if raw.startswith(b'BZh'):return bz2.decompress(raw)
    return raw

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    original,final_url=request_data(LIST_URL,180000)
    text=original.decode('ascii')
    links=[x.strip() for x in text.splitlines() if x.strip()]
    if len(links)!=EXPECTED_LIST_ENTRIES or len(set(links))!=EXPECTED_LIST_ENTRIES:
        raise RuntimeError(f'Official index unexpected number of URIs: {len(links)}')
    for url in links:
        if not re.fullmatch(r'http://benchmark-database\.de/file/[a-f0-9]{32}',url):
            raise ValueError('official URI list format changed: '+url)
    selected=sorted(random.Random(SEED).sample(links,SAMPLE))
    (DEST/'official_2026_uri_index_provenance.json').write_text(json.dumps(dict(
        source_repo=LIST_SOURCE_REPO,source_commit=LIST_COMMIT,url=LIST_URL,
        uri_index_sha256=hashlib.sha256(original).hexdigest(),number_official_entries=len(links),
        selection_seed=SEED,selected_before_downloads=selected,
        note='Official competition contains 400 hashed files; this is a preselected 24-file smoke sample, not entire official competition',
        storage='Global Benchmark Database (GBD) source URLs from organizers'),indent=2))
    records=[]
    for index,url in enumerate(selected,1):
        hash_id=url.rsplit('/',1)[1]
        # Official list is HTTP. Upgrade transport only, keep exact host/path/id.
        https_url='https://benchmark-database.de/file/'+hash_id
        record=dict(index=index,gbd_id=hash_id,source_url=https_url,
            status='NOT_FETCHED',reason='',raw_sha256='',dimacs_sha256='',
            download_bytes='',dimacs_bytes='',variables='',clauses='',resolved_url='')
        try:
            # Known GBD download endpoint; no fallback to unofficial CNFs.
            raw,redirected=request_data(https_url,MAX_DOWNLOAD_BYTES)
            normalized=unpack(raw)
            if len(normalized)>MAX_CNFSIZE_BYTES:raise ValueError('decompressed-too-large')
            path=DEST/(f'sc26_{index:03d}.cnf')
            path.write_bytes(normalized)
            n,cls=header_check(path)
            record.update(status='READY',raw_sha256=hashlib.sha256(raw).hexdigest(),
                dimacs_sha256=hashlib.sha256(normalized).hexdigest(),
                download_bytes=len(raw),dimacs_bytes=len(normalized),
                variables=n,clauses=cls,resolved_url=redirected)
        except Exception as e:
            record.update(status='UNAVAILABLE',reason=f'{type(e).__name__}:{str(e)[:200]}')
            (DEST/(f'sc26_{index:03d}.cnf')).unlink(missing_ok=True)
        records.append(record)
        print('OFFICIAL CNF',index,'/',len(selected),hash_id,record['status'],record['reason'],flush=True)
    with (DEST/'source_manifest.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    valid=[r for r in records if r['status']=='READY']
    print('OFFICIAL-2026 DOWNLOAD RESULTS:',len(valid),'downloadable of',len(selected),
          '; no substitutions or cherry-picks',flush=True)
    if not valid:
        raise RuntimeError('All official GBD downloads were unavailable. This is a DATA ACQUISITION failure, not a solver result.')

if __name__=='__main__':main()
