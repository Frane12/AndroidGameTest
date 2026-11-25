#!/usr/bin/env python3
import os,sys,subprocess,json,hashlib,time,pathlib,urllib.request,base64,lzma,gzip,bz2,resource,re
M=json.loads(pathlib.Path(__file__).with_name("manifest.json").read_text())
CAP=M["solver_cap_s"]
root=pathlib.Path(__file__).resolve().parents[1]/"native-general4"
out=pathlib.Path("native-catalog-out")
out.mkdir(exist_ok=True)
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

def build():
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

def sha(b): return hashlib.sha256(b).hexdigest()
def fetch(case):
    req=urllib.request.Request(case["url"],headers={"User-Agent":"DRNAS-NATIVE-CATALOG57/1.0"})
    limit=M["max_archive_bytes"] if "file_id" in case else M["max_raw_bytes"]
    with urllib.request.urlopen(req,timeout=45) as response:
        if int(response.headers.get("Content-Length",0))>limit: raise ValueError("archive_size_excluded")
        packed=response.read(limit+1)
    if len(packed)>limit: raise ValueError("archive_size_excluded")
    if "archive_sha256" in case and sha(packed)!=case["archive_sha256"]: raise ValueError("archive_hash_mismatch")
    if "blob" in case and hashlib.sha1(b"blob "+str(len(packed)).encode()+b"\0"+packed).hexdigest()!=case["blob"]:raise ValueError("git_blob_hash_mismatch")
    if packed.startswith(b"\xfd7zXZ\x00"):
        dec=lzma.LZMADecompressor(memlimit=256*1024*1024)
        data=dec.decompress(packed,max_length=M["max_raw_bytes"]+1)
        if not dec.eof:raise ValueError("raw_size_excluded_or_truncated")
    elif packed.startswith(b"\x1f\x8b"):
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as f:data=f.read(M["max_raw_bytes"]+1)
    elif packed.startswith(b"BZh"):
        dec=bz2.BZ2Decompressor();data=dec.decompress(packed,max_length=M["max_raw_bytes"]+1)
        if not dec.eof:raise ValueError("raw_size_excluded_or_truncated")
    else:data=packed
    if len(data)>M["max_raw_bytes"]:raise ValueError("raw_size_excluded")
    if "sha256" in case and sha(data)!=case["sha256"]:raise ValueError("raw_hash_mismatch")
    h=re.search(rb"^p\s+cnf\s+(\d+)\s+(\d+)\s*$",data,re.M)
    if not h:raise ValueError("missing_DIMACS_header")
    nv,nc=map(int,h.groups())
    if nv>M["max_variables"] or nc>M["max_clauses"]:raise ValueError("header_size_excluded")
    return data,sha(packed),nv,nc
def restrict():
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
def main(i):
    case=M["cases"][i]; result=dict(case,rows=[])
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    try:
        data,archive_hash,nv,nc=fetch(case)
        result.update(source_sha256=sha(data),download_sha256=archive_hash,variables=nv,clauses=nc,raw_bytes=len(data))
        n,cs=parse(data)
        inp=out/"input.cnf";inp.write_bytes(data)
        build()
        result["input_status"]="READY"
        result["binary_sha256"]=sha((out/"native").read_bytes())
        for mode in M["arms"]:
            prefix=out/mode;start=time.monotonic()
            try:
                p=subprocess.run([str((out/"native").resolve()),str(inp),str(CAP),mode,str(prefix)],capture_output=True,text=True,timeout=CAP+0.3,preexec_fn=restrict)
                if p.returncode!=0:
                    row={"status":"ERROR","method":"process_exit","returncode":p.returncode,"stderr":p.stderr[-500:]}
                else:
                    row=json.loads(p.stdout.strip().splitlines()[-1])
            except subprocess.TimeoutExpired:row={"status":"UNKNOWN","method":"wall_timeout"}
            except Exception as exc:row={"status":"ERROR","method":"execution_error","error":str(exc)[:500]}
            elapsed=time.monotonic()-start
            row.update(mode=mode,elapsed_s=round(elapsed,6),cpu=cpu,cap_s=CAP)
            try:
                audit_start=time.monotonic()
                row["verification"]=audit(row,n,cs,prefix)
                row["audit_wall_s"]=round(time.monotonic()-audit_start,6)
            except Exception as exc:
                row["verification"]="AUDIT_FAILED";row["audit_error"]=str(exc)[:500]
                row["audit_wall_s"]=round(time.monotonic()-audit_start,6)
            row["e2e_s"]=round(elapsed+row["audit_wall_s"],6)
            row["strict_par2_s"]=row["e2e_s"] if row["verification"] in ("INDEPENDENT_MODEL_VERIFIED","INDEPENDENT_RUP_VERIFIED") and row["e2e_s"]<=CAP else 2*CAP
            result["rows"].append(row)
    except Exception as exc:
        result["input_status"]="EXCLUDED_OR_ERROR";result["reason"]=type(exc).__name__+": "+str(exc)[:500]
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print("CATALOG57_RESULT",json.dumps(result),flush=True)
if __name__=="__main__":main(int(sys.argv[1]))
