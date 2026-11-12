#!/usr/bin/env python3
"""Persistent contextual priors; SQLite stays outside the native conflict loop."""
import argparse,hashlib,json,math,os,pathlib,re,signal,sqlite3,subprocess,tempfile,time
from drnas_r28_native_check import parse_dimacs,verify
SCHEMA='DRNAS_R28_CONTEXT_V1'
BINARY='mre_r28_context/drnas_r28_context'
DELTA=re.compile(r'^c R28_CONTEXT_DELTA key=(\d+) phase=(\d+) arm=(\d+) n=(\d+) sum=([\deE.+-]+)$',re.M)
def file_sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

class Memory:
    def __init__(self,path):
        self.path=pathlib.Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=.25)
        self.db.execute('PRAGMA journal_mode=DELETE');self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS stats(context INTEGER,phase INTEGER,arm INTEGER,weight REAL NOT NULL,mean REAL NOT NULL,
            PRIMARY KEY(context,phase,arm),CHECK(context BETWEEN 0 AND 71),CHECK(phase BETWEEN 0 AND 1),CHECK(arm BETWEEN 0 AND 3),CHECK(weight>0 AND weight<=128),CHECK(mean>=0 AND mean<=1));
          CREATE TABLE IF NOT EXISTS formulas(sha TEXT PRIMARY KEY,role TEXT NOT NULL CHECK(role IN ('train','eval')),trained INTEGER NOT NULL DEFAULT 0,status TEXT,build TEXT,e2e_s REAL);
        ''')
        old=self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if old and old[0]!=SCHEMA:raise ValueError('incompatible context schema; explicit migration required')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('schema',SCHEMA))
            self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('generation','0'))
        self.temp=tempfile.TemporaryDirectory(prefix='drnas-context-');self.snapshot_path=pathlib.Path(self.temp.name)/'prior.txt';self.revision=0;self.exported=-1
    def close(self):self.db.close();self.temp.cleanup()
    def generation(self):return int(self.db.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0])
    def advance(self):
        with self.db:self.db.execute("UPDATE meta SET value=? WHERE key='generation'",(str(self.generation()+1),))
    def register(self,sha,role):
        if role not in ('train','eval'):raise ValueError('split must be train or eval')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO formulas(sha,role) VALUES (?,?)',(sha,role))
            old=self.db.execute('SELECT role FROM formulas WHERE sha=?',(sha,)).fetchone()[0]
            if old!=role:raise ValueError('train/evaluation leakage blocked for '+sha)
    def digest(self):
        rows=self.db.execute('SELECT context,phase,arm,weight,mean FROM stats ORDER BY context,phase,arm').fetchall()
        return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
    def snapshot(self):
        if self.exported!=self.revision:
            lines=[SCHEMA]
            for c,p,a,w,m in self.db.execute('SELECT context,phase,arm,weight,mean FROM stats ORDER BY context,phase,arm'):
                if not math.isfinite(w) or not math.isfinite(m):raise ValueError('invalid prior')
                # One formula contributes at most four units: >=8 requires at least three.
                if w<8:continue
                lines.append(f'{c} {p} {a} 1 {m:.17g}')
            data='\n'.join(lines)+'\n';assert len(data.encode())<=65536
            tmp=self.snapshot_path.with_suffix('.tmp');tmp.write_text(data);os.replace(tmp,self.snapshot_path)
            self.exported=self.revision
        return str(self.snapshot_path)
    def learn(self,sha,status,verified,out,e2e,build='local'):
        # Store only NEW per-formula samples, never re-ingest loaded priors.
        if not verified:return dict(updated=False,reason='answer_not_verified')
        samples=[];seen=set();context=None
        if len(DELTA.findall(out))!=sum(line.startswith('c R28_CONTEXT_DELTA') for line in out.splitlines()):raise ValueError('malformed native context telemetry')
        for match in DELTA.finditer(out):
            c,p,a,n=map(int,match.groups()[:4]);total=float(match[5]);key=(c,p,a)
            if not 0<=c<72 or not 0<=p<2 or not 0<=a<4 or not 1<=n<=100000000 or not math.isfinite(total) or not 0<=total<=n+1e-8 or key in seen:raise ValueError('invalid native context telemetry')
            if context is not None and c!=context:raise ValueError('multiple structural contexts')
            context=c;seen.add(key);samples.append((c,p,a,min(n,4),min(1.,total/n)))
        with self.db:
            # Lock before checking deduplication to avoid double-counting concurrent workers.
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT role,trained FROM formulas WHERE sha=?',(sha,)).fetchone()
            if not old or old[0]!='train':raise ValueError('cannot train on an evaluation or unregistered formula')
            if old[1]:return dict(updated=False,reason='duplicate_sha')
            for c,p,a,n,m in samples:
                oldstat=self.db.execute('SELECT weight,mean FROM stats WHERE context=? AND phase=? AND arm=?',(c,p,a)).fetchone()
                weight,mean=oldstat or (0.,0.)
                weight=min(weight*.98,128-n);newweight=weight+n;newmean=(weight*mean+n*m)/newweight
                self.db.execute('INSERT INTO stats VALUES (?,?,?,?,?) ON CONFLICT(context,phase,arm) DO UPDATE SET weight=excluded.weight,mean=excluded.mean',(c,p,a,newweight,newmean))
            self.db.execute('UPDATE formulas SET trained=1,status=?,build=?,e2e_s=? WHERE sha=?',(status,build,e2e,sha))
        if samples:self.revision+=1
        return dict(updated=bool(samples),cells=len(samples),reason='verified_new_formula' if samples else 'no_learning_windows')
    def info(self):
        return dict(schema=SCHEMA,generation=self.generation(),cells=self.db.execute('SELECT count(*) FROM stats').fetchone()[0],train=self.db.execute("SELECT count(*) FROM formulas WHERE role='train'").fetchone()[0],trained=self.db.execute('SELECT count(*) FROM formulas WHERE trained=1').fetchone()[0],holdout=self.db.execute("SELECT count(*) FROM formulas WHERE role='eval'").fetchone()[0],stats_sha256=self.digest(),bytes=self.path.stat().st_size)
    def backup(self,path):
        target=sqlite3.connect(path)
        try:self.db.backup(target)
        finally:target.close()

def solve(memory,cnf,split='eval',cap=1.,seed=17,warm=True,binary=BINARY,build='local'):
    if not 0<cap<=120:raise ValueError('invalid time cap')
    started=time.perf_counter();sha=file_sha(cnf);memory.register(sha,split)
    env=dict(os.environ,DRNAS_LTM8_MEMORY='')
    env.pop('DRNAS_CONTEXT_SNAPSHOT',None)
    if warm:env['DRNAS_CONTEXT_SNAPSHOT']=memory.snapshot()
    else:
        empty=pathlib.Path(memory.temp.name)/'empty.txt'
        if not empty.exists():empty.write_text(SCHEMA+'\n')
        env['DRNAS_CONTEXT_SNAPSHOT']=str(empty)
    prep_s=time.perf_counter()-started
    remaining=max(.000001,cap-prep_s)
    cmd=[binary,str(cnf),'--time',str(remaining),'--profile','direct','--seed',str(seed)]
    began=time.perf_counter();proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
    timed=False
    try:out,err=proc.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        timed=True;os.killpg(proc.pid,signal.SIGKILL);out,err=proc.communicate()
    solve_s=time.perf_counter()-began;timed=timed or prep_s+solve_s>cap
    if not timed and proc.returncode not in (0,10,20):raise RuntimeError((proc.returncode,err[-1000:]))
    vstart=time.perf_counter()
    status,valid=('TIMEOUT',False) if timed else verify(parse_dimacs(cnf),out,proc.returncode)
    verify_s=time.perf_counter()-vstart
    update_start=time.perf_counter();update=dict(updated=False,reason='evaluation_frozen')
    if split=='train' and warm:update=memory.learn(sha,status,valid,out,solve_s,build)
    update_s=time.perf_counter()-update_start
    # Include memory lookup and learning commit in the practical score; verification is separate.
    e2e=prep_s+solve_s+update_s
    reported=status.startswith(('SAT_','UNSAT_'))
    row=dict(sha256=sha,split=split,warm=warm,seed=seed,cap_s=cap,status=status,answer_verified=valid,verified=valid and e2e<=cap,reported_solved=reported and e2e<=cap,solve_s=solve_s,prepare_s=prep_s,verify_s=verify_s,memory_update_s=update_s,e2e_s=e2e,PAR2_verified_s=e2e if valid and e2e<=cap else 2*cap,PAR2_reported_s=e2e if reported and e2e<=cap else 2*cap,update=update,context=[l for l in out.splitlines() if l.startswith(('c R28_CONTEXT_LOAD','c R28_CONTEXT_START'))],windows=[l for l in out.splitlines() if 'LTM13_WINDOW' in l][-2:])
    return row,out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('cnf');ap.add_argument('--db',default='drnas_memory/memory.sqlite');ap.add_argument('--split',choices=['train','eval'],default='eval');ap.add_argument('--time',type=float,default=10);ap.add_argument('--seed',type=int,default=17);ap.add_argument('--cold',action='store_true');a=ap.parse_args()
    m=Memory(a.db)
    try:
        row,out=solve(m,a.cnf,a.split,a.time,a.seed,not a.cold,build=os.getenv('GITHUB_SHA','local'));print(out,end='');print('R28_CONTEXT_RESULT',json.dumps(row,sort_keys=True));print('R28_CONTEXT_MEMORY',json.dumps(m.info(),sort_keys=True))
    finally:m.close()
if __name__=='__main__':main()
