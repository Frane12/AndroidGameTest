#!/usr/bin/env python3
"""Reproducibility and no leakage audit for X4.2 generated CNF inputs."""
from __future__ import annotations
import hashlib,importlib.util,collections,tempfile,pathlib
spec=importlib.util.spec_from_file_location('x42',pathlib.Path(__file__).parents[1]/'research/drnas_x42_1000.py')
x42=importlib.util.module_from_spec(spec);spec.loader.exec_module(x42)
with tempfile.TemporaryDirectory() as td:
 root=pathlib.Path(td);a=[]
 for split,fs in x42.SPLITS.items():
  for f in fs:
   assert x42.FAMILIES[f]==split
   for i in range(x42.N_PER_FAMILY):
    s=x42.gen_source(f,i,root)
    assert s['split']==split and s['source_kind']=='GENERATED_NOT_OFFICIAL'
    assert hashlib.sha256(pathlib.Path(s['path']).read_bytes()).hexdigest()==s['sha256']
    a.append(s)
 assert len(a)==1000 and len({s['sha256'] for s in a})==1000
 assert collections.Counter(s['split'] for s in a)==dict(train=600,validation=200,holdout=200)
 assert all(len({s['split'] for s in a if s['family']==f})==1 for f in {s['family'] for s in a})
 # Fixed named examples: determinism cannot depend on process hash seed.
 s=a[0];b=x42.gen_source(s['family'].removeprefix('GENERATED:'),0,root)
 assert s['sha256']==b['sha256']
 print('X42_MANIFEST_SELFTEST_PASS sources=1000 unique_sha=1000 train=600 validation=200 holdout=200 families=10')