"""Paired original SAT2026 experiment; affine pre-pass + frozen ATTACK2.
No CDCL in either DRNAS arm. All accepted outcomes audited independently.
"""
import pathlib,os,sys,json,hashlib,subprocess,time,urllib.request,gzip,lzma,bz2,textwrap,math,collections
P=pathlib.Path
root=P(__file__).resolve().parent
out=P("general6-out");out.mkdir(exist_ok=True)
bin=P("bin").resolve();bin.mkdir(exist_ok=True)
sha=lambda x:hashlib.sha256(x).hexdigest()
CAP=15.0
def build():
    # Reuse exact source reconstruction (including all SHA assertions) from
    # original GENERAL4 run.py, without downloading its four regression inputs.
    old=root.parent/"native-general4"
    text=(old/"run.py").read_text()
    chunk=text.split("    src=lzma.decompress",1)[1].split("    n,cs=parse(data);",1)[0]
    chunk=textwrap.dedent("    src=lzma.decompress"+chunk)
    import base64
    env=dict(root=old,out=bin,lzma=lzma,base64=base64,hashlib=hashlib,subprocess=subprocess)
    exec(compile(chunk,"frozen-general4-build","exec"),env)
    assert sha((root/"affine.cpp").read_bytes())=="d4c2ebcde8b0e96ea099b19021e510c9d81c5c90e445a4432d71cd507eda3095"
    subprocess.run(["g++","-O3","-std=c++17",str(root/"affine.cpp"),"-o",str(bin/"affine")],check=True)
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"DRNAS General6 research"}),timeout=45) as r:
        b=r.read(64*1024*1024+1)
    if len(b)>64*1024*1024:raise ValueError("compressed input exceeds cap")
    raw=b
    if b.startswith(b"\xfd7zXZ\x00"):raw=lzma.decompress(b)
    elif b.startswith(b"\x1f\x8b"):raw=gzip.decompress(b)
    elif b.startswith(b"BZh"):raw=bz2.decompress(b)
    if len(raw)>128*1024*1024:raise ValueError("input exceeds cap")
    if not any(l.startswith(b"p cnf ") for l in raw.splitlines()):raise ValueError("not DIMACS")
    return raw
def parse(path):
    n=m=None;cs=[];c=[]
    for line in path.open():
        line=line.strip()
        if not line or line.startswith("c"):continue
        if line.startswith("%"):break
        if line.startswith("p "):
            _,_,n,m=line.split();n=int(n);m=int(m);continue
        for l in map(int,line.split()):
            if l:c.append(l)
            else:cs.append(c);c=[]
    assert n is not None and len(cs)==m and not c and all(0<abs(l)<=n for c in cs for l in c)
    return n,cs
def audit_model(path,model):
    n,cs=parse(path);a={}
    for ln in model.splitlines():
        if not ln.startswith("v "):continue
        for l in map(int,ln.split()[1:]):
            if l==0:continue
            if abs(l)>n or (abs(l) in a and a[abs(l)]!=(l>0)):return False
            a[abs(l)]=l>0
    return all(any(a.get(abs(l))==(l>0) for l in c) for c in cs)
def audit_proof(path,proof):
    if not proof.exists():return False
    p=subprocess.run([str(bin/"drat-trim"),str(path),str(proof)],capture_output=True,text=True,timeout=90)
    return "s VERIFIED" in p.stdout
