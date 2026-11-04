#!/usr/bin/env python3
"""R106 fixed public SAT Competition 2025 sample. No synthetic fallback."""
import hashlib,json,lzma,pathlib,sys,urllib.request
def main(root):
    root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(pathlib.Path('research/r106_manifest.json').read_text())
    items=[]
    for name,status,ident,digest,size in manifest['cases']:
        request=urllib.request.Request('https://benchmark-database.de/file/'+ident,
                                      headers={'User-Agent':'DRNAS-R106-research/1'})
        with urllib.request.urlopen(request,timeout=100) as r:
            payload=r.read(3_000_000)
        if len(payload)>=3_000_000:raise RuntimeError('R106 oversized compressed source '+name)
        data=lzma.decompress(payload,memlimit=128*1024*1024)
        if len(data)!=size or hashlib.sha256(data).hexdigest()!=digest:
            raise RuntimeError('R106 immutable CNF hash/size mismatch '+name)
        (root/name).write_bytes(data)
        items.append(dict(name=name,expected=status,sha256=digest,bytes=size,
             source='SAT Competition 2025 GBD',url='https://benchmark-database.de/file/'+ident))
        print('R106_SHA_PINNED',name,digest,flush=True)
    (root.parent/'manifest.json').write_text(json.dumps(items,indent=2))
if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: fetch root-dir')
    main(sys.argv[1])
