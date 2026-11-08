// DRNAS MRE X: C3 dedup plus MRE11 source-certified structural reduction (C4 baseline).
// The comparator C2 binary is loaded unchanged: this file adds ONLY cpp_tail.
// No unsound inferred XORs, no proof computed from rewritten CNF.
// Standalone mode (-DMRE9_STANDALONE) permits exhaustive pure-CNF selftests.
// Native mode links against the SAME pinned CryptoMiniSat 5.11.15 shared library.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
#ifndef MRE9_STANDALONE
#include <cryptominisat5/cryptominisat.h>
#endif

using namespace std;
using Clock = chrono::steady_clock;
static constexpr unsigned MIN_MERGES=128, MIN_DROP=256;
static constexpr double MIN_FRACTION=0.08;
static constexpr size_t MAX_CLAUSES=85000;
static void need(bool x,const string& m){if(!x) throw runtime_error("MRE10_FAIL_CLOSED "+m);}
static double elapsed(Clock::time_point t){
    return chrono::duration<double>(Clock::now()-t).count();
}
struct CNF {
    unsigned vars=0;
    vector<vector<int>> clauses;
};
static CNF parse_dimacs(const string& filename){
    ifstream f(filename);
    need(bool(f),"cannot open CNF");
    CNF x;
    string tok;
    bool header=false;
    unsigned declared=0;
    vector<int> clause;
    while(f>>tok){
        if(tok=="c"){string tail;getline(f,tail);continue;}
        if(tok=="%")break;
        if(tok=="p"){
            need(!header && clause.empty(),"duplicate header");
            string type;
            need(bool(f>>type>>x.vars>>declared),"incomplete header");
            need(type=="cnf" && x.vars>0 && declared>0 &&
                 x.vars<=1000000 && declared<=5000000,"invalid DIMACS header");
            header=true;continue;
        }
        need(header,"literal outside header");
        int v=0;
        try{
            size_t p=0;
            v=stoi(tok,&p);
            need(p==tok.size(),"bad numeric token");
        }catch(const exception&){throw runtime_error("MRE10_FAIL_CLOSED invalid DIMACS literal");}
        if(v==0){x.clauses.push_back(std::move(clause));clause.clear();}
        else{
            need(v!=numeric_limits<int>::min() && abs(v)<=int(x.vars),
                 "out of-range literal");
            clause.push_back(v);
        }
    }
    need(header && clause.empty() && x.clauses.size()==declared,
         "DIMACS incomplete clause count");
    return x;
}
static uint64_t edgekey(unsigned a,unsigned b){
    return (uint64_t(a)<<32)|uint64_t(b);
}
struct DSU{
    vector<unsigned> parent;
    explicit DSU(unsigned n):parent(n+1){iota(parent.begin(),parent.end(),0);}
    unsigned root(unsigned v){
        while(parent[v]!=v){parent[v]=parent[parent[v]];v=parent[v];}
        return v;
    }
    void join(unsigned a,unsigned b){
        a=root(a);b=root(b);
        if(a!=b)parent[max(a,b)]=min(a,b);
    }
};
struct Gate {
    bool applied=false;
    unsigned pairs=0, eliminated=0, removed=0, taut_clauses=0, duplicate_clauses=0, duplicate_literals=0, duplicate_clauses_moved=0;
    double fraction=0, reduce_s=0;
    string reason="NATIVE_NO_TRANSFORM";
    vector<unsigned> representative;
    vector<vector<int>> reduced;
};
static Gate certified_gate(const CNF& original,const string& mode){
    auto start=Clock::now();
    const bool native=(mode=="cpp_native");
    const bool ren=(mode=="cpp_rename");
    const bool clean=(mode=="cpp_clean");
    const bool joint=(mode=="cpp_joint");
    const bool route=(mode=="cpp_route");
    const bool oldgate=(mode=="cpp_ref_6f");
    const bool dedup=(mode=="cpp_dedup");
    const bool taut=(mode=="cpp_taut");
    const bool local=(mode=="cpp_local");
    const bool tail=(mode=="cpp_tail");
    need(native||ren||clean||joint||route||oldgate||dedup||taut||local||tail,
         "unsupported C4 arm");
    Gate result;
    if(native){result.reason="ORIGINAL_NATIVE_R28_UNMODIFIED_REFERENCE";return result;}
    if(original.clauses.size()>MAX_CLAUSES){
        result.reason="ABSTAIN_LARGE_SOURCE_LIMIT";
        result.reduce_s=elapsed(start);return result;
    }
    // C4 intervention: retain EVERY original clause, including duplicates, but
    // move second and later exact-canonical duplicates to the very end.
    // Unique first-occurrence order is unchanged. This isolates clause-load
    // order from clause multiplicity; the multiset of original clauses is identical.
    if(tail){
        unordered_set<string> seen;
        seen.reserve(original.clauses.size()*2+1);
        vector<vector<int>> primary, duplicates;
        primary.reserve(original.clauses.size());
        for(const auto& clause:original.clauses){
            vector<int> sorted=clause;
            sort(sorted.begin(),sorted.end());
            sorted.erase(unique(sorted.begin(),sorted.end()),sorted.end());
            string key=sorted.empty()?string():
               string(reinterpret_cast<const char*>(sorted.data()),
                      sorted.size()*sizeof(int));
            if(seen.insert(key).second) primary.push_back(clause);
            else duplicates.push_back(clause);
        }
        result.duplicate_clauses_moved=unsigned(duplicates.size());
        if(!duplicates.empty()){
            primary.insert(primary.end(),duplicates.begin(),duplicates.end());
            need(primary.size()==original.clauses.size(),
                 "tail did not preserve original clause multiplicity");
            result.reduced=std::move(primary);
            result.representative.resize(original.vars+1);
            iota(result.representative.begin(),result.representative.end(),0);
            result.applied=true;
            result.reason="SOURCE_CNF_EXACT_CLAUSE_PERMUTATION";
        }else result.reason="NO_DUPLICATES_SOURCE_ABSTAIN";
        result.reduce_s=elapsed(start);
        return result;
    }
    unordered_map<uint64_t,uint8_t> directions;
    if(ren||joint||route||oldgate){
        directions.reserve(original.clauses.size()/3+1);
        for(const auto& clause:original.clauses){
            if(clause.size()!=2)continue;
            int p=clause[0],q=clause[1];
            if((p<0)==(q<0)||abs(p)==abs(q))continue;
            unsigned a=unsigned(min(abs(p),abs(q)));
            unsigned b=unsigned(max(abs(p),abs(q)));
            int l_a=(unsigned(abs(p))==a)?p:q;
            directions[edgekey(a,b)]|=((l_a<0)?1:2);
        }
        for(const auto& v:directions)if(v.second==3)result.pairs++;
    }
    DSU dsu(original.vars);
    if(ren||joint||route||oldgate)for(const auto& v:directions){
        if(v.second!=3)continue;
        unsigned a=unsigned(v.first>>32),b=unsigned(v.first&0xffffffffu);
        need(directions.at(edgekey(a,b))==3,"missing original two-way positive implication");
        dsu.join(a,b);
    }
    vector<unsigned> rep(original.vars+1);
    iota(rep.begin(),rep.end(),0);
    for(unsigned v=1;v<=original.vars;v++){
        rep[v]=dsu.root(v);
        result.eliminated+=(rep[v]!=v);
    }
    bool active_rename=(ren||joint);
    bool active_clean=(clean||joint);
    if(route){
        if(result.eliminated>=64){
            active_rename=true;active_clean=true;
            result.reason="ROUTE_DENSE_JOINT";
        }else if(result.eliminated>=2){
            active_rename=true;active_clean=false;
            result.reason="ROUTE_SPARSE_RENAME";
        }else{
            result.reason="ROUTE_NATIVE_ABSTAIN";
            result.reduce_s=elapsed(start);return result;
        }
    }
    if(oldgate){
        if(result.eliminated<MIN_MERGES){
            result.reason="MRE6F_ABSTAIN_INSUFFICIENT_EQ";
            result.reduce_s=elapsed(start);return result;
        }
        active_rename=true;active_clean=true;
    }
    if(ren && result.eliminated==0){
        result.reason="RENAME_ABSTAIN_NO_EQ";
        result.reduce_s=elapsed(start);return result;
    }
    const bool active_dedup=active_clean||dedup;
    const bool active_taut=active_clean||taut;
    const bool active_local=active_clean||local;
    unordered_set<string> seen;
    if(active_dedup)seen.reserve(original.clauses.size()*2+1);
    vector<vector<int>> rewritten;
    bool anyChanged=false;
    rewritten.reserve(original.clauses.size());
    for(const auto& clause:original.clauses){
        vector<int> mapped;mapped.reserve(clause.size());
        for(int literal:clause){
            unsigned v=active_rename?rep[unsigned(abs(literal))]:unsigned(abs(literal));
            mapped.push_back(literal<0?-int(v):int(v));
        }
        if(active_dedup||active_taut||active_local){
            vector<int> sorted=mapped;
            sort(sorted.begin(),sorted.end());
            sorted.erase(unique(sorted.begin(),sorted.end()),sorted.end());
            if(active_taut){
                bool contradictory=false;
                for(int lit:sorted)
                    if(binary_search(sorted.begin(),sorted.end(),-lit)){
                        contradictory=true;break;
                    }
                if(contradictory){
                    result.taut_clauses++;
                    anyChanged=true;
                    continue;
                }
            }
            if(active_dedup){
                // Canonical source-clause key; no inference beyond exact logical duplication.
                string key=sorted.empty()?string():
                    string(reinterpret_cast<const char*>(sorted.data()),
                           sorted.size()*sizeof(int));
                if(!seen.insert(key).second){
                    result.duplicate_clauses++;
                    anyChanged=true;
                    continue;
                }
            }
            if(active_local){
                unordered_set<int> local_seen;
                local_seen.reserve(mapped.size()*2+1);
                vector<int> stable;stable.reserve(mapped.size());
                for(int lit:mapped)
                    if(local_seen.insert(lit).second)stable.push_back(lit);
                result.duplicate_literals+=unsigned(mapped.size()-stable.size());
                anyChanged=anyChanged||(stable!=clause);
                rewritten.push_back(std::move(stable));
            }else{
                // The single-arm ablations preserve exact remaining clause contents.
                anyChanged=anyChanged||(mapped!=clause);
                rewritten.push_back(std::move(mapped));
            }
        }else{
            anyChanged=anyChanged||(mapped!=clause);
            rewritten.push_back(std::move(mapped));
        }
    }
    need(rewritten.size()<=original.clauses.size(),"rewrite added clauses");
    result.removed=unsigned(original.clauses.size()-rewritten.size());
    result.fraction=double(result.removed)/double(original.clauses.size());
    if(oldgate && !(result.eliminated>=MIN_MERGES &&
         result.removed>=MIN_DROP && result.fraction>=MIN_FRACTION)){
        result.reason="MRE6F_ABSTAIN_SMALL_ACTUAL_QUOTIENT";
        result.reduce_s=elapsed(start);return result;
    }
    // Clean-only must have identity map; all other variants preserve exact source
    // positive-equivalence proof. Do not assert speed benefits from modifications.
    result.applied=anyChanged;
    if(result.applied){
        if(result.reason=="NATIVE_NO_TRANSFORM")
            result.reason="APPLY_ORIGINAL_CERTIFIED_TRANSFORMATION";
        result.representative=std::move(rep);
        result.reduced=std::move(rewritten);
    }else result.reason="NO_EFFECT_NATIVE_FALLBACK";
    result.reduce_s=elapsed(start);
    return result;
}

