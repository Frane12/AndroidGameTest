#!/usr/bin/env python3
"""Retrospective guard-only screening on the unchanged 24-source MATH4 artifact.
No general solver speed claim; no holdout claim; counts independent certificates.
"""
import argparse,hashlib,json,os,platform,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_bridge import call
from check_math5 import verify
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pcmax_capacity'))
from check_clause_hall import check as check_hall
from check_capacity import check as check_bdd
FAMILIES=['exam-scheduling','school-timetabling','graph-coloring','lights-out','linear-equations',
          'multiplier-circuit-miters','stable-semantics','syndrome-decoding','van-der-waerden','chnl','count','boxfolding']
def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--start',type=int,default=0);p.add_argument('--stop',type=int,default=24)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    paths=sorted(args.inputs.glob('*.cnf'));assert len(paths)==24
    manifest=[dict(id=int(f.name.split('-')[0]),file=f.name,family=FAMILIES[int(f.name.split('-')[0])//2],
                   sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for f in paths]
    protocol=dict(kind='retrospective guard-only screen',source_count=24,repetitions=1,guard_budget_ms=750,
                  source_artifact=14133712771,source_run=43646454422,source_archive_sha256='44ecbad24dded4352bb07c9f13752e43bc62b70f9b81187f8bf9b280aa809d36',
                  single_logical_cpu=cpu,platform=platform.platform(),sources=manifest,
                  binaries={arm:hashlib.sha256(b.read_bytes()).hexdigest() for arm,b in [('MATH4',args.baseline),('MATH5',args.binary)]})
    (args.out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    rows=[]
    for f,source in list(zip(paths,manifest))[args.start:args.stop]:
        raw=f.read_bytes();row=dict(source);row['arms']={}
        # Alternate order to reduce fixed ordering bias; this is not a timing benchmark.
        arms=[('MATH4',args.baseline,'--math4'),('MATH5',args.binary,'--math5')]
        if source['id']%2:arms.reverse()
        for arm,binary,flag in arms:
            cert=args.out/(f.stem+'.'+arm+'.json')
            rc,wall,tele=call(binary,f,cert,flag,750)
            entry=dict(rc=rc,native_wall_s=wall,telemetry=tele,verified=False,checker_s=0)
            if rc==20:
                proof=json.loads(cert.read_text());fmt=proof['format'];t=time.perf_counter()
                if fmt=='drnas-math5-eo-xor-unit-v1':checked=verify(raw,proof)
                elif fmt=='drnas-math4-xor-unit-v1':checked=verify(raw,{**proof,'format':'drnas-math5-eo-xor-unit-v1','exact_one_groups':[]})
                elif fmt=='pcmax-clause-hall-v1':checked=check_hall(raw,proof)
                elif fmt=='pcmax-capacity-v1':checked=check_bdd(raw,proof)
                else:raise AssertionError(fmt)
                entry.update(verified=True,checker_s=time.perf_counter()-t,certificate_format=fmt,checked=checked)
            else:assert not cert.exists()
            entry['e2e_s']=wall+entry['checker_s'];row['arms'][arm]=entry
        rows.append(row)
        print(json.dumps({'id':source['id'],'family':source['family'],'arms':{a:{'verified':e['verified'],'e2e_s':round(e['e2e_s'],6),'reason':e['telemetry'].get('reason')} for a,e in row['arms'].items()}}),flush=True)
    (args.out/f'rows-{args.start}-{args.stop}.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main()
