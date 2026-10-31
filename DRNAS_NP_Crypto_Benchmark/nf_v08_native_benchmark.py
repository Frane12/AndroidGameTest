#!/usr/bin/env python3
"""Compare native DRNAS NeuroFlow v0.8 to the same native CaDiCaL library.

Everything runs in one C++ executable. Both arms parse the same DIMACS and
run in their own fresh process. Internal timing is measured inside C++.
External CNFs were previously tested in v0.6.3-0.7.1: regression, not blind test.
Constructed controls are separately labelled and never pooled for broad claims.
"""
import csv,hashlib,json,random,statistics,subprocess,time
from pathlib import Path
from drnas_np_lab import normalize,read_dimacs
from nf_v063_external_fetch import build as get_sources

ROOT=Path(__file__).resolve().parent
BIN=ROOT/'native_v08/drnas_nf08'
EXTERNAL=ROOT/'nf063_external'
CONTROL=ROOT/'native_v08/constructed_controls'
OUT=ROOT/'native_v08/results'
REPEATS=3
MS_BUDGET=2000
MODES=('base','neuro','force')

def record_csv(path,records):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)

def constructed():
    """36 new deterministic synthetic renamable-Horn controls (12 each)."""
    CONTROL.mkdir(parents=True,exist_ok=True)
    out=[]
    for n in (30,60,100):
        for family in ('horn_sat','horn_unsat','near_horn'):
            for rep in range(4):
                rng=random.Random(202610310801+n*613+len(family)*191+rep*147)
                flips=[bool(rng.getrandbits(1)) for _ in range(n)]
                cls=[]
                for _ in range(3*n):
                    vs=rng.sample(range(1,n+1),3);head=rng.randrange(4)
                    cls.append(tuple(v if j==head else -v for j,v in enumerate(vs)))
                if family=='horn_unsat':
                    cls.extend([(1,),(-1,)])
                if family=='near_horn':
                    for _ in range(n//2):
                        a,b,c=rng.sample(range(1,n+1),3)
                        cls.append((a,b,c))
                cls=normalize(n,[tuple(-lit if flips[abs(lit)-1] else lit for lit in cl) for cl in cls])
                identifier=f'native_control_{family}_{n}_{rep}'
                file=CONTROL/(identifier+'.cnf')
                file.write_text(f'p cnf {n} {len(cls)}\n'+''.join(
                    ' '.join(map(str,c))+' 0\n' for c in cls),encoding='ascii')
                assert read_dimacs(file)==(n,cls)
                out.append(dict(id=identifier,family=family,group='constructed',
                  path=file,n=n,source_sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    return out

def external():
    with (EXTERNAL/'manifest.csv').open(encoding='utf-8') as f:
        manifest=list(csv.DictReader(f))
    assert len(manifest)==60
    rs=[]
    for item in manifest:
        if item['fetch_status']!='READY':continue
        f=EXTERNAL/(item['case_id']+'.cnf')
        assert hashlib.sha256(f.read_bytes()).hexdigest()==item['canonical_sha256']
        rs.append(dict(id=item['case_id'],family=item['source_group'],
            group='external',path=f,n=int(item['variables']),
            source_sha256=item['source_sha256']))
    return rs

def cms_reference(path):
    try:
        x=subprocess.run(['cryptominisat5','--verb','0',str(path)],
             text=True,capture_output=True,timeout=8)
        if 's UNSATISFIABLE' in x.stdout:return 'UNSAT'
        if 's SATISFIABLE' in x.stdout:return 'SAT'
        return 'UNKNOWN'
    except subprocess.TimeoutExpired:return 'REF_TIMEOUT'

def native(binary,path,mode,budget):
    t=time.perf_counter()
    try:
        process=subprocess.run([str(binary),'--input',str(path),'--mode',mode,
            '--budget-ms',str(budget)],capture_output=True,text=True,
            timeout=budget/1000+3)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'native hard timeout: {path.name} / {mode}')
    external_ms=(time.perf_counter()-t)*1000
    if process.returncode:
        raise RuntimeError(f'native crashed: {path.name}/{mode}: '+process.stderr[-1500:])
    try:res=json.loads(process.stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):
        raise RuntimeError(f'non-JSON native output {mode}: {process.stdout[-500:]} {process.stderr[-500:]}')
    assert res['status'] in ('SAT','UNSAT','UNKNOWN')
    assert res['status']!='SAT' or res['witness_valid'] is True
    res['external_process_ms']=round(external_ms,5)
    return res

def benchmark():
    OUT.mkdir(parents=True,exist_ok=True)
    # Corpus fetch is a separate immutable-source CI step, not trained here.
    examples=external()+constructed()
    random.Random(202610318808).shuffle(examples)
    cases=[];measurements=[]
    for idx,x in enumerate(examples):
        ref=cms_reference(x['path'])
        cases.append(dict(id=x['id'],group=x['group'],family=x['family'],
            n=x['n'],original_sha256=x['source_sha256'],reference=ref))
        for repeat in range(REPEATS):
            shift=(idx+repeat)%len(MODES)
            modes=MODES[shift:]+MODES[:shift]
            for mode in modes:
                r=native(BIN,x['path'],mode,MS_BUDGET)
                if ref in ('SAT','UNSAT') and r['status'] in ('SAT','UNSAT'):
                    assert ref==r['status'],(x['id'],mode,ref,r)
                measurements.append(dict(id=x['id'],group=x['group'],family=x['family'],
                    repeat=repeat,method=mode,reference=ref,
                    status=r['status'],route=r['route'],
                    total_ms=r['total_ms'],external_process_ms=r['external_process_ms'],
                    parse_ms=r['parse_ms'],gate_ms=r['gate_ms'],
                    probe_ms=r['probe_ms'],solver_ms=r['solver_ms'],
                    witness_valid=r['witness_valid']))
        if (idx+1)%10==0:print('EVALUATED',idx+1,'/',len(examples),flush=True)
    record_csv(OUT/'case_reference.csv',cases)
    record_csv(OUT/'raw_timings.csv',measurements)
    lookup={(m['id'],m['repeat'],m['method']):m for m in measurements}
    summaries=[]
    groups=sorted(set((m['group'],m['family']) for m in measurements))
    groups += [('external','ALL'),('constructed','ALL'),('ALL','ALL')]
    for group,family in groups:
        relevant=[c for c in cases if
            (group=='ALL' or c['group']==group) and
            (family=='ALL' or c['family']==family)]
        pairs=[];by_route={};closed={m:0 for m in MODES}
        for c in relevant:
            for k in range(REPEATS):
                trials={m:lookup[(c['id'],k,m)] for m in MODES}
                for key,item in trials.items():
                    if item['status'] in ('SAT','UNSAT'):
                        closed[key]+=1
                a,b=trials['base'],trials['neuro']
                if (c['reference'] in ('SAT','UNSAT') and
                    a['status']==b['status']==c['reference']):
                    pairs.append((float(a['total_ms']),float(b['total_ms'])))
                by_route[trials['neuro']['route']]=by_route.get(trials['neuro']['route'],0)+1
        gains=[a-b for a,b in pairs]
        summaries.append(dict(group=group,family=family,cases=len(relevant),
          reference_known=sum(c['reference'] in ('SAT','UNSAT') for c in relevant),
          base_solved=closed['base']//REPEATS,neuro_solved=closed['neuro']//REPEATS,
          force_solved=closed['force']//REPEATS,
          matched_pairs=len(pairs),
          base_median_ms=round(statistics.median(a for a,b in pairs),5) if pairs else '',
          neuro_median_ms=round(statistics.median(b for a,b in pairs),5) if pairs else '',
          mean_paired_gain_ms=round(statistics.mean(gains),5) if gains else '',
          median_paired_gain_ms=round(statistics.median(gains),5) if gains else '',
          neuro_wins=sum(x>0 for x in gains),
          horn_recognized=len({r['id'] for r in measurements if
              r['id'] in {c['id'] for c in relevant} and
              r['method']=='neuro' and 'Horn' in r['route']}),
          route_counts=json.dumps(by_route,sort_keys=True)))
    record_csv(OUT/'summary.csv',summaries)
    (OUT/'protocol.json').write_text(json.dumps(dict(
        release='v0.8 native C++ single-parse CaDiCaL',
        external_cases=60,constructed_cases=36,repeats=REPEATS,
        budget_ms=MS_BUDGET,source_reuse='60 external cases used previously; NOT a fresh holdout',
        baseline='same C++ parser and in-process libcadical as neuro fallback',
        time_metric='internal measured wall time, includes parsing, gates and libcadical; process startup separately measured',
        status_reference='CryptoMiniSat; reference timeouts excluded from speed paired gains',
        no_external_retraining=True,
        note='Counts and timeout rates accompany all matched-case comparisons.'
        ),indent=2))
    print('FINAL NATIVE V08 SUMMARY',flush=True)
    for s in summaries:print(json.dumps(s,ensure_ascii=False),flush=True)

if __name__=='__main__':benchmark()
