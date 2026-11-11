#!/usr/bin/env python3
"""Compile persisted, exhaustively verified ATLAS8 JSONL into a native C++ rule table.
Fails closed when a catalog row has been modified or its local proof fails.
"""
import hashlib,json,pathlib,sys
def holds(clauses,mask,k):
    return all(any(bool(mask>>(abs(l)-1)&1)==(l>0) for l in c) for c in clauses)
def fmt(clauses):
    return "{"+",".join("{"+",".join(str(l) for l in c)+"}" for c in clauses)+"}"
def main():
    src=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "research/atlas8_reduction_table.jsonl")
    dest=pathlib.Path(sys.argv[2] if len(sys.argv)>2 else "mre_atlas9/atlas8_rules.hpp")
    raw=src.read_bytes()
    data=[json.loads(line) for line in raw.splitlines() if line.strip()]
    assert len(data)==len({x["id"] for x in data}) and data
    for r in data:
        k=r["vars"];old=r["original"];new=r["reduced"]
        assert 2<=k<=4
        assert hashlib.sha256(json.dumps([k,old],sort_keys=True).encode()).hexdigest()==r["id"],r["id"]
        assert all(1<=abs(l)<=k for c in old+new for l in c)
        assert all(holds(old,t,k)==holds(new,t,k) for t in range(1<<k)),r["id"]
        assert sum(len(c) for c in old)>sum(len(c) for c in new),r["id"]
        assert r["saved_literals"]==sum(map(len,old))-sum(map(len,new))
    rules=",\n".join("{"+fmt(r["original"])+","+fmt(r["reduced"])+"}" for r in data)
    header="""// Generated from persistent ATLAS8 proof-checked original CNF catalog.
#pragma once
#include <vector>
namespace atlas9_data {
struct Rule { std::vector<std::vector<int>> original, reduced; };
inline std::vector<Rule> load() {
return std::vector<Rule>{
""" + rules + """
};
}
inline constexpr int kRuleCount=""" + str(len(data)) + """;
inline constexpr const char* kSourceSHA256=""" + json.dumps(hashlib.sha256(raw).hexdigest()) + """;
}
"""
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(header)
    print("ATLAS9_CATALOG_EXPORT "+json.dumps({"rules":len(data),"input_sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(header)}),flush=True)
if __name__=="__main__":main()
