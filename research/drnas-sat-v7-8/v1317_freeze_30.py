#!/usr/bin/env python3
"""V13.17: freeze another 30 new 2024 CNFs before 20-second fixed-policy validation.

Public, pinned 2024 meta/result archives. 15 SAT and 15 UNSAT from diverse
families; deterministic precommitted selection based on IDs, family & labels,
never on the DRNAS or modern Kissat solving times. SHA excludes all
historical listed DRNAS 2026 cohorts. Size restrictions explicitly audited.
"""
import argparse,collections,csv,hashlib,io,json,urllib.request,zipfile
from pathlib import Path
import official_shortlong_select as source

PROTOCOL="DRNAS-V1313-SC2024-THIRTY-SHA-DISJOINT-20261101-v1"
HOLDOUT_PROTOCOL="DRNAS-V1317-NEW30-SC2024-FIXED20-V1315-20261101-v1"
YEAR_COMMIT="fa06f42b914ec155b2120aef936ce9305a3e4128"
ROOT="https://raw.githubusercontent.com/satcompetition/2024/"+YEAR_COMMIT+"/downloads/"
EXPECTED_META="c8703ab84f28b4369c96bbdfd3d6cc0f00b0b5212bc58cd2d5d7eca48cafc0ce"
EXPECTED_RESULTS="dfdf1d515fc95e95d3b76f907a2ce67932af1f8905f90c3dd7f743ea6c2b751a"
SALT="DRNAS-V1317-NEW30-CAP20-DIVERSE-20261101"
TARGET=30;PER_LABEL=15;MAX_ATTEMPTS=340
source.RAW_CAP=96*1024**2
source.CNF_CAP=64*1024**2
source.VARIABLE_CAP=500000
source.CLAUSE_CAP=1000000
def sha(data):return hashlib.sha256(data).hexdigest()
def check(v,msg):
    if not v:raise RuntimeError(msg)
def load(p):return json.loads(Path(p).read_text())
def save(p,x):
    out=Path(p);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def fetch(name):
    with urllib.request.urlopen(ROOT+name,timeout=75) as url:return url.read()
