#!/usr/bin/env python3
"""Strict application subset. Exclude generic cryptography (including crypto-WFF
mixtures) by provenance BEFORE viewing solver outcomes. Keep explicitly named
ASCON/SIMON cryptographic applications and hardware/planning/scheduling/bitvector.
Reuse unchanged measured code and frozen native binaries; never retune a gate.
"""
import argparse
import json
import gate_real36 as B

B.ALLOWED.discard('cryptography')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=('freeze','shard','finish','selftest'))
    p.add_argument('--shard',type=int,default=0)
    a=p.parse_args()
    if a.stage=='freeze':
        B.freeze()
        protocol=json.loads((B.ROOT/'protocol.json').read_text())
        protocol['provenance_filter']='Exclude generic cryptography, including combined-crypto1-wff; only explicit application families retained'
        protocol['allowed_metadata_families']=sorted(B.ALLOWED)
        protocol['excluded_before_performance_inspection']=['cryptography']
        protocol['native_binary_source_run']=43386621130
        B.dump(B.ROOT/'protocol.json',protocol)
        B.emit('REAL36_STRICT_FROZEN',protocol)
    elif a.stage=='shard':
        if not 0<=a.shard<B.SHARDS: p.error('Invalid shard')
        B.shard(a.shard)
    elif a.stage=='finish': B.finish()
    else: B.selftest()

if __name__=='__main__': main()
