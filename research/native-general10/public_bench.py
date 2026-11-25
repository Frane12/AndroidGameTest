"""Prospective public CNF comparison, native kernels, no CDCL in DRNAS.
The two G10 portfolios differ only by permission to use G9 split-only.
Only independently verified models and standard DRAT proofs count. G8 symbolic
UNSAT is reported separately because the original benchmark has no DRAT export.
"""
import os,sys,pathlib,subprocess,time,json,hashlib,urllib.request,gzip,lzma,bz2,io,re,collections,resource
P=pathlib.Path; here=P(__file__).resolve().parent;out=P("g10-public");out.mkdir(exist_ok=True);bin=P("bin").resolve()
CAP=15.; ARMS=("G7","G8","G9","G10_STRUCT","G10_AUTO","Kissat","CaDiCaL")
sha=lambda b:hashlib.sha256(b).hexdigest()
def fetch(url,limit=64*1024*1024):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"DRNAS-G10-reproducibility"}),timeout=45) as r:b=r.read(limit+1)
    if len(b)>limit:raise ValueError("archive size limit")
    return b
def raw(url):
    b=fetch(url);limit=128*1024*1024
    if b.startswith(b"\xfd7zXZ\x00"):
        d=lzma.LZMADecompressor(memlimit=256*1024*1024);a=d.decompress(b,max_length=limit+1)
        if not d.eof:raise ValueError("xz raw limit or truncated")
    elif b.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(b)) as f:a=f.read(limit+1)
    elif b.startswith(b"BZh"):
        d=bz2.BZ2Decompressor();a=d.decompress(b,max_length=limit+1)
        if not d.eof:raise ValueError("bz2 raw limit or truncated")
    else:a=b
    if len(a)>limit:raise ValueError("raw size limit")
    h=re.search(rb"^p\s+cnf\s+(\d+)\s+(\d+)\s*$",a,re.M)
    if not h:raise ValueError("not DIMACS")
    return a,int(h[1]),int(h[2])
def restrict():
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
def audit_model(path,model,n):
    a={}
    for line in model.splitlines():
        if not line.startswith("v "):continue
        for l in map(int,line.split()[1:]):
            if not l:continue
            if abs(l)>n or (abs(l) in a and a[abs(l)]!=(l>0)):return False
            a[abs(l)]=l>0
    sat=False;pending=False;count=0
    with path.open() as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith(("c","p")):continue
            if line.startswith("%"):break
            for l in map(int,line.split()):
                if l:pending=True;sat=sat or a.get(abs(l))==(l>0)
                else:
                    if not sat:return False
                    sat=False;pending=False;count+=1
    return not pending
def cheap_scope(path,n,m):
    if n>10000 or m>100000:return False
    adj=[set() for _ in range(n+1)];c=[]
    with path.open() as f:
        for ln in f:
            ln=ln.strip()
            if not ln or ln.startswith(("c","p")):continue
            if ln.startswith("%"):break
            for x in map(int,ln.split()):
                if x:c.append(abs(x));continue
                v=set(c);c=[]
                for y in v:adj[y].update(v-{y})
    active=sum(bool(a) for a in adj)
    return active==0 or sum(0<len(a)<=13 for a in adj)>=.35*active
