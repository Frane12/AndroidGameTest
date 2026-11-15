#!/usr/bin/env python3
"""Outcome-free, preregistered selection; no solver or result reader is imported."""
import collections, gzip, hashlib, json, lzma, re, sqlite3, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'math5_blind_inputs'
P = json.loads((HERE / 'prespec.json').read_text())
def digest(raw): return hashlib.sha256(raw).hexdigest()
def save(p, data): p.write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')
def download(url, limit):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'DRNAS-MATH5-BLIND30/1'}), timeout=35) as f:
        if int(f.headers.get('Content-Length', 0)) > limit: raise ValueError('archive_size_gate')
        raw=f.read(limit+1)
    if len(raw)>limit: raise ValueError('archive_size_gate')
    return raw
def dimensions(raw):
    n=m=None; count=0; pending=False
    for line in raw.decode('ascii').splitlines():
        x=line.split()
        if not x or x[0]=='c': continue
        if x[0]=='p':
            if n is not None or len(x)!=4 or x[1]!='cnf': raise ValueError('bad_header')
            n,m=map(int,x[2:])
            if not 0<n<=P['max_vars'] or not 0<=m<=P['max_clauses']: raise ValueError('dimension_gate')
            continue
        if n is None: raise ValueError('missing_header')
        for token in x:
            v=int(token)
            if abs(v)>n: raise ValueError('literal_out_of_range')
            if v: pending=True
            else: count+=1;pending=False
    if n is None or pending or count!=m: raise ValueError('bad_clause_count')
    return n,m