// DRNAS MRE X: frozen C3 clause-dedup mechanism and MRE11 structural policy.
// No SAT labels, CDCL timing, historical formula IDs or oracle results in routing.
static Gate x_mre11_gate(const CNF& original){
    auto start=Clock::now();
    if(original.clauses.size()>MAX_CLAUSES){
        Gate g;g.reason="X_MRE_ABSTAIN_SOURCE_TOO_LARGE";
        g.reduce_s=elapsed(start);return g;
    }
    Gate ren=certified_gate(original,"cpp_rename");
    if(ren.applied && ren.eliminated>=4){
        ren.reason="X_MRE11_SELECT_RENAME";ren.reduce_s=elapsed(start);return ren;
    }
    Gate clean=certified_gate(original,"cpp_clean");
    if(clean.applied && clean.removed>=64 && clean.fraction>=0.005){
        clean.reason="X_MRE11_SELECT_CLEAN";clean.reduce_s=elapsed(start);return clean;
    }
    Gate g;g.reason="X_MRE11_ABSTAIN_NO_STRONG_SOURCE_SIGNAL";
    g.pairs=ren.pairs;g.eliminated=ren.eliminated;
    g.removed=clean.removed;g.fraction=clean.fraction;
    g.reduce_s=elapsed(start);return g;
}
static pair<vector<vector<int>>,unsigned> x_exact_c3_dedup(
        const vector<vector<int>>& clauses){
    unordered_set<string> seen;seen.reserve(clauses.size()*2+1);
    vector<vector<int>> out;out.reserve(clauses.size());
    unsigned removed=0;
    for(const auto& clause:clauses){
        vector<int> sorted=clause;
        sort(sorted.begin(),sorted.end());
        sorted.erase(unique(sorted.begin(),sorted.end()),sorted.end());
        string key=sorted.empty()?string():
            string(reinterpret_cast<const char*>(sorted.data()),
                   sorted.size()*sizeof(int));
        if(seen.insert(key).second)out.push_back(clause);
        else removed++;
    }
    need(out.size()+removed==clauses.size(),"C3 identity count mismatch");
    return {std::move(out),removed};
}
static bool x_mode(const string& mode){
    return mode=="x_native"||mode=="x_mre11"||mode=="x_dedup"||
           mode=="x_tail"||mode=="x_joint"||
           mode=="x_composed"||mode=="x_adaptive";
}
static Gate x_gate(const CNF& original,const string& mode){
    if(mode=="x_native")return certified_gate(original,"cpp_native");
    if(mode=="x_mre11")return x_mre11_gate(original);
    if(mode=="x_dedup")return certified_gate(original,"cpp_dedup");
    if(mode=="x_tail")return certified_gate(original,"cpp_tail");
    if(mode=="x_joint")return certified_gate(original,"cpp_joint");
    need(mode=="x_composed"||mode=="x_adaptive","unrecognized MRE X method");
    auto start=Clock::now();
    Gate g=x_mre11_gate(original);
    if(original.clauses.size()>MAX_CLAUSES){
        g.reason="X_COMPOSITE_ABSTAIN_SOURCE_TOO_LARGE";
        g.reduce_s=elapsed(start);return g;
    }
    if(mode=="x_adaptive"){
        // Source-only precommitted trigger: >=64 duplicate original clauses
        // AND >=2 percent of source clauses, before any CDCL attempt.
        auto census=x_exact_c3_dedup(original.clauses);
        const unsigned duplicate=census.second;
        if(duplicate<64 ||
           double(duplicate)/double(original.clauses.size())<0.02){
            g.reason=g.applied?"X_ADAPTIVE_MRE11_ONLY":
                                  "X_ADAPTIVE_ABSTAIN_NO_SOURCE_DUPLICATES";
            g.reduce_s=elapsed(start);return g;
        }
    }
    // MRE11 proof uses two-way positive implications from ORIGINAL CNF.
    // C3 step removes ONLY syntactically identical clauses from the
    // certified quotient or untouched original. The composed step is
    // equisatisfiable, with existing MRE11 model lifting unmodified.
    const auto& before=(g.applied?g.reduced:original.clauses);
    auto filtered=x_exact_c3_dedup(before);
    if(filtered.second){
        if(!g.applied){
            g.representative.resize(original.vars+1);
            iota(g.representative.begin(),g.representative.end(),0);
        }
        g.applied=true;
        g.reduced=std::move(filtered.first);
        g.duplicate_clauses+=filtered.second;
        g.removed=unsigned(original.clauses.size()-g.reduced.size());
        g.fraction=double(g.removed)/double(original.clauses.size());
        g.reason=mode=="x_adaptive"?"X_ADAPTIVE_MRE11_PLUS_EXACT_C3":
                                      "X_MRE11_PLUS_EXACT_C3";
    }else if(!g.applied)g.reason="X_COMPOSE_NO_EFFECT";
    else g.reason="X_COMPOSE_MRE11_ONLY";
    g.reduce_s=elapsed(start);
    return g;
}
static string x_cert(const string& mode){
    if(mode=="x_native")return "original_CNF_unchanged";
    if(mode=="x_tail")return "original_CNF_exact_clause_permutation";
    if(mode=="x_dedup")return "original_CNF_clause_identity";
    if(mode=="x_composed"||mode=="x_adaptive")
        return "original_CNF_certified_equivalence_plus_exact_duplicate_identity";
    return "two_original_CNF_binary_clauses_transitive_closure";
}

