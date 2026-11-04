#!/usr/bin/env python3
"""R87: frozen, native, feedback-controlled XOR scan cadence, DEVELOPMENT test.

Apply AFTER the exact R32b/R32n/R32s/R32u/R84/R85/R86 patches to the
previously pinned Kissat tree. Only the scheduling interval is changed.
The source-certified XOR inference, clauses, CDCL 1-UIP, and V15.3.1 frozen
solver remain unchanged. No SAT label, instance name or wall time is used.
"""
import argparse
from pathlib import Path

DECL=r'''
/* R87 fixed utility-feedback scheduling (frozen before the replay).
 * 128 actual scans per decision window; start at 16. After a window,
 * prefer 4 if a source-certified native reason was used in first UIP,
 * 16 if only a sound reason was attached, 64 on the first idle window,
 * and 256 after two or more idle windows. Never changes SAT semantics.
 */
static int r87_adapt=0;
static unsigned r87_last_window=0, r87_idle_windows=0, r87_switches=0;
static unsigned r87_last_attached=0;
static uint64_t r87_last_uip=0;
static void r87_tick(void) {
  if(!r87_adapt || !r32u_nrows || r32u_probed<128 ||
     r32u_probed-r87_last_window<128) return;
  const uint64_t new_uip=r85_first_uip_uses-r87_last_uip;
  const unsigned new_attach=r32u_added-r87_last_attached;
  const unsigned old=r84_interval;
  if(new_uip) {r84_interval=4;r87_idle_windows=0;}
  else if(new_attach) {r84_interval=16;r87_idle_windows=0;}
  else {
    if(r87_idle_windows<2)r87_idle_windows++;
    r84_interval=r87_idle_windows>=2 ? 256 : 64;
  }
  r87_last_window=r32u_probed;
  r87_last_uip=r85_first_uip_uses;
  r87_last_attached=r32u_added;
  if(old!=r84_interval) {
    r87_switches++;
    if(r87_switches<=16 || !(r87_switches%128)) {
      printf("c R87_SWITCH scans=%u from=%u to=%u attached_delta=%u"
             " first_uip_delta=%" PRIu64 " idle_windows=%u\n",
        r32u_probed,old,(unsigned)r84_interval,new_attach,
        new_uip,r87_idle_windows);
      fflush(stdout);
    }
  }
}
static void r87_finish(void) {
  if(!r87_adapt)return;
  printf("c R87_FINAL scans=%u interval=%u switches=%u"
         " attached=%u first_uip=%" PRIu64 "\n",
      r32u_probed,(unsigned)r84_interval,r87_switches,
      r32u_added,r85_first_uip_uses);
  fflush(stdout);
}
'''

def replace_once(text,old,new,tag):
    n=text.count(old)
    if n!=1:
        raise RuntimeError(f"R87_FAIL_CLOSED patch anchor {tag}: expected=1 actual={n}")
    return text.replace(old,new,1)

def patch(path):
    s=path.read_text()
    s=replace_once(s,
        "static void r32u_initialize(kissat *solver) {",
        DECL+"\nstatic void r32u_initialize(kissat *solver) {",
        "declaration_before_initialization")
    s=replace_once(s,
        "  r85_last_ms=-1;\n",
        '  r85_last_ms=-1;\n'
        '  const char *r87_env=getenv("R87_ADAPT");\n'
        '  r87_adapt=r87_env && !strcmp(r87_env,"1");\n'
        '  r87_last_window=r87_idle_windows=r87_switches=0;\n'
        '  r87_last_attached=0;r87_last_uip=0;\n'
        '  if(r87_adapt)r84_interval=16;\n'
        '  printf("c R87_MODE dynamic=%d initial_interval=%u window_scans=128\\n",\n'
        '      r87_adapt,(unsigned)r84_interval);\n'
        '  fflush(stdout);\n',
        "initialize_adaptive_state")
    s=replace_once(s,
        'static void r32u_scan(kissat *solver) {\n  r85_emit(solver,0);',
        'static void r32u_scan(kissat *solver) {\n'
        '  r87_tick();\n  r85_emit(solver,0);',
        "switch_before_next_scan")
    s=replace_once(s,
        'static void r32u_final(kissat *solver) {\n  r85_emit(solver,1);',
        'static void r32u_final(kissat *solver) {\n'
        '  r87_finish();\n  r85_emit(solver,1);',
        "final_progress")
    path.write_text(s)
    print("R87_FROZEN_FEEDBACK_CADENCE_PATCH_PASS",flush=True)

def selftest():
    assert "first_uip_uses-r87_last_uip" in DECL
    assert "r32u_probed-r87_last_window<128" in DECL
    assert "r87_idle_windows>=2 ? 256 : 64" in DECL
    assert "r84_interval=4" in DECL
    print("R87_FIXED_PREDECLARED_FEEDBACK_RULE_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    elif a.kissat_root:patch(a.kissat_root/"src"/"search.c")
    else:p.error("specify --kissat-root or --selftest")
