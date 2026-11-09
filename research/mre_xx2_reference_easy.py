#!/usr/bin/env python3
"""DRNAS XX2: prospective independent-reference-selected easy official originals.

12 fresh SAT Competition 2021-23 original GBD CNFs, selected by a predeclared
Kissat-only 0.02-4s screen (UNSAT additionally cross-checked with CaDiCaL).
NOT selected by DRNAS/CMS runtimes, structural features, or DRNAS outcomes.
8 modes, two source-matched seeds, 12s E2E cap, 192 trials, 6 shards.
Original CNF SHA pinned. SAT models replayed on original CNF; no independent LRAT.
XX2 is a held-out test of frozen, precommitted source-only feature policies.
Historical exclusion is explicit, not claimed globally exhaustive.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,subprocess,tempfile,time
import urllib.parse,urllib.request
import mre_xx_structural_gate as xx
import mre6b_blind_freeze as prior

ROOT=pathlib.Path('mre_xx2')
PROTO='DRNAS-XX2-FRESH-REFERENCE-EASY-12SHA-8ARM-2REP-12S-E2E-v1'
SALT='DRNAS-XX2-20261109-SOURCE-ONLY-RANK-FROZEN-v1'
YEARS=('2021','2022','2023')
URIS={
  '2021':'https://raw.githubusercontent.com/satcompetition/2021/master/downloads/main2021.url',
  '2022':'https://satcompetition.github.io/2022/downloads/track_main_2022.uri',
  '2023':'https://satcompetition.github.io/2023/downloads/track_main_2023.uri',
}
MODES=('original','scan_placebo','front100','front_short',
       'gate_dup','gate_context','kissat','cadical')
CAP=12.0
REPS=2
TARGET=12
SHARDS=6
MAX_FETCH=260
MAX_RAW=7*1024*1024
MAX_PLAIN=10*1024*1024
MAX_VARS=35000
MAX_CLAUSES=90000
SCREEN_CAP=4.0
REF_MIN_S=0.02
REF_MAX_S=4.0
UNSAT_CADICAL_CAP=6.0
# No training or gate threshold changes after seeing outcomes.
DUP_MIN_COUNT=16
DUP_MIN_RATIO=0.0005
SHORT_MIN_RATE=0.20
LATE_SHORT_MIN_FRAC=0.70

def need(ok,msg):
    if not ok: raise RuntimeError('XX2_FAIL_CLOSED '+str(msg))
def sha(b):return hashlib.sha256(b).hexdigest()
def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def seed(c,rep):return xx.seed(c,rep)
def get(url,maxbytes,seconds=35):
    q=urllib.request.Request(url,headers={'User-Agent':'DRNAS-XX2-Frozen-Original-20261109/1.0'})
    with urllib.request.urlopen(q,timeout=seconds) as f:b=f.read(maxbytes+1)
    need(len(b)<=maxbytes,'source exceeds hard download limit '+url)
    return b
def official_ids(year):
    url=URIS[year];raw=get(url,150000,35)
    ids=[line.strip().rsplit('/',1)[-1] for line in raw.decode().splitlines()
         if line.strip() and not line.startswith('#')]
    need(len(ids)>=300 and len(set(ids))==len(ids) and
         all(re.fullmatch('[a-f0-9]{32}',g) for g in ids),
         'official main track GBD index unexpectedly changed '+year)
    return ids,dict(url=url,sha256=sha(raw),count=len(ids))

def mini_metadata(year,universe):
    query='track=main_'+year+' and minisat1m=yes'
    url='https://benchmark-database.de/getinstances?context=cnf&query='+urllib.parse.quote(query,safe='')
    try:
        raw=get(url,500000,25)
        ids=[line.strip().rsplit('/',1)[-1] for line in raw.decode().splitlines() if line.strip()]
        if not ids or not all(re.fullmatch('[a-f0-9]{32}',g) for g in ids):
            return set(),dict(usable=False,reason='no_valid_32_hex_ids')
        return set(ids)&set(universe),dict(usable=True,sha256=sha(raw),count=len(ids))
    except Exception as ex:
        return set(),dict(usable=False,reason=(type(ex).__name__+': '+str(ex))[:140])

def parse_ref(p,src):
    need(p.returncode in (10,20),'reference solver failed exit code')
    status='SAT' if p.returncode==10 else 'UNSAT'
    need(('s SATISFIABLE' if status=='SAT' else 's UNSATISFIABLE') in p.stdout,
         'reference reported contradictory verdict text')
    if status=='SAT':
        model={}
        for line in p.stdout.splitlines():
            if line.startswith('v '):
                for lit in map(int,line[2:].split()):
                    if lit:
                        need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                             'reference model repeated contradictory literal')
                        model[abs(lit)]=lit>0
        xx.x11.x9.x6.x4.base.cms.verify_model(src,model)
    return status

def reference_screen(src):
    # Only Kissat & CaDiCaL determine eligibility; DRNAS never called here.
    start=time.perf_counter()
    try:
        p=subprocess.run([str(pathlib.Path('built/bin/kissat_4_0_4').resolve()),
            '--seed=117',str(src.resolve())],capture_output=True,text=True,
            errors='replace',timeout=SCREEN_CAP)
    except subprocess.TimeoutExpired:
        return dict(status='KISSAT_TIMEOUT',kissat_s=SCREEN_CAP,eligible=False)
    t=time.perf_counter()-start
    need(p.returncode in (10,20),'Kissat screening process exited abnormally')
    verdict=parse_ref(p,src)
    cross=False
    if verdict=='UNSAT':
        try:
            q=subprocess.run(['/usr/bin/cadical',str(src.resolve())],
                capture_output=True,text=True,errors='replace',
                timeout=UNSAT_CADICAL_CAP)
        except subprocess.TimeoutExpired:
            return dict(status='UNSAT_CADICAL_TIMEOUT',kissat_s=round(t,6),
                        eligible=False)
        cross=(q.returncode==20 and 's UNSATISFIABLE' in q.stdout)
        need(cross,'independent CaDiCaL disagrees with Kissat UNSAT')
    accepted=(REF_MIN_S<=t<=REF_MAX_S)
    return dict(status=verdict,kissat_s=round(t,6),
       eligible=accepted,SAT_original_verified=verdict=='SAT',
       UNSAT_cross_solver_without_LRAT=cross)

def structure(src,n,m):
    _,clauses=xx.x11.x9.x2.parse(src)
    need(len(clauses)==m,'source DIMACS clause count mismatch')
    dup_idx=xx.x11.x9.x6.x3.duplicates(clauses)
    q=max(1,len(clauses)//2)
    short=sum(len(c)<=3 for c in clauses)
    late=sum(len(c)<=3 for c in clauses[q:])
    first_short=sum(len(c)<=3 for c in clauses[:q])
    counts=collections.Counter(len(c) for c in clauses)
    return dict(duplicate_count=len(dup_idx),duplicate_rate=len(dup_idx)/max(1,m),
       duplicate_front_quarter=sum(i<m//4 for i in dup_idx),
       short_rate=short/max(1,m),late_short_fraction=late/max(1,short),
       early_short_rate=first_short/max(1,q),
       binary_rate=counts[2]/max(1,m),ternary_rate=counts[3]/max(1,m),
       unit_rate=counts[1]/max(1,m),vars=n,clauses=m,
       transformed_front_short_changes=any(len(c)>3 for c in clauses[:max(1,m//3)]),
       source_only=True)

def choose(sig,mode):
    if mode=='gate_dup':
        return 'front100' if sig['duplicate_count']>0 else 'original'
    need(mode=='gate_context','unknown gate')
    if (sig['duplicate_count']>=DUP_MIN_COUNT and
        sig['duplicate_rate']>=DUP_MIN_RATIO):
        return 'front100'
    if (sig['short_rate']>=SHORT_MIN_RATE and
        sig['late_short_fraction']>=LATE_SHORT_MIN_FRAC):
        return 'front_short'
    return 'original'

def reorder_short(clauses):
    # Stable partition into unit, binary, ternary, long; no clause is changed.
    parts=[[],[],[],[]]
    for c in clauses:parts[min(len(c),4)-1].append(c) if len(c)<=3 else parts[3].append(c)
    out=[c for part in parts for c in part]
    need(collections.Counter(out)==collections.Counter(clauses),
         'front_short changes exact original raw clause multiset')
    return out

def freeze():
    ROOT.mkdir(exist_ok=True)
    xx_manifest=json.loads(pathlib.Path('mre_xx/manifest.json').read_text())
    x11_manifest=json.loads(pathlib.Path('mre_x11/manifest.json').read_text())
    need(len(xx_manifest['cases'])==24 and len(x11_manifest['cases'])==32,
         'X11 or XX prior complete original manifests unavailable')
    indices={};pools={};all_ids=set();minis={}
    for year in YEARS:
        ids,info=official_ids(year)
        mini,mmeta=mini_metadata(year,ids)
        indices[year]=info;minis[year]=mmeta;pools[year]=(ids,mini)
        all_ids.update(ids)
    prior_ids,prior_sha=prior.inspect_repo_ids(all_ids)
    prior_historical=set(s.strip() for s in prior.PRIOR.read_text().splitlines()
         if re.fullmatch('[a-f0-9]{32}',s.strip()))
    exclude=prior_ids|prior_historical|{c['gbd'] for c in xx_manifest['cases']}|{
        c['gbd'] for c in x11_manifest['cases']}
    prior_sha|={c['sha256'] for c in xx_manifest['cases']}|{
        c['sha256'] for c in x11_manifest['cases']}
    # Rank metadata 'minisat1m=yes' first, then all other official originals.
    # Reference screen, never metadata alone, decides admission.
    ranked={}
    for year in YEARS:
        ids,mini=pools[year]
        ranked[year]=sorted((g for g in ids if g not in exclude),
             key=lambda g:(0 if g in mini else 1,
                           sha((SALT+'|'+year+'|'+g).encode())))
    queue=[]
    for idx in range(max(map(len,ranked.values()))):
        for year in YEARS:
            if idx<len(ranked[year]):queue.append((year,ranked[year][idx]))
    trace=[];selected=[];sigs=[];seen=set();counts=collections.Counter()
    prior.r32p.CNF_LIMIT=MAX_PLAIN
    for pos,(year,gbd) in enumerate(queue[:MAX_FETCH]):
        if len(selected)>=TARGET:break
        rec=dict(year=year,gbd=gbd,rank=pos,metadata_easy=(gbd in pools[year][1]))
        path=ROOT/(gbd+'.cnf')
        try:
            packed=get('https://benchmark-database.de/file/'+gbd,MAX_RAW,20)
            plain,compress=prior.r32p.decode(packed)
            need(len(plain)<=MAX_PLAIN,'decompressed CNF too large')
            n,m=prior.r32p.parse_dimacs_metadata(plain)
            need(0<n<=MAX_VARS and 0<m<=MAX_CLAUSES,'geometry above hard bounds')
            digest=sha(plain)
            need(digest not in prior_sha and digest not in seen,
                 'source SHA historically used or repeated')
            path.write_bytes(plain)
            screen=reference_screen(path)
            rec.update(sha256=digest,vars=n,clauses=m,
                       screen=screen,compression=compress)
            if screen['eligible']:
                sig=structure(path,n,m)
                selected.append(dict(gbd=gbd,sha256=digest,filename=path.name,
                    year=year,vars=n,clauses=m,bytes=len(plain),
                    cohort='fresh_reference_easy',reference_screen=screen,
                    source_url='https://benchmark-database.de/file/'+gbd,
                    source_registry_checked_not_globally_exhaustive=True))
                sigs.append(dict(gbd=gbd,sha256=digest,**sig))
                seen.add(digest)
                counts[year]+=1
                rec['action']='frozen_after_reference_only_screen'
            else:
                rec['action']='rejected_by_reference_only_band'
                path.unlink(missing_ok=True)
        except Exception as ex:
            path.unlink(missing_ok=True)
            rec['action']='source_error_rejected'
            rec['detail']=(type(ex).__name__+': '+str(ex))[:200]
        trace.append(rec)
        print('XX2_SCREEN',json.dumps(rec,sort_keys=True),flush=True)
    need(len(selected)==TARGET,
         'insufficient reference-easy official original CNFs; refuse to invent 12 sources')
    need(len({c['sha256'] for c in selected})==TARGET,'source repeated')
    decisions=[]
    for c,s in zip(selected,sigs):
        need(c['sha256']==s['sha256'],'source/signal paired incorrectly')
        decisions.append(dict(gbd=c['gbd'],sha256=c['sha256'],
             simple=choose(s,'gate_dup'),context=choose(s,'gate_context'),
             structural_signal_only=True))
    save(ROOT/'structures.json',dict(protocol=PROTO,sources=sigs))
    save(ROOT/'manifest.json',dict(protocol=PROTO,cases=selected,
         source_count=TARGET,expected_trials=TARGET*REPS*len(MODES),
         modes=MODES,reps=REPS,cap_s=CAP,years=YEARS,
         reference_min_s=REF_MIN_S,reference_max_s=REF_MAX_S,
         reference_screen_solver='unchanged X11 Kissat-4.0.4 binary',
         unsat_reference_crosscheck='CaDiCaL-1.7.4; not independent LRAT',
         reference_conditioned_sampling=True,
         not_globally_blind=True,
         no_DRNAS_timing_or_feature_in_selection=True,
         source_disjoint_declared_registry=True,
         historical_registry_not_exhaustive=True,
         no_auto_promotion=True,
         group_counts=dict(counts),prior_exclusions=len(exclude),
         source_indices=indices,mini_metadata=minis,gate_thresholds=dict(
             duplicates_min=DUP_MIN_COUNT,duplicate_rate_min=DUP_MIN_RATIO,
             short_rate_min=SHORT_MIN_RATE,
             late_short_fraction_min=LATE_SHORT_MIN_FRAC),
         gate_decisions=decisions,screen_trace=trace))
    print('XX2_FREEZE_PASS',TARGET,dict(counts),
          'gate',collections.Counter(d['context'] for d in decisions),flush=True)

def verify():
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and len(m['cases'])==TARGET and
         m['expected_trials']==192 and m['cap_s']==CAP and
         m['modes']==list(MODES),'XX2 frozen protocol drift')
    for c in m['cases']:
        p=ROOT/c['filename']
        need(sha(p.read_bytes())==c['sha256'] and len(p.read_bytes())==c['bytes'],
             'original CNF SHA or length mismatch')
    return m

def trial(c,rep,mode):
    need(mode in MODES and rep in range(REPS),'unknown mode/rep')
    src=ROOT/c['filename'];random_seed=seed(c,rep)
    env=os.environ.copy();env.pop('DRNAS_MAX_CONFLICTS',None)
    selection=mode;sig=None;verified=False;model={};stats=None
    status='TIMEOUT';raw='TIMEOUT'
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        start=time.perf_counter();use=src
        if mode in ('scan_placebo','gate_dup','gate_context'):
            sig=structure(src,c['vars'],c['clauses'])
            selection=('original' if mode=='scan_placebo' else choose(sig,mode))
        if selection in ('front100','front_short'):
            n,clauses=xx.x11.x9.x2.parse(src)
            changed=(xx.x11.transform(clauses,'front100')
                     if selection=='front100' else reorder_short(clauses))
            need(collections.Counter(changed)==collections.Counter(clauses),
                 'non-permutation introduced in XX2 E2E')
            use=pathlib.Path(td)/'permuted.cnf'
            xx.x11.x9.x2.write(use,n,changed)
        prep=time.perf_counter()-start
        if CAP-prep>0:
            if selection=='kissat':
                cmd=[str(pathlib.Path('built/bin/kissat_4_0_4').resolve()),
                     '--seed='+str(random_seed),str(use.resolve())]
            elif selection=='cadical':
                cmd=['/usr/bin/cadical',str(use.resolve())]
            else:
                cmd=[str(pathlib.Path('mre_x4/bin/native').resolve()),
                    str(use.resolve()),'x_native',str(random_seed)]
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,
                    errors='replace',env=env,timeout=CAP-prep)
            except subprocess.TimeoutExpired:p=None
            if p is not None:
                if selection in ('kissat','cadical'):
                    status=parse_ref(p,src)
                    verified=(status=='SAT')
                else:
                    need(p.returncode==0,'CMS backend crash: '+p.stderr[-350:])
                    gate=xx.x11.x9.x6.x4.base.parse_gate(p.stdout,'x_native')
                    need(not gate['applied'],'CMS changed its original CNF')
                    status,model,stats=xx.x11.x9.x6.x4.base.cms.parsed_native(p.stdout)
                    if status=='SAT':
                        xx.x11.x9.x6.x4.base.cms.verify_model(src,model)
                        verified=True
        elapsed=time.perf_counter()-start
        raw=status
        if elapsed>CAP or status not in ('SAT','UNSAT'):status='TIMEOUT'
    binary=('/usr/bin/cadical' if selection=='cadical' else
            'built/bin/kissat_4_0_4' if selection=='kissat' else 'mre_x4/bin/native')
    return dict(protocol=PROTO,gbd=c['gbd'],sha256=c['sha256'],
         year=c['year'],cohort=c['cohort'],rep=rep,seed=random_seed,
         mode=mode,selected=selection,status=status,raw_status=raw,
         elapsed_s=round(elapsed,6),preprocessing_s=round(prep,6),
         PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),
         SAT_original_verified=verified,UNSAT_independent_LRAT=False,
         source_signals=sig,native_stats=stats,
         binary_sha256=sha(pathlib.Path(binary).read_bytes()),
         independent_seed_applied=selection!='cadical')

def shard(idx):
    m=verify();need(0<=idx<SHARDS,'shard out of bounds')
    cases=[c for i,c in enumerate(m['cases']) if i%SHARDS==idx]
    need(len(cases)==2,'shard must contain two originals')
    rows=[]
    for c in cases:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(seed(c,rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,rep,mode)
                rows.append(r);save(ROOT/('shard-%d.json'%idx),rows)
                print('XX2_TRIAL',json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==32,'shard lost rows')
    print('XX2_SHARD_PASS',idx,32,flush=True)

def audit():
    m=verify();rows=[];seen=set()
    bysha={c['sha256']:c for c in m['cases']}
    structs={s['sha256']:s for s in json.loads((ROOT/'structures.json').read_text())['sources']}
    for i in range(SHARDS):
        rows+=json.loads((ROOT/('shard-%d.json'%i)).read_text())
    need(len(rows)==TARGET*REPS*len(MODES)==192,'not 192 paired original trials')
    for r in rows:
        c=bysha.get(r['sha256'])
        need(c and c['gbd']==r['gbd'] and r['protocol']==PROTO and
             r['mode'] in MODES and r['rep'] in range(REPS) and
             seed(c,r['rep'])==r['seed'],'original SHA/seed pairing broken')
        key=(r['sha256'],r['mode'],r['rep'])
        need(key not in seen,'duplicate matched trial');seen.add(key)
        need(r['status'] in ('SAT','UNSAT','TIMEOUT'),'invalid verdict')
        need(r['status']!='SAT' or r['SAT_original_verified'],
             'SAT witness not checked against original')
        need(r['status']!='TIMEOUT' or r['PAR2_s']==2*CAP,'PAR2 timeout wrong')
        need(r['status']=='TIMEOUT' or
             (r['elapsed_s']<=CAP and r['PAR2_s']==r['elapsed_s']),
             'successful time outside E2E cap')
        if r['mode'] in ('gate_dup','gate_context','scan_placebo'):
            srcsig=structs[r['sha256']]
            got=r['source_signals']
            need(got is not None and got['duplicate_count']==srcsig['duplicate_count'] and
                 abs(got['short_rate']-srcsig['short_rate'])<1e-10,
                 'stratum features changed at runtime')
            expected=('original' if r['mode']=='scan_placebo' else choose(srcsig,r['mode']))
            need(expected==r['selected'],'source-only gate changed policy')
        else:
            need(r['selected']==r['mode'],'fixed-arm selection changed')
    per_source=[]
    for c in m['cases']:
        rr=[r for r in rows if r['sha256']==c['sha256']]
        verdicts={r['status'] for r in rr if r['status']!='TIMEOUT'}
        need(len(verdicts)<=1,'original CNF produced conflicting SAT/UNSAT verdicts')
        ref_unsat=any(r['mode'] in ('kissat','cadical') and r['status']=='UNSAT'
                      for r in rr)
        cms_unsat=any(r['mode'] not in ('kissat','cadical') and r['status']=='UNSAT'
                      for r in rr)
        for r in rr:
            r['UNSAT_cross_solver_agreement_no_LRAT']=(
              r['status']=='UNSAT' and ref_unsat and cms_unsat)
            r['accepted_solved']=(
              r['status']=='SAT' or r['UNSAT_cross_solver_agreement_no_LRAT'])
            r['audited_PAR2_s']=(r['PAR2_s'] if r['accepted_solved'] else 2*CAP)
        scores={mode:round(sum(r['audited_PAR2_s'] for r in rr
                          if r['mode']==mode),6) for mode in MODES}
        per_source.append(dict(gbd=c['gbd'],sha256=c['sha256'],year=c['year'],
          structure=structs[c['sha256']],PAR2_s=scores,
          gains_s={mode:round(scores['original']-scores[mode],6) for mode in MODES}))
    scores={}
    for mode in MODES:
        sub=[r for r in rows if r['mode']==mode]
        scores[mode]=dict(PAR2_s=round(sum(r['audited_PAR2_s'] for r in sub),6),
           solved=sum(r['accepted_solved'] for r in sub),n=len(sub),
           timeouts=sum(r['status']=='TIMEOUT' for r in sub),
           preprocessing_s=round(sum(r['preprocessing_s'] for r in sub),6))
    for mode in MODES:
        for ref in ('original','scan_placebo','kissat','cadical'):
            base=scores[ref]['PAR2_s'];test=scores[mode]['PAR2_s']
            scores[mode]['speedup_vs_'+ref]=round(base/max(test,1e-9),6)
            scores[mode]['pct_less_PAR2_vs_'+ref]=round(100*(1-test/base),5)
    wins={}
    for mode in ('front100','front_short','gate_dup','gate_context','scan_placebo'):
        count=collections.Counter()
        for r in per_source:
            t=r['PAR2_s'][mode];b=r['PAR2_s']['original']
            count['wins' if t<b-0.001 else 'losses' if t>b+0.001 else 'ties']+=1
        wins[mode]=dict(count)
    decisions=collections.Counter(choose(s,'gate_context') for s in structs.values())
    dups=sum(s['duplicate_count']>0 for s in structs.values())
    summary=dict(protocol=PROTO,sources=TARGET,trials=len(rows),
       reference_only_sampled=True,reference_band_s=[REF_MIN_S,REF_MAX_S],
       independent_new_sha_within_declared_registry=True,
       no_global_holdout_claim=True,solved_after_source_screen=True,
       context_choices=dict(decisions),new_sources_with_duplicates=dups,
       score=scores,wins_vs_original=wins,
       exact_raw_clause_multiset_preserved=True,
       original_SHA_pinned=True,SAT_original_witness_replayed=True,
       UNSAT_independent_LRAT=False,UNSAT_cross_solver_scoring_required=True,
       actual_E2E_not_bounded_checkpoint=True,
       no_auto_promotion=True)
    save(ROOT/'report.json',dict(summary,per_source=per_source,rows=rows))
    print('XX2_FINAL',json.dumps(summary,sort_keys=True),flush=True)

def selftest():
    original=[(1,2,3,4),(1,2),(-1,3),(-1,3),(4,),(-2,3,4,5)]
    changed=reorder_short(original)
    need(collections.Counter(changed)==collections.Counter(original),
         'short transform changed clauses')
    need(changed!=original,'front short does not actually rearrange')
    s=structure_test=dict(duplicate_count=2,duplicate_rate=0.2,
         short_rate=0.6,late_short_fraction=0.8)
    need(choose(s,'gate_dup')=='front100','simple gate condition')
    need(choose(s,'gate_context')=='front_short','short position gate condition')
    s.update(duplicate_count=100)
    need(choose(s,'gate_context')=='front100','dense duplicate gate condition')
    need(len(MODES)==8 and TARGET*REPS*len(MODES)==192,'trial count drift')
    print('XX2_SELFTEST_PASS',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('selftest','freeze','verify','shard','audit'))
    p.add_argument('--shard',type=int,default=0)
    a=p.parse_args()
    if a.action=='selftest':selftest()
    elif a.action=='freeze':freeze()
    elif a.action=='verify':verify();print('XX2_VERIFY_PASS',flush=True)
    elif a.action=='shard':shard(a.shard)
    else:audit()
if __name__=='__main__':main()