[[maybe_unused]] static void write_dimacs(const string& filename,unsigned n,
                         const vector<vector<int>>& clauses){
    ofstream out(filename);
    need(bool(out),"cannot write certified CNF");
    out<<"p cnf "<<n<<" "<<clauses.size()<<"\n";
    for(const auto& c:clauses){
        for(int l:c)out<<l<<" ";
        out<<"0\n";
    }
    need(bool(out),"CNF write failed");
}
static void print_gate(const Gate& g,const string& mode,double parse_s){
    cout<<fixed<<setprecision(8)
        <<"MRE10_GATE {\"mode\":\""<<mode<<"\",\"applied\":"
        <<(g.applied?"true":"false")
        <<",\"reason\":\""<<g.reason<<"\""
        <<",\"source_direct_pairs\":"<<g.pairs
        <<",\"variables_eliminated\":"<<g.eliminated
        <<",\"clauses_removed\":"<<g.removed
        <<",\"taut_clauses_removed\":"<<g.taut_clauses
        <<",\"duplicate_clauses_removed\":"<<g.duplicate_clauses
        <<",\"duplicate_literals_removed\":"<<g.duplicate_literals
        <<",\"duplicate_clauses_moved\":"<<g.duplicate_clauses_moved
        <<",\"removed_fraction\":"<<g.fraction
        <<",\"native_parse_s\":"<<parse_s
        <<",\"native_gate_s\":"<<g.reduce_s
        <<",\"certificate\":\""<<x_cert(mode)<<"\"}"
        <<"\n";
}
#ifndef MRE9_STANDALONE
using namespace CMSat;
static void result_line(const string& status,SATSolver* p){
    uint64_t conflicts=p?p->get_last_conflicts():0;
    uint64_t decisions=p?p->get_last_decisions():0;
    uint64_t propagations=p?p->get_last_propagations():0;
    cout<<"R195_RESULT status="<<status<<" conflicts="<<conflicts
        <<" decisions="<<decisions<<" propagations="<<propagations
        <<" source_rows=0 derived_rows=0\n";
}
static void native_solve(const CNF& original,const Gate& gate,unsigned seed){
    const auto& working=gate.applied?gate.reduced:original.clauses;
    SATSolver cms;
    cms.set_num_threads(1);
    cms.set_seed(seed);
    cms.set_verbosity(0);
    const char* limit=getenv("DRNAS_MAX_CONFLICTS");
    bool bounded=(limit && *limit);
    if(bounded){
        uint64_t cap=stoull(limit);
        need(cap==100 || cap==1000 || cap==5000,"unlocked conflict cap");
        cms.set_max_confl(cap);
    }
    // Keep OTF Gauss disabled, matching the pinned MRE6f source_xor_no_gauss arm.
    cms.new_vars(original.vars);
    bool root_unsat=false;
    for(const auto& clause:working){
        vector<Lit> ls;
        ls.reserve(clause.size());
        for(int l:clause)ls.emplace_back(unsigned(abs(l)-1),l<0);
        if(!cms.add_clause(ls)){root_unsat=true;break;}
    }
    if(root_unsat){
        result_line("UNSAT",nullptr);
        return;
    }
    const lbool status=cms.solve();
    string result=status==l_True?"SAT":(status==l_False?"UNSAT":
                                             (bounded?"BUDGET":"UNKNOWN"));
    vector<bool> lifted(original.vars+1,false);
    if(status==l_True){
        const auto& values=cms.get_model();
        need(values.size()>=original.vars,"truncated native SAT model");
        for(unsigned v=1;v<=original.vars;v++){
            unsigned root=(gate.applied?gate.representative[v]:v);
            need(root>=1 && root<=original.vars,"reconstructed representative out of range");
            // l_Undef is possible for declared but unused original variables;
            // those are unconstrained and can safely take false.
            lifted[v]=(values[root-1]==l_True);
        }
        // Independently replay the COMPLETE original CNF, not only the quotient.
        for(const auto& clause:original.clauses){
            bool sat=false;
            for(int lit:clause)
                if(lifted[unsigned(abs(lit))]==(lit>0)){sat=true;break;}
            need(sat,"reconstructed SAT model falsifies original CNF clause");
        }
    }
    result_line(result,&cms);
    if(status==l_True){
        for(unsigned k=1;k<=original.vars;k+=60){
            cout<<"v ";
            for(unsigned v=k;v<=original.vars && v<k+60;v++)
                cout<<(lifted[v]?int(v):-int(v))<<" ";
            cout<<"0\n";
        }
    }
    cout<<flush;
}
#endif

