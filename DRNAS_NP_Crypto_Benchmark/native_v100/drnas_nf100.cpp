// DRNAS NP v1.0 — trained native structural autoselector for CaDiCaL::phase.
// The SAME parser, process, and CaDiCaL::Solver are used in the baseline and
// fallback; only the proof-checked Horn shortcut differs.
// Compile: g++ -std=c++17 -O2 -Wall -Wextra -pedantic nf_v08_native.cpp -lcadical -pthread -o drnas_nf08
#include <cadical.hpp>
#include <algorithm>
#include <chrono>
#include <climits>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using Clock=std::chrono::steady_clock;
using Time=Clock::time_point;
static double millis(Time start) {
    return std::chrono::duration<double,std::milli>(Clock::now()-start).count();
}
struct CNF {
    int n=0;
    std::vector<std::vector<int>> clauses;
    std::vector<int> pos, neg;
    int unit_count=0;
    std::int64_t literal_count=0;
    std::vector<unsigned char> used;
};
static CNF read_cnf(const std::string &path,bool count_signs) {
    std::ifstream in(path);
    if(!in) throw std::runtime_error("cannot open CNF");
    CNF f; bool header=false;
    int expected=-1; std::vector<int> curr; std::string line;
    while(std::getline(in,line)) {
        std::size_t off=line.find_first_not_of(" \t\r");
        if(off==std::string::npos) continue;
        char first=line[off];
        if(first=='c') continue;
        if(first=='%') break;
        if(first=='p') {
            if(header || !curr.empty()) throw std::runtime_error("multiple DIMACS headers");
            std::istringstream h(line.substr(off));
            std::string marker,format;h>>marker>>format>>f.n>>expected;
            if(marker!="p" || format!="cnf" || f.n<1 || f.n>1000000 ||
               expected<0 || expected>3000000) throw std::runtime_error("invalid CNF header");
            header=true;
            f.clauses.reserve(static_cast<std::size_t>(expected));
            f.used.assign(f.n,0);
            if(count_signs) {f.pos.assign(f.n,0);f.neg.assign(f.n,0);}
            continue;
        }
        if(!header) throw std::runtime_error("missing DIMACS header");
        std::istringstream tokens(line.substr(off));std::string part;
        while(tokens>>part) {
            std::size_t len=0;long val=0;
            try {val=std::stol(part,&len,10);}
            catch(const std::exception&) {throw std::runtime_error("invalid DIMACS literal");}
            if(len!=part.size() || val>INT_MAX || val<INT_MIN)
                throw std::runtime_error("invalid DIMACS token");
            int lit=static_cast<int>(val);
            if(!lit) {
                f.unit_count+=(curr.size()==1);
                f.clauses.emplace_back(std::move(curr));
                curr.clear();
                if(static_cast<int>(f.clauses.size())>expected)
                    throw std::runtime_error("too many clauses");
            } else {
                int v=std::abs(lit)-1;
                if(v<0 || v>=f.n) throw std::runtime_error("literal outside DIMACS range");
                curr.push_back(lit);f.used[v]=1;
                ++f.literal_count;
                if(count_signs) {
                    if(lit>0)++f.pos[v];else ++f.neg[v];
                }
            }
        }
    }
    if(!header || !curr.empty() || static_cast<int>(f.clauses.size())!=expected)
        throw std::runtime_error("incomplete DIMACS file");
    return f;
}
static bool verify(const CNF &f,const std::vector<unsigned char> &model) {
    if(static_cast<int>(model.size())!=f.n) return false;
    for(const auto &cl:f.clauses) {
        bool satisfied=false;
        for(int lit:cl)
            if((model[std::abs(lit)-1]!=0)==(lit>0)){satisfied=true;break;}
        if(!satisfied)return false;
    }
    return true;
}
struct Outcome {
    int code=0;std::string route="unknown";
    std::string selected="base";
    int phase_count=0;double phase_ms=0;
    std::vector<unsigned char> model;
    double parse_ms=0,gate_ms=0,probe_ms=0,solver_ms=0,total_ms=0;
    int n=0,clauses=0;bool valid=false;
};
class Deadline final:public CaDiCaL::Terminator{
    Time until;
public:
    explicit Deadline(Time t):until(t){}
    bool terminate() override{return Clock::now()>=until;}
};
// Decision phase hints NEVER assume literals and NEVER change the CNF.
// CaDiCaL::Solver::phase(lit) biases polarity but SAT/UNSAT remains exact.
static int cdcl(const CNF &f,Time deadline,std::vector<unsigned char> &model,
                const std::string &phase_kind,int &phase_count,double &phase_ms) {
    CaDiCaL::Solver solver;
    solver.set("quiet",1);
    for(const auto &cl:f.clauses){
        for(int lit:cl) solver.add(lit);
        solver.add(0);
    }
    if(phase_kind!="none") {
        Time hint_start=Clock::now();
        if(static_cast<int>(f.pos.size())!=f.n || static_cast<int>(f.neg.size())!=f.n)
            throw std::runtime_error("phase counts not available");
        for(int i=0;i<f.n;++i) {
            if(!f.used[i])continue;
            int pos=f.pos[i],neg=f.neg[i],degree=pos+neg;
            if(degree==0)continue;
            // Selective hints: at least 8 occurrences and at least
            // 60 percent signed-imbalance. This is fixed, NOT fit on tests.
            bool select=(phase_kind!="selective") ||
                    (degree>=8 && 10*std::abs(pos-neg)>=6*degree);
            if(!select)continue;
            int preferred=((pos>=neg)?(i+1):-(i+1));
            if(phase_kind=="minority")preferred=-preferred;
            solver.phase(preferred);
            ++phase_count;
        }
        phase_ms=millis(hint_start);
    }
    Deadline limit(deadline);
    solver.connect_terminator(&limit);
    int status=solver.solve();
    solver.disconnect_terminator();
    if(status==10) {
        model.assign(f.n,0);
        for(int i=0;i<f.n;++i)if(f.used[i])model[i]=solver.val(i+1)>0;
    }
    return status;
}
static double minority_ratio(const CNF &f){
    std::int64_t mn=0;
    for(int i=0;i<f.n;++i)mn+=std::min(f.pos[i],f.neg[i]);
    return double(mn)/std::max<std::int64_t>(1,f.literal_count);
}
static std::vector<unsigned char> majority(const CNF &f){
    std::vector<unsigned char> flips(f.n,0);
    for(int i=0;i<f.n;++i) flips[i]=(f.pos[i]>f.neg[i]);
    return flips;
}
static int horn_defects(const CNF &f,const std::vector<unsigned char> &flips){
    int bad=0;
    for(const auto &cl:f.clauses) {
        int heads=0;
        for(int lit:cl)
            if((lit>0)!=bool(flips[std::abs(lit)-1]) && ++heads>1)
                {++bad;break;}
    }
    return bad;
}
// Forward-chaining for a PROVEN (renamable-)Horn formula. In the renamed
// coordinates every clause has at most one positive literal.
// A clause with zero negatives forces its positive head (if present).
static int horn_solve(const CNF &f,const std::vector<unsigned char> &flips,
                      std::vector<unsigned char> &output){
    struct Rule{int head=-1;int left=0;};
    std::vector<Rule> rules;
    rules.reserve(f.clauses.size());
    std::vector<std::vector<int>> deps(f.n);
    std::vector<unsigned char> truths(f.n,0);
    std::queue<int> work;
    for(const auto &cl:f.clauses){
        Rule r;
        const int index=static_cast<int>(rules.size());
        for(int lit:cl){
            int var=std::abs(lit)-1;
            bool positive=(lit>0)!=bool(flips[var]);
            if(positive) {
                if(r.head!=-1)throw std::runtime_error("non-Horn formula reached Horn solver");
                r.head=var;
            } else {
                ++r.left;deps[var].push_back(index);
            }
        }
        rules.push_back(r);
    }
    auto force=[&](int v) {
        if(!truths[v]){truths[v]=1;work.push(v);}
    };
    for(const Rule &r:rules)if(r.left==0){
        if(r.head<0)return 20;
        force(r.head);
    }
    while(!work.empty()){
        int v=work.front();work.pop();
        for(int ix:deps[v]) {
            Rule &r=rules[ix];
            if(--r.left==0){
                if(r.head<0)return 20;
                force(r.head);
            }
        }
    }
    output.assign(f.n,0);
    for(int i=0;i<f.n;++i)output[i]=bool(truths[i])!=bool(flips[i]);
    return 10;
}
// Exact renamable-Horn recognition: each pair of literals in a clause
// must not both become positive. Encode pair restriction as 2-SAT:
// NOT((flip_i==needed_i) AND (flip_j==needed_j)).
static bool rename_horn_2sat(const CNF &f,std::vector<unsigned char> &flips,
                            Time deadline,std::size_t max_pairs=200000){
    const int nn=2*f.n;
    std::vector<std::vector<int>> g(nn),rg(nn);
    std::size_t pairs=0;
    auto add_edge=[&](int x,int y){g[x].push_back(y);rg[y].push_back(x);};
    for(const auto &cl:f.clauses) {
        if(Clock::now()>deadline)return false;
        const std::size_t len=cl.size();
        if(len>0 && (len-1)>((max_pairs-pairs)*2/len))return false;
        for(std::size_t a=0;a<len;++a)for(std::size_t b=a+1;b<len;++b){
            if(++pairs>max_pairs)return false;
            int va=std::abs(cl[a])-1,vb=std::abs(cl[b])-1;
            int ta=(cl[a]<0)?1:0,tb=(cl[b]<0)?1:0;
            int left=2*va+ta,right=2*vb+tb;
            add_edge(left,2*vb+(1-tb));
            add_edge(right,2*va+(1-ta));
        }
    }
    // Iterative Kosaraju, avoiding recursion on long implication chains.
    std::vector<unsigned char> seen(nn,0);
    std::vector<int> order;order.reserve(nn);
    std::vector<std::pair<int,std::size_t>> stack;
    for(int s=0;s<nn;++s)if(!seen[s]){
        seen[s]=1;stack.emplace_back(s,0);
        while(!stack.empty()){
            auto &top=stack.back();
            if(top.second<g[top.first].size()){
                int v=g[top.first][top.second++];
                if(!seen[v]){seen[v]=1;stack.emplace_back(v,0);}
            }else{order.push_back(top.first);stack.pop_back();}
        }
        if(Clock::now()>deadline)return false;
    }
    std::vector<int> comp(nn,-1),dfs;
    int nc=0;
    for(auto it=order.rbegin();it!=order.rend();++it){
        int s=*it;if(comp[s]>=0)continue;
        comp[s]=nc;dfs.push_back(s);
        while(!dfs.empty()){
            int v=dfs.back();dfs.pop_back();
            for(int u:rg[v])if(comp[u]<0){comp[u]=nc;dfs.push_back(u);}
        }
        ++nc;
        if(Clock::now()>deadline)return false;
    }
    flips.assign(f.n,0);
    for(int v=0;v<f.n;++v){
        if(comp[2*v]==comp[2*v+1])return false;
        flips[v]=(comp[2*v]<comp[2*v+1]);
    }
    return horn_defects(f,flips)==0;
}
// Train-derived one-rule policy. File must be frozen before TEST inputs are opened.
// Its only effect is to select optional search polarity, never CNF clauses.
struct AutoPolicy{
    std::string engine="base";
    int min_n=INT_MAX,max_n=INT_MAX;
    double min_density=0,max_density=1e20;
    double min_minority=0,max_minority=1;
    double min_long=0,max_long=1;
};
static AutoPolicy read_policy(const std::string &path){
    AutoPolicy a;
    if(path.empty())return a; // no model means OFF
    std::ifstream in(path);
    if(!in)throw std::runtime_error("frozen policy not found");
    std::string signature;
    in>>signature>>a.engine>>a.min_n>>a.max_n>>a.min_density
      >>a.max_density>>a.min_minority>>a.max_minority
      >>a.min_long>>a.max_long;
    if(!in || signature!="DRNAS_V100_POLICY" ||
        (a.engine!="base"&&a.engine!="majority"&&a.engine!="selective") ||
        a.min_n<0 || a.max_n<a.min_n || a.max_density<a.min_density ||
        a.max_minority<a.min_minority || a.max_long<a.min_long)
        throw std::runtime_error("invalid frozen policy format");
    return a;
}
static std::string auto_engine(const CNF &f,const AutoPolicy &policy) {
    if(policy.engine=="base")return "none";
    const double density=double(f.clauses.size())/std::max(1,f.n);
    const double minority=minority_ratio(f);
    std::size_t longer=0;
    for(const auto &cl:f.clauses)longer+=(cl.size()>=4);
    const double long_share=double(longer)/std::max<std::size_t>(1,f.clauses.size());
    if(f.n<policy.min_n || f.n>policy.max_n ||
       density<policy.min_density || density>policy.max_density ||
       minority<policy.min_minority || minority>policy.max_minority ||
       long_share<policy.min_long || long_share>policy.max_long)return "none";
    return policy.engine;
}
int main(int argc,char **argv){
    try {
        std::string path,mode="base",policy_path;double budget_ms=2000.;
        for(int i=1;i<argc;++i){
            std::string arg(argv[i]);
            if(arg=="--input" && i+1<argc)path=argv[++i];
            else if(arg=="--mode" && i+1<argc)mode=argv[++i];
            else if(arg=="--budget-ms" && i+1<argc)budget_ms=std::stod(argv[++i]);
            else if(arg=="--policy" && i+1<argc)policy_path=argv[++i];
            else throw std::runtime_error("usage: drnas_nf100 --input FILE --mode auto|base|neuro|neuro-phase|phase-majority|phase-minority|phase-selective|force [--budget-ms 2000]");
        }
        if(path.empty() || (mode!="base"&&mode!="neuro"&&mode!="neuro-phase"&&mode!="phase-majority"&&mode!="phase-minority"&&mode!="phase-selective"&&mode!="force"&&mode!="auto") ||
           !std::isfinite(budget_ms) || budget_ms<=0)
            throw std::runtime_error("invalid command arguments");
        const Time begin=Clock::now();
        const Time deadline=begin+std::chrono::duration_cast<Clock::duration>(
                     std::chrono::duration<double,std::milli>(budget_ms));
        bool screening=(mode=="neuro" || mode=="neuro-phase" || mode=="force");
        const AutoPolicy policy=(mode=="auto")?read_policy(policy_path):AutoPolicy{};
        // Policy OFF uses the EXACT same parsing path as plain CaDiCaL.
        const bool phase_work=((mode=="auto" && policy.engine!="base")||
            mode=="phase-majority"||mode=="phase-minority"||
            mode=="phase-selective"||mode=="neuro-phase");
        std::string hint_kind=(mode=="phase-majority"?"majority":mode=="phase-minority"?"minority":phase_work?"selective":"none");
        const Time p0=Clock::now();
        CNF f=read_cnf(path,screening||phase_work);
        if(mode=="auto")hint_kind=auto_engine(f,policy);
        Outcome r;r.n=f.n;r.clauses=static_cast<int>(f.clauses.size());
        r.selected=(hint_kind=="none"?"base":hint_kind);
        r.parse_ms=millis(p0);
        bool recognized=false;
        std::vector<unsigned char> flips;
        if(screening && (mode=="force" || f.n>=30)) {
            Time gate_start=Clock::now();
            const double minor=minority_ratio(f);
            const double unit=double(f.unit_count)/std::max<std::size_t>(1,f.clauses.size());
            bool gate=(mode=="force" || (minor>=.13 && minor<=.28 && unit==0.));
            int bad=0;
            if(gate){
                flips=majority(f);bad=horn_defects(f,flips);
                if(mode!="force" && double(bad)/std::max<std::size_t>(1,f.clauses.size())>.10)
                    gate=false;
            }
            r.gate_ms=millis(gate_start);
            if(!gate)r.route="gate-skip";
            else {
                const Time probe_start=Clock::now();
                if(bad==0) {recognized=true;r.route="direct-Horn";}
                else {
                    Time cap=std::min(deadline,Clock::now()+std::chrono::milliseconds(12));
                    if(cap>Clock::now() && rename_horn_2sat(f,flips,cap)) {
                        recognized=true;r.route="renamable-Horn";
                    }else r.route="2sat-fallback";
                }
                r.probe_ms=millis(probe_start);
            }
        }else if(screening)r.route="small-bypass";
        if(recognized && Clock::now()<deadline){
            const Time t=Clock::now();
            r.code=horn_solve(f,flips,r.model);
            r.solver_ms=millis(t);
        }else {
            const Time t=Clock::now();
            if(Clock::now()>=deadline){r.code=0;r.route="budget-timeout";}
            else{
                r.code=cdcl(f,deadline,r.model,hint_kind,r.phase_count,r.phase_ms);r.solver_ms=millis(t);
                if(r.route=="unknown" || !screening)r.route=(hint_kind=="none"?"cadical":"phase-"+hint_kind+"->cadical");
                else r.route+=(hint_kind=="none"?"->cadical":"->phase-"+hint_kind+"->cadical");
            }
        }
        if(r.code==10 && !verify(f,r.model))
            throw std::runtime_error("INVALID SAT witness");
        r.valid=(r.code==10);
        r.total_ms=millis(begin);
        const char* status=(r.code==10?"SAT":r.code==20?"UNSAT":"UNKNOWN");
        std::cout<<std::fixed<<std::setprecision(5)
            <<"{\"status\":\""<<status<<"\",\"route\":\""<<r.route
            <<"\",\"n\":"<<r.n<<",\"clauses\":"<<r.clauses
            <<",\"parse_ms\":"<<r.parse_ms<<",\"gate_ms\":"<<r.gate_ms
            <<",\"probe_ms\":"<<r.probe_ms<<",\"phase_ms\":"<<r.phase_ms
            <<",\"phase_count\":"<<r.phase_count<<",\"selected\":\""<<r.selected
            <<"\",\"solver_ms\":"<<r.solver_ms
            <<",\"total_ms\":"<<r.total_ms<<",\"witness_valid\":"
            <<(r.valid?"true":"false")<<"}\n";
        return 0;
    }catch(const std::exception &e){
        std::cerr<<"DRNAS_NATIVE_ERROR: "<<e.what()<<"\n";
        return 2;
    }
}
