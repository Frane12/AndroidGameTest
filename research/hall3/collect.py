#!/usr/bin/env python3
"""Freeze a metadata-selected subset of the actual SAT Competition 2026 Main track.

No solver is called. Size exclusions and download failures are retained.
Fresh means disjoint from the recorded exclusion manifest, not all historic runs.
"""
import hashlib, json, lzma, re, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'hall3_inputs'
CAT_URL = 'https://raw.githubusercontent.com/satcompetition/2026/d2f8f186dacc48b9bab7e4374aef0a3f46b96582/downloads/benchmark-compilation-script/benchmarks2026.csv'
MAIN_URL = 'https://satcompetition.github.io/2026/downloads/track_main_2026.uri'
FAMILIES = ['exam-scheduling', 'school-timetabling', 'graph-coloring',
    'lights-out', 'linear-equations', 'multiplier-circuit-miters',
    'argumentation', 'stable-semantics', 'syndrome-decoding',
    'ecc-equivalence-checking', 'cyclic-anti-bandwidth', 'van-der-waerden',
    'chnl', 'count', 'boxfolding', 'ntil', 'xor-shifting', 'sudoku-php']
MAX_ARCHIVE = 12_000_000
MAX_RAW = 65_000_000

def sha(data): return hashlib.sha256(data).hexdigest()

def download(url, limit):
    req = urllib.request.Request(url, headers={'User-Agent':'DRNAS-HALL3-frozen-standard26/1.0'})
    with urllib.request.urlopen(req, timeout=35) as response:
        if int(response.headers.get('Content-Length', 0)) > limit:
            raise ValueError('archive_size_excluded')
        data = response.read(limit+1)
    if len(data)>limit: raise ValueError('archive_size_excluded')
    return data

def main():
    OUT.mkdir(exist_ok=True)
    (OUT/'cnf').mkdir(exist_ok=True)
    exclusions=json.loads((ROOT/'research/hall3/exclusions.json').read_text())
    old_ids=set(exclusions['file_ids']); old_sha=set(exclusions['source_sha256'])
    cat=download(CAT_URL,3_000_000); uri=download(MAIN_URL,200_000)
    (OUT/'catalog.csv').write_bytes(cat); (OUT/'track_main_2026.uri').write_bytes(uri)
    ids=set(re.findall(r'/file/([a-f0-9]{32})',uri.decode()))
    assert len(ids)==400, ('unexpected_main_track_size',len(ids))
    rows=[dict(zip(('file_id','author','family','catalog_label','isohash','participates'),l.split()))
          for l in cat.decode().splitlines()[1:] if len(l.split())==6]
    rows=[r for r in rows if r['file_id'] in ids and r['file_id'] not in old_ids]
    cache_path=OUT/'selection-cache.json'
    cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    selected=[]; attempts=[]; used_iso=set(); used_sha=set()
    for family in FAMILIES:
        if len(selected)==24:break
        candidates=[r for r in rows if r['family']==family]
        picked=[]
        for wanted in ('sat','unsat'):
            # Catalog labels only balance the selection; they never certify outcomes.
            candidates.sort(key=lambda r:(r['catalog_label']!=wanted,
                sha(('HALL3-STANDARD26-V1:'+r['file_id']).encode())))
            for entry in candidates:
                if entry in picked or entry['isohash'] in used_iso: continue
                url='https://benchmark-database.de/file/'+entry['file_id']+'?context=cnf'
                try:
                    prior=cache.get(entry['file_id'])
                    if prior and 'error' in prior:raise ValueError(prior['error'])
                    if prior:
                        raw=(ROOT/prior['path']).read_bytes()
                        assert sha(raw)==prior['sha256']
                        archive_sha=prior['archive_sha256'];archive_size=prior['archive_bytes']
                    else:
                        packed=download(url,MAX_ARCHIVE)
                        archive_sha=sha(packed);archive_size=len(packed)
                        if packed.startswith(b'\xfd7zXZ\x00'):
                            decoder=lzma.LZMADecompressor()
                            raw=decoder.decompress(packed,max_length=MAX_RAW+1)
                            if len(raw)>MAX_RAW or not decoder.eof: raise ValueError('raw_size_excluded')
                        else: raw=packed
                    if len(raw)>MAX_RAW: raise ValueError('raw_size_excluded')
                    h=re.search(rb'^p\s+cnf\s+(\d+)\s+(\d+)\s*$',raw,re.M)
                    if not h: raise ValueError('missing_DIMACS_header')
                    digest=sha(raw)
                    if digest in old_sha or digest in used_sha: raise ValueError('known_source_excluded')
                    nv,nc=map(int,h.groups())
                    if nv>1_000_000 or nc>3_000_000: raise ValueError('header_size_excluded')
                    index=len(selected)
                    path=OUT/'cnf'/f'{index:02d}-{entry["file_id"]}.cnf'
                    path.write_bytes(raw)
                    rec=dict(entry,id=index,path=str(path.relative_to(ROOT)),url=url,
                        sha256=digest,archive_sha256=archive_sha,bytes=len(raw),
                        archive_bytes=archive_size,variables=nv,clauses=nc,
                        selected_main_track=True)
                    selected.append(rec);picked.append(entry)
                    used_sha.add(digest);used_iso.add(entry['isohash'])
                    print('HALL3_SOURCE '+json.dumps(rec,sort_keys=True),flush=True)
                    attempts.append(dict(file_id=entry['file_id'],family=family,result='selected'))
                    cache[entry['file_id']]=rec
                    cache_path.write_text(json.dumps(cache,indent=2)+'\n')
                    break
                except Exception as error:
                    attempts.append(dict(file_id=entry['file_id'],family=family,result=str(error)))
                    print('HALL3_EXCLUSION '+json.dumps(attempts[-1]),flush=True)
                    # Never retry the same unavailable/oversize candidate in the other label slot.
                    used_iso.add(entry['isohash'])
                    cache[entry['file_id']]={'error':str(error)}
                    cache_path.write_text(json.dumps(cache,indent=2)+'\n')
            else:
                attempts.append(dict(family=family,result='family_has_fewer_than_two_eligible_sources'))
                for old in selected[-len(picked):] if picked else []:
                    used_sha.discard(old['sha256']);used_iso.discard(old['isohash'])
                if picked:del selected[-len(picked):]
                break
    assert len(selected)==24 and len(used_sha)==24
    manifest=dict(protocol='HALL3-CF7-STANDARD26-V1',sources=selected,
        official_main_url=MAIN_URL,official_main_sha256=sha(uri),
        catalog_url=CAT_URL,catalog_sha256=sha(cat),
        exclusions_sha256=sha((ROOT/'research/hall3/exclusions.json').read_bytes()),
        selection='First 12 declared families with two eligible sources; label balance then fixed salted SHA order; size gates only',
        original_cnfs_unchanged=True,global_historical_novelty_claim=False,
        disjoint_from_recorded_exclusions=True,attempts=attempts)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('HALL3_FROZEN '+json.dumps(dict(sources=len(selected),families=len({s['family'] for s in selected}),
        manifest_sha256=sha((OUT/'manifest.json').read_bytes()))),flush=True)

if __name__=='__main__': main()
