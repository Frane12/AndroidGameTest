#!/usr/bin/env python3
"""Reuse the entire immutable general source set; never import a solver."""
import hashlib, json, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'math5_general_inputs'
P=json.loads((HERE/'prespec.json').read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    oldpath=ROOT/'cf7/manifest.json'
    assert digest(oldpath)==P['prior_source_manifest_sha256']
    old=json.loads(oldpath.read_text())
    assert old['count']==100 and len(old['sources'])==100
    assert len({s['sha256'] for s in old['sources']})==100
    assert len({s['normalized_name_family'] for s in old['sources']})==100
    assert {s['id'] for s in old['sources']}==set(range(100))
    OUT.mkdir(exist_ok=False);(OUT/'cnf').mkdir()
    sources=[]
    for s in sorted(old['sources'],key=lambda s:s['id']):
        original=ROOT/s['path'];assert digest(original)==s['sha256']
        path=OUT/'cnf'/f'{s["id"]:03d}-{s["sha256"][:16]}.cnf'
        shutil.copy2(original,path)
        sources.append(dict(id=s['id'],family=s['normalized_name_family'],sha256=s['sha256'],
            path=str(path.relative_to(ROOT)),bytes=s['bytes'],source_file=s['source_file'],
            prior_exposure=True,original_archive=old['archive']))
    manifest=dict(protocol=P['name'],sources=sources,selected=100,target=100,
        prespec_sha256=digest(HERE/'prespec.json'),prior_manifest_sha256=digest(oldpath),
        prior_source_run=43613581688,prior_source_artifact=14120948662,
        blind_holdout=False,selection_before_any_solver=True,blindness=P['blindness'])
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print('GENERAL_FROZEN '+json.dumps(dict(sources=100,name_groups=100,manifest_sha256=digest(OUT/'manifest.json'))),flush=True)

if __name__=='__main__':main()
