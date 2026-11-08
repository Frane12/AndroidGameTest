// DRNAS MRE9: native C++ source-certified equality gate, MRE6f as reference.
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
static void need(bool x,const string& m){if(!x) throw runtime_error("MRE9_FAIL_CLOSED "+m);}
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
        }catch(const exception&){throw runtime_error("MRE9_FAIL_CLOSED invalid DIMACS literal");}
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
    unsigned pairs=0, eliminated=0, removed=0;
    double fraction=0, reduce_s=0;
    string reason="NATIVE_NO_TRANSFORM";
    vector<unsigned> representative;
    vector<vector<int>> reduced;
};
static Gate certified_gate(const CNF& original,const string& mode){
    auto start=Clock::now();
    need(mode=="cpp_gate" || mode=="cpp_all" || mode=="cpp_native","mode");
    Gate result;
    if(mode=="cpp_native"){
        result.reason="NATIVE_UNMODIFIED";
        return result;
    }
    // Signed source clauses (-a OR b) and (a OR -b), a<b.
    // Only ORIGINAL exact binary clauses are admitted as proof certificates.
    unordered_map<uint64_t,uint8_t> directions;
    directions.reserve(original.clauses.size()/3+1);
    for(const auto& c:original.clauses){
        if(c.size()!=2)continue;
        int p=c[0],q=c[1];
        if((p<0)==(q<0) || abs(p)==abs(q))continue;
        unsigned a=unsigned(min(abs(p),abs(q)));
        unsigned b=unsigned(max(abs(p),abs(q)));
        int l_a=(unsigned(abs(p))==a)?p:q;
        uint8_t bit=(l_a<0)?1:2;
        directions[edgekey(a,b)]|=bit;
    }
    for(const auto& e:directions)if(e.second==3)result.pairs++;
    result.reason="ABSTAIN_INSUFFICIENT_DIRECT_PAIRS";
    if(result.pairs<(mode=="cpp_all"?1u:MIN_MERGES)){
        result.reduce_s=elapsed(start);return result;
    }
    DSU dsu(original.vars);
    for(const auto& e:directions){
        if(e.second!=3)continue;
        unsigned a=unsigned(e.first>>32);
        unsigned b=unsigned(e.first&0xffffffffu);
        // Explicit replay against the two original binary clause directions.
        need(directions.at(edgekey(a,b))==3,"source certificate missing");
        dsu.join(a,b);
    }
    vector<unsigned> rep(original.vars+1);
    iota(rep.begin(),rep.end(),0);
    for(unsigned v=1;v<=original.vars;v++){
        rep[v]=dsu.root(v);
        if(rep[v]!=v)result.eliminated++;
    }
    unordered_set<string> seen;
    seen.reserve(original.clauses.size()*2+1);
    vector<vector<int>> rewritten;
    rewritten.reserve(original.clauses.size());
    for(const auto& clause:original.clauses){
        vector<int> mapped;
        mapped.reserve(clause.size());
        for(int literal:clause){
            unsigned v=rep[unsigned(abs(literal))];
            mapped.push_back(literal<0?-int(v):int(v));
        }
        // Duplicate and tautology handling must preserve original clause order
        // for CDCL. Sorted copy is ONLY a canonical membership certificate.
        vector<int> sorted=mapped;
        sort(sorted.begin(),sorted.end());
        sorted.erase(unique(sorted.begin(),sorted.end()),sorted.end());
        bool taut=false;
        for(int lit:sorted)
            if(binary_search(sorted.begin(),sorted.end(),-lit)){taut=true;break;}
        if(taut)continue;
        string key(reinterpret_cast<const char*>(sorted.data()),
                   sorted.size()*sizeof(int));
        if(!seen.insert(key).second)continue;
        unordered_set<int> local;
        local.reserve(mapped.size()*2+1);
        vector<int> stable;
        stable.reserve(mapped.size());
        for(int lit:mapped)if(local.insert(lit).second)stable.push_back(lit);
        rewritten.push_back(std::move(stable));
    }
    need(rewritten.size()<=original.clauses.size(),"increasing clause count");
    result.removed=unsigned(original.clauses.size()-rewritten.size());
    result.fraction=double(result.removed)/double(original.clauses.size());
    bool eligible=result.eliminated>=MIN_MERGES &&
                  result.removed>=MIN_DROP &&
                  result.fraction>=MIN_FRACTION;
    if(mode=="cpp_all")eligible=(result.eliminated>0);
    if(eligible){
        result.applied=true;
        result.reason="APPLY_CERTIFIED_SOURCE_EQUIVALENCES";
        result.representative=std::move(rep);
        result.reduced=std::move(rewritten);
    }else result.reason="ABSTAIN_UNPROFITABLE_ACTUAL_QUOTIENT";
    result.reduce_s=elapsed(start);
    return result;
}
static void write_dimacs(const string& filename,unsigned n,
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
        <<"MRE9_GATE {\"mode\":\""<<mode<<"\",\"applied\":"
        <<(g.applied?"true":"false")
        <<",\"reason\":\""<<g.reason<<"\""
        <<",\"source_direct_pairs\":"<<g.pairs
        <<",\"variables_eliminated\":"<<g.eliminated
        <<",\"clauses_removed\":"<<g.removed
        <<",\"removed_fraction\":"<<g.fraction
        <<",\"native_parse_s\":"<<parse_s
        <<",\"native_gate_s\":"<<g.reduce_s
        <<",\"certificate\":\"two_original_CNF_binary_clauses_transitive_closure\"}"
        <<"\n";
}
#ifndef MRE9_STANDALONE
using namespace CMSat;
static void result_line(const string& status,const SATSolver* p){
    uint64_t conflicts=p?p->get_last_conflicts():0;
    uint64_t decisions=p?p->get_last_decisions():0;
    uint64_t propagations=p?p->get_last_propagations():0;
    cout<<"R195_RESULT status="<<status<<" conflicts="<<conflicts
        <<" decisions="<<decisions<<" propagations="<<propagations
        <<" source_rows=0 derived_rows=0\n";
}
static void native_solve(const CNF& original,const Gate& gate,
                         const string& mode,unsigned seed){
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
        Gate gate=certified_gate(original,mode);
        write_dimacs(out,original.vars,gate.applied?gate.reduced:original.clauses);
        print_gate(gate,mode,parse_s);
#else
        need(argc==4,"usage: mre9_native_cms CNF cpp_native|cpp_gate|cpp_all SEED");
        const string file=argv[1],mode=argv[2];
        need(mode=="cpp_native"||mode=="cpp_gate"||mode=="cpp_all","mode");
        unsigned long s=stoul(argv[3]);
        need(s<=numeric_limits<unsigned>::max(),"seed overflow");
        auto t=Clock::now();
        CNF original=parse_dimacs(file);
        double parse_s=elapsed(t);
        Gate gate=certified_gate(original,mode);
        print_gate(gate,mode,parse_s);
        native_solve(original,gate,mode,unsigned(s));
#endif
        return 0;
    }catch(const exception& e){
        cerr<<e.what()<<"\n";
        return 78;
    }
}