def one(name,path,prefix,n,m):
    start=time.monotonic();trace=[];method="";rc=0;model=None;proof=None
    cert=prefix.with_suffix(".cert")
    def remaining():return max(0,int((CAP-(time.monotonic()-start))*1000))
    def launch(kernel,ms,mode=None):
        nonlocal rc,method,model,proof
        if ms<10:return
        cert.unlink(missing_ok=True);method=kernel
        if kernel in ("Kissat","CaDiCaL"):cmd=[bin/kernel.lower(),"-q",path,cert]
        else:cmd=[bin/kernel,path,cert,str(ms)]+([mode] if mode else [])
        try:
            p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=ms/1000+.03,preexec_fn=restrict)
            rc=p.returncode;trace.append(kernel+":"+p.stdout[-500:].strip())
            if rc not in (0,10,20):raise RuntimeError("process exit "+str(rc)+" "+p.stderr[-300:])
            if rc==10:model=p.stdout if kernel in ("Kissat","CaDiCaL") else cert.read_text()
            if rc==20:proof=cert
        except subprocess.TimeoutExpired:rc=0;trace.append(kernel+":external_timeout")
    try:
        if name=="G7":launch("general7",int(CAP*1000),"hybrid")
        elif name=="G8":launch("general8",int(CAP*1000),"hybrid")
        elif name=="G9":launch("general9",int(CAP*1000))
        elif name in ("Kissat","CaDiCaL"):launch(name,int(CAP*1000))
        else:
            sparse=cheap_scope(path,n,m);structural=int(CAP*1000*(.60 if name=="G10_AUTO" else 1));stage=time.monotonic()
            def sl():return min(remaining(),max(0,structural-int((time.monotonic()-stage)*1000)))
            order=["general10","general7","general8"] if sparse else ["general7","general8","general10"]
            for i,k in enumerate(order):
                if rc:break
                launch(k,min(sl(),max(10,int(sl()*[.50,.65,1][i]))),"adaptive" if k=="general10" else "hybrid")
            if not rc and name=="G10_AUTO":launch("general9",remaining(),"split-only")
    except Exception as e:return dict(solver=name,status="ERROR",method=method,wall_s=time.monotonic()-start,check_s=0,par2_s=2*CAP,detail=repr(e),telemetry=trace)
    wall=time.monotonic()-start;check_start=time.monotonic();status="UNKNOWN";detail=""
    try:
        if wall>CAP+.035:status="TIMEOUT"
        elif rc==10:status="SAT" if audit_model(path,model,n) else "AUDIT_FAILED"
        elif rc==20:
            with proof.open("rb") as f:head=f.read(32)
            if head.startswith(b"symbolic-elimination-v1"):status="SYMBOLIC_UNCERTIFIED"
            else:
                p=subprocess.run([str(bin/"drat-trim"),str(path),str(proof)],capture_output=True,text=True,timeout=90,preexec_fn=restrict)
                status="UNSAT" if "s VERIFIED" in p.stdout else "AUDIT_FAILED"
    except subprocess.TimeoutExpired:status="AUDIT_LIMIT"
    except Exception as e:status="AUDIT_FAILED";detail=repr(e)
    if status=="SAT":prefix.with_suffix(".model.gz").write_bytes(gzip.compress(model.encode(),mtime=0))
    if status=="UNSAT":prefix.with_suffix(".proof.gz").write_bytes(gzip.compress(proof.read_bytes(),mtime=0))
    return dict(solver=name,status=status,method=method,wall_s=wall,check_s=time.monotonic()-check_start,par2_s=wall if status in ("SAT","UNSAT") else 2*CAP,detail=detail,telemetry=trace)
def main(shard):
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    uri=fetch("https://satcompetition.github.io/2026/downloads/track_main_2026.uri")
    urls=sorted(set(l.strip() for l in uri.decode().splitlines() if l.strip().startswith(("https://","http://"))))
    old=set(sorted(urls,key=lambda u:sha(("8c7b1552bbfca9a762924bec390ef265c83b122a|sat2026|"+u).encode()))[:12])
    old.update(sorted(set(urls)-old,key=lambda u:sha(("4485aafc98ecaeaededef68bc937ec4c2c6023ee|general6|"+u).encode()))[:50])
    seed=os.environ["GITHUB_SHA"];draw=sorted(set(urls)-old,key=lambda u:sha((seed+"|general10|"+u).encode()))[:50];assert len(draw)==50
    (out/"manifest.json").write_text(json.dumps(dict(freeze=seed,draw=draw,excluded=sorted(old),list_sha256=sha(uri),cpu=cpu,cap=CAP,shard=shard,binaries={k:sha((bin/k).read_bytes()) for k in ("general7","general8","general9","general10","kissat","cadical","drat-trim")}),indent=2))
    with (out/"rows.jsonl").open("w") as f:
        for i in range(shard,50,10):
            url=draw[i];path=out/"input.cnf"
            try:a,n,m=raw(url);path.write_bytes(a);h=sha(a)
            except Exception as e:
                row=dict(id=i,url=url,status="SOURCE_FAILED",detail=repr(e));f.write(json.dumps(row)+"\n");f.flush();print("G10_SOURCE",json.dumps(row),flush=True);continue
            del a;rows=[]
            for name in ARMS[i%len(ARMS):]+ARMS[:i%len(ARMS)]:
                row=dict(id=i,url=url,sha256=h,n=n,m=m,**one(name,path,out/f"{i:02}-{name}"));rows.append(row);f.write(json.dumps(row)+"\n");f.flush();print("G10_ROW",json.dumps(row),flush=True)
            assert len({r["status"] for r in rows if r["status"] in ("SAT","UNSAT")})<=1
            path.unlink()
            for p in out.glob(f"{i:02}-*.cert"):p.unlink()
if __name__=="__main__":main(int(sys.argv[1]))
