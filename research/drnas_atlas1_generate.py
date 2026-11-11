#!/usr/bin/env python3
"""DRNAS ATLAS1: build-time exhaustive NPN index and exact small-CNF recipes.
Every Boolean function of 2, 3, and 4 variables is assigned one NPN orbit.
For each representative AND its complement, produce an equivalent implicate
cover. The runtime maps recipes back using a witnessed input permutation,
input polarity, and separately indexed output polarity. Never infer a CNF
rewrite from class ID alone.
"""
import argparse,itertools,pathlib

def permuted(table,k,permutation,flip,invert):
    out=0
    for assignment in range(1<<k):
        original=0
        for j in range(k):
            bit=((assignment>>permutation[j])&1)^((flip>>j)&1)
            original|=bit<<j
        value=((table>>original)&1)^invert
        out|=value<<assignment
    return out

def recipe(table,k):
    assignments=1<<k
    full=(1<<assignments)-1
    if table==0:return [0]  # contradiction = empty clause
    if table==full:return [] # tautology = empty conjunction
    false=full^table
    choices=[]
    for code in range(1,3**k):
        v=code;digits=[]
        for j in range(k):digits.append(v%3);v//=3
        falsifies=0
        for assignment in range(assignments):
            sat=False
            for j,digit in enumerate(digits):
                if digit and ((assignment>>j)&1)==(1 if digit==1 else 0):
                    sat=True;break
            if not sat:falsifies|=1<<assignment
        if falsifies and not (falsifies&table):
            choices.append((code,falsifies,sum(d!=0 for d in digits)))
    answer=[];uncovered=false
    while uncovered:
        best=None;best_key=None
        for code,cover,width in choices:
            gain=(cover&uncovered).bit_count()
            if gain==0:continue
            # Deterministic greedy set cover; runtime additionally verifies truth.
            rank=(gain,-width,-code)
            if best is None or rank>best_key:best=(code,cover);best_key=rank
        if best is None:raise AssertionError("no full implicate cover")
        answer.append(best[0]);uncovered &= ~best[1]
    # Independent verification of the complete truth table.
    rebuilt=full
    for code in answer:
        v=code;digits=[]
        for j in range(k):digits.append(v%3);v//=3
        for assignment in range(assignments):
            if all(not d or ((assignment>>j)&1)!=(1 if d==1 else 0)
                   for j,d in enumerate(digits)):
                rebuilt &= ~(1<<assignment)
    assert rebuilt==table,(k,table,answer,rebuilt)
    return answer

def build(k):
    funcs=1<<(1<<k)
    perms=list(itertools.permutations(range(k)))
    cls=[-1]*funcs
    witness=[-1]*funcs
    representatives=[]
    for table in range(funcs):
        if cls[table]>=0:continue
        classid=len(representatives)
        assert classid<256
        representatives.append(table)
        for pidx,p in enumerate(perms):
            for flip in range(1<<k):
                for out in (0,1):
                    target=permuted(table,k,p,flip,out)
                    if cls[target]<0:
                        cls[target]=classid
                        witness[target]=(pidx<<(k+1))|(flip<<1)|out
    expected={2:4,3:14,4:222}
    assert len(representatives)==expected[k],(k,len(representatives))
    assert min(cls)>=0 and min(witness)>=0
    packed=[c|(w<<8) for c,w in zip(cls,witness)]
    recipe_data=[];offset=[0]
    maxmask=(1<<(1<<k))-1
    for rep in representatives:
        for table in (rep,maxmask^rep):
            r=recipe(table,k)
            recipe_data.extend(r)
            offset.append(len(recipe_data))
    assert max(offset)<65536
    return dict(perms=perms,packed=packed,offset=offset,data=recipe_data,classes=len(representatives))

def emit_array(f,name,values,ctype,width=18):
    f.write(f"inline constexpr {ctype} {name}[{len(values)}] = {{\n")
    for i in range(0,len(values),width):
        f.write("  "+",".join(str(v) for v in values[i:i+width])+",\n")
    f.write("};\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="mre_atlas1/atlas1_table.hpp")
    args=ap.parse_args()
    target=pathlib.Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w",encoding="utf-8") as f:
        f.write("// DETERMINISTIC AUTO-GENERATED: research/drnas_atlas1_generate.py\n")
        f.write("#pragma once\n#include <cstdint>\nnamespace drnas_atlas1_data {\n")
        for k in (2,3,4):
            data=build(k)
            f.write(f"inline constexpr unsigned classes{k}={data['classes']};\n")
            f.write(f"inline constexpr std::uint8_t perm{k}[{len(data['perms'])}][{k}] = {{\n")
            for row in data["perms"]:f.write("  {"+",".join(map(str,row))+"},\n")
            f.write("};\n")
            emit_array(f,f"index{k}",data["packed"],"std::uint32_t")
            emit_array(f,f"offset{k}",data["offset"],"std::uint16_t")
            emit_array(f,f"recipes{k}",data["data"],"std::uint8_t")
            print(f"ATLAS1_GENERATED k={k} functions={len(data['packed'])} NPN_classes={data['classes']} stored_rewrites={data['classes']*2}")
        f.write("}\n")
    print(f"ATLAS1_TABLE_READY {target} bytes={target.stat().st_size}")
if __name__=="__main__":main()
