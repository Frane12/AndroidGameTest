#!/usr/bin/env python3
"""DRNAS ECDLP-SAT R1: self-generated, toy twisted-Edwards elliptic curves.

Genuine bit-blasted nonlinear finite-field model of kG=Q. Uses only tiny
private-key ranges; NEVER accepts an external public key or address.
"""
import argparse,csv,hashlib,json,random,re,subprocess,time
from pathlib import Path

CASES=((17,3,4),(29,2,5),(67,2,6))
ID=(0,1)

def ecadd(a,b,p,d):
    x,y=a;u,v=b;t=d*x*u*y*v%p
    return ((x*v+y*u)*pow(1+t,-1,p)%p,(y*v-x*u)*pow(1-t,-1,p)%p)

def ecmul(k,base,p,d):
    q=ID
    while k:
        if k&1:q=ecadd(q,base,p,d)
        base=ecadd(base,base,p,d)
        k>>=1
    return q

def basepoint(p,d,bits):
    for x in range(p):
      for y in range(p):
        if (x,y)==ID or (x*x+y*y-1-d*x*x*y*y)%p:continue
        q=(x,y);r=ID
        for order in range(1,2*p+4):
            r=ecadd(r,q,p,d)
            if r==ID:break
        if order>=(1<<bits):return q,order
    raise RuntimeError('no full-order base point')

class CNF:
    def __init__(self):
        self.n=0;self.clauses=[];self.values={}
        self.one=self.new(True);self.clause(self.one)
    def new(self,val):
        self.n+=1;self.values[self.n]=bool(val);return self.n
    def value(self,lit):return self.values[abs(lit)]==(lit>0)
    def clause(self,*lits):self.clauses.append(tuple(lits))
    def must(self,lit):
        assert self.value(lit)
        self.clause(lit)
    def eq(self,a,b):
        assert self.value(a)==self.value(b)
        self.clause(-a,b);self.clause(a,-b)
    def and_(self,a,b):
        if a==b:return a
        if a==-b:return -self.one
        z=self.new(self.value(a) and self.value(b))
        self.clause(-z,a);self.clause(-z,b);self.clause(z,-a,-b)
        return z
    def or_(self,a,b):return -self.and_(-a,-b)
    def xor(self,a,b):
        if a==b:return -self.one
        if a==-b:return self.one
        z=self.new(self.value(a)!=self.value(b))
        self.clause(-a,-b,-z);self.clause(a,b,-z)
        self.clause(a,-b,z);self.clause(-a,b,z)
        return z
    def mux(self,s,a,b):
        if a==b:return a
        return self.or_(self.and_(s,a),self.and_(-s,b))
    def bits(self,n,w):return [self.one if n>>i&1 else -self.one for i in range(w)]
    def num(self,bits):return sum(1<<i for i,a in enumerate(bits) if self.value(a))
    def add(self,a,b,carry=None):
        assert len(a)==len(b)
        c=carry if carry is not None else -self.one
        out=[]
        for x,y in zip(a,b):
            z=self.xor(x,y);out.append(self.xor(z,c))
            c=self.or_(self.and_(x,y),self.and_(z,c))
        return out,c
    def subtract_const(self,a,c):
        w=len(a)
        return self.add(a,self.bits((1<<w)-c,w)) if c else (a,self.one)
    def ltconst(self,a,c):
        _,cy=self.subtract_const(a,c)
        return -cy

class Field:
    def __init__(self,cnf,p):self.c=cnf;self.p=p;self.w=p.bit_length()
    def const(self,x):return self.c.bits(x%self.p,self.w)
    def fresh(self,n):
        assert 0<=n<self.p
        a=[self.c.new(bool(n>>i&1)) for i in range(self.w)]
        self.c.must(self.c.ltconst(a,self.p))
        return a
    def add(self,a,b):
        c=self.c;assert len(a)==self.w==len(b)
        raw,cy=c.add(a,b);raw=raw+[cy]
        reduced,ge=c.subtract_const(raw,self.p)
        out=[c.mux(ge,reduced[i],raw[i]) for i in range(self.w)]
        assert c.num(out)==(c.num(a)+c.num(b))%self.p
        return out
    def neg(self,a):
        c=self.c
        negative,carry=c.add(c.bits(self.p,self.w+1),[-ai for ai in a]+[-c.one],c.one)
        assert not c.value(carry)
        result=negative[:self.w]
        return [c.mux(c.ltconst(a,1),-c.one,result[i]) for i in range(self.w)]
    def sub(self,a,b):return self.add(a,self.neg(b))
    def mul(self,a,b):
        c=self.c;acc=self.const(0);part=a
        for i,bit in enumerate(b):
            term=[c.and_(bit,ai) for ai in part]
            acc=self.add(acc,term)
            if i<self.w-1:part=self.add(part,part)
        assert c.num(acc)==c.num(a)*c.num(b)%self.p
        return acc
    def mul_const(self,a,k):
        out=self.const(0);part=a
        while k:
            if k&1:out=self.add(out,part)
            k>>=1
            if k:part=self.add(part,part)
        return out
    def eq(self,a,b):
        for x,y in zip(a,b):self.c.eq(x,y)

