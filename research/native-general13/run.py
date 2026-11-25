import os, sys, subprocess, json, hashlib, time, pathlib, urllib.request, base64, lzma
CASES = [["ekmett/ersatz","7e08b9e4bbec5ea93804e6cab36b9a7424cc2844","data/dimacs/blocksworld/bw_large.a.cnf","e04e95e8165d240ce2e8e25c81eed8e524bc4a7a"],["ekmett/ersatz","7e08b9e4bbec5ea93804e6cab36b9a7424cc2844","data/dimacs/blocksworld/huge.cnf","2ff4b15a9b66ad6f2d3d9d17ae9237b7b3eaf91f"],["ekmett/ersatz","7e08b9e4bbec5ea93804e6cab36b9a7424cc2844","data/dimacs/logistics/logistics.a.cnf","69e5b388b9d9d5c1589d26cbff5b4d587ba32277"],["ekmett/ersatz","7e08b9e4bbec5ea93804e6cab36b9a7424cc2844","data/dimacs/logistics/logistics.b.cnf","9d6be9629b4903a490d0e99fcf9b2363a16fb294"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/hanoi/hanoi4.cnf","b8178ea722a1215e33708b3a4de537988f1e37d6"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/hanoi/hanoi5.cnf","86418b6f58d3b0aa338bfecd7a06132ab524cb57"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/aim/aim-100-1_6-no-1.cnf","0b72579b2fb750f98b717df2072953471af4db68"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/aim/aim-100-1_6-no-2.cnf","144d8aaa39efbb5314971bae8f1558bce82339ac"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/jnh/jnh1.cnf","894c494e259eda017609ce1ac68110b0dd75abbf"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/jnh/jnh10.cnf","74b2830e06c754777552a9d0a14f46b04274175e"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/jnh/jnh11.cnf","0a459074764e199c5956e002e4120d0d655e3eef"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/jnh/jnh12.cnf","9a147a7043a1480aa7007e6c00da24ece6ffb556"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/ii/ii8a2.cnf","bc1195452bd7a3e7eff49a4845d3d27b6416f510"]]
CAP=20
root=pathlib.Path(__file__).resolve().parent
out=pathlib.Path("native13-out"); out.mkdir(exist_ok=True)
def parse(data):
    n=m=None; cs=[]; c=[]
    for line in data.decode().splitlines():
        line=line.strip()
        if not line or line.startswith("c"): continue
        if line.startswith("%"): break
        if line.startswith("p "):
            _,_,n,m=line.split(); n=int(n); m=int(m); continue
        for x in map(int,line.split()):
            if x: c.append(x)
            else: cs.append(c); c=[]
    assert n is not None and len(cs)==m and not c and all(abs(x)<=n for c in cs for x in c)
    return n,cs
def rup(cs,assume,n):
    a=[0]*(n+1)
    for l in assume:
        v=abs(l); s=1 if l>0 else -1
        if a[v]==-s:return True
        a[v]=s
    while True:
        changed=False
        for c in cs:
            rem=[]; sat=False
            for l in c:
                if a[abs(l)]==(1 if l>0 else -1):sat=True;break
                if not a[abs(l)]:rem.append(l)
            if sat:continue
            if not rem:return True
            if len(rem)==1:
                l=rem[0];a[abs(l)]=1 if l>0 else -1;changed=True
        if not changed:return False
def audit(row, n, cs, prefix):
    start=time.monotonic()
    if row["status"]=="SAT_VERIFIED":
        model=prefix.with_suffix(".model")
        vals={}
        for l in model.read_text().split():
            if l in ("v","0"):continue
            x=int(l);assert 1<=abs(x)<=n and abs(x) not in vals
            vals[abs(x)]=x>0
        assert len(vals)==n
        assert all(any(vals[abs(l)]==(l>0) for l in c) for c in cs)
        verdict="INDEPENDENT_MODEL_VERIFIED"
    elif row["status"]=="UNSAT_CHECKED" and row["method"]=="resolution":
        proof=prefix.with_suffix(".drat"); base=[list(dict.fromkeys(c)) for c in cs]; verified=False
        for line in proof.read_text().splitlines():
            xs=list(map(int,line.split()));assert xs and xs[-1]==0
            c=xs[:-1]; assert rup(base,[-l for l in c],n)
            base.append(c)
            if not c:verified=True;break
            if time.monotonic()-start>90: return "AUDIT_TIMEOUT"
        assert verified
        verdict="INDEPENDENT_RUP_VERIFIED"
    elif row["status"]=="UNSAT_CHECKED":verdict="INTERNAL_CERTIFICATE_ONLY"
    else:verdict="UNKNOWN"
    row["external_check_ms"]=round((time.monotonic()-start)*1000)
    return verdict
def main(i):
    repo,commit,path,blob=CASES[i]
    url=f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
    data=urllib.request.urlopen(url,timeout=60).read()
    actual=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
    assert actual==blob,(actual,blob)
    inp=out/"input.cnf";inp.write_bytes(data)
    src=lzma.decompress(base64.b64decode((root/"native.cpp.xz.b64").read_text()))
    assert hashlib.sha256(src).hexdigest()=="518e684419c7c28c3d934733ec8009bfcc8f347588279683d18a2be77b40eb90"
    (out/"native.cpp").write_bytes(src)
    subprocess.run(["g++","-O3","-std=c++17","-DNDEBUG",str(out/"native.cpp"),"-o",str(out/"native")],check=True)
    n,cs=parse(data); cpu=min(os.sched_getaffinity(0)); rows=[]
    for mode in ("base","attack"):
        prefix=out/mode;start=time.monotonic()
        try:
            r=subprocess.run(["taskset","-c",str(cpu),str(out/"native"),str(inp),str(CAP),mode,str(prefix)],capture_output=True,text=True,timeout=CAP+3)
            assert r.returncode==0,(r.returncode,r.stderr)
            row=json.loads(r.stdout.strip().splitlines()[-1])
        except subprocess.TimeoutExpired:row={"status":"UNKNOWN","method":"wall_timeout"}
        row.update({"mode":mode,"elapsed_s":round(time.monotonic()-start,6),"cap_s":CAP,"cpu":cpu})
        row["verification"]=audit(row,n,cs,prefix)
        rows.append(row)
    result={"id":i,"file":path,"source":url,"blob":actual,"sha256":hashlib.sha256(data).hexdigest(),"variables":n,"clauses":len(cs),"rows":rows}
    (out/"result.json").write_text(json.dumps(result,indent=2))
    print("NATIVE13_RESULT",json.dumps(result),flush=True)
if __name__=="__main__":main(int(sys.argv[1]))
