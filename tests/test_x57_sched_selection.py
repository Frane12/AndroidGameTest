#!/usr/bin/env python3
"""Offline tests for outcome-independent SAT2024 scheduling selection."""
import bz2,gzip,lzma,pathlib,sys,zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"research"))
import drnas_x57_sched_unseen as E

def info(path,size=10000):
    i=zipfile.ZipInfo("official/"+path)
    i.file_size=size
    return i

def main():
    m=[]
    for cat in ("worker","Break_unsat","pcmax-scheduling"):
        for i in range(9):
            m.append(info(f"{cat}_{i:03d}_2024.cnf.xz",10000+i*1400))
    names=("alpha","beta","gamma","delta","epsilon","zeta","theta",
           "iota","kappa","lambda","mu","nu","xi","omicron","pi","rho")
    for i,name in enumerate(names):
        m.append(info(f"control{name}_{i+1}.cnf.xz",12000+i*1000))
    old=[{"filename":"worker_000_2024.cnf.xz",
          "archive_entry":"worker_000_2024.cnf.xz",
          "sha256":"abc"}]
    selected,stats=E.select_zip_members(m,old)
    selected2,stats2=E.select_zip_members(m,old)
    assert [(x.filename,y) for x,y in selected]==[(x.filename,y) for x,y in selected2]
    assert stats==stats2
    assert len(selected)==20
    assert stats["selected_sched"]==12 and stats["selected_control"]==8
    assert len({x.filename for x,_ in selected})==20
    assert all("worker_000" not in x.filename for x,_ in selected)
    assert len({E.name_family(x.filename) for x,c in selected if c=="control-other-filename"})==8
    assert {c for _,c in selected if c!="control-other-filename"}=={
       "scheduling-worker","scheduling-break","scheduling-pcmax"}
    # Source decoding is exact; the official benchmark path must preserve raw
    # bytes, without preprocess/simplify or transforming clauses.
    raw=b"p cnf 2 2\n1 0\n-1 2 0\n"
    for ext,comp in (("gz",gzip.compress),("xz",lzma.compress),
                     ("bz2",bz2.compress)):
        obj=info(f"test.cnf.{ext}",size=4000)
        assert E.decode(obj,comp(raw))==raw
    # Minimal sample with too few scheduling names must fail explicitly.
    try:
        E.select_zip_members([info("alpha_1.cnf.xz")],[])
    except RuntimeError as ex:
        assert "scheduling" in str(ex)
    else:raise AssertionError("insufficient scheduling sources unexpectedly permitted")
    print("X57_SCHED_SELECTOR_SELFTEST_PASS "+
          str({"synthetic_zip_members":len(m),"selected":len(selected),
               "scheduling":stats["selected_sched"],
               "controls":stats["selected_control"],
               "verified_compression_formats":3}))

if __name__=="__main__":main()