def one(name,path,prefix):
    start=time.monotonic();status="UNKNOWN";method="";proof=None;model=None;detail=""
    def run(cmd,seconds):
        return subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=max(0.001,seconds))
    def base():
        remain=CAP-(time.monotonic()-start)
        if remain<1:return "TIMEOUT","ATTACK2",None,None
        p=run([bin/"native",path,str(max(1,int(remain))),"attack2",prefix],remain)
        if p.returncode!=0:raise RuntimeError("ATTACK2 exit "+str(p.returncode))
        x=json.loads(p.stdout.strip().splitlines()[-1]);st=x["status"]
        if st=="SAT_VERIFIED":
            return "SAT",x["method"],None,prefix.with_suffix(".model").read_text()
        if st=="UNSAT_CHECKED" and prefix.with_suffix(".drat").exists():
            return "UNSAT",x["method"],prefix.with_suffix(".drat"),None
        if st=="UNSAT_CHECKED":return "UNCERTIFIED",x["method"],None,None
        return "UNKNOWN",x["method"],None,None
    try:
        if name=="GENERAL6":
            cert=prefix.with_suffix(".affine")
            p=run([bin/"affine",path,cert,"1500"],2.0)
            detail=p.stdout.strip()
            if p.returncode==10:status,method,model="SAT","AFFINE",cert.read_text()
            elif p.returncode==20:status,method,proof="UNSAT","AFFINE",cert
            elif p.returncode==0:status,method,proof,model=base()
            else:raise RuntimeError("affine exit "+str(p.returncode))
        elif name=="ATTACK2":status,method,proof,model=base()
        else:
            cert=prefix.with_suffix(".drat")
            p=run([bin/name.lower(),"-q",path,cert],CAP)
            if p.returncode==10:status,method,model="SAT",name,p.stdout
            elif p.returncode==20:status,method,proof="UNSAT",name,cert
            elif p.returncode==0:status="UNKNOWN"
            else:raise RuntimeError("reference exit "+str(p.returncode))
    except subprocess.TimeoutExpired:status="TIMEOUT"
    except Exception as e:status="ERROR";detail+=repr(e)
    elapsed=time.monotonic()-start
    if elapsed>CAP:status="TIMEOUT"
    check_start=time.monotonic()
    try:
        if status=="SAT" and not audit_model(path,model):status="AUDIT_FAILED"
        if status=="UNSAT" and not audit_proof(path,proof):status="AUDIT_FAILED"
    except Exception as e:status="AUDIT_FAILED";detail+=repr(e)
    check_s=time.monotonic()-check_start
    if status=="SAT":prefix.with_suffix(".verified.model.gz").write_bytes(gzip.compress(model.encode(),mtime=0))
    if status=="UNSAT":prefix.with_suffix(".verified.proof.gz").write_bytes(gzip.compress(proof.read_bytes(),mtime=0))
    return dict(solver=name,status=status,method=method,wall_s=elapsed,check_s=check_s,par2_s=elapsed if status in ("SAT","UNSAT") else 2*CAP,detail=detail)
def main(shard):
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    build()
    uri=get_list()
    urls=sorted(set(x.strip() for x in uri.decode().splitlines() if x.startswith(("https://","http://"))))
    pilot_seed="8c7b1552bbfca9a762924bec390ef265c83b122a"
    old=set(sorted(urls,key=lambda u:sha((pilot_seed+"|sat2026|"+u).encode()))[:12])
    seed=os.environ["GITHUB_SHA"]
    draw=sorted(set(urls)-old,key=lambda u:sha((seed+"|general6|"+u).encode()))[:50]
    assert len(draw)==50
    (out/"manifest.json").write_text(json.dumps(dict(seed=seed,list_sha256=sha(uri),draw=draw,excluded_pilot=sorted(old),shard=shard,cpu=cpu,cap=CAP,binaries={x:sha((bin/x).read_bytes()) for x in ("native","affine","kissat","cadical","drat-trim")}),indent=2))
    rows=[];arms=["ATTACK2","GENERAL6","Kissat","CaDiCaL"]
    with (out/"rows.jsonl").open("w") as f:
        for i in range(shard,50,5):
            url=draw[i];path=out/"input.cnf"
            try:raw=get(url);path.write_bytes(raw)
            except Exception as e:
                row=dict(id=i,url=url,status="SOURCE_FAILED",detail=repr(e));f.write(json.dumps(row)+"\n");f.flush();print("G6_SOURCE",json.dumps(row),flush=True);continue
            h=sha(raw)
            for name in arms[i%4:]+arms[:i%4]:
                prefix=out/("%02d-%s"%(i,name))
                row=dict(id=i,url=url,sha256=h,bytes=len(raw),**one(name,path,prefix))
                rows.append(row);f.write(json.dumps(row)+"\n");f.flush();print("G6_ROW",json.dumps(row),flush=True)
            answers={x["status"] for x in rows if x["id"]==i and x["status"] in ("SAT","UNSAT")}
            assert len(answers)<=1,"contradictory audited results"
            path.unlink()
    summary={name:dict(collections.Counter(x["status"] for x in rows if x["solver"]==name)) for name in arms}
    print("G6_SUMMARY",json.dumps(summary),flush=True)
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    if any(x["status"] in ("ERROR","AUDIT_FAILED") for x in rows):raise SystemExit("solver/audit error; see evidence")
def get_list():
    with urllib.request.urlopen("https://satcompetition.github.io/2026/downloads/track_main_2026.uri",timeout=60) as f:return f.read()
if __name__=="__main__":main(int(sys.argv[1]))
