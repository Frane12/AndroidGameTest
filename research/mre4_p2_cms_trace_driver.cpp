// DRNAS MRE4 P2: preserve R28 externally; native instrumented CMS counts\n// exact imported-lemma watched BCP reason events during solve().
// All original CNF clauses are retained. Imported/derived XOR constraints are
// source-certified before invoking this binary. This activates CMS's EXISTING
// in-CDCL Gaussian propagation -- NOT an external DRNAS trail callback yet.
// Exact four-arm causal ablation: native/import/shadow/derived_active.
#include <cryptominisat5/cryptominisat.h>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
using namespace CMSat;
extern "C" void drnas_mre4_trace_import(int enabled);
extern "C" void drnas_mre4_trace_solve(int enabled);
extern "C" void drnas_mre4_trace_dump();
static vector<vector<int>> load_derived_lemmas(const string& filename,unsigned n){
    ifstream in(filename);
    check(bool(in),"cannot open certified derived CNF input");
    vector<vector<int>> rows;
    string line;
    while(getline(in,line)){
        if(line.empty()||line[0]=='c')continue;
        istringstream tok(line);
        vector<int> lits;int v;
        bool end=false;
        while(tok>>v){
            if(v==0){end=true;check(tok.eof() || !bool(tok>>v),"extra literal after zero");break;}
            check(v!=INT32_MIN&&abs(v)<=int(n),"derived literal out of range");
            lits.push_back(v);
        }
        check(end && lits.size()>=2 && lits.size()<=2,"derived clauses must be binary");
        check(abs(lits[0])!=abs(lits[1]),"duplicate/tautological derived CNF");
        rows.push_back(lits);
    }
    check(rows.size()<=2,"at most two derived lemmas allowed");
    return rows;
}

static void fail(const string& m) { throw runtime_error("R195_NATIVE_FAIL "+m); }
static void check(bool ok,const string& m){if(!ok)fail(m);}
struct Stats { uint64_t source_rows=0, derived_rows=0; };

