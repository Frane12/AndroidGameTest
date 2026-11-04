#!/usr/bin/env python3
"""DRNAS ECDLP R1 controlled test: tiny GF(2^m) elliptic curves, NOT Bitcoin.
Builds a genuine bit-blasted finite-field EC scalar multiplication CNF circuit.
Public target Q is fixed, but secret key bits remain unknown to the SAT solver.
Never supplies a secret-to-public lookup table. Uses self-generated test keys.
"""
import argparse,csv,hashlib,json,pathlib,random,re,subprocess,time

CURVES={
 5:(0x25,1,2,(27,31),34),
 6:(0x43,1,2,(63,50),64),
 7:(0x83,1,1,(126,68),142),
 8:(0x11b,1,7,(217,131),272),
}
def mul(a,b,m,p):
    out=0
    while b:
        if b&1:out^=a
        b>>=1;a<<=1
        if a&(1<<m):a^=p
    return out
def power(a,n,m,p):
    out=1
    while n:
        if n&1:out=mul(out,a,m,p)
        a=mul(a,a,m,p);n>>=1
    return out
def add(P,Q,c):
    if P is None:return Q
    if Q is None:return P
    m,p,a,b,G,order=c
    x,y=P;z,w=Q
    if x==z:
        if y^w==x:return None
        assert P==Q and x
        s=x^mul(y,power(x,(1<<m)-2,m,p),m,p)
        nx=mul(s,s,m,p)^s^a
        ny=mul(x,x,m,p)^mul(s^1,nx,m,p)
    else:
        s=mul(y^w,power(x^z,(1<<m)-2,m,p),m,p)
        nx=mul(s,s,m,p)^s^x^z^a
        ny=mul(s,x^nx,m,p)^nx^y
    return (nx,ny)
def point(k,c):
    P=None;T=c[4]
    while k:
        if k&1:P=add(P,T,c)
        T=add(T,T,c);k>>=1
    return P
class CNF:
    def __init__(self):
        self.n=1;self.clauses=[[1]];self.nxor=0
    def var(self):self.n+=1;return self.n
    def A(self,x,y):
        if x==-1 or y==-1 or x==-y:return -1
        if x==1:return y
        if y==1 or x==y:return x
        z=self.var();self.clauses.extend([[-x,-y,z],[x,-z],[y,-z]])
        return z
    def X(self,x,y):
        if x==-1:return y
        if y==-1:return x
        if x==1:return -y
        if y==1:return -x
        if x==y:return -1
        if x==-y:return 1
        z=self.var();self.clauses.extend([[-x,-y,-z],[x,y,-z],[x,-y,z],[-x,y,z]])
        self.nxor+=1;return z
    def M(self,s,on,off):
        if on==off:return on
        if on==-off:return self.X(s,off)
        if on==1:return -self.A(-s,-off)
        if on==-1:return self.A(-s,off)
        if off==1:return -self.A(s,-on)
        if off==-1:return self.A(s,on)
        z=self.var()
        self.clauses.extend([[-s,-on,z],[-s,on,-z],[s,-off,z],[s,off,-z]])
        return z
    def bits(self,n,m):return [1 if n>>i&1 else -1 for i in range(m)]
    def xorall(self,ls):
        out=-1
        for v in ls:out=self.X(out,v)
        return out
    def fix(self,lit,value):self.clauses.append([lit if value else -lit])
    def write(self,path):
        with path.open('w') as f:
            f.write('p cnf %d %d\n'%(self.n,len(self.clauses)))
            for cl in self.clauses:f.write(' '.join(map(str,cl))+' 0\n')
def remainder(i,poly,m):
    value=1<<i
    while value.bit_length()>m:value^=poly<<(value.bit_length()-m-1)
    return value
class Circuit:
    def __init__(self,c,C):self.c=c;self.C=C;self.m=c[0]
    def const(self,a):return self.C.bits(a,self.m)
    def xor(self,*vecs):
        out=self.const(0)
        for v in vecs:out=[self.C.X(a,b) for a,b in zip(out,v)]
        return out
    def square(self,x):
        _,poly,_,_,_,_=self.c
        return [self.C.xorall(x[i] for i in range(self.m)
                if remainder(2*i,poly,self.m)>>j&1) for j in range(self.m)]
    def mult(self,x,y):
        _,poly,_,_,_,_=self.c
        terms=[[] for _ in range(self.m)]
        for i in range(self.m):
            for j in range(self.m):
                t=self.C.A(x[i],y[j])
                r=remainder(i+j,poly,self.m)
                for b in range(self.m):
                    if r>>b&1:terms[b].append(t)
        return [self.C.xorall(lst) for lst in terms]
    def inverse(self,x):
        v=x
        for i in range(1,self.m-1):
            v=self.mult(self.square(v),x)
        return self.square(v)
    def encode(self,Q):
        m,poly,a,b,G,order=self.c;C=self.C
        keys=[C.var() for _ in range(m)]
        x=self.const(0);y=self.const(0);inf=1;T=G
        for bit in keys:
            tx,ty=T
            numerator=self.xor(y,self.const(ty))
            denominator=self.xor(x,self.const(tx))
            slope=self.mult(numerator,self.inverse(denominator))
            x3=self.xor(self.square(slope),slope,x,self.const(tx),self.const(a))
            y3=self.xor(self.mult(slope,self.xor(x,x3)),x3,y)
            outx=[C.M(inf,yes,no) for yes,no in zip(self.const(tx),x3)]
            outy=[C.M(inf,yes,no) for yes,no in zip(self.const(ty),y3)]
            x=[C.M(bit,yes,no) for yes,no in zip(outx,x)]
            y=[C.M(bit,yes,no) for yes,no in zip(outy,y)]
            inf=C.A(inf,-bit)
            T=add(T,T,self.c)
        for i,v in enumerate(x):C.fix(v,(Q[0]>>i)&1)
        for i,v in enumerate(y):C.fix(v,(Q[1]>>i)&1)
        C.fix(inf,False)
        return keys