def freeze(a):
    ids=set();shas=set();history=[]
    for p in (a.v131,a.mini,a.v100,a.v132,a.v138,a.v139,a.v1313,a.v1316):
        doc=load(p)
        check(isinstance(doc.get("cases"),list),"Invalid historical manifest: "+p)
        for c in doc["cases"]:
            ids.add(c["id"]);shas.add(c["sha256"])
        history.append({"source":p,"sha256":sha(Path(p).read_bytes()),"n":len(doc["cases"])})
    check(len(ids)>=204 and len(shas)>=204,"Historical exclusion incomplete")
    meta=fetch("meta.csv");zdata=fetch("detailed_results.zip")
    check(sha(meta)==EXPECTED_META and sha(zdata)==EXPECTED_RESULTS,"2024 official source checksum changed")
    with zipfile.ZipFile(io.BytesIO(zdata)) as archive:
        official=list(csv.DictReader(io.StringIO(archive.read("detailed_main.csv").decode("utf-8"))))
    check(len(official)==400,"Incomplete Main Track result table")
    records={r["hash"]:r for r in official}
    rows=[]
    for line in meta.decode("utf-8").splitlines()[1:]:
        fields=line.split()
        if len(fields)<4:continue
        ident=fields[0];filename=fields[1];family=fields[2]
        check(ident in records,"Metadata result ID mismatch")
        verdict=records[ident]["vresult"]
        if verdict not in ("sat","unsat") or ident in ids:continue
        rows.append({"id":ident,"filename":filename,"family":family,
             "cohort":verdict.upper(),"official_label":verdict.upper(),
             "official_2024_CaDiCaL_s":records[ident]["CaDiCaL"]})
    check(len(rows)>=110,"Not enough published solved 2024 instances")
    # Deterministic family round robin within each label, hashed family order;
    # no previously seen solver or V13.7 timing contributes to selection.
    queues={}
    for label in ("SAT","UNSAT"):
        fam=collections.defaultdict(list)
        for r in rows:
            if r["official_label"]==label:
                fam[r["family"]].append(r)
        families=sorted(fam,key=lambda k:sha((SALT+"/family/"+label+"/"+k).encode()))
        for family in families:
            fam[family].sort(key=lambda r:sha((SALT+"/instance/"+r["id"]).encode()))
        queues[label]=(families,fam)
    print("V1313_2024_SOURCE_CLASS_COUNTS",dict(collections.Counter(r["cohort"] for r in rows)),
          "families",len({r["family"] for r in rows}),flush=True)
    selected=[];attempts=[];seen=shas.copy()
    accepted=collections.Counter()
    depth=0
    while len(selected)<TARGET and len(attempts)<MAX_ATTEMPTS:
        progressed=False
        for label in ("SAT","UNSAT"):
            if len(selected)>=TARGET or len(attempts)>=MAX_ATTEMPTS:break
            if accepted[label]>=PER_LABEL:continue
            families,fam=queues[label]
            # Iterating first by family prevents all accepted instances sharing one known family.
            for family in families:
                if len(selected)>=TARGET or len(attempts)>=MAX_ATTEMPTS or accepted[label]>=PER_LABEL:break
                if len(fam[family])<=depth:continue
                r=fam[family][depth]
                progressed=True
                try:
                    got=source.download_and_features(r["id"])
                    check(got["sha256"] not in seen,"Previously measured SHA duplicate")
                    got.update(cohort=r["cohort"],family=family,official_label=label,
                               official_year=2024,official_filename=r["filename"],
                               published_2024_CaDiCaL_s=r["official_2024_CaDiCaL_s"])
                    seen.add(got["sha256"]);selected.append(got);accepted[label]+=1
                    attempts.append({"id":r["id"],"family":family,"label":label,"accepted":True})
                    print("V1313_2024_ACCEPT",len(selected),label,family,
                          r["id"],got["cnf_bytes"],got["sha256"],flush=True)
                except Exception as e:
                    attempts.append({"id":r["id"],"family":family,"label":label,
                                     "accepted":False,"reason":str(e)[:160]})
                    print("V1313_2024_SKIP",label,family,r["id"],str(e)[:130],flush=True)
            if accepted[label]>=PER_LABEL:continue
        if not progressed:break
        depth+=1
    if len(selected)!=TARGET or accepted["SAT"]!=PER_LABEL or accepted["UNSAT"]!=PER_LABEL:
        save(a.out+".diagnostic.json",{
          "status":"incomplete_2024_sample","chosen":len(selected),"labels":dict(accepted),
          "attempts":len(attempts),"rejected":attempts[-35:]
        })
        raise RuntimeError(f"2024 eligible external sample incomplete {len(selected)}/{TARGET}, "
                           f"SAT {accepted['SAT']}/15 UNSAT {accepted['UNSAT']}/15")
    check(len({x["id"] for x in selected})==TARGET,"Duplicate official ID")
    check(len({x["sha256"] for x in selected})==TARGET,"Duplicate CNF SHA")
    check(not set(x["id"] for x in selected)&ids,"Prior ID leakage")
    check(not set(x["sha256"] for x in selected)&shas,"Prior SHA leakage")
    selected.sort(key=lambda x:sha((SALT+"/schedule/"+x["id"]).encode()))
    data={"protocol":PROTOCOL,"holdout_protocol":HOLDOUT_PROTOCOL,"cases":selected,"n":TARGET,"shards":10,"repetitions":1,
          "cap_seconds":None,"origin_year":2024,
          "official_source_commit":YEAR_COMMIT,
          "metadata_sha256":EXPECTED_META,"results_zip_sha256":EXPECTED_RESULTS,
          "unseen_excluded_ids":len(ids),"unseen_excluded_shas":len(shas),
          "historic_manifest_digests":history,
          "selection_rule":"Deterministic hashed family round-robin: 15 SAT + 15 UNSAT; source labels only, independent of DRNAS or Kissat measurements.",
          "rejection_count":sum(not r["accepted"] for r in attempts),
          "attempt_count":len(attempts),"excluded_prior_shas":True,
          "families":dict(collections.Counter(x["family"] for x in selected)),
          "warnings":[
           "True external public SAT Competition 2024 Main Track CNFs; SAT/UNSAT official result labels.",
           "All 30 cases SHA-frozen before new trials; exact V13.15 gate and GF2 code used, only wall limit changed to 20 s.",
           "SHA-disjoint from listed V13.1, V13.2, V13.8, V13.9, V13.13, V13.16, mini and V100 manifests.",
           "Selection using labels and metadata family but no experiment solver runtimes; family selection is intentionally stratified.",
           "15 SAT and 15 UNSAT from the published 2024 result table.",
           "Size-filtered 30 formulas, unrepresentative of entire 2024 Main Track.",
           "Validation uses existing V13.15 policies with 20s cutoff for longer solving benchmarks; not an official competition.",
           "Published SAT/UNSAT labels only used to stratify selection and check final verdicts, not algorithm routing."
          ]}
    save(a.out,data)
    print("V1317_NEW30_FREEZE_PASS",TARGET,
          json.dumps(data["families"],sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser()
    for a in ("v131","mini","v100","v132","v138","v139","v1313","v1316","out"):p.add_argument("--"+a,required=True)
    freeze(p.parse_args())
if __name__=="__main__":main()
