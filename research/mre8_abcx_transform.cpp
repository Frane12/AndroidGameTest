// DRNAS MRE8: independently ablate certified positive equivalence quotient,
// tautology elimination, and clause dedup on ORIGINAL SHA-locked SAT CNFs.
// No external solver metadata or previous outcomes influence transformations.
// All active quotient edges are original binary clauses (-a v b) & (a v -b).
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
using Clause=vector<int>;
static void need(bool ok,const string& why){if(!ok)throw runtime_error("MRE8_CERT_FAIL "+why);}
static string canonical(const Clause& c){
    Clause v=c;
    sort(v.begin(),v.end());v.erase(unique(v.begin(),v.end()),v.end());
    string k;for(int x:v){k+=to_string(x);k+=',';}return k;
}
static vector<Clause> load(const string& src,int& n){
    ifstream in(src);need(bool(in),"cannot read original CNF");
    string word,fmt;size_t decl=0;bool got=false;
    vector<Clause> all;Clause c;
    while(in>>word){
        if(word=="c"){string comment;getline(in,comment);continue;}
        if(word=="%")break;
        if(word=="p"){
            need(!got,"duplicate header");
            in>>fmt>>n>>decl;
            need(bool(in)&&fmt=="cnf"&&n>0&&decl>0&&decl<=300000,"bad DIMACS header");
            got=true;continue;
        }
        need(got,"CNF literal before header");
        long long v=stoll(word);need(v>=-n&&v<=n,"literal out of range");
        if(v==0){all.push_back(c);c.clear();}
        else c.push_back(int(v));
    }
    need(got&&c.empty()&&all.size()==decl,"incorrect clause count");
    return all;
}
struct DSU{
    vector<int> parent;
    explicit DSU(int n):parent(n+1){for(int i=0;i<=n;i++)parent[i]=i;}
    int find(int x){if(parent[x]!=x)parent[x]=find(parent[x]);return parent[x];}
    void unite(int a,int b){a=find(a);b=find(b);if(a!=b)parent[max(a,b)]=min(a,b);}
};
struct Edges{
    vector<pair<int,int>> certified;
    DSU dsu;
    Edges(const vector<Clause>& orig,int n):dsu(n){
        set<pair<int,int>> binaries;
        for(const auto& c:orig){
            if(c.size()!=2||c[0]==c[1]||c[0]==-c[1]||((long long)c[0]*c[1]>=0))continue;
            int x=c[0],y=c[1];if(x>y)swap(x,y);
            binaries.emplace(x,y);
        }
        set<pair<int,int>> already;
        for(const auto& cl:binaries){
            int x=-cl.first,y=-cl.second;if(x>y)swap(x,y);
            if(!binaries.count({x,y}))continue;
            int a=abs(cl.first),b=abs(cl.second);
            need(a!=b,"self equivalence disallowed");
            if(a>b)swap(a,b);
            if(already.emplace(a,b).second){
                // Validate the two exact original clauses before union.
                need(binaries.count({-b,a})&&binaries.count({-a,b}),
                    "no two-way direct original implication certificate");
                certified.emplace_back(a,b);
                dsu.unite(a,b);
            }
        }
    }
};
static bool tautology(const Clause& c){
    set<int> seen;for(int x:c){if(seen.count(-x))return true;seen.insert(x);}return false;
}
static void write_cnf(const string& path,int n,const vector<Clause>& cs){
    ofstream out(path);need(bool(out),"output CNF inaccessible");
    out<<"p cnf "<<n<<" "<<cs.size()<<"\n";
    for(const auto& c:cs){for(int x:c)out<<x<<" ";out<<"0\n";}
    need(bool(out),"output DIMACS write failed");
}
int main(int argc,char** argv){
    try{
        need(argc==6,"usage: mre8_transform MODE input.cnf output.cnf report.json map.txt");
        string mode=argv[1];
        const set<string> allowed={"A","B","C","D","E","X5","X50"};
        need(allowed.count(mode)!=0,"unsupported ablation arm");
        int n=0;auto original=load(argv[2],n);
        Edges edges(original,n);
        const int threshold=mode=="X5"?5:mode=="X50"?50:0;
        bool chosen=threshold==0||int(edges.certified.size())>=threshold;
        int mapped=0;for(int v=1;v<=n;v++)mapped+=(edges.dsu.find(v)!=v);
        // A: original clause-only dedup.
        // B: quotient only, leaving tautologies and duplicate clauses.
        // C: quotient + remove tautologies, retaining duplicate clauses.
        // D: quotient + remove duplicates, retaining tautologies.
        // E: quotient + remove both.
        // X5/X50: cheap certified pair-count gate; if enabled use full E,
        //          else feed EXACT original source to solver (output unused).
        bool do_map=(mode!="A"&&chosen);
        bool drop_taut=(mode=="C"||mode=="E"||(mode[0]=='X'&&chosen));
        bool drop_dup=(mode=="A"||mode=="D"||mode=="E"||(mode[0]=='X'&&chosen));
        set<string> uniques;
        vector<Clause> rewritten;rewritten.reserve(original.size());
        int removed_taut=0,removed_dup=0,replaced=0;
        for(const auto& c:original){
            Clause v;v.reserve(c.size());
            for(int l:c){
                int w=(do_map?edges.dsu.find(abs(l)):abs(l));
                int shifted=l<0?-w:w;
                replaced+=(l!=shifted);
                v.push_back(shifted);
            }
            if(drop_taut&&tautology(v)){removed_taut++;continue;}
            if(drop_dup&&!uniques.emplace(canonical(v)).second){removed_dup++;continue;}
            if(drop_taut&&drop_dup){
                Clause cleaned;set<int> seen;
                for(int l:v)if(seen.emplace(l).second)cleaned.push_back(l);
                v.swap(cleaned);
            }
            rewritten.push_back(move(v));
        }
        if(mode[0]=='X'&&!chosen)rewritten.clear(); // native will use original file
        else write_cnf(argv[3],n,rewritten);
        {
            ofstream mapout(argv[5]);need(bool(mapout),"mapping output inaccessible");
            if(do_map)for(int v=1;v<=n;v++){
                int root=edges.dsu.find(v);
                if(root!=v)mapout<<v<<" "<<root<<"\n";
            }
            need(bool(mapout),"mapping write failed");
        }
        {
            ofstream edgeout(string(argv[5])+".edges");
            need(bool(edgeout),"edge certificate output inaccessible");
            if(do_map)for(auto [a,b]:edges.certified)edgeout<<a<<" "<<b<<"\n";
            need(bool(edgeout),"edge certificate write failed");
        }
        ofstream report(argv[4]);need(bool(report),"JSON report inaccessible");
        report<<"{\"mode\":\""<<mode<<"\",\"vars\":"<<n
              <<",\"original_clauses\":"<<original.size()
              <<",\"output_clauses\":"<<((mode[0]=='X'&&!chosen)?original.size():rewritten.size())
              <<",\"candidate_pairs\":"<<edges.certified.size()
              <<",\"merged_vars\":"<<(do_map?mapped:0)
              <<",\"replaced_literals\":"<<replaced
              <<",\"removed_tautologies\":"<<removed_taut
              <<",\"removed_duplicates\":"<<removed_dup
              <<",\"active_quotient\":"<<(do_map?"true":"false")
              <<",\"gate_accepted\":"<<(chosen?"true":"false")
              <<",\"use_original\":"<<((mode[0]=='X'&&!chosen)?"true":"false")
              <<",\"certificate\":\"two original opposite binary implications\"}\n";
        need(bool(report),"JSON report write failed");
        cout<<"MRE8_TRANSFORM_PASS mode="<<mode<<" pairs="<<edges.certified.size()
            <<" merged="<<(do_map?mapped:0)<<" kept="<<((mode[0]=='X'&&!chosen)?original.size():rewritten.size())
            <<" native="<<(mode[0]=='X'&&!chosen?1:0)<<"\n";
    }catch(const exception& e){cerr<<e.what()<<"\n";return 78;}
    return 0;
}
