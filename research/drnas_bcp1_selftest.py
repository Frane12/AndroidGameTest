#!/usr/bin/env python3
import subprocess
import drnas_r28_native_selftest as T
def main():
    for name in ('BLOCKER','CIRCULAR'):
        subprocess.run(['mre_bcp1/test_'+name],check=True,timeout=120)
        T.BIN='mre_bcp1/'+name;T.main()
    print('BCP1_SELFTEST_PASS both_variants=true UBSAN=true',flush=True)
if __name__=='__main__':main()
