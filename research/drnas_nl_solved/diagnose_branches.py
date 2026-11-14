#!/usr/bin/env python3
"""Observational 100ms traces. No pruning policy and no speed benchmark."""
import argparse,json,os,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research/drnas_nl_solved'))
import bench as T
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default='branch_diagnostic');a=p.parse_args()
    os.chdir(R);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert T.sha('build/drnas-nl-solved')=='7c11ef877f18fea0e6f84e2445aa1bb4cc295245dcabfd81477b7528fc3cd81a'
    sources=json.load(open('research/drnas_nl_solved/cohort_summary.json'))['sources']
    folder=Path(a.out);folder.mkdir(exist_ok=True);report=[]
    for s in sources:
        assert T.sha(s['path'])==s['sha256'];modes={}
        for mode in ('base','inputs'):
            stem=folder/f"{s['id']}-{mode}"
            cmd=['build/drnas-nl-solved',s['path'],'--mode','trace','--transitions',str(stem)+'.jsonl',
                 '--nl-focus',mode,'--coop4','off','--coop5','off','--time','.1','--stats','--x5-no-minimize']
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=2)
            assert r.returncode in (0,10),(s['id'],mode,r.returncode)
            stem.with_suffix('.stderr').write_text(r.stderr);stem.with_suffix('.stdout').write_text(r.stdout)
            if r.returncode==10:
                n,cs=T.B.parse_cnf(Path(s['path']).read_bytes());assert T.B.check_sat(r.stdout,cs,n)
            tr=[json.loads(l) for l in Path(str(stem)+'.jsonl').read_text().splitlines()]
            tr=[x for x in tr if x['type']=='transition']
            st=T.events(r.stderr,'X41_STATS')[0]
            modes[mode]={'status':st['status'],'decisions':st['decisions'],'conflicts':st['conflicts'],
                'first16_literals':[x['decision_literal'] for x in tr[:16]],
                'first16_implied':[x['logic']['unit_propagations_under_assumptions'] for x in tr[:16]],
                'first16_conflict':[x['propagation_conflict'] for x in tr[:16]],
                'assigned_after_16':next((x['after']['assigned'] for x in tr if x['before']['decisions']==16),None),
                'root_assigned':tr[0]['before']['assigned'] if tr else None,'transitions':tr}
        report.append({'id':s['id'],'name':s['filename'],'sha256':s['sha256'],'modes':modes})
    T.save(folder/'trace_report.json',{'diagnostic_only':True,'cap_s':.1,'no_speed_claim':True,'rows':report,
        'legacy_trace_policy_label_not_authoritative':True,'actual_policy_defined_by_nl_focus_mode':True})
    print('BRANCH_DIAGNOSTIC_COMPLETE',len(report))
if __name__=='__main__':main()
