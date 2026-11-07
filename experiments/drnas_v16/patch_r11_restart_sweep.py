#!/usr/bin/env python3
"""R11 frozen in-process timing/interval sweep on exactly the R7 instrumented Kissat.
The only changed solver action is the same restartint option as in R7.
No learned classifier, no edits to V15.3.1.
"""
from pathlib import Path
import argparse, hashlib
from patch_r6_trace import patch as patch_r6

PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
MARKS=(32,64,96,128,192,256,384,512,768,1024,1536,2048,3072,4096,6144,8192)
VALID={(512,25),(1024,25),(2048,25),(4096,25),(2048,50)}

def once(text, old, new):
    found=text.count(old)
    if found!=1:
        raise ValueError(f"R11 pinned R6 patch anchor invalid: {old[:75]} found={found}")
    return text.replace(old,new,1)

def patch(source):
    s=patch_r6(source)
    s=once(s,
       '  const bool drnas_forced=!strcmp(drnas_mode,"switch2048");',
       """  unsigned r11_at=0;
  int r11_interval=25;
  char r11_extra=0;
  const bool r11_mode=sscanf(drnas_mode, "r11_%u_%d%c",
                            &r11_at, &r11_interval, &r11_extra)==2;
  if (r11_mode &&
      !((r11_at==512 && r11_interval==25) ||
        (r11_at==1024 && r11_interval==25) ||
        (r11_at==2048 && (r11_interval==25 || r11_interval==50)) ||
        (r11_at==4096 && r11_interval==25))) {
    fprintf(stderr,"R11_INVALID_MODE\\n");
    exit(79);
  }
  const bool drnas_forced=!strcmp(drnas_mode,"switch2048") || r11_mode;""")
    s=once(s,
       '    if (drnas_forced) drnas_target=2048;',
       '    if (drnas_forced) drnas_target=r11_mode ? r11_at : 2048;')
    s=once(s,
       '          kissat_set_option(solver,"restartint",25);',
       '          kissat_set_option(solver,"restartint",r11_mode ? r11_interval : 25);')
    s=once(s,'r6_checkpoint_index<7',f'r6_checkpoint_index<{len(MARKS)}')
    s=once(s,
       'static const uint64_t r6_marks[7]={100,250,500,1000,2000,4096,8192};',
       'static const uint64_t r6_marks['+str(len(MARKS))+']={'+','.join(map(str,MARKS))+'};')
    if s.count("c R6_TRACE")!=1 or s.count("DRNAS_V177_SWITCH")!=1:
        raise ValueError("Telemetry or intervention marker missing")
    return s

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",required=True,type=Path)
    args=p.parse_args()
    f=args.kissat_root/"src"/"search.c"
    result=patch(f.read_text())
    f.write_text(result)
    print("R11_PINNED_TIMING_PATCH_OK",PIN,
          hashlib.sha256(result.encode()).hexdigest(),len(MARKS),flush=True)
if __name__=="__main__":
    main()
