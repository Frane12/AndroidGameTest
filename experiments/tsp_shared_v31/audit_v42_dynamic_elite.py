#!/usr/bin/env python3
"""Fail-closed paired TSP v4.2 review: six seeds, four solvers, 30s checkpoints."""
import argparse,csv,json,statistics
from pathlib import Path
METHODS=('LKH-3','DRNAS v4','DRNAS v4.1 restart','DRNAS v4.2 selective')
CHECKPOINTS=(2,4,6,8,10,15,20,25,30)
CITIES=(2000,5000)
SEEDS=(0,1,2)

def ck(ok,msg):
    if not ok:raise RuntimeError('V42_AUDIT_FAILURE '+str(msg))

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--csv',required=True)
    a.add_argument('--out',required=True)
    args=a.parse_args()
    rows=list(csv.DictReader(open(args.csv,newline='')))
    ck(len(rows)==len(CITIES)*len(SEEDS)*len(METHODS)*len(CHECKPOINTS),
       'rows mismatch')
    keyed={}
    for r in rows:
        ck(r['method'] in METHODS and int(r['cities']) in CITIES and
           int(r['seed']) in SEEDS and int(r['checkpoint_s']) in CHECKPOINTS,
           'unknown method or instance')
        key=(int(r['cities']),int(r['seed']),r['method'],int(r['checkpoint_s']))
        ck(key not in keyed,'duplicate checkpoint')
        keyed[key]=r
    ck(len(keyed)==216,'missing/duplicate checkpoints')
    summary={}
    pairwise=[]
    for n in CITIES:
        table={}
        for method in METHODS:
            for seed in SEEDS:
                rr=[keyed[(n,seed,method,cp)] for cp in CHECKPOINTS]
                ck(all(row['status']!='error' for row in rr),'solver error')
                ck(all(row['final_length_units'] for row in rr),'missing final length')
                available=[float(row['best_length_units']) for row in rr
                           if row['best_length_units']]
                ck(bool(available),'no feasible tour at all')
                ck(all(a>=b-1e-6 for a,b in zip(available,available[1:])),
                   'incumbent increased')
                ck(float(rr[-1]['best_length_units'])>0 and
                   abs(float(rr[-1]['best_length_units'])-float(rr[-1]['final_length_units']))<0.001,
                   '30s incumbent/final disagreement')
                if method=='DRNAS v4.2 selective':
                    ck(all(int(row['protected_elite_slots'])==16 for row in rr),
                       'v4.2 protected elite slots changed')
                    ck(all(0<=int(row['selected_agents_unique'])<=64 for row in rr),
                       'invalid total distinct agent count (dynamic elite set permits 64 across waves)')
                ck(all(float(row['end_to_end_s'])>0 for row in rr),
                   'nonpositive measured elapsed time')
            subset=[keyed[(n,seed,method,30)] for seed in SEEDS]
            values=[float(row['final_length_units']) for row in subset]
            table[method]=dict(mean=round(statistics.mean(values),5),
                min=round(min(values),5),max=round(max(values),5),
                seeds=values,
                avg_first_incumbent_s=round(statistics.mean(
                    float(row['first_incumbent_s']) for row in subset),5),
                restart_waves=[int(row['restart_waves']) for row in subset],
                agent_unique=[int(row['selected_agents_unique']) for row in subset])
        base=table['DRNAS v4.1 restart']['mean']
        challenger=table['DRNAS v4.2 selective']['mean']
        table['v42_gain_over_v41_pct']=round(100*(base-challenger)/base,6)
        table['v42_gain_over_v4_pct']=round(100*(
            table['DRNAS v4']['mean']-challenger)/table['DRNAS v4']['mean'],6)
        table['v42_gap_to_lkh_pct']=round(100*(challenger-table['LKH-3']['mean'])/
                                         table['LKH-3']['mean'],6)
        table['v42_wins_vs_v41']=sum(
            table['DRNAS v4.2 selective']['seeds'][k] <
            table['DRNAS v4.1 restart']['seeds'][k] for k in range(3))
        summary[str(n)]=table
        for seed in SEEDS:
            pairwise.append(dict(cities=n,seed=seed,
                lkh=table['LKH-3']['seeds'][seed],
                v4=table['DRNAS v4']['seeds'][seed],
                v41=table['DRNAS v4.1 restart']['seeds'][seed],
                v42=table['DRNAS v4.2 selective']['seeds'][seed]))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    report=dict(protocol='DRNAS-TSP-V42-SELECTIVE-20261104',status='PASS_UNOFFICIAL',
                original_tsp_euc2d=True,inputs=6,methods=4,cutoffs=list(CHECKPOINTS),
                complete_trial_rows=len(rows),summary=summary,paired=pairwise,
                caveats=[
                    'Not a certified globally optimal tour; genuine LKH-3 is a heuristic benchmark',
                    'First LKH feasible-tour times approximate preprocessing + trial CPU time',
                    '64 DRNAS virtual agents are sequential, not 64 physical CPU cores',
                    'A same-runner paired experiment of only 3 seeds per city count; limited generality',
                    'Input generation is included for DRNAS and LKH preprocessing time is logged separately',
                    'Restart guard protects 16 ranked elites at each restart event; metrics do not prove other modes are identical',
                    'Same seed does not imply an identical initial tour across methods',
                    'This is an unofficial research comparison, not a world record'])
    (out/'r42_final.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# DRNAS TSP v4.2 Selective Stagnation — Final 30 s Comparison',
           '',
           '| Cities | LKH-3 | v4 | v4.1 restart | v4.2 selective | v4.2 gain vs v4.1 | v4.2 wins/3 |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for n in CITIES:
        d=summary[str(n)]
        lines.append('| '+str(n)+' | '+' | '.join(
            f"{d[m]['mean']:.3f}" for m in METHODS)+' | '+
            f"{d['v42_gain_over_v41_pct']:.4f}% | {d['v42_wins_vs_v41']}/3 |")
    lines+=['','## Selected restart behavior']
    for n in CITIES:
        r=summary[str(n)]['DRNAS v4.2 selective']
        lines.append(f"- {n} cities: restarts per seed {r['restart_waves']}, "
                     f"unique restart agents {r['agent_unique']}")
    lines+=['','## Limitations']+['- '+x for x in report['caveats']]
    (out/'r42_final.md').write_text('\n'.join(lines)+'\n')
    print('DRNAS_TSP_V42_FINAL_AUDIT_PASS',json.dumps(dict(
        inputs=6,rows=len(rows),summary=summary)),flush=True)

if __name__=='__main__':main()
