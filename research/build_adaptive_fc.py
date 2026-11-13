#!/usr/bin/env python3
"""Generate a first-real-conflict gate from the immutable X3 source.
Only policy change: suppress both probing and 2-SAT calls in x3_fc until the
first actual CDCL conflict. Probe conflicts never open the gate. Existing
post-conflict schedules, scoring, restarts and deletion remain unchanged.
The generated x3 control has the identical lightweight diagnostic counters.
"""
from pathlib import Path
import hashlib
import json

SOURCE_BLOB = '4320c64e63d0b12290c3a83a6ebd54c027380f7d'

def generate():
    raw = Path('src/drnas_x3.cpp').read_bytes()
    if hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest() != SOURCE_BLOB:
        raise RuntimeError('Immutable X3 source checksum changed')
    text = raw.decode()
    def patch(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise RuntimeError('Ambiguous source anchor: ' + old[:90])
        text = text.replace(old, new)
    patch('use_backdoor_(mode_ == "gate" || mode_ == "x3"),',
          'use_backdoor_(mode_ == "gate" || mode_ == "x3" || mode_ == "x3_fc"),')
    patch('use_depth_(mode_ == "x3"),',
          'use_depth_(mode_ == "x3" || mode_ == "x3_fc"),')
    patch('    Backdoor tryTwoSat() {\n',
          '    Backdoor tryTwoSat() {\n'
          '        if (mode_ == "x3_fc" && stats_.conflicts == 0) return Backdoor::SKIP;\n')
    patch('        if (!use_depth_ || (stats_.decisions%32)!=0 ||',
          '        if (!use_depth_ || (mode_ == "x3_fc" && stats_.conflicts == 0) ||\n'
          '            (stats_.decisions%32)!=0 ||')
    patch('(mode!="core" && mode!="gate" && mode!="x3")',
          '(mode!="core" && mode!="gate" && mode!="x3" && mode!="x3_fc")')
    patch('[--mode core|gate|x3]', '[--mode core|gate|x3|x3_fc]')
    patch('    int64_t controller_cooldowns = 0, controller_gained_long = 0;\n',
          '    int64_t controller_cooldowns = 0, controller_gained_long = 0;\n'
          '    int64_t fc_first_conflict_decision = -1, fc_prefix_decisions = 0;\n'
          '    int64_t fc_first_probe_conflicts = -1, fc_probes_before_conflict = 0;\n'
          '    int64_t fc_first_probe_decision = -1;\n'
          '    int64_t fc_first_backdoor_conflicts = -1;\n'
          '    int fc_first_literal = 0;\n'
          '    uint64_t fc_prefix_hash = 14695981039346656037ULL;\n')
    patch('                ++stats_.conflicts;\n',
          '                if (stats_.conflicts == 0)\n'
          '                    stats_.fc_first_conflict_decision = stats_.decisions;\n'
          '                ++stats_.conflicts;\n')
    patch('            ++stats_.decisions;\n            newDecisionLevel();',
          '            if (stats_.decisions == 0) stats_.fc_first_literal = phase_[v]*(v+1);\n'
          '            if (stats_.conflicts == 0) {\n'
          '                ++stats_.fc_prefix_decisions;\n'
          '                const uint64_t code = static_cast<uint64_t>(v+1)*2ULL + (phase_[v]<0?1ULL:0ULL);\n'
          '                stats_.fc_prefix_hash = (stats_.fc_prefix_hash ^ code)*1099511628211ULL;\n'
          '            }\n'
          '            ++stats_.decisions;\n            newDecisionLevel();')
    patch('        ++stats_.backdoor_checks;\n',
          '        if (stats_.fc_first_backdoor_conflicts < 0)\n'
          '            stats_.fc_first_backdoor_conflicts = stats_.conflicts;\n'
          '        ++stats_.backdoor_checks;\n')
    patch('    Probe probe(int lit) {\n',
          '    Probe probe(int lit) {\n'
          '        if (stats_.fc_first_probe_conflicts < 0) {\n'
          '            stats_.fc_first_probe_conflicts = stats_.conflicts;\n'
          '            stats_.fc_first_probe_decision = stats_.decisions;\n'
          '        }\n'
          '        if (stats_.conflicts == 0) ++stats_.fc_probes_before_conflict;\n')
    marker = next(line for line in text.splitlines() if 'probe_seconds' in line and 'solver->probeSeconds()' in line)
    keys = ('fc_first_conflict_decision','fc_prefix_decisions','fc_prefix_hash',
            'fc_first_literal','fc_first_probe_conflicts','fc_first_probe_decision',
            'fc_probes_before_conflict','fc_first_backdoor_conflicts')
    extra = ['                 <<'+json.dumps(','+json.dumps(key)+':')+'<<s.'+key for key in keys]
    patch(marker, '\n'.join(extra)+'\n'+marker)
    path = Path('build/drnas_adaptive_fc.cpp')
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    proof = {'source_git_blob':SOURCE_BLOB, 'generated_sha256':hashlib.sha256(text.encode()).hexdigest(),
             'policy_change':'x3_fc suppresses depth probes and 2-SAT calls only while real CDCL conflict count is zero',
             'post_conflict_policy_unchanged':True,'diagnostic_counters_identical_in_x3_and_x3_fc':True}
    Path('build/adaptive_fc_source.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof

if __name__ == '__main__':
    print('ADAPTIVE_FC_BUILD '+json.dumps(generate(),sort_keys=True))
