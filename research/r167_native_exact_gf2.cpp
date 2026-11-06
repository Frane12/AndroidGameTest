// DRNAS R167 native, exact CNF-equivalent GF(2) dispatch plus CaDiCaL CDCL fallback.
// Research-only: no UNSAT LRAT/FRAT for the CDCL fallback. Source-complete
// XOR truth-table clauses + original unit clauses are the ONLY exact fastpath.
// Neither partial patterns nor approximate entropy/heuristics can claim SAT/UNSAT.
#include "cadical.hpp"
#include <openssl/sha.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace std;
using Clock=chrono::steady_clock;
static auto begin_time=Clock::now();
static double seconds(){return chrono::duration<double>(Clock::now()-begin_time).count();}
static void require(bool yes,const string& why){if(!yes)throw runtime_error("R167_FAIL_CLOSED: "+why);}
struct CNF{
    int n=0;
    long long declared=-1;
    vector<vector<int>> clauses;
};
static string sha256_file(const string& path){
    ifstream f(path,ios::binary);
    require(f.good(),"cannot hash source file");
    SHA256_CTX ctx;
    SHA256_Init(&ctx);
    char buf[1<<16];
    while(f){f.read(buf,sizeof buf);auto count=f.gcount();if(count>0)SHA256_Update(&ctx,buf,size_t(count));}
    unsigned char digest[SHA256_DIGEST_LENGTH];
    SHA256_Final(digest,&ctx);
    ostringstream out;out<<hex<<setfill('0');
    for(unsigned char c:digest)out<<setw(2)<<unsigned(c);
    return out.str();
}
static CNF load_dimacs(const string& path){
    ifstream in(path);
    require(in.good(),"CNF not readable");
    CNF x; bool header=false; vector<int> clause;
    string line; size_t lit_count=0;
    while(getline(in,line)){
        size_t i=line.find_first_not_of(" \r\t");
        if(i==string::npos||line[i]=='c'||line[i]=='%')continue;
        istringstream ss(line.substr(i));
        if(line[i]=='p'){
            string p,cnf,extra;
            require(!header&&clause.empty(),"duplicate/late CNF header");
            ss>>p>>cnf>>x.n>>x.declared;
            require(p=="p"&&cnf=="cnf"&&x.n>=0&&x.declared>=0 &&
                    x.declared<=20000000 && !(ss>>extra),"bad DIMACS header");
            header=true;continue;
        }
        require(header,"clauses before CNF header");
        long long l=0;
        while(ss>>l){
            require(l>=-x.n&&l<=x.n,"literal outside variable range");
            if(l==0){
                x.clauses.push_back(move(clause));clause.clear();
                require((long long)x.clauses.size()<=x.declared,"too many clauses");
            } else{
                clause.push_back(int(l));
                require(++lit_count<=100000000,"source too large for research runner");
            }
        }
        require(ss.eof(),"malformed integer in DIMACS");
    }
    require(header&&clause.empty()&&(long long)x.clauses.size()==x.declared,
            "malformed clause/header count");
    return x;
}
struct Row{vector<int> vars;uint8_t rhs=0;};
struct Detection{bool exact=false;vector<Row> rows;size_t covered=0;};
static Detection detect(const CNF& cnf,double cap){
    // Masks encode which literals are negated, relative to ascending variables.
    // A complete forbidden parity block proves XOR(vars)=1-parity.
    using Masks=map<unsigned,vector<size_t>>;
    map<vector<int>,Masks> groups;
    Detection d;
    vector<unsigned char> seen(cnf.clauses.size(),0);
    for(size_t i=0;i<cnf.clauses.size();++i){
        if((i&4095)==0&&seconds()>=cap)return d;
        const auto& clause=cnf.clauses[i];
        if(clause.size()==1){
            int lit=clause[0];
            d.rows.push_back({{abs(lit)},uint8_t(lit>0)});
            seen[i]=1;
            continue;
        }
        if(clause.size()<2||clause.size()>6)continue;
        vector<int> sorted=clause;
        sort(sorted.begin(),sorted.end(),[](int a,int b){return abs(a)<abs(b);});
        vector<int> vs;unsigned mask=0;bool duplicate=false;
        for(size_t j=0;j<sorted.size();++j){
            int v=abs(sorted[j]);
            if(j&&v==vs.back()){duplicate=true;break;}
            vs.push_back(v);
            if(sorted[j]<0)mask|=(1U<<j);
        }
        if(!duplicate)groups[vs][mask].push_back(i);
    }
    for(const auto& group:groups){
        if(seconds()>=cap)return d;
        auto width=group.first.size();
        unsigned count=1U<<width;
        for(unsigned parity=0;parity<=1;parity++){
            bool full=true;
            for(unsigned mask=0;mask<count;mask++)
                if((__builtin_popcount(mask)&1)==int(parity)&&
                   !group.second.count(mask)){full=false;break;}
            if(!full)continue;
            d.rows.push_back({group.first,uint8_t(1U-parity)});
            for(unsigned mask=0;mask<count;mask++){
                if((__builtin_popcount(mask)&1)!=int(parity))continue;
                for(auto index:group.second.at(mask))seen[index]=1;
            }
        }
    }
    for(auto v:seen)d.covered+=v;
    d.exact=(d.covered==cnf.clauses.size());
    return d;
}
static int first_pivot(const vector<uint64_t>& row){
    for(size_t j=0;j<row.size();++j)
        if(row[j])return int(j*64+__builtin_ctzll(row[j]));
    return -1;
}
static void xor_into(vector<uint64_t>& a,const vector<uint64_t>& b){
    for(size_t j=0;j<a.size();++j)a[j]^=b[j];
}
struct GF2Answer {
    string status="TIMEOUT";
    vector<unsigned char> model;
    vector<size_t> contradiction;
    size_t rank=0;
};
static GF2Answer gaussian(const CNF& cnf,const vector<Row>& rows,double cap){
    GF2Answer answer;
    const size_t n=size_t(cnf.n),m=rows.size();
    if(n>200000||m>20000)return answer;
    const size_t width=(n+63)/64,combwidth=(m+63)/64;
    struct Pivot{vector<uint64_t> bits,combo;uint8_t rhs=0;};
    vector<unique_ptr<Pivot>> pivots(n);
    for(size_t j=0;j<m;j++){
        if((j&63)==0&&seconds()>=cap)return answer;
        vector<uint64_t> bits(width,0),comb(combwidth,0);
        for(int v:rows[j].vars){
            require(v>0&&size_t(v)<=n,"bad source row variable");
            bits[(v-1)/64]^=1ULL<<((v-1)%64);
        }
        if(combwidth)comb[j/64]=1ULL<<(j%64);
        uint8_t rhs=rows[j].rhs;
        while(true){
            int p=first_pivot(bits);
            if(p<0){
                if(rhs){
                    vector<uint64_t> replay(width,0);
                    unsigned parity=0;
                    for(size_t k=0;k<m;k++){
                        if(!(comb[k/64]&(1ULL<<(k%64))))continue;
                        answer.contradiction.push_back(k);
                        for(int v:rows[k].vars)replay[(v-1)/64]^=1ULL<<((v-1)%64);
                        parity^=rows[k].rhs;
                    }
                    require(first_pivot(replay)<0&&parity==1,
                            "independent native XOR contradiction replay failed");
                    answer.status="UNSAT";return answer;
                }
                break;
            }
            auto& old=pivots[size_t(p)];
            if(!old){
                auto pvt=make_unique<Pivot>();
                pvt->bits=move(bits);pvt->combo=move(comb);pvt->rhs=rhs;
                old=move(pvt);answer.rank++;break;
            }
            xor_into(bits,old->bits);
            xor_into(comb,old->combo);
            rhs^=old->rhs;
        }
    }
    answer.model.assign(n,0);
    for(int p=int(n)-1;p>=0;--p){
        if((p&4095)==0 && seconds()>=cap){answer.model.clear();return answer;}
        if(!pivots[size_t(p)])continue;
        auto& pivot=*pivots[size_t(p)];
        unsigned parity=pivot.rhs;
        for(size_t w=0;w<width;w++){
            auto word=pivot.bits[w];
            while(word){
                int bit=__builtin_ctzll(word);
                size_t v=w*64+size_t(bit);
                if(v!=size_t(p))parity^=answer.model[v];
                word&=word-1;
            }
        }
        answer.model[size_t(p)]=parity;
    }
    for(const auto& row:rows){
        unsigned parity=0;
        for(int v:row.vars)parity^=answer.model[size_t(v-1)];
        require(parity==row.rhs,"native gaussian source-row SAT check failed");
    }
    for(const auto& clause:cnf.clauses){
        bool ok=false;
        for(int l:clause)if((answer.model[size_t(abs(l)-1)]!=0)==(l>0)){ok=true;break;}
        require(ok,"native gaussian original-CNF SAT witness check failed");
    }
    answer.status="SAT";return answer;
}
static bool source_model_check(const CNF& c,CaDiCaL::Solver& solver){
    for(const auto& clause:c.clauses){
        bool sat=false;
        for(int lit:clause){
            int value=solver.val(abs(lit));
            if((lit>0&&value>0)||(lit<0&&value<0)){sat=true;break;}
        }
        if(!sat)return false;
    }
    return true;
}
class Deadline final:public CaDiCaL::Terminator{
    double cap_;
public:
    explicit Deadline(double cap):cap_(cap){}
    bool terminate() override{return seconds()>=cap_;}
};
static string escape_json(const string& text){
    string result;
    for(char c:text){
        if(c=='"'||c=='\\')result.push_back('\\');
        result.push_back(c);
    }
    return result;
}
static void proof_json(const string& path,const string& sha,
                       const CNF& c,const Detection& d,const GF2Answer& ans){
    ofstream out(path);
    require(out.good(),"cannot write certificate file");
    out<<"{\"source_sha256\":\""<<sha<<"\",\"source_vars\":"<<c.n
       <<",\"source_clauses\":"<<c.clauses.size()
       <<",\"status\":\""<<ans.status<<"\",\"rows\":[";
    for(size_t i=0;i<d.rows.size();i++){
        if(i)out<<",";
        out<<"[[";
        for(size_t j=0;j<d.rows[i].vars.size();j++){
            if(j)out<<",";
            out<<d.rows[i].vars[j];
        }
        out<<"],"<<unsigned(d.rows[i].rhs)<<"]";
    }
    out<<"],\"gauss_rank\":"<<ans.rank;
    if(ans.status=="SAT"){
        out<<",\"model_true_vars\":[";
        bool first=true;
        for(size_t i=0;i<ans.model.size();i++)if(ans.model[i]){
            if(!first)out<<",";
            first=false;out<<i+1;
        }
        out<<"]";
        // Independent Python verifier computes SAT model SHA itself if present.
    }else{
        out<<",\"conflict_row_ids\":[";
        for(size_t j=0;j<ans.contradiction.size();j++){
            if(j)out<<",";
            out<<ans.contradiction[j];
        }
        out<<"]";
    }
    out<<"}\n";
}
int main(int argc,char** argv){
    try{
        if(argc<2)throw runtime_error("usage: r167-native FILE.cnf [--cap seconds] [--force-clean] [--proof proof.json]");
        string path=argv[1],proof;double cap=10.0;bool force_clean=false;
        for(int i=2;i<argc;i++){
            string a=argv[i];
            if(a=="--force-clean")force_clean=true;
            else if(a=="--cap"&&i+1<argc)cap=stod(argv[++i]);
            else if(a=="--proof"&&i+1<argc)proof=argv[++i];
            else throw runtime_error("unknown or incomplete argument "+a);
        }
        require(isfinite(cap)&&cap>=0.1&&cap<=3600,"invalid cap");
        begin_time=Clock::now();
        CNF cnf=load_dimacs(path);
        string sha=sha256_file(path);
        Detection detected;
        GF2Answer answer;
        string method="CDCL_CLEAN",status="TIMEOUT";
        double detect_s=0;
        if(!force_clean && seconds()<cap){
            detected=detect(cnf,cap);
            detect_s=seconds();
            if(detected.exact){
                answer=gaussian(cnf,detected.rows,cap);
                if(answer.status!="TIMEOUT"){
                    status=answer.status;
                    method="NATIVE_EXACT_GF2";
                    if(!proof.empty())proof_json(proof,sha,cnf,detected,answer);
                }
            }
        }
        unique_ptr<CaDiCaL::Solver> solver;
        if(method!="NATIVE_EXACT_GF2"&&seconds()<cap){
            method=force_clean?"CDCL_CLEAN":"CDCL_FALLBACK";
            solver=make_unique<CaDiCaL::Solver>();
            for(const auto& clause:cnf.clauses){
                for(int lit:clause)solver->add(lit);
                solver->add(0);
            }
            Deadline timer(cap);
            solver->connect_terminator(&timer);
            int code=solver->solve();
            solver->disconnect_terminator();
            require(code==0||code==10||code==20,"invalid CaDiCaL status code");
            if(code==10){
                require(source_model_check(cnf,*solver),"CDCL SAT model fails original CNF check");
                status="SAT";
            }else if(code==20){status="UNSAT";}
        }
        double elapsed=seconds();
        if(elapsed>cap&&status!="TIMEOUT"){status="TIMEOUT";method+="_OVER_CAP";}
        cerr<<"R167_DEBUG version=1 exact="<<detected.exact<<" rows="<<detected.rows.size()
            <<" source_sha="<<sha<<"\n";
        cout<<setprecision(8)<<fixed;
        cout<<"R167_RESULT {\"status\":\""<<status<<"\",\"method\":\""<<method
            <<"\",\"wall_s\":"<<elapsed<<",\"cap_s\":"<<cap
            <<",\"detect_s\":"<<detect_s<<",\"exact\":"<<(detected.exact?"true":"false")
            <<",\"xor_rows\":"<<detected.rows.size()
            <<",\"covered\":"<<detected.covered
            <<",\"source_sha256\":\""<<sha<<"\",\"nvars\":"<<cnf.n
            <<",\"clauses\":"<<cnf.clauses.size()<<"}\n";
        cout<<"s "<<(status=="SAT"?"SATISFIABLE":status=="UNSAT"?"UNSATISFIABLE":"UNKNOWN")<<"\n";
        if(status=="SAT"){
            cout<<"v ";
            for(int v=1;v<=cnf.n;v++){
                int lit=method=="NATIVE_EXACT_GF2"
                       ?(answer.model[size_t(v-1)]?v:-v)
                       :(solver->val(v)>0?v:-v);
                cout<<lit<<" ";
                if(v%64==0)cout<<"0\nv ";
            }
            cout<<"0\n";
        }
        return status=="SAT"?10:status=="UNSAT"?20:0;
    }catch(const exception& e){
        cerr<<"R167_ERROR "<<e.what()<<"\n";return 2;
    }
}
