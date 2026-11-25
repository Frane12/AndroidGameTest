import os, sys, subprocess, json, hashlib, time, pathlib, urllib.request, base64, lzma
CASES = [["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/hanoi/hanoi4.cnf","b8178ea722a1215e33708b3a4de537988f1e37d6"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/hanoi/hanoi5.cnf","86418b6f58d3b0aa338bfecd7a06132ab524cb57"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/jnh/jnh10.cnf","74b2830e06c754777552a9d0a14f46b04274175e"],["jariazavalverde/sat","74dc16cd5d186d512274a6ce3c768dba96eb5752","sample/jnh/jnh11.cnf","0a459074764e199c5956e002e4120d0d655e3eef"]]
CAP=20
root=pathlib.Path(__file__).resolve().parent
out=pathlib.Path("native4-out"); out.mkdir(exist_ok=True)
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
    src=lzma.decompress(base64.b64decode((root.parent/"native-general13"/"native.cpp.xz.b64").read_text()))
    assert hashlib.sha256(src).hexdigest()=="518e684419c7c28c3d934733ec8009bfcc8f347588279683d18a2be77b40eb90"
    hdr=lzma.decompress(base64.b64decode((root/"general4.hpp.xz.b64").read_text()))
    assert hashlib.sha256(hdr).hexdigest()=="e8bd4f4c4bfdefff0828a6308fbc63410b48158761f817a6c8633b70f8bcd92a"
    (out/"general4.hpp").write_bytes(hdr)
    s=src.decode()
    s=s.replace('int main(int argc,char**argv)', '#include "general4.hpp"\nint main(int argc,char**argv)')
    s=s.replace('bool attack=argc<4||string(argv[3])!="base";', 'bool attack=argc<4||string(argv[3])!="base";bool newmode=argc>3&&string(argv[3])=="attack2";')
    s=s.replace('auto cap=capacity(d.c);if(cap.first', 'auto cap=capacity(d.c);TemporalResult tr;long long splitnodes=0;if(newmode)tr=temporal_chain(d,min(end,Clock::now()+chrono::milliseconds(sec*450)));if(tr.sat){a=move(tr.a);status="SAT_VERIFIED";method="temporal_chain";}else if(cap.first')
    s=s.replace('else{if(attack&&(gf2(f', 'else{if(newmode&&remaining<=160){auto sr=split_core(p,min(end,Clock::now()+chrono::milliseconds(sec*350)),50000);splitnodes=sr.nodes;if(sr.status==1){a=move(sr.a);if(p.lift(a)){status="SAT_VERIFIED";method="case_decomposition";}}else if(sr.status==-1&&p.audit(end)){status="UNSAT_CHECKED";method="resolution";if(!prefix.empty())p.drat(prefix+".drat");}proof=p.proof.size();}if(status=="UNKNOWN"&&attack&&(gf2(f')
    s=s.replace('<<",\\\"ms\\\":"<<ms(start)', '<<",\\\"temporal_layers\\\":"<<tr.layers<<",\\\"temporal_states\\\":"<<tr.states<<",\\\"temporal_edges\\\":"<<tr.edges<<",\\\"split_nodes\\\":"<<splitnodes<<",\\\"ms\\\":"<<ms(start)')
    src=s.encode()
    assert hashlib.sha256(src).hexdigest()=="4b615e9ca9fad11563bb4a6565776aeb016357439c0bd46c05cac21dd5c20bd0"
    (out/"native.cpp").write_bytes(src)
    subprocess.run(["g++","-O3","-std=c++17","-DNDEBUG",str(out/"native.cpp"),"-o",str(out/"native")],check=True)
    n,cs=parse(data); cpu=min(os.sched_getaffinity(0)); rows=[]
    for mode in ("attack","attack2"):
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
    print("NATIVE4_RESULT",json.dumps(result),flush=True)
if __name__=="__main__":main(int(sys.argv[1]))