int main(int argc,char**argv){
    try{
#ifdef MRE9_STANDALONE
        need(argc==5 && string(argv[1])=="--emit",
             "standalone usage: --emit INPUT MODE OUTPUT");
        const string file=argv[2],mode=argv[3],out=argv[4];
        auto t=Clock::now();
        CNF original=parse_dimacs(file);
        double parse_s=elapsed(t);
        need(x_mode(mode),"MRE X mode invalid");
        Gate gate=x_gate(original,mode);
        write_dimacs(out,original.vars,gate.applied?gate.reduced:original.clauses);
        print_gate(gate,mode,parse_s);
#else
        need(argc==4,"usage: mre_x_native CNF X_MODE SEED");
        const string file=argv[1],mode=argv[2];
        need(x_mode(mode),"MRE X native mode invalid");
        unsigned long s=stoul(argv[3]);
        need(s<=numeric_limits<unsigned>::max(),"seed overflow");
        auto t=Clock::now();
        CNF original=parse_dimacs(file);
        double parse_s=elapsed(t);
        need(x_mode(mode),"MRE X mode invalid");
        Gate gate=x_gate(original,mode);
        print_gate(gate,mode,parse_s);
        native_solve(original,gate,unsigned(s));
#endif
        return 0;
    }catch(const exception& e){
        cerr<<e.what()<<"\n";
        return 78;
    }
}
