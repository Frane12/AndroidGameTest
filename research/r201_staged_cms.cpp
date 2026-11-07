// DRNAS R201: staged, source-certified partial XOR into CMS 5.11.15.
// This exchanges constraints BETWEEN incremental solve() calls, not inside a
// running CDCL conflict. Never claim IPASIR-UP support in CMS 5.11.
// The source-derived TSV and proof traces are independently checked by Python.
#include <cryptominisat5/cryptominisat.h>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <algorithm>

using namespace std;
using namespace CMSat;
using Clock = chrono::steady_clock;
using T = chrono::duration<double>;
static void need(bool yes,const string& msg) {
    if (!yes) throw runtime_error("R201_DRIVER_FAIL " + msg);
}
struct Input {
    unsigned n=0, declared=0;
    vector<vector<int>> clauses;
};
static Input readcnf(const string& path) {
    ifstream f(path);need(bool(f),"cannot open original CNF");
    Input in;string token;vector<int> clause;
    while(f>>token) {
        if(token=="c") {string discard;getline(f,discard);continue;}
        if(token=="p") {
            string fmt;f>>fmt>>in.n>>in.declared;
            need(fmt=="cnf" && in.n>0 && in.n<=5000000,"unsupported DIMACS");
            continue;
        }
        need(in.n>0,"no DIMACS header");
        int lit=stoi(token);
        if(lit==0) {in.clauses.push_back(clause);clause.clear();}
        else {need(abs(lit)<=int(in.n),"literal exceeds variable count");clause.push_back(lit);}
    }
    need(clause.empty() && in.clauses.size()==in.declared,"invalid DIMACS clauses");
    return in;
}
struct Row {vector<unsigned> variables;bool rhs;};
static vector<Row> readrows(const string& path,unsigned n) {
    ifstream f(path);need(bool(f),"missing proof-derived TSV");
    vector<Row> rows;string line;
    while(getline(f,line)) {
        if(line.empty() || line[0]=='#')continue;
        istringstream ss(line);unsigned count=0;int rhs=-1;
        need(bool(ss>>count>>rhs) && count>=2 && count<=8 && (rhs==0||rhs==1),"bad XOR row header");
        Row r;r.rhs=(rhs==1);r.variables.reserve(count);
        for(unsigned i=0;i<count;i++) {
            unsigned v=0;need(bool(ss>>v) && v>0 && v<=n,"bad XOR variable");
            r.variables.push_back(v-1);
        }
        unsigned excess;need(!(ss>>excess),"extra XOR row columns");
        need(is_sorted(r.variables.begin(),r.variables.end()) &&
             adjacent_find(r.variables.begin(),r.variables.end())==r.variables.end(),"repeated XOR variable");
        rows.push_back(r);
        need(rows.size()<=16,"more than 16 rows: bounded budget enforced");
    }
    return rows;
}
static vector<Lit> litsof(const vector<int>& clause) {
    vector<Lit> out;out.reserve(clause.size());
    for(int x:clause)out.emplace_back(unsigned(abs(x)-1),x<0);
    return out;
}
static const char* answer(lbool x) {
    if(x==l_True)return "SAT";
    if(x==l_False)return "UNSAT";
    return "UNKNOWN";
}
int main(int argc,char**argv) {
    try {
        need(argc==7,"usage: driver MODE CNF VERIFIED_TSV FIRST_CONFLICTS CAP_SECONDS WITNESS_PATH");
        const string mode=argv[1];
        need(mode=="plain"||mode=="shadow"||mode=="stage"||mode=="static","invalid mode");
        const string source=argv[2];
        const unsigned first_confl=stoul(argv[4]);
        const double cap=stod(argv[5]);
        need(first_confl>=1 && first_confl<=100000 && cap>=0.1 && cap<=60,"invalid budget");
        auto start=Clock::now();
        auto elapsed=[&](){return T(Clock::now()-start).count();};
        Input in=readcnf(source);
        vector<Row> rows=readrows(argv[3],in.n);
        SATSolver solver;
        solver.set_verbosity(0);
        solver.new_vars(in.n);
        bool clauses_ok=true;
        for(auto& c:in.clauses)clauses_ok=solver.add_clause(litsof(c)) && clauses_ok;
        unsigned inserted=0;
        auto inject=[&](){
            for(const Row& r:rows) {
                solver.add_xor_clause(r.variables,r.rhs);
                ++inserted;
            }
        };
        lbool first=l_Undef, final=l_Undef;
        if(mode=="static")inject();
        if(mode=="shadow"||mode=="stage") {
            solver.set_max_confl(first_confl);
            solver.set_max_time(max(0.001,cap-elapsed()-0.02));
            first=solver.solve();
            final=first;
            if(first==l_Undef && elapsed()<cap-0.03) {
                if(mode=="stage")inject();
                solver.set_max_confl(1000000000000ULL);
                solver.set_max_time(max(0.001,cap-elapsed()-0.02));
                final=solver.solve();
            }
        } else {
            solver.set_max_confl(1000000000000ULL);
            solver.set_max_time(max(0.001,cap-elapsed()-0.02));
            final=solver.solve();
        }
        bool checked=false;
        if(final==l_True) {
            const auto& model=solver.get_model();
            need(model.size()>=in.n,"SAT model has too few variables");
            for(const auto& c:in.clauses) {
                bool satisfied=false;
                for(int lit:c) {
                    auto m=model[abs(lit)-1];
                    satisfied|=(m==l_True && lit>0)||(m==l_False && lit<0);
                }
                need(satisfied,"SAT model contradicts ORIGINAL CNF");
            }
            ofstream out(argv[6]);need(bool(out),"cannot write witness");
            for(unsigned i=0;i<in.n;i++){
                if(model[i]==l_True)out<<(i+1)<<" ";
                else if(model[i]==l_False)out<<"-"<<(i+1)<<" ";
            }
            out<<"0\n";checked=true;
        }
        cout<<"R201_DRIVER {\"mode\":\""<<mode<<"\",\"status\":\""<<answer(final)
            <<"\",\"pilot_status\":\""<<answer(first)<<"\",\"variables\":"<<in.n
            <<",\"clauses\":"<<in.clauses.size()
            <<",\"source_clauses_added\":"<<(clauses_ok?"true":"false")
            <<",\"certified_rows_available\":"<<rows.size()
            <<",\"certified_rows_injected\":"<<inserted
            <<",\"sat_model_original_verified\":"<<(checked?"true":"false")
            <<",\"conflicts\":"<<solver.get_sum_conflicts()
            <<",\"elapsed_s\":"<<elapsed()<<"}\n";
        return 0;
    } catch(const exception& e) {
        cerr<<"R201_DRIVER_FAIL "<<e.what()<<"\n";
        return 2;
    }
}
