#!/usr/bin/env python3
"""REAL-LEARN1 material revision 2. No synthetic training or outcome-based test selection."""
from __future__ import annotations
import argparse, bz2, collections, gzip, hashlib, io, json, lzma, re, tarfile, urllib.request
from pathlib import Path

PROTOCOL = 'DRNAS-REAL-LEARN1-MATERIAL2'
ARCHIVE = 'https://zenodo.org/records/15125952/files/sc02to24.zip?download=1'
SATLIB = 'https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/'
PACKAGES = (
    ('planning-blocks', 'PLANNING/BlocksWorld/blocksworld.tar.gz', 'planning_encoding'),
    ('planning-logistics', 'PLANNING/Logistics/logistics.tar.gz', 'planning_encoding'),
    ('bmc-hardware', 'BMC/bmc.tar.gz', 'documented_industrial_hardware'),
    ('circuit-bridge', 'DIMACS/BF/bf.tar.gz', 'circuit_fault_analysis'),
    ('circuit-stuck', 'DIMACS/SSA/ssa.tar.gz', 'circuit_fault_analysis'),
)
MAX_RAW = 18_000_000
FEATURES = ('log_vars','log_clauses','density','binary','unit','horn','width')

def sha(data): return hashlib.sha256(data).hexdigest()
def emit(tag, value): print(tag+' '+json.dumps(value,sort_keys=True),flush=True)
def save(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')

def family(name):
    name=Path(name).name.lower()
    name=re.sub(r'\.(cnf|xz|gz|bz2)$','',name)
    name=re.sub(r'\.(cnf|xz|gz|bz2)$','',name)
    name=re.sub(r'(?:[._-](?:used|shuffled)-as[._-]sat\d+[-_]\d+|[-_.]sc\d{4})','',name)
    name=re.sub(r'(?:[._-](?:sat|unsat|sanitized|debugged))(?=[._-]|$)','',name)
    # Related numerical variants and permutations must remain in one split.
    name=re.sub(r'\d+','#',name)
    return name

def parse(raw):
    """Validate all DIMACS tokens, preserve original bytes, canonicalize only for identity."""
    if not 1 <= len(raw) <= MAX_RAW: raise ValueError('raw size bound')
    header=None; clauses=[]; current=[]
    for line in raw.decode('ascii').splitlines():
        line=line.strip()
        if not line or line.startswith('c'): continue
        if line.startswith('%'): break
        fields=line.split()
        if fields[0]=='p':
            if header is not None or len(fields)!=4 or fields[1]!='cnf': raise ValueError('header')
            header=tuple(map(int,fields[2:]))
            if not 0<=header[0]<=300000 or not 0<=header[1]<=900000: raise ValueError('dimensions')
            continue
        if header is None: raise ValueError('missing header')
        for token in fields:
            lit=int(token)
            if abs(lit)>header[0]: raise ValueError('out-of-range literal')
            if lit: current.append(lit)
            else: clauses.append(tuple(current)); current=[]
    if header is None or current or len(clauses)!=header[1]: raise ValueError('clause count/termination')
    canonical=sorted(set(tuple(sorted(set(c))) for c in clauses))
    # Header counts, formatting, comment changes, duplicate clauses and order do not create new sources.
    identity=sha(('\n'.join(' '.join(map(str,c))+' 0' for c in canonical)).encode())
    return header[0],header[1],clauses,identity

def features(raw):
    """Bounded structural prefix, no filename, family, answer or reference-solver signal."""
    import math
    n=m=None; widths=[]; binary=unit=horn=0; current=[]
    for line in io.BytesIO(raw[:131072]):
        line=line.strip()
        if not line or line.startswith(b'c'): continue
        if line.startswith(b'%'): break
        fields=line.split()
        if fields[0]==b'p':
            if len(fields)!=4: break
            n,m=map(int,fields[2:]); continue
        if n is None: break
        for token in fields:
            try: lit=int(token)
            except ValueError: continue
            if lit: current.append(lit)
            else:
                k=len(current); widths.append(k); binary+=k==2; unit+=k==1
                horn+=sum(x>0 for x in current)<=1; current=[]
                if len(widths)>=256: break
        if len(widths)>=256: break
    if n is None: raise ValueError('no header in bounded feature prefix')
    count=max(1,len(widths))
    return dict(zip(FEATURES,(math.log1p(n),math.log1p(m),m/max(1,n),
                  binary/count,unit/count,horn/count,sum(widths)/count)))

def split_for(group):
    v=int(sha(('REAL1-MATERIAL2-SPLIT|'+group).encode())[:8],16)%100
    return 'train' if v<60 else 'validation' if v<80 else 'holdout'

def decompress(name,data):
    stream=io.BytesIO(data)
    if name.endswith('.xz'): stream=lzma.LZMAFile(stream)
    elif name.endswith('.gz'): stream=gzip.GzipFile(fileobj=stream)
    elif name.endswith('.bz2'): stream=bz2.BZ2File(stream)
    raw=stream.read(MAX_RAW+1)
    if len(raw)>MAX_RAW: raise ValueError('decompression limit')
    return raw

def prepare(args):
    from remotezip import RemoteZip
    out=args.out; out.mkdir(parents=True,exist_ok=False); (out/'cnf').mkdir()
    old_names=set(); old_sha=set(); excluded=collections.Counter(); errors=[]
    for p in args.previous.rglob('splits.json'):
        for s in json.loads(p.read_text()).get('sources',[]):
            old_sha.add(s['sha256'])
            if s.get('archive_path'): old_names.add(family(s['archive_path']))
    if not old_sha: raise RuntimeError('previous REAL1 provenance missing; refuse unsafe split reset')
    result=[]; identities=set(); per_family=collections.Counter(); total_bytes=0
    def add(raw,name,group,url,kind):
        nonlocal total_bytes
        try: n,m,clauses,identity=parse(raw)
        except (ValueError,UnicodeError) as e:
            excluded['invalid_or_oversized']+=1; return False
        h=sha(raw)
        if h in old_sha or family(name) in old_names:
            excluded['previous_REAL1_source_or_family']+=1; return False
        if identity in identities: excluded['semantic_duplicate']+=1; return False
        if per_family[group]>=12: excluded['family_quota']+=1; return False
        if total_bytes+len(raw)>1_000_000_000: raise RuntimeError('material byte budget exhausted')
        fn='cnf/'+h+'.cnf'; (out/fn).write_bytes(raw)
        result.append({'sha256':h,'semantic_sha256':identity,'file':fn,'family':group,
            'split':split_for(group),'source_url':url,'archive_path':name,'provenance':kind,
            'nvars':n,'nclauses':m,'bytes':len(raw),'features':features(raw)})
        identities.add(identity); per_family[group]+=1; total_bytes+=len(raw)
        return True
    for group,relative,kind in PACKAGES:
        url=SATLIB+relative
        try:
            with urllib.request.urlopen(url,timeout=60) as response:
                data=response.read(50_000_001)
            if len(data)>50_000_000: raise ValueError('package too large')
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
                for member in sorted(archive.getmembers(),key=lambda x:x.name):
                    if not member.isfile() or not member.name.lower().endswith('.cnf') or member.size>MAX_RAW: continue
                    add(archive.extractfile(member).read(MAX_RAW+1),member.name,group,url,kind)
        except Exception as exc:
            errors.append({'source':url,'error':str(exc)[:250]})
        emit('REAL1_MATERIAL_PACKAGE',{'package':group,'accepted':len(result),'errors':len(errors)})
    # Only range-download selected members, never the 28.7-GB archive as a whole.
    with RemoteZip(ARCHIVE,timeout=90) as archive:
        groups=collections.defaultdict(list)
        for e in archive.infolist():
            if e.is_dir() or not e.filename.lower().endswith(('.cnf','.cnf.xz','.cnf.gz','.cnf.bz2')): continue
            if not 40<=e.file_size<=800000: continue
            f=family(e.filename)
            if f in old_names: excluded['previous_family_metadata']+=1; continue
            if any(t in f for t in ('rbsat','rand','pigeon','php','tseitin','clique','colour','color','xor','queens')):
                excluded['named_crafted_or_random']+=1; continue
            groups[f].append(e)
        for values in groups.values(): values.sort(key=lambda e:(e.file_size,e.filename))
        order=sorted(groups,key=lambda f:(groups[f][0].file_size,sha(f.encode())))
        # Size-prioritized family-round-robin, independent of solver outcomes.
        attempts=0
        for depth in range(12):
            for f in order:
                if len(result)>=args.count or attempts>=args.count*3: break
                if depth>=len(groups[f]): continue
                e=groups[f][depth]; attempts+=1
                try: add(decompress(e.filename,archive.read(e)),e.filename,f,ARCHIVE,'publisher_normalized_competition_mixed')
                except (OSError,ValueError,EOFError,lzma.LZMAError) as exc:
                    excluded['read_or_decode_error']+=1
                if attempts%25==0: emit('REAL1_MATERIAL_PROGRESS',{'selected':len(result),'attempts':attempts})
            if len(result)>=args.count or attempts>=args.count*3: break
    splits={s:[r for r in result if r['split']==s] for s in ('train','validation','holdout')}
    if len(result)<100 or any(len(rr)<12 for rr in splits.values()):
        raise RuntimeError('insufficient independently split material: '+str({k:len(v) for k,v in splits.items()}))
    manifest={'protocol':PROTOCOL,'selection':'size-first family coverage; no solver results used',
        'scope':'retrospective mixed competition + documented SATLIB applications; NOT all industrial',
        'prior_exclusion_sources':len(old_sha),'prior_exclusion_families':len(old_names),
        'split_counts':{k:len(v) for k,v in splits.items()},
        'split_families':{k:len({r['family'] for r in v}) for k,v in splits.items()},
        'provenance_counts':dict(collections.Counter(r['provenance'] for r in result)),
        'exclusions':dict(excluded),'source_errors':errors,'sources':result,'total_bytes':total_bytes,
        'limits':['Semantic hash does not detect arbitrary variable-renaming isomorphism.',
                  'Filename families are conservative proxies, not verified application provenance.',
                  'No claim of global blindness across every historical experiment.']}
    save(out/'manifest.json',manifest)
    emit('REAL1_MATERIAL_READY',{k:v for k,v in manifest.items() if k!='sources'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--previous',type=Path,required=True);p.add_argument('--count',type=int,default=480)
    prepare(p.parse_args())
