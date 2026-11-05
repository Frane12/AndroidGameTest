#!/usr/bin/env python3
"""Build the actual public SAT Competition 2026 biere source archive.
No substituted or renamed upstream binary. Build SHA and archive SHA pinned in
an artifact; fail closed if the requested submitted solver cannot be built.
"""
import hashlib,json,os,pathlib,shutil,subprocess,sys,tarfile,urllib.request
ROOT=pathlib.Path("r28full");ROOT.mkdir(exist_ok=True)
ARCHIVE_URL="https://satcompetition.github.io/2026/downloads/solvers/biere.tar.xz"
OUT=ROOT/"sc2024-kissat"
def sha(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def need(ok,msg):
 if not ok:raise RuntimeError("R28_OFFICIAL_SUBMISSION_BUILD_REFUSED "+str(msg))
def run(args,cwd=None,timeout=160):
 x=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=timeout)
 print("R28_OFFICIAL_BUILD_COMMAND",args,"rc",x.returncode,
       "stdout_tail",x.stdout[-2000:],"stderr_tail",x.stderr[-2000:],flush=True)
 need(x.returncode==0,"failed to build submitted SAT2026 source "+repr(args))
def test(exe):
 testdir=ROOT/"smoke";testdir.mkdir(exist_ok=True)
 (testdir/"sat.cnf").write_text("p cnf 2 2\n1 0\n2 0\n")
 (testdir/"unsat.cnf").write_text("p cnf 1 2\n1 0\n-1 0\n")
 for name,expected in (("sat",10),("unsat",20)):
  p=subprocess.run([str(exe.resolve()),str((testdir/(name+".cnf")).resolve())],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=12)
  need(p.returncode==expected,
       "wrong competition solver exit status "+name+" "+str(p.returncode)+" "+p.stderr[-100:].decode(errors="replace"))
  if name=="sat":
   # Runner validates all SAT models; enforce output at smoke time too.
   model=set()
   for line in p.stdout.decode(errors="replace").splitlines():
    if line.startswith("v "):
     model.update(int(x) for x in line[2:].split() if x!="0")
   need(1 in model and 2 in model,"competition solver does not emit complete SAT witness by default")
  print("R28_OFFICIAL_SMOKE_PASS",name,p.returncode,flush=True)
def main():
 outarchive=ROOT/"official-2026-biere.tar.xz"
 req=urllib.request.Request(ARCHIVE_URL,headers={"User-Agent":"DRNAS-Research-Competition-Source-Check/1.0"})
 with urllib.request.urlopen(req,timeout=90) as r:
  data=r.read(90_000_001)
 need(len(data)<=90_000_000 and len(data)>1000,"official archive missing or oversized")
 outarchive.write_bytes(data)
 sourcehash=sha(outarchive)
 unpack=ROOT/"official-source"
 unpack.mkdir(exist_ok=True)
 with tarfile.open(outarchive,"r:xz") as tar:
  members=tar.getmembers()
  need(0<len(members)<=100000,"unexpected source archive entries")
  for m in members:
   p=pathlib.PurePosixPath(m.name)
   need(not p.is_absolute() and ".." not in p.parts,"path traversal in source archive")
  safe=[]
  skipped=[]
  for member in members:
   # Official author package contains an absolute symlink
   # biere/kissat/src/src/makefile. Never extract an absolute/outside link.
   # Preserve the archive's original SHA, and never change regular source files.
   if member.issym() or member.islnk():
    link=pathlib.PurePosixPath(member.linkname)
    if link.is_absolute():
     skipped.append((member.name,member.linkname))
     continue
   safe.append(member)
  tar.extractall(unpack,members=safe,filter="data")
  print("R28_OFFICIAL_SKIPPED_UNSAFE_LINKS",repr(skipped),flush=True)
 print("R28_OFFICIAL_ARCHIVE",ARCHIVE_URL,sourcehash,"entries",len(members),flush=True)
 paths=list(unpack.rglob("configure"))
 candidates=[p.parent for p in paths if p.is_file() and "kissat" in str(p.parent).lower()]
 candidates.sort(key=lambda p:(("sc2024" not in str(p).lower()),len(p.parts),str(p)))
 need(bool(candidates),
      "submitted biere archive has no Kissat configure script; candidates="+
      repr([str(p) for p in paths[:25]]))
 # Only the submitted source package is allowed. Multiple Kissat directories
 # are searched by a fixed priority; never substitute a different project.
 failures=[]
 for source in candidates:
  try:
   run(["sh","configure"],cwd=source,timeout=75)
   run(["make","-j2"],cwd=source,timeout=270)
   executables=[source/"build/kissat",source/"kissat",source/"bin/kissat"]
   executables += sorted(p for p in source.rglob("*") if p.is_file() and p.name=="kissat" and os.access(p,os.X_OK))
   for binary in executables:
    if not binary.is_file() or not os.access(binary,os.X_OK):continue
    shutil.copyfile(binary,OUT);OUT.chmod(0o755)
    test(OUT)
    report=dict(source="SAT Competition 2026 official submitted archive biere.tar.xz",
        archive_url=ARCHIVE_URL,archive_sha256=sourcehash,
        selected_subdirectory=str(source.relative_to(unpack)),binary_sha256=sha(OUT),
        build_command="sh configure && make -j2",smoke="SAT and UNSAT with witness verified",
        source_archive_entries=len(members),competition_source_unmodified=True)
    (ROOT/"official-build.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("R28_OFFICIAL_BUILD_PASS",json.dumps(report,sort_keys=True),flush=True)
    return
   failures.append((str(source),"missing executable Kissat binary"))
  except Exception as e:
   failures.append((str(source),str(e)[:500]))
   print("R28_OFFICIAL_BUILD_CANDIDATE_FAILED",str(source),str(e)[:500],flush=True)
 raise RuntimeError("No buildable verified source under competition biere archive "+repr(failures))
if __name__=="__main__":main()