def build(p,d,bits,secret):
    g,order=basepoint(p,d,bits)
    assert order>=(1<<bits)
    c=CNF();f=Field(c,p)
    key=[c.new(secret>>i&1) for i in range(bits)]
    x,y=f.const(0),f.const(1)
    point=ID
    for index in range(bits):
        bx,by=ecmul(1<<index,g,p,d)
        s=key[index]
        sx=[c.mux(s,a,b) for a,b in zip(f.const(bx),f.const(0))]
        sy=[c.mux(s,a,b) for a,b in zip(f.const(by),f.const(1))]
        chosen=(bx,by) if secret>>index&1 else ID
        nxt=ecadd(point,chosen,p,d)
        xnext=f.fresh(nxt[0]);ynext=f.fresh(nxt[1])
        t=f.mul_const(f.mul(f.mul(x,sx),f.mul(y,sy)),d)
        denx=f.add(f.const(1),t)
        deny=f.sub(f.const(1),t)
        numx=f.add(f.mul(x,sy),f.mul(y,sx))
        numy=f.sub(f.mul(y,sy),f.mul(x,sx))
        f.eq(f.mul(xnext,denx),numx)
        f.eq(f.mul(ynext,deny),numy)
        x,y=xnext,ynext;point=nxt
    q=ecmul(secret,g,p,d)
    assert point==q
    f.eq(x,f.const(q[0]));f.eq(y,f.const(q[1]))
    assert all(any(c.value(lit) for lit in clause) for clause in c.clauses)
    return c,key,q,g,order

def solve(binary,mode,src,cap):
    cmd=[binary,mode,str(src)] if mode in ('clean','bridge') else [binary,str(src)]
    start=time.perf_counter()
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=cap)
        elapsed=time.perf_counter()-start
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',elapsed=cap,model={},audit='')
    if r.returncode not in (10,20):
        raise RuntimeError('solver failure '+str(r.returncode)+' '+r.stderr[-1000:])
    model={}
    for line in r.stdout.splitlines():
        if line.startswith('v '):
            for item in line.split()[1:]:
                lit=int(item)
                if lit:model[abs(lit)]=lit>0
    return dict(status='SAT' if r.returncode==10 else 'UNSAT',
                elapsed=elapsed,model=model,audit=r.stderr[-1000:])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--r111',required=True)
    p.add_argument('--cadical',required=True)
    p.add_argument('--prime',type=int,required=True,choices=[17,29,67])
    p.add_argument('--out',default='drnas-ecdlp-r1-results')
    p.add_argument('--cap',type=int,default=15)
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    prime,d,bits=next(c for c in CASES if c[0]==a.prime)
    secret=(1<<bits)*67//100+bits%3
    c,key,Q,G,order=build(prime,d,bits,secret)
    src=out/f'ecdlp-edwards-p{prime}-{bits}bit.cnf'
    src.write_text(f'p cnf {c.n} {len(c.clauses)}\n'+
        ''.join(' '.join(map(str,clause))+' 0\n' for clause in c.clauses))
    sha=hashlib.sha256(src.read_bytes()).hexdigest()
    print('R1_SOURCE',prime,bits,'group_order',order,'nvars',c.n,'clauses',len(c.clauses),'sha256',sha,flush=True)
    rows=[]
    for trial in range(2):
        modes=['cadical','clean','bridge']
        random.Random(str(prime)+str(trial)).shuffle(modes)
        for mode in modes:
            binary=a.cadical if mode=='cadical' else a.r111
            data=solve(binary,mode,src,a.cap)
            rec=sum(1<<i for i,k in enumerate(key) if data['model'].get(k,False)) if data['status']=='SAT' else None
            valid=(data['status']=='SAT' and rec==secret and ecmul(rec,G,prime,d)==Q)
            if data['status']=='SAT' and not valid:
                raise RuntimeError(f'Wrong recovered private key {prime} {mode} {rec}')
            audit=data['audit']
            row=dict(prime=prime,bits=bits,group_order=order,trial=trial,mode=mode,
                status=data['status'],seconds=round(data['elapsed'],6),recovered_ok=valid,
                source_sha256=sha,drnas_gate=re.search(r'gate=(\S+)',audit).group(1) if 'gate=' in audit else '',
                source_xor=int(re.search(r'source_xor=(\d+)',audit).group(1)) if 'source_xor=' in audit else -1,
                derived_gf2=int(re.search(r'derived_GF2_rows=(\d+)',audit).group(1)) if 'derived_GF2_rows=' in audit else -1,
                external_lemmas=int(re.search(r'external_lemmas=(\d+)',audit).group(1)) if 'external_lemmas=' in audit else -1)
            rows.append(row)
            print('R1_TRIAL',json.dumps(row),flush=True)
    if hashlib.sha256(src.read_bytes()).hexdigest()!=sha:raise RuntimeError('Source CNF mutated')
    with (out/'results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (out/'protocol.json').write_text(json.dumps({'experiment':'DRNAS ECDLP SAT R1',
      'prime':prime,'secret_bits':bits,'curve_type':'toy twisted Edwards; NOT secp256k1',
      'expected_private_key':secret,'public_point':Q,'group_order':order,
      'cap_s':a.cap,'trials':2,'sat_inputs_not_key_lookup_tables':True,
      'warning':'No extrapolation to full 256-bit ECDLP; do not claim cryptographic break'},indent=2)+'\n')
    print('R1_COMPLETE',json.dumps({'prime':prime,'tests':len(rows),'verified':sum(x['recovered_ok'] for x in rows),
      'timeouts':sum(x['status']=='TIMEOUT' for x in rows)}),flush=True)

if __name__=='__main__':main()
