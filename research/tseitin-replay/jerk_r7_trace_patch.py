#!/usr/bin/env python3
"""R7 passive timed checkpoint extension on the pinned R6 Kissat patch.
Does NOT modify frozen DRNAS V15.3.1; never changes branching or restart heuristics.
"""
import argparse,hashlib
from pathlib import Path
MARKS=[32,64,96,128,160,192,224,256,320,384,448,512,640,768,896,1024,1280,1536,1792,2048,2560,3072,4096,5120,6144,8192,12288,16384]
def once(s,old,new):
 n=s.count(old)
 if n!=1:raise RuntimeError(f"Expected exactly one pinned R6 anchor, found {n}: {old[:90]}")
 return s.replace(old,new,1)
def main():
 p=argparse.ArgumentParser();p.add_argument('--kissat-root',type=Path,required=True);a=p.parse_args()
 path=a.kissat_root/'src/search.c';s=path.read_text()
 assert "c R6_TRACE" in s and 'r6_checkpoint_index<7' in s, 'R6 patch must be applied first'
 s='#include <time.h>\n'+s
 s=once(s,'r6_checkpoint_index<7',f'r6_checkpoint_index<{len(MARKS)}')
 s=once(s,'static const uint64_t r6_marks[7]={100,250,500,1000,2000,4096,8192};',
        f'static const uint64_t r6_marks[{len(MARKS)}]={{'+','.join(map(str,MARKS))+'};')
 s=once(s,'            printf("c R6_TRACE conflict=%" PRIu64',
        '''            struct timespec drnas_jerk_clock;
            if (clock_gettime(CLOCK_MONOTONIC,&drnas_jerk_clock))
              abort();
            const uint64_t drnas_jerk_wall_ns =
              (uint64_t)drnas_jerk_clock.tv_sec*1000000000ULL +
              (uint64_t)drnas_jerk_clock.tv_nsec;
            printf("c R6_TRACE conflict=%" PRIu64 " wall_ns=%" PRIu64''')
 s=once(s,'                drnas_seen, solver->statistics.restarts-r6_base_restarts,',
        '                drnas_seen, drnas_jerk_wall_ns, solver->statistics.restarts-r6_base_restarts,')
 path.write_text(s)
 print('R7_TIMED_TRACE_APPLIED',hashlib.sha256(s.encode()).hexdigest(),len(MARKS))
if __name__=='__main__':main()