static vector<vector<int>> load_cnf(const string& fn,unsigned& n) {
    ifstream in(fn);
    check(bool(in),"cannot open original CNF");
    string tok;bool header=false;
    unsigned nc=0;
    vector<vector<int>> clauses;
    vector<int> current;
    while(in>>tok) {
        if(tok=="c") { string line;getline(in,line); continue; }
        if(tok=="%") break;
        if(tok=="p"){
            string fmt;in>>fmt>>n>>nc;
            check(fmt=="cnf"&&n>0&&nc>0,"wrong DIMACS header");
            header=true; continue;
        }
        check(header,"literal before header");
        int lit=0;
        try {lit=stoi(tok);}catch(...){fail("not a DIMACS literal");}
        if(lit==0) {clauses.push_back(current);current.clear();}
        else {check(lit!=INT32_MIN && abs(lit)<=int(n),"literal outside CNF");current.push_back(lit);}
    }
    check(header && current.empty() && clauses.size()==nc,"DIMACS clause count mismatch");
    return clauses;
}
static vector<pair<vector<unsigned>,bool>> load_rows(const string& filename,unsigned n) {
    ifstream in(filename);
    check(bool(in),"cannot open certified XOR TSV");
    vector<pair<vector<unsigned>,bool>> result;
    unsigned k=0;int rhs=0;
    while(in>>k>>rhs){
        check(k>=2&&k<=6&&(rhs==0||rhs==1),"bad XOR row width/rhs");
        vector<unsigned> vs;
        for(unsigned j=0;j<k;j++){
            unsigned v=0;check(bool(in>>v),"truncated XOR row");
            check(v>=1&&v<=n,"XOR var out of range");
            vs.push_back(v-1); // CMS API uses zero-based variable IDs
        }
        check(is_sorted(vs.begin(),vs.end()),"XOR variables not ascending");
        check(adjacent_find(vs.begin(),vs.end())==vs.end(),"duplicate XOR variable");
        result.push_back({vs,rhs==1});
    }
    check(in.eof(),"malformed XOR TSV");
    return result;
}
int main(int argc,char**argv) {
    try {
        check(argc==6,"usage: r195_native CNF SOURCE_ROWS DERIVED_ROWS MODE SEED");
        const string cnf=argv[1],src_rows=argv[2],derived_rows=argv[3],mode=argv[4];
        check(mode=="cms_native"||mode=="source_xor_import"||mode=="derived_shadow"||
              mode=="derived_active"||mode=="source_xor_no_gauss"||mode=="mre4_trace_active"||mode=="mre4_trace_shadow"||mode=="mre4_trace_xor",
              "unsupported mode");
        unsigned seed=unsigned(stoul(argv[5]));
        unsigned n=0;
        const auto clauses=load_cnf(cnf,n);
        SATSolver cms;
        cms.set_num_threads(1);
        cms.set_seed(seed);
        cms.set_verbosity(0);
        // CryptoMiniSat 5.11.15 witness audit: OTF Gauss without imported XOR
        // produced an invalid SAT model on frozen SHA b2c2008e... (2/2).
        // Keep OTF Gauss for certified-XOR arms; native baseline omits it.
        // Isolated shard-5 SAT witness issue: OTF Gauss + 8 replayed CRR
        // clauses generated invalid SAT model at seed=3670242714.
        // The source_xor_no_gauss mode preserves XOR import but disables
        // the opportunistic Gaussian routine. Keep independent model checks.
        if(mode!="cms_native" && mode!="source_xor_no_gauss" && mode!="mre4_trace_active" && mode!="mre4_trace_shadow" && mode!="mre4_trace_xor")
            cms.set_allow_otf_gauss();
        cms.new_vars(n);
        for(const auto& c:clauses) {
            vector<Lit> lits;
            lits.reserve(c.size());
            for(int l:c) lits.emplace_back(unsigned(abs(l)-1),l<0);
            if(!cms.add_clause(lits)) {
                drnas_mre4_trace_dump();
                cout<<"R195_RESULT status=UNSAT conflicts=0 decisions=0 propagations=0"
                    <<" source_rows=0 derived_rows=0\n"<<flush;
                return 0;
            }
        }
        Stats stats;
        if(mode!="cms_native"){
            const auto source=load_rows(src_rows,n);
            for(const auto& row:source){
                cms.add_xor_clause(row.first,row.second);
                stats.source_rows++;
            }
            if(mode=="derived_shadow"||mode=="derived_active"){
                const auto derived=load_rows(derived_rows,n);
                for(const auto& row:derived){
                    if(mode=="derived_active"){
                        cms.add_xor_clause(row.first,row.second);
                        stats.derived_rows++;
                    }
                }
            }
        }

        if(mode=="mre4_trace_active"){
            const auto derived=load_derived_lemmas(derived_rows,n);
            for(const auto& row:derived){
                vector<Lit> cls;
                for(int l:row)cls.emplace_back(unsigned(abs(l)-1),l<0);
                drnas_mre4_trace_import(1);
                const bool ok_added=cms.add_clause(cls);
                drnas_mre4_trace_import(0);
                check(ok_added,"certified binary lemma conflicts at root");
                stats.derived_rows++;
            }
        }
        drnas_mre4_trace_solve(1);
        const lbool status=cms.solve();
        drnas_mre4_trace_solve(0);
        drnas_mre4_trace_dump();
        string result="TIMEOUT";
        if(status==l_True)result="SAT";
        if(status==l_False)result="UNSAT";
        // Fail closed at the native boundary, before emitting any SAT verdict:
        // check the entire original CNF against CMS's reconstructed model.
        if(status==l_True){
            const auto& witness=cms.get_model();
            check(witness.size()>=n,"SAT model missing variables");
            for(size_t i=0;i<clauses.size();i++){
                bool satisfied=false;
                for(int lit:clauses[i]){
                    const lbool value=witness[unsigned(abs(lit)-1)];
                    if(value==(lit>0?l_True:l_False)){
                        satisfied=true;
                        break;
                    }
                }
                check(satisfied,"SAT witness falsifies original clause index="+to_string(i));
            }
        }
        cout<<"R195_RESULT status="<<result
            <<" conflicts="<<cms.get_last_conflicts()
            <<" decisions="<<cms.get_last_decisions()
            <<" propagations="<<cms.get_last_propagations()
            <<" source_rows="<<stats.source_rows
            <<" derived_rows="<<stats.derived_rows<<"\n";
        if(status==l_True){
            const auto& model=cms.get_model();
            check(model.size()>=n,"CMS model missing declared original variables");
            for(unsigned k=0;k<n;k+=60){
                cout<<"v ";
                for(unsigned j=k;j<min(n,k+60);j++){
                    check(model[j]==l_True || model[j]==l_False,
                          "undefined original variable in SAT witness");
                    cout<<(model[j]==l_True?int(j+1):-int(j+1))<<" ";
                }
                cout<<"0\n";
            }
        }
        cout<<flush;
        return 0;
    }catch(const exception& e){
        cerr<<e.what()<<"\n";
        return 78;
    }
}
