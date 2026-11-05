from pathlib import Path
import itertools, hashlib, json, os, random, resource, subprocess, time
from proofcheck import dimacs,check_hidden,check_whole,verify_model

here=Path(__file__).resolve().parent
root=here.parent
cases_dir=root/'cnf'; cases_dir.mkdir(exist_ok=True)
hashof=lambda data:hashlib.sha256(data).hexdigest()
seed=174120261101
def generate(n, idx):
    rng=random.Random(seed+1000*n+idx)
    ring=[(i,(i+1)%n) for i in range(n)]
    pairing=list(range(n))
    while True:
        rng.shuffle(pairing)
        extra=list(zip(pairing[::2],pairing[1::2]))
        if all((u-v)%n not in (1,n-1) for u,v in extra):
            break
    edges=ring+extra
    rng.shuffle(edges)
    vertices=[[] for _ in range(n)]
    for var,(u,v) in enumerate(edges,1):
        vertices[u].append(var);vertices[v].append(var)
    charges=[rng.randrange(2) for _ in vertices]
    charges[0]=sum(charges[1:])%2
    for unsat in (0,1):
        para=charges.copy();para[0]^=unsat
        ordering=random.Random(seed+1000*n+idx+98201)
        cs=[]
        for vs,rhs in zip(vertices,para):
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2 != rhs:
                    c=[(-v if b else v) for b,v in zip(bits,vs)]
                    ordering.shuffle(c);cs.append(c)
        ordering.shuffle(cs)
        raw=('p cnf %d %d\n'%(len(edges),len(cs))+''.join(' '.join(map(str,c))+' 0\n' for c in cs)).encode()
        label='UNSAT' if unsat else 'SAT'
        name=f'g{n:03}_{idx}_{label}'
        (cases_dir/(name+'.cnf')).write_bytes(raw)
        yield dict(case=name,n=n,graph=idx,label=label,sha256=hashof(raw))

def run():
    manifest=[c for n in (48,96,162,256,384) for i in range(3) for c in generate(n,i)]
    assert len(set(c['sha256'] for c in manifest))==30
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2))
    binaries={s:(root/'bin'/s).resolve() for s in ('v142_fastgate','v145_native','kissat_solver')}
    cap=8
    ordered=manifest.copy()
    rng=random.Random(seed)
    rng.shuffle(ordered)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    with (root/'trials.jsonl').open('w',buffering=1) as out:
        for rep in range(2):
            for case in ordered:
                p=cases_dir/(case['case']+'.cnf')
                assert hashof(p.read_bytes())==case['sha256']
                n,clauses=dimacs(p)
                modes=list(binaries);rng.shuffle(modes)
                for mode in modes:
                    cmd=[str(binaries[mode]),str(p)]
                    if mode!='kissat_solver':
                        cmd.extend([str(binaries['kissat_solver']),'0'])
                    start=time.monotonic()
                    try:
                        proc=subprocess.run(cmd,timeout=cap,capture_output=True,text=True)
                        sec=time.monotonic()-start
                        tag=[x for x in proc.stdout.splitlines() if x.startswith('DRNAS_') and '_RESULT\t' in x]
                        if sec>cap:
                            status,route,sec='TIMEOUT','timeout',cap
                        elif tag:
                            assert proc.returncode==0 and len(tag)==1
                            data=json.loads(tag[0].split('\t')[1])
                            status,route=data['status'],data['path']
                            if route=='hidden_parity_gf2':check_hidden(clauses,data['proof'])
                            elif route=='affine_exact':check_whole(n,clauses,data)
                            else:raise ValueError(route)
                        else:
                            status={10:'SAT',20:'UNSAT'}[proc.returncode]
                            route='Kissat'
                            if status=='SAT':
                                verify_model(n,clauses,[int(v) for line in proc.stdout.splitlines() if line.startswith('v ') for v in line.split()[1:]])
                        if status not in (case['label'],'TIMEOUT'):raise ValueError('wrong verdict')
                    except subprocess.TimeoutExpired:
                        status,route,sec='TIMEOUT','timeout',cap
                    out.write(json.dumps(dict(case=case['case'],label=case['label'],solver=mode,rep=rep,status=status,path=route,seconds=sec))+'\n')
            ordered.reverse()
if __name__=='__main__':run()
