#!/usr/bin/env python3
"""R27: native, in-process *hypothesis*, deliberately frozen before fresh tests.

Only at the 4096th conflict: if 1-UIP mature-low-LBD antecedent share is low,
fast/slow glue ratio is >=1, and there were at least 8 restarts, set restartint
to 50. Otherwise abstain. No formula name, result, seed or family is inspected.
This threshold was motivated by the known R26 4-case diagnostic, *not* fitted
on R27 holdout. It is not a universal SAT law.
"""
from pathlib import Path
import argparse
import hashlib

MODE = "r27_cautious_late50"
UPSTREAM = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
RESTARTS_MIN = 8
GLUE_MIN = 1.0
MATURE_LOW_MAX = 0.15

def replace_once(s, a, b, desc):
    count = s.count(a)
    if count != 1:
        raise RuntimeError(f"R27_EXACT_ANCHOR {desc} expected=1 actual={count}")
    return s.replace(a, b, 1)

def patch(root):
    search = root / "src" / "search.c"
    deduce = root / "src" / "deduce.c"
    s = search.read_text()
    d = deduce.read_text()
    d = replace_once(d,
        "static inline void r24_reason (const clause *c) {",
        """// R27: read-only snapshot; never touch Kissat's learned-clause state.
void drnas_r27_get_reason_statistics (uint64_t *out) {
  out[0] = r24_calls;
  out[1] = r24_revisits;
  out[2] = r24_crosslevel;
  out[3] = r24_long;
  out[4] = r24_reason_reused;
  out[5] = drnas_r21_counts[11]; // mature low-LBD antecedent reasons
  out[6] = drnas_r21_counts[6];  // all antecedent reasons
}
static inline void r24_reason (const clause *c) {""", "deduce_getter")
    # R27b: the R21 sidecar registry is telemetry, not solver correctness
    # state. An exhausted research table must never kill a valid SAT solve.
    d = replace_once(d,
        '#define R21_BIRTH_CAPACITY (1u<<18)',
        '#define R21_BIRTH_CAPACITY (1u<<20)',
        "registry_capacity")
    d = replace_once(d,
        'static drnas_r21_birth_entry drnas_r21_births[R21_BIRTH_CAPACITY];',
        'static drnas_r21_birth_entry drnas_r21_births[R21_BIRTH_CAPACITY];\n'
        'static bool r27_birth_registry_saturated = false;',
        "registry_sentinel")
    d = replace_once(d,
        '  if (!c->redundant || c->size<=2)return;',
        '  if (!c->redundant || c->size<=2)return;\n'
        '  if (r27_birth_registry_saturated) { drnas_r21_counts[10]++; return; }',
        "registry_fast_fallback")
    full_line=next(line for line in d.splitlines() if 'R21_BIRTH_TABLE_FULL' in line)
    d = replace_once(d, full_line,
        '  r27_birth_registry_saturated = true; drnas_r21_counts[10]++; return;',
        "registry_bounded_overflow")
    s = replace_once(s, "int kissat_search (kissat *solver) {",
        "extern void drnas_r27_get_reason_statistics (uint64_t *out);\nint kissat_search (kissat *solver) {",
        "external_getter")
    s = replace_once(s, "  unsigned r11_at=0;",
        '  const bool r27_cautious=!strcmp(drnas_mode,"r27_cautious_late50");\n  unsigned r11_at=0;',
        "r27_mode")
    s = replace_once(s,
        '  const bool drnas_forced=!strcmp(drnas_mode,"switch2048") || r11_mode;',
        '  const bool drnas_forced=!strcmp(drnas_mode,"switch2048") || r11_mode || r27_cautious;',
        "set_forced")
    s = replace_once(s,
        '    if (drnas_forced) drnas_target=r11_mode ? r11_at : 2048;',
        '    if (drnas_forced) drnas_target=r27_cautious ? 4096 : (r11_mode ? r11_at : 2048);',
        "target_4096")
    anchor = '''        if (drnas_active && !res && !drnas_changed && drnas_target &&
            drnas_seen>=drnas_target) {'''
    block = '''        // R27 frozen 4096-conflict gate. The decision happens before the
        // existing native option switch, not after the solve.
        if (r27_cautious && !res && !drnas_changed && drnas_target &&
            drnas_seen>=4096) {
          uint64_t r27_reason[7]={0};
          drnas_r27_get_reason_statistics(r27_reason);
          const double mature_share=(double)r27_reason[5]/
              (1.0+(double)r27_reason[6]);
          const double glue_ratio=AVERAGE(fast_glue)/
              (AVERAGE(slow_glue)>1e-9?AVERAGE(slow_glue):1e-9);
          const uint64_t recent_restarts=
              solver->statistics.restarts-r6_base_restarts;
          const bool selected=
              mature_share<0.15 && glue_ratio>=1.0 && recent_restarts>=8;
          fprintf(stdout,
              "c R27_GATE conflict=%" PRIu64
              " mature_low=%" PRIu64 " antecedent=%" PRIu64
              " mature_share=%.12f glue=%.12f restarts=%" PRIu64
              " selected=%d\\n",
              drnas_seen,r27_reason[5],r27_reason[6],
              mature_share,glue_ratio,recent_restarts,(int)selected);
          fflush(stdout);
          if (!selected) drnas_target=0;
        }
'''
    s = replace_once(s, anchor, block + anchor, "r27_gate_before_switch")
    # R16's audited base patch already wraps the option in its r16_active
    # ternary; keep that original expression and add the R27 50 option only.
    s = replace_once(s,
        'r11_mode ? r11_interval : (r16_active ||',
        'r11_mode ? r11_interval : (r27_cautious || r16_active ||',
        "set_interval")
    if d.count("drnas_r27_get_reason_statistics") != 1:
        raise RuntimeError("R27_GETTER_COUNT")
    if s.count("c R27_GATE") != 1:
        raise RuntimeError("R27_GATE_COUNT")
    deduce.write_text(d)
    search.write_text(s)
    print("R27_NATIVE_PATCH_OK", UPSTREAM,
          "search_sha256", hashlib.sha256(s.encode()).hexdigest(),
          "deduce_sha256", hashlib.sha256(d.encode()).hexdigest(), flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    patch(a.kissat_root)
