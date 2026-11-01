#!/usr/bin/env python3
"""Inspect authoritative SAT Competition 2024 per-instance metadata and outcomes."""
import csv,hashlib,io,os,urllib.request,zipfile
COMMIT="fa06f42b914ec155b2120aef936ce9305a3e4128"
URL="https://raw.githubusercontent.com/satcompetition/2024/"+COMMIT+"/downloads/"
def fetch(name):
    with urllib.request.urlopen(URL+name,timeout=75) as response:return response.read()
def main():
    meta=fetch("meta.csv");data=fetch("detailed_results.zip")
    print("SC2024_META_SHA256",hashlib.sha256(meta).hexdigest(),len(meta),flush=True)
    print("SC2024_RESULTS_SHA256",hashlib.sha256(data).hexdigest(),len(data),flush=True)
    rows=meta.decode().splitlines()
    print("SC2024_METADATA_FIRST_LINES",rows[:5],flush=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zip:
        names=zip.namelist()
        print("SC2024_ZIP_FILES",names[:35],flush=True)
        for name in names[:5]:
            if name.endswith("/"):continue
            item=zip.read(name)
            print("SC2024_FILE_DETAIL",name,len(item),item[:4200].decode("utf-8","replace"),flush=True)
        main=list(csv.DictReader(io.StringIO(zip.read("detailed_main.csv").decode("utf-8"))))
        print("SC2024_MAIN_ROWS",len(main),flush=True)
        print("SC2024_MAIN_FIRST",main[:3],flush=True)
        print("SC2024_MAIN_VRESULT_COUNTS",dict(__import__("collections").Counter(row.get("vresult") for row in main)),flush=True)
    samples=[r.split()[0] for r in rows[:4] if r.strip()]
    for sample in samples[:2]:
        url="https://benchmark-database.de/file/"+sample
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-2024-probe/1.0"})
            with urllib.request.urlopen(req,timeout=25) as response:
                head=response.read(12)
                print("SC2024_CNF_RETRIEVAL",sample,response.status,
                      response.headers.get("Content-Length"),head.hex(),flush=True)
        except Exception as e:print("SC2024_CNF_RETRIEVAL_ERROR",sample,str(e)[:250],flush=True)
if __name__=="__main__":main()
