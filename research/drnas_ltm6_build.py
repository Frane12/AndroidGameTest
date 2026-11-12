#!/usr/bin/env python3
"""LTM6 experiment: source-certified structural gate for EXISTING live native GF(2).

No guessed clauses or signature-based deductions. LTM6_LIVE shares exactly the
A36_75 CDCL policy, but enables the existing proof-backed native trail XOR
propagator when certified XOR rows have a useful graph cancellation. Gates are
computed before solving; propagations and reason clauses occur inside native
CDCL and are independently logged. Never alters BASE/LTM5.
"""
from pathlib import Path

path = Path("mre_atlas23/native.cpp")
src = path.read_text()

def one(before, after):
    global src
    assert src.count(before) == 1, ("LTM6 patch drift", before[:120], src.count(before))
    src = src.replace(before, after, 1)

anchor = 'mode=="A36_75"'
assert src.count(anchor) >= 3, ("A36_75 dispatch missing", src.count(anchor))
src = src.replace(anchor, anchor + '||mode=="LTM6_LIVE"')

screen = r"""
// LTM6's gate is a structural *observation*, not a proof. Both endpoints of
// every candidate relation are extracted from complete source-CNF XOR clauses.
namespace ltm6 {
struct Screen {
    size_t rows=0, overlaps=0, reductive_pairs=0, short_pairs=0;
    bool enabled=false;
};
static Screen inspect(const drnas::CNF& src) {
    Screen s;
    const auto certified = drnas::extract_source_xors(src);
    s.rows=certified.size();
    // Never pay for quadratic analysis on large or unselective instances.
    if(s.rows < 2 || s.rows > 128 || src.vars > 2000) return s;
    for(size_t i=0;i<certified.size();++i) {
        const auto& a=certified[i].vars;
        for(size_t j=i+1;j<certified.size();++j) {
            const auto& b=certified[j].vars;
            size_t overlap=0;
            for(int v:a) if(std::binary_search(b.begin(),b.end(),v)) ++overlap;
            if(!overlap) continue;
            ++s.overlaps;
            const size_t width=a.size()+b.size()-2*overlap;
            if(width < std::max(a.size(),b.size())) {
                ++s.reductive_pairs;
                if(width <= 3) ++s.short_pairs;
            }
        }
    }
    s.enabled = s.short_pairs > 0;
    return s;
}
} // namespace ltm6
"""
one('int main(int argc,char**argv){', screen + '\nint main(int argc,char**argv){')
one('  const drnas::CNF orig=drnas::read_dimacs(argv[1]);',
    '  const drnas::CNF orig=drnas::read_dimacs(argv[1]);\n'
    '  const auto ltm6_screen = mode=="LTM6_LIVE"?ltm6::inspect(orig):ltm6::Screen{};')
one('   solver.add_cnf(work);',
    '   solver.add_cnf(work);\n'
    '   if(mode=="LTM6_LIVE" && ltm6_screen.enabled)\n'
    '     solver.enable_gf2_from_original(orig);')
one('  std::cout<<std::fixed<<std::setprecision(8)',
    '''  if(mode=="LTM6_LIVE")std::cout
           <<"LTM6_GRAPH source_rows="<<ltm6_screen.rows
           <<" overlaps="<<ltm6_screen.overlaps
           <<" reductive_pairs="<<ltm6_screen.reductive_pairs
           <<" short_pairs="<<ltm6_screen.short_pairs
           <<" enabled="<<int(ltm6_screen.enabled)<<"\\n";
  std::cout<<std::fixed<<std::setprecision(8)''')
one('           <<" SAT_original_verified="<<int(status==10)',
    '''           <<" ltm6_gate="<<int(ltm6_screen.enabled)
           <<" ltm6_source_rows="<<ltm6_screen.rows
           <<" ltm6_short_pairs="<<ltm6_screen.short_pairs
           <<" ltm6_live_checks="<<st.xor_checks
           <<" ltm6_live_implications="<<st.xor_implications
           <<" ltm6_live_conflicts="<<st.xor_conflicts
           <<" ltm6_derived_implications="<<st.xor_derived_implications
           <<" ltm6_reason_clauses="<<st.xor_reasons
           <<" ltm6_budget_off="<<st.xor_budget_off
           <<" SAT_original_verified="<<int(status==10)''')
assert 'if(mode=="A36_75"||mode=="LTM6_LIVE")solver.atlas36_enable_quota(75);' in src
assert src.count('mode=="LTM6_LIVE"') >= 5
path.write_text(src)
print("LTM6_BUILD_PATCH_PASS certified_graph_gate=true native_live_GF2=true baseline_unchanged=true")
