#!/usr/bin/env python3
"""Proof-safe fast abstention regression on a previously observed no-block original."""
import json,os,sys,subprocess,pathlib,tempfile
R=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research"))
import drnas_x55_cpu_real36 as B
def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows,_=B.official_manifest()
    c=next(z for z in rows if z["id"]==20)
    cnf=pathlib.Path(c["path"])
    assert B.sha(cnf.read_bytes())==c["sha256"]
    report={}
    with tempfile.TemporaryDirectory() as d:
        for arm in ("drnas-coop53-repair","drnas-coop54-gate"):
            proof=pathlib.Path(d)/(arm+".drat")
            p=subprocess.run([str(R/"build"/arm),str(cnf),"--mode","core",
                             "--time","1.5","--stats","--x5-no-minimize",
                             "--coop4","on","--coop5","on","--proof",str(proof)],
                             capture_output=True,text=True,timeout=3)
            assert p.returncode in (0,10,20,153),(arm,p.returncode,p.stderr[-450:])
            data={}
            for marker in ("COOP4_STATS","COOP53_CONTRACT","COOP54_DISPATCH"):
                found=[json.loads(z.split(" ",1)[1]) for z in p.stderr.splitlines()
                       if z.startswith(marker+" ")]
                if found:data[marker]=found[0]
            assert data["COOP4_STATS"]["prepared"] is True,(arm,data)
            assert data["COOP4_STATS"]["blocks"]==0,(arm,data)
            assert data["COOP53_CONTRACT"]["bridge_calls"]>100,(arm,data)
            if arm.endswith("-gate"):
                assert data["COOP54_DISPATCH"]["skipped_dead_dispatch"]>100,(arm,data)
            report[arm]={
                "status":p.returncode,
                "component_calls":data["COOP53_CONTRACT"]["bridge_calls"],
                "skipped_dead":data.get("COOP54_DISPATCH",{}).get("skipped_dead_dispatch",0),
                "conflicts":next((json.loads(z.split(" ",1)[1])["conflicts"]
                   for z in p.stderr.splitlines() if z.startswith("X41_STATS ")),0)
            }
            if p.returncode==10:
                n,cs=B.parse_cnf(cnf.read_bytes())
                assert B.check_sat(p.stdout,cs,n)
            elif p.returncode==20:
                q=subprocess.run([str(R/"build/drat-trim"),str(cnf),str(proof)],
                                 capture_output=True,text=True,timeout=20)
                assert "s VERIFIED" in q.stdout
    print("COOP54B_EMPTY_BLOCK_FASTPATH_PASS",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":main()