def main():
    assert not OUT.exists(), 'Refuse overwrite of frozen inputs'
    OUT.mkdir(); (OUT/'cnf').mkdir()
    catraw=(ROOT/'research/hall3/catalog2026.csv').read_bytes()
    trackraw=(HERE/'track_main_2026.uri').read_bytes()
    old=json.loads((ROOT/'research/hall3/manifest.json').read_text())
    assert digest(catraw)==old['catalog_sha256']
    assert digest(trackraw)==old['official_main_sha256']
    mainids=set(re.findall(r'/file/([a-f0-9]{32})',trackraw.decode()));assert len(mainids)==400
    rows=[dict(zip(('file_id','author','family','catalog_label','isohash','participates'),l.split()))
        for l in catraw.decode().splitlines()[1:] if len(l.split())==6]
    exc=json.loads((ROOT/'research/hall3/exclusions.json').read_text())
    prior=old['sources']+json.loads((HERE/'prior_math4_selection.json').read_text())['source_ids']+json.loads((HERE/'prior_maxpar2_selection.json').read_text())['selected_sources']
    oldids=set(exc['file_ids'])|{r['file_id'] for r in prior}
    oldiso={r['isohash'] for r in prior}|{r['isohash'] for r in rows if r['file_id'] in oldids}
    oldsha=set(exc['source_sha256'])|{r['sha256'] for r in prior if 'sha256' in r}
    memory=ROOT/'global_snapshot/research/memory/global/global.sqlite.gz'
    assert memory.exists(), 'Pinned memory snapshot is mandatory'
    with tempfile.TemporaryDirectory() as d:
        db=Path(d)/'memory.sqlite';db.write_bytes(gzip.decompress(memory.read_bytes()))
        cx=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
        assert cx.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        memsha={r[0] for r in cx.execute('SELECT sha256 FROM sources UNION SELECT source_sha FROM observations UNION SELECT source_sha FROM legacy_experiences')}
        cx.close()
    oldsha.update(x for x in memsha if re.fullmatch('[a-f0-9]{64}',str(x)))
    save(OUT/'exclusion_audit.json',dict(memory_commit=P['memory_commit'],memory_gzip_sha256=digest(memory.read_bytes()),
        file_ids=sorted(oldids),isohashes=sorted(oldiso),source_sha256=sorted(oldsha),basis=P['blindness']))
    candidates=[r for r in rows if r['file_id'] in mainids and r['file_id'] not in oldids and r['isohash'] not in oldiso]
    rank=lambda s:digest((P['selection_seed']+':'+s).encode())
    candidates.sort(key=lambda r:(rank(r['family']),rank(r['file_id'])))
    save(OUT/'candidate_ranking.json',candidates)
    selected=[];attempts=[];seenids=set();seeniso=set(oldiso);seensha=set(oldsha);fc=collections.Counter()
    def choose(wanted,target):
        families=sorted({r['family'] for r in candidates},key=rank)
        while len(selected)<target:
            progress=False
            for family in families:
                if len(selected)>=target:break
                if fc[family]>=P['family_cap']:continue
                for row in candidates:
                    if row['family']!=family or row['file_id'] in seenids or row['isohash'] in seeniso:continue
                    if wanted and row['catalog_label']!=wanted:continue
                    seenids.add(row['file_id']); url='https://benchmark-database.de/file/'+row['file_id']+'?context=cnf'
                    try:
                        packed=download(url,P['archive_max_bytes'])
                        if packed.startswith(b'\xfd7zXZ\x00'):
                            dec=lzma.LZMADecompressor(memlimit=256*1024**2);raw=dec.decompress(packed,max_length=P['raw_max_bytes']+1)
                            if not dec.eof:raise ValueError('raw_size_gate')
                        else:raw=packed
                        if len(raw)>P['raw_max_bytes']:raise ValueError('raw_size_gate')
                        sha=digest(raw)
                        if sha in seensha:raise ValueError('known_or_duplicate_source_sha')
                        nv,nc=dimensions(raw);idx=len(selected)
                        path=OUT/'cnf'/f'{idx:02d}-{row["file_id"]}.cnf';path.write_bytes(raw)
                        record=dict(row,id=idx,path=str(path.relative_to(ROOT)),sha256=sha,archive_sha256=digest(packed),
                            bytes=len(raw),variables=nv,clauses=nc,url=url,selection_stage=wanted or 'diverse')
                        selected.append(record);seeniso.add(row['isohash']);seensha.add(sha);fc[family]+=1;progress=True
                        attempts.append(dict(file_id=row['file_id'],status='SELECTED'))
                        print('BLIND_SOURCE '+json.dumps(record,sort_keys=True),flush=True)
                        break
                    except (ValueError,OSError,lzma.LZMAError) as e:
                        attempts.append(dict(file_id=row['file_id'],family=family,status='INPUT_EXCLUDED',reason=str(e)[:250]))
                        print('BLIND_INPUT_EXCLUDED '+json.dumps(attempts[-1]),flush=True)
                save(OUT/'selection_progress.json',dict(sources=selected,attempts=attempts))
            if not progress:break
    choose('sat',8);sat_count=len(selected)
    choose('unsat',len(selected)+8);unsat_count=len(selected)-sat_count
    choose(None,P['target_sources'])
    manifest=dict(protocol=P['name'],sources=selected,attempts=attempts,target=P['target_sources'],selected=len(selected),
        catalog_sha256=digest(catraw),track_sha256=digest(trackraw),prespec_sha256=digest((HERE/'prespec.json').read_bytes()),
        exclusion_sha256=digest((OUT/'exclusion_audit.json').read_bytes()),catalog_sat_controls=sat_count,
        catalog_unsat_controls=unsat_count,selection_before_any_solver=True,blindness=P['blindness'])
    save(OUT/'manifest.json',manifest)
    assert len(selected)>=P['min_sources'], ('insufficient_inputs',len(selected))
    assert sat_count>=4, ('insufficient_SAT_controls',sat_count)
    print('BLIND_FROZEN '+json.dumps(dict(sources=len(selected),families=dict(fc),manifest_sha256=digest((OUT/'manifest.json').read_bytes()))),flush=True)
if __name__=='__main__':main()
