#!/usr/bin/env python3
"""Post-hoc first-real-conflict ablation, not a blind generalization claim.
Reuse the audited REAL3 input, execution, SAT witness and reference-proof code.
All original binaries remain immutable. The candidate and rebuilt x3 control
share one new binary, compiler flags and diagnostic counters.
"""
from pathlib import Path
import argparse, json, os
import gate_real3_diagnosis as D
import gate_real36 as B

B.ARMS={
    'CORE':('build/drnas-x41','core'),
    'ADAPTIVE':('build/drnas-x3','x3'),
    'ADAPTIVE_REBUILT':('build/drnas-adaptive-fc','x3'),
    'ADAPTIVE_FC':('build/drnas-adaptive-fc','x3_fc'),
    'GATE_R3':('build/drnas-gate-r3','gate_r3'),
    'KISSAT':('build/kissat',None),
    'CADICAL':('build/cadical',None),
}
D.DEST=Path('fc_frozen')
D.FIELDS += ('fc_first_conflict_decision','fc_prefix_decisions','fc_first_literal',
             'fc_first_probe_conflicts','fc_first_probe_decision',
             'fc_probes_before_conflict','fc_first_backdoor_conflicts')

def freeze():
    D.freeze()
    p=json.loads((D.DEST/'protocol.json').read_text())
    p.update(experiment='ADAPTIVE_FIRST_REAL_CONFLICT',
        policy_change='Suppress depth probing and 2-SAT only until the first real CDCL conflict; keep all later policy rules unchanged',
        candidate='ADAPTIVE_FC',instrumented_control='ADAPTIVE_REBUILT',
        unmodified_reference_arms=['CORE','ADAPTIVE','GATE_R3','KISSAT','CADICAL'],
        candidate_source=json.loads(Path('build/adaptive_fc_source.json').read_text()),
        mechanism_tests=json.loads(Path('build/adaptive_fc_test.json').read_text()),
        source_base_commit='007bca3314ff4531092c482496344c12111a6ca3',
        diagnostic_success_rule={
          'SIMON':'all six candidate attempts verified SAT under one second',
          'BREAK':'at 30s all three candidate attempts verified; median no more than 10 percent above both frozen and rebuilt ADAPTIVE controls, each also verified 3/3',
          'MRPP':'report only; no tuning or exclusion',
          'statistical_claim':False,'promotion_to_main':False},
        limitations='Selected already-seen diagnosis, not independent test; no filename or source-ID routing enters native solver')
    D.dump(D.DEST/'protocol.json',p)
    B.emit('ADAPTIVE_FC_FROZEN',p)

def finish():
    D.finish()
    dest=Path('real3_final')
    report=json.loads((dest/'report.json').read_text())
    rows=[json.loads(s) for s in (dest/'paired_trials.jsonl').read_text().splitlines()]
    fc=[r for r in rows if r['arm']=='ADAPTIVE_FC']
    violations=[];missing=[]
    for r in fc:
        s=r['stats'];key=[r['filename'],r['rep'],r['cap_s']]
        if not s:missing.append(key);continue
        if s['fc_probes_before_conflict']!=0:violations.append(key+['early_probe'])
        if s['fc_first_probe_conflicts']!=-1 and s['fc_first_probe_conflicts']<1:
            violations.append(key+['probe_not_after_conflict'])
        if s['fc_first_backdoor_conflicts']!=-1 and s['fc_first_backdoor_conflicts']<1:
            violations.append(key+['early_2sat'])
        if s['conflicts']==0 and (s['depth_probes'] or s['backdoor_checks']):
            violations.append(key+['intervention_without_conflict'])
    simon=[r for r in fc if r['id']==2]
    simon_ok=len(simon)==6 and all(r['accepted'] and r['reported']=='SAT_WITNESS_VERIFIED' and r['process_wall_s']<1 for r in simon)
    name=D.TARGETS[0][0];results=report['results'][name]['30']
    candidate=results['ADAPTIVE_FC'];break_comparisons={}
    for arm in ('ADAPTIVE','ADAPTIVE_REBUILT'):
        control=results[arm]
        valid=candidate['accepted']==control['accepted']==3
        ratio=candidate['median_process_wall_s']/control['median_process_wall_s'] if valid else None
        break_comparisons[arm]={'both_verified_3_of_3':valid,'candidate_over_control_time_ratio':ratio,
                               'within_prespecified_10_percent':valid and ratio<=1.10}
    diagnostic_pass=simon_ok and all(x['within_prespecified_10_percent'] for x in break_comparisons.values()) and not violations and not missing
    report['first_conflict_audit']={'candidate_runs':len(fc),'observed_telemetry_runs':len(fc)-len(missing),
        'missing_telemetry':missing,'violations':violations,'simon_goal_pass':simon_ok,
        'break_comparisons':break_comparisons,'diagnostic_success_rule_pass':diagnostic_pass,
        'not_a_generalization_or_statistical_success_claim':True}
    report['status']='COMPLETE' if not violations else 'FAILED_MECHANISM_AUDIT'
    D.dump(dest/'report.json',report)
    lines=['# ADAPTIVE-FC: first-real-conflict diagnostic ablation','',
        'Three already-seen original CNFs. Seven paired arms, three repetitions, independent 5s and 30s deadlines: 126 runs.',
        'ADAPTIVE_REBUILT and ADAPTIVE_FC share the generated binary. Other controls reuse frozen original binaries.','',
        '| Formula | Cap | Arm | Verified / 3 | Median process wall (s) | PAR2 sum (s) |',
        '|---|---:|---|---:|---:|---:|']
    for name,caps in report['results'].items():
        for cap,arms in caps.items():
            for arm in B.ARMS:
                v=arms[arm]
                lines.append(f"| {name} | {cap} | {arm} | {v['accepted']} | {v['median_process_wall_s']:.6f} | {v['PAR2_sum_s']:.6f} |")
    lines += ['', '## Prespecified diagnostic goal', json.dumps(report['first_conflict_audit'],indent=2),
        '', 'SAT witnesses checked independently. UNSAT uses a checked reference-instance certificate, not a native DRNAS proof.',
        'All launch, supervisor and native probe costs enter process time; correctness audit costs are separate.',
        'A pass here is not permission to promote the candidate: an independent application benchmark is still required.']
    text='\n'.join(lines)+'\n';(dest/'summary.md').write_text(text)
    if os.getenv('GITHUB_STEP_SUMMARY'):Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(text)
    B.emit('ADAPTIVE_FC_FINAL',report)
    if violations:raise RuntimeError('First-real-conflict gate violation')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['freeze','shard','finish']);p.add_argument('--shard',type=int,default=0);a=p.parse_args()
    if a.stage=='freeze':freeze()
    elif a.stage=='shard':D.run_shard(a.shard)
    else:finish()
