#!/usr/bin/env python3
"""Locate a successful compatible memory artifact; validate before using its SQLite DB."""
import argparse,json,os,pathlib,sqlite3,urllib.parse,urllib.request
from drnas_r28_context_memory import Memory,SCHEMA,file_sha
NAME='drnas-context-memory-v1'
WORKFLOW='.github/workflows/drnas-r28-context-learning.yml'
def locate():
    repo=os.environ['GITHUB_REPOSITORY'];token=os.environ['GH_TOKEN'];current=int(os.environ.get('GITHUB_RUN_ID','0'))
    def api(path):
        req=urllib.request.Request('https://api.github.com/repos/'+repo+'/'+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
        with urllib.request.urlopen(req,timeout=30) as f:return json.load(f)
    found=None
    for page in range(1,4):
        items=api('actions/artifacts?name='+urllib.parse.quote(NAME)+'&per_page=100&page='+str(page))['artifacts']
        for art in items:
            run=art.get('workflow_run') or {};rid=run.get('id')
            if art['expired'] or not rid or rid==current or art['size_in_bytes']>32*1024*1024:continue
            meta=api('actions/runs/'+str(rid))
            if meta['conclusion']!='success' or meta['path']!=WORKFLOW or meta['event'] not in ('push','workflow_dispatch','workflow_call'):continue
            if meta['head_repository']['full_name']!=repo:continue
            found=rid;break
        if found or len(items)<100:break
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:
        f.write('found='+str(bool(found)).lower()+'\n')
        if found:f.write('run_id='+str(found)+'\n')
    print('R153_CONTEXT_RESTORE_SOURCE',json.dumps(dict(run_id=found,cold_start=not bool(found))),flush=True)
def validate(root):
    db=root/'memory.sqlite';manifest=root/'manifest.json'
    if not db.exists() and not manifest.exists():
        print('R153_CONTEXT_COLD_START no_previous_successful_snapshot=true',flush=True);return
    if not db.exists() or not manifest.exists():raise ValueError('incomplete saved memory')
    meta=json.loads(manifest.read_text())
    assert meta['schema']==SCHEMA and file_sha(db)==meta['database_sha256'],'snapshot version or SHA mismatch'
    conn=sqlite3.connect('file:'+str(db.resolve())+'?mode=ro',uri=True)
    assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok';conn.close()
    memory=Memory(db)
    try:
        assert memory.digest()==meta['stats_sha256'] and memory.generation()==meta['generation']
        print('R153_CONTEXT_RESTORE_VERIFIED',json.dumps(memory.info(),sort_keys=True),flush=True)
    finally:memory.close()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['locate','validate']);ap.add_argument('--root',type=pathlib.Path,default=pathlib.Path('drnas_memory'));a=ap.parse_args()
    if a.action=='locate':locate()
    else:validate(a.root)
if __name__=='__main__':main()
