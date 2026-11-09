// DRNAS X24: streaming directed signed-literal implication graph scout.
// Tracks strongly connected components at 25/50/75/100 percent of source CNF.
// Graph is observational; every eventual quotient is proof replayed by X22.
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using namespace std;
static void need(bool ok,const string& msg){
    if(!ok)throw runtime_error("X24_GRAPH_FAIL_CLOSED "+msg);
}
static int node(int l){return 2*(abs(l)-1)+(l<0);}
static int lit_of(int n){return (n/2+1)*(n%2?-1:1);}
struct Snap {
    int clauses=0, edges=0, sccs=0, largest=0, cyclic=0;
    int aliases=0, contrad=0;
};
struct Graph {
    int vars=0, nclauses=0, clauses_seen=0, edge_count=0;
    vector<vector<int>> forward,reverse;
    explicit Graph(int n,int m):vars(n),nclauses(m),forward(2*n),reverse(2*n){}
    void edge(int a,int b){
        int from=node(a),to=node(b);
        forward[from].push_back(to);
        reverse[to].push_back(from);
        ++edge_count;
        need(edge_count<=3200000,"graph edge cap");
    }
    void clause(const vector<int>& c){
        ++clauses_seen;
        if(c.size()!=2 || c[0]==c[1] || c[0]==-c[1])return;
        edge(-c[0],c[1]);
        edge(-c[1],c[0]);
    }
    Snap snapshot() const {
        const int count=2*vars;
        vector<uint8_t> seen(count,0);vector<int> order;order.reserve(count);
        for(int source=0;source<count;++source)if(!seen[source]){
            vector<pair<int,size_t>> stack{{source,0}};
            seen[source]=1;
            while(!stack.empty()){
                auto& f=stack.back();
                if(f.second<forward[f.first].size()){
                    int to=forward[f.first][f.second++];
                    if(!seen[to]){
                        seen[to]=1;
                        stack.push_back({to,0});
                    }
                }else{
                    order.push_back(f.first);
                    stack.pop_back();
                }
            }
        }
        vector<int> component(count,-1),size,canonical;
        int next=0;
        for(auto it=order.rbegin();it!=order.rend();++it){
            if(component[*it]>=0)continue;
            vector<int> stack{*it};
            component[*it]=next;
            int total=0,best=0;
            while(!stack.empty()){
                int v=stack.back();stack.pop_back();
                ++total;
                int l=lit_of(v);
                if(!best || abs(l)<abs(best) || (abs(l)==abs(best)&&l>best))best=l;
                for(int to:reverse[v])if(component[to]<0){
                    component[to]=next;
                    stack.push_back(to);
                }
            }
            size.push_back(total);
            canonical.push_back(best);
            ++next;
        }
        Snap r;
        r.clauses=clauses_seen;
        r.edges=edge_count;
        r.sccs=next;
        for(int s:size){
            r.largest=max(r.largest,s);
            if(s>1)++r.cyclic;
        }
        for(int v=1;v<=vars;++v){
            if(component[node(v)]==component[node(-v)]){
                ++r.contrad;
            }else{
                int target=canonical[component[node(v)]];
                if(abs(target)<v)++r.aliases;
            }
        }
        return r;
    }
};
static void print_snap(const Snap& s){
    cout<<"{\"clauses\":"<<s.clauses
        <<",\"edges\":"<<s.edges
        <<",\"components\":"<<s.sccs
        <<",\"nontrivial_scc\":"<<s.cyclic
        <<",\"max_scc_literals\":"<<s.largest
        <<",\"signed_alias_candidates\":"<<s.aliases
        <<",\"contradictory_variables\":"<<s.contrad
        <<"}";
}
int main(int argc,char**argv){
    try{
        need(argc==2,"usage: graph_scout ORIGINAL.cnf");
        ifstream file(argv[1]);need(bool(file),"input file");
        int vars=-1,declared=-1;
        string token;
        vector<int> current;
        vector<Snap> snapshots;
        uint64_t literal_count=0;
        int next_checkpoint=1;
        Graph* graph=nullptr;
        while(file>>token){
            if(token=="c"){string rest;getline(file,rest);continue;}
            if(token=="%")break;
            if(token=="p"){
                string mode;
                need(vars<0 && current.empty() && bool(file>>mode>>vars>>declared),
                     "DIMACS header");
                need(mode=="cnf" && vars>=0 && vars<=200000 &&
                     declared>=0 && declared<=700000,"DIMACS size");
                graph=new Graph(vars,declared);
                continue;
            }
            need(graph!=nullptr,"literal before header");
            size_t pos=0;
            int lit;
            try{lit=stoi(token,&pos);}catch(...){
                throw runtime_error("nonnumeric DIMACS literal");
            }
            need(pos==token.size(),"invalid literal token");
            if(lit==0){
                need(graph->clauses_seen<declared,"too many clauses");
                graph->clause(current);current.clear();
                while(next_checkpoint<=4 &&
                      graph->clauses_seen>=((int64_t(declared)*next_checkpoint+3)/4)){
                    snapshots.push_back(graph->snapshot());
                    ++next_checkpoint;
                }
            }else{
                need(lit!=numeric_limits<int>::min() && abs(lit)<=vars,
                     "literal out of source range");
                current.push_back(lit);
                need(++literal_count<=8000000,"literal cap");
            }
        }
        need(graph!=nullptr && current.empty() &&
             graph->clauses_seen==declared,"DIMACS source incomplete");
        while(next_checkpoint<=4){
            snapshots.push_back(graph->snapshot());
            ++next_checkpoint;
        }
        need(snapshots.size()==4,"incomplete checkpoints");
        const Snap& final=snapshots.back();
        cout<<"X24_GRAPH {\"source_clauses\":"<<declared
            <<",\"source_vars\":"<<vars
            <<",\"binary_implication_edges\":"<<final.edges
            <<",\"checkpoint_fractions\":[0.25,0.5,0.75,1.0]"
            <<",\"checkpoints\":[";
        for(size_t i=0;i<snapshots.size();++i){
            if(i)cout<<",";
            print_snap(snapshots[i]);
        }
        cout<<"],\"new_aliases_last_quarter\":"
            <<max(0,snapshots[3].aliases-snapshots[2].aliases)
            <<",\"graph_monotone_edges\":true,\"source_only\":true}\n";
        delete graph;
        return 0;
    }catch(const exception& e){
        cerr<<e.what()<<"\n";
        return 78;
    }
}
