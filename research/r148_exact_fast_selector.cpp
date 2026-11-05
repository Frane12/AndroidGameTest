// DRNAS R148: native, faster read-only copy of the FROZEN R135 policy.
// CaDiCaL iff FULL R135 scan and round6(binary_ratio)<.30 AND round6(horn_ratio)<.55.
// Original Kissat, CaDiCaL, R135, and V15.3.1 remain unmodified.
#include <charconv>
#include <cmath>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>
#include <system_error>
using namespace std;
constexpr uint64_t MAX_BYTES=8ULL*1024ULL*1024ULL;
constexpr uint64_t MAX_CLAUSES=120000ULL;
static bool parse_uint(string_view v,uint64_t &n) {
    if(v.empty()) return false;
    auto r=from_chars(v.data(),v.data()+v.size(),n);
    return r.ec==errc() && r.ptr==v.data()+v.size();
}
static bool parse_int(string_view v,int64_t &n) {
    if(v.empty()) return false;
    auto r=from_chars(v.data(),v.data()+v.size(),n);
    return r.ec==errc() && r.ptr==v.data()+v.size();
}
static string_view trim(string_view x){
    while(!x.empty()&&isspace(static_cast<unsigned char>(x.front())))x.remove_prefix(1);
    while(!x.empty()&&isspace(static_cast<unsigned char>(x.back())))x.remove_suffix(1);
    return x;
}
struct Tokens {
    string_view rest;
    explicit Tokens(string_view t):rest(t){}
    string_view next(){
        rest=trim(rest);
        if(rest.empty())return {};
        size_t p=0;
        while(p<rest.size()&&!isspace(static_cast<unsigned char>(rest[p])))++p;
        auto result=rest.substr(0,p);rest.remove_prefix(p);return result;
    }
};
static double round6(uint64_t numerator,uint64_t denominator){
    if(!denominator)return 0.0;
    return nearbyint(1000000.0*double(numerator)/double(denominator))/1000000.0;
}
int main(int argc,char **argv){
    if(argc!=2){cerr<<"usage: r148_selector original-verified.cnf\n";return 2;}
    ifstream f(argv[1],ios::binary|ios::ate);
    if(!f){cerr<<"R148_SOURCE_UNREADABLE\n";return 3;}
    auto size_off=f.tellg();
    if(size_off<0){cerr<<"R148_STAT_ERROR\n";return 3;}
    uint64_t size=static_cast<uint64_t>(size_off);
    auto output=[&](string route,string reason,uint64_t declared,uint64_t observed,uint64_t binary,uint64_t horn,uint64_t scanned,bool complete){
        cout<<fixed<<setprecision(6)<<"c R148_SELECTOR route="<<route
            <<" reason="<<reason<<" declared="<<declared<<" observed="<<observed
            <<" binary_fraction="<<round6(binary,observed)
            <<" horn_fraction="<<round6(horn,observed)
            <<" scanned_bytes="<<scanned<<" source_bytes="<<size
            <<" fully_scanned="<<(complete?1:0)
            <<" equivalent_to=R135_8MiB_120k_0.30_0.55\n";
    };
    // In previously SHA/DIMACS-audited sources, R135 always defaults to Kissat
    // if its 8 MiB byte cap is exceeded. This shortcut is never a new heuristic.
    if(size>MAX_BYTES){output("KISSAT","source_over_R135_byte_cap",0,0,0,0,0,false);return 0;}
    string buf(static_cast<size_t>(size),'\0');
    f.seekg(0,ios::beg);
    if(size&&!f.read(buf.data(),static_cast<streamsize>(size))){cerr<<"R148_READ_ERROR\n";return 3;}
    uint64_t vars=0,declared=0,seen=0,binary=0,horn=0,scanned=0;
    uint64_t clause_len=0,pos=0;
    bool header=false;
    size_t at=0;
    auto fail=[&](const char* reason){cerr<<"R148_INVALID_DIMACS "<<reason<<"\n";return 4;};
    while(at<buf.size()){
        size_t end=buf.find('\n',at);
        if(end==string::npos)end=buf.size();
        auto line=trim(string_view(buf.data()+at,end-at));
        scanned=end+((end<buf.size())?1:0);
        at=scanned;
        if(line.empty())continue;
        if((line[0]=='c'||line[0]=='%')&&(line.size()==1||line[1]==' '||line[1]=='\t'))continue;
        if(line.size()>=2 && line[0]=='p'&&line[1]==' '){
            if(header)return fail("duplicate_header");
            Tokens t(line);
            if(t.next()!="p"||t.next()!="cnf"||!parse_uint(t.next(),vars)
               ||!parse_uint(t.next(),declared)||!t.next().empty()||vars<1||declared<1)
                return fail("header");
            header=true;
            // Python R135 stops when 120000th clause is seen, even on EOF.
            if(declared>=MAX_CLAUSES){
                output("KISSAT","declared_over_R135_clause_cap",declared,0,0,0,scanned,false);
                return 0;
            }
            continue;
        }
        if(!header)return fail("missing_header");
        Tokens t(line);
        for(string_view token=t.next();!token.empty();token=t.next()){
            int64_t lit=0;
            if(!parse_int(token,lit))return fail("invalid_literal");
            if(lit){
                if(lit>int64_t(vars)||lit < -int64_t(vars))return fail("literal_outside_header");
                ++clause_len;
                pos+=(lit>0);
            } else {
                ++seen;
                binary+=(clause_len==2);
                horn+=(pos<=1);
                clause_len=pos=0;
                if(seen>declared)return fail("too_many_clauses");
                // Certified lower bound: remaining clauses cannot lower the
                // eventual binary/Horn numerator. Prefix *ratios* are NOT
                // used for routing; only a proven R135 Kissat decision.
                if(round6(binary,declared)>=0.30){
                    output("KISSAT","certified_binary_lower_bound",declared,seen,binary,horn,scanned,false);
                    return 0;
                }
                if(round6(horn,declared)>=0.55){
                    output("KISSAT","certified_horn_lower_bound",declared,seen,binary,horn,scanned,false);
                    return 0;
                }
            }
        }
    }
    if(!header||clause_len||seen!=declared)return fail("incomplete_or_mismatched_clause_count");
    const double br=round6(binary,seen),hr=round6(horn,seen);
    const bool cadical=br<0.30&&hr<0.55;
    output(cadical?"CADICAL":"KISSAT",cadical?"complete_sparse_nonhorn":"complete_binary_or_horn",
           declared,seen,binary,horn,scanned,true);
    return 0;
}