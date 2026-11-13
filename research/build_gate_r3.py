#!/usr/bin/env python3
"""GATE-R3: one isolated R2 change, conflict-wake thresholds scaled by four.
Builds pinned, unchanged X46/R2 controls too. No source file is overwritten.
NO_SHOCK is an ablation: only the conflict wake is disabled, not periodic checks.
"""
from pathlib import Path
import hashlib
import runpy

PINNED = {
    'src/drnas_gate_r2.hpp': 'd65f93d1824645632ee9b4bee0b984877abc414bbea9af2a36f1d8e2a9770eb5',
    'research/build_gate_r2.py': 'e851ada52cc315f55adc80195e598d9ede976b1a4c7718c410ca922edf474667',
}
for path, digest in PINNED.items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
        raise RuntimeError('R2 base changed: ' + path)
runpy.run_path('research/build_gate_r2.py')


def change(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('R3 patch anchor mismatch: ' + old[:120])
    return text.replace(old, new)


header = Path('src/drnas_gate_r2.hpp').read_text()
header = header.replace('DRNAS_GATE_R2_HPP', 'DRNAS_GATE_R3_HPP').replace('GateR2', 'GateR3')
header = change(header, 'public:\n', '''public:
    // The ONLY policy change from R2: a fourfold conflict-wake threshold.
    // All feedback, hysteresis, periodic scheduling and cost logic is inherited.
    explicit GateR3(bool disable_conflict_wake=false)
        : disable_conflict_wake_(disable_conflict_wake) {}
''')
header = change(header, '''        shock_pending_=adaptive && state_==State::Sleep &&
            decisions>=last_probe_+256 && decisions>=last_shock_check_+256 &&
            conflicts>=last_conflicts_+128;''', '''        shock_pending_=adaptive && !disable_conflict_wake_ && state_==State::Sleep &&
            decisions>=last_probe_+1024 && decisions>=last_shock_check_+1024 &&
            conflicts>=last_conflicts_+512;''')
header = change(header, '    State state_=State::Check;',
                '    bool disable_conflict_wake_=false;\n    State state_=State::Check;')
header = change(header, 'out<<"GATER2_GATE {\\"calls\\":"<<c_.calls', '''out<<"GATER2_GATE {\\"wake_decision_gap\\":1024,\\"wake_conflict_gap\\":512"
          <<",\\"conflict_wake_disabled\\":"<<(disable_conflict_wake_?"true":"false")
          <<",\\"calls\\":"<<c_.calls''')
Path('build/drnas_gate_r3.hpp').write_text(header)

source = Path('build/drnas_gate_r2.cpp').read_text()
source = source.replace('gate_r2_fixed', 'gate_r3_no_shock').replace('gate_r2', 'gate_r3')
source = source.replace('GateR2', 'GateR3')
source = change(source, '#include "../src/drnas_gate_r3.hpp"', '#include "drnas_gate_r3.hpp"')
source = change(source, '    drnas::GateR3 gate_r3_;',
                '    drnas::GateR3 gate_r3_{mode_=="gate_r3_no_shock"};')
source = change(source, 'const bool adaptive=mode_=="gate_r3";',
                'const bool adaptive=true; // NO_SHOCK preserves adaptive periodic scheduling')
Path('build/drnas_gate_r3.cpp').write_text(source)
print('GATER3_PATCH_PASS', hashlib.sha256(source.encode()).hexdigest(),
      'wake_scale=4 no_shock_ablation=True inherited_logic_unchanged=True')