def generate(bits,trial,out):
    c=(bits,)+CURVES[bits]
    assert point(c[5],c) is None
    assert c[5]>=1<<bits and all(point(k,c) is not None for k in range(1,1<<bits))
    secret=random.Random(20261104+bits*10007+trial*997).randrange(1,1<<bits)
    Q=point(secret,c)
    C=CNF();key=Circuit(c,C).encode(Q)
    src=out/('curve%d_trial%d.cnf'%(bits,trial));C.write(src)
    meta=dict(bits=bits,trial=trial,curve=list(c),public_Q=list(Q),
        self_generated_secret=secret,key_literals=key,
        variables=C.n,clauses=len(C.clauses),xor_gates=C.nxor,
        file=src.name,sha256=hashlib.sha256(src.read_bytes()).hexdigest())
    print('ECDLP_CASE',json.dumps({k:v for k,v in meta.items() if k!='self_generated_secret'}),flush=True)
    return src,meta
def verify_model(stdout,src,meta):
    assert 's SATISFIABLE' in stdout
    values={}
    for line in stdout.splitlines():
        if line.startswith('v '):
            for word in line[2:].split():
                lit=int(word)
                if lit:values[abs(lit)]=lit>0
    assert len(values)==meta['variables'], ('model incomplete',len(values))
    with src.open() as f:
        for line in f:
            if not line or line[0] in 'pc':continue
            clause=[int(t) for t in line.split() if t!='0']
            if clause:assert any(values[abs(t)]==(t>0) for t in clause)
    k=sum(1<<i for i,v in enumerate(meta['key_literals']) if values[v])
    assert point(k,(meta['bits'],)+CURVES[meta['bits']])==tuple(meta['public_Q'])
    assert k==meta['self_generated_secret']
    return k
def run(binary,mode,src,meta,cap):
    start=time.perf_counter()
    try:
        p=subprocess.run([binary,mode,str(src)],capture_output=True,text=True,timeout=cap)
        elapsed=time.perf_counter()-start
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',elapsed_s=cap,gate='',derived_GF2_rows=0,external_lemmas=0)
    if p.returncode!=10:raise RuntimeError('SAT solver failed '+str(p.returncode)+' '+p.stderr[-400:])
    recovered=verify_model(p.stdout,src,meta)
    if 'R111_AUDIT' not in p.stderr:raise RuntimeError('missing R111 audit')
    audit=p.stderr.split('R111_AUDIT')[-1]
    get=lambda key:(re.search(r'\b'+key+r'=([^\s]+)',audit) or [None,''])[1]
    return dict(status='SAT',elapsed_s=round(elapsed,6),recovered=recovered,
        gate=get('gate'),derived_GF2_rows=int(get('derived_GF2_rows') or 0),
        external_lemmas=int(get('external_lemmas') or 0))
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--bits',type=int,required=True,choices=sorted(CURVES))
    ap.add_argument('--out',required=True)
    ap.add_argument('--solver',required=True)
    ap.add_argument('--trials',type=int,default=3)
    ap.add_argument('--repeats',type=int,default=2)
    ap.add_argument('--cap',type=float,default=8)
    a=ap.parse_args()
    root=pathlib.Path(a.out);root.mkdir(parents=True,exist_ok=True)
    rows=[];meta=[]
    for trial in range(a.trials):
        src,case=generate(a.bits,trial,root)
        meta.append(case)
        for repeat in range(a.repeats):
            modes=['clean','bridge'] if (trial+repeat)%2==0 else ['bridge','clean']
            for mode in modes:
                res=run(a.solver,mode,src,case,a.cap)
                row=dict(bits=a.bits,trial=trial,repeat=repeat,mode=mode,sha256=case['sha256'],**res)
                rows.append(row)
                print('ECDLP_TRIAL',json.dumps(row),flush=True)
        assert hashlib.sha256(src.read_bytes()).hexdigest()==case['sha256']
    (root/'cases.json').write_text(json.dumps(meta,indent=2)+'\n')
    with (root/'results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summaries={}
    for mode in ['clean','bridge']:
        subset=[r for r in rows if r['mode']==mode]
        summaries[mode]=dict(solved=sum(r['status']=='SAT' for r in subset),
            total=len(subset),time_sum_s=round(sum(r['elapsed_s'] for r in subset),6),
            gf2_rows=sum(r['derived_GF2_rows'] for r in subset),
            lemmas=sum(r['external_lemmas'] for r in subset))
    summary=dict(protocol='DRNAS-ECDLP-R1-TOY-BINARY-EC',bits=a.bits,
        limitations='Toy binary-field EC with 5-8 bit secrets, NOT Bitcoin secp256k1',
        modes=summaries)
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('ECDLP_COMPLETE',json.dumps(summary),flush=True)
if __name__=='__main__':main()
