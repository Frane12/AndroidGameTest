#include <bits/stdc++.h>
using namespace std;
using V=vector<int>; using Clock=chrono::steady_clock;
struct Limit{};
struct Row{V x; int b;};
int n; vector<V> src; set<V> known; vector<V> proof;
map<V,int> seen; vector<Row> rows; Clock::time_point deadline;
long long joined=0, blocked=0; int detected=0;
void guard(){if(Clock::now()>deadline || proof.size()>200000 || rows.size()>50000)throw Limit{};}
V canon(V a){sort(a.begin(),a.end(),[](int x,int y){return abs(x)<abs(y)||(abs(x)==abs(y)&&x<y);});a.erase(unique(a.begin(),a.end()),a.end());return a;}
void emit(V c){guard();c=canon(c);if(known.insert(c).second)proof.push_back(c);}
V forbid(const V& x,unsigned mask){V c;for(size_t i=0;i<x.size();i++)c.push_back((mask>>i&1)?-x[i]:x[i]);return c;}
int parity(unsigned x){return __builtin_parity(x);}
// Complete parity encoding. For a sum row, the forbidden boundary assignment
// forces inconsistent parities on the intersection. Enumerate only that local
// intersection, emit RUP leaf clauses, then resolve the local binary tree.
void lift(V c,const V& common,size_t k){guard();if(k==common.size()){emit(c);return;}c.push_back(common[k]);lift(c,common,k+1);c.back()=-common[k];lift(c,common,k+1);c.pop_back();emit(c);}
Row sumrow(const Row&a,const Row&b){Row r;set_symmetric_difference(a.x.begin(),a.x.end(),b.x.begin(),b.x.end(),back_inserter(r.x));r.b=a.b^b.b;return r;}
bool derive(const Row&a,const Row&b,Row&r){guard();r=sumrow(a,b);V common;set_intersection(a.x.begin(),a.x.end(),b.x.begin(),b.x.end(),back_inserter(common));if(common.empty()||r.x.size()>7||r.x.size()+common.size()>11){blocked++;return false;}
 if(seen[r.x]&(1<<r.b))return true;
 for(unsigned mask=0;mask<(1u<<r.x.size());mask++)if(parity(mask)!=r.b)lift(forbid(r.x,mask),common,0);
 seen[r.x]|=1<<r.b;rows.push_back(r);joined++;return true;}
bool readcnf(const string&f){ifstream in(f);string line;V c;long long m=-1;while(getline(in,line)){guard();if(line.empty())continue;istringstream s(line);string t;s>>t;if(t.empty()||t=="c")continue;if(t=="%")break;if(t=="p"){string fmt;s>>fmt>>n>>m;if(fmt!="cnf"||n<0||n>2000000||m<0||m>5000000)return false;continue;}s.clear();s.str(line);long long l;while(s>>l){if(l==0){src.push_back(canon(c));c.clear();}else{if(m<0||abs(l)>n)return false;c.push_back((int)l);}}}return m>=0&&c.empty()&&(long long)src.size()==m;}
void writeproof(const string&f){ofstream o(f);for(const V&c:proof){for(int l:c)o<<l<<' ';o<<"0\n";}}
bool check(const V&a){for(const auto&c:src){bool ok=false;for(int l:c)if(a[abs(l)]==(l>0)){ok=true;break;}if(!ok)return false;}return true;}
// Model from sparse echelon basis, with unconstrained variables initially false.
V model(const vector<pair<int,Row>>&basis){V a(n+1,0);for(auto it=basis.rbegin();it!=basis.rend();++it){int v=it->first,b=it->second.b;for(int u:it->second.x)if(u!=v)b^=a[u];a[v]=b;}return a;}
// Sparse elimination chooses the pivot that minimizes projected row width,
// not the numeric variable ID. Reverse-order reconstruction preserves model.
void sparse(vector<Row> active,vector<pair<int,Row>>&basis){
 while(!active.empty()){
  guard(); map<int,vector<int>> incidence;
  for(int i=0;i<(int)active.size();i++){if(active[i].x.empty())continue;for(int v:active[i].x)incidence[v].push_back(i);}
  if(incidence.empty())return;
  int best=-1,pivot=-1; tuple<int,long long,int,int> score{INT_MAX,LLONG_MAX,INT_MAX,INT_MAX};
  for(auto&[v,ix]:incidence){guard();int p=*min_element(ix.begin(),ix.end(),[&](int i,int j){return active[i].x.size()<active[j].x.size();});int width=0;long long cost=0;bool legal=true;
   for(int j:ix)if(j!=p){Row q=sumrow(active[p],active[j]);int w=q.x.size();int common=(active[p].x.size()+active[j].x.size()-w)/2;if(w>7||w+common>11){legal=false;break;}width=max(width,w);cost+=1LL<<(w+common);}
   if(!legal)continue;
   auto key=make_tuple(width,cost,(int)ix.size(),v);if(key<score){score=key;best=v;pivot=p;}}
  if(best<0)return;
  Row p=active[pivot];basis.push_back({best,p});vector<Row> next;next.reserve(active.size());
  for(int i=0;i<(int)active.size();i++){guard();if(i==pivot)continue;Row r=move(active[i]);if(binary_search(r.x.begin(),r.x.end(),best)){Row q;if(!derive(p,r,q))throw Limit{};r=move(q);}if(r.x.empty()){if(r.b)return;}else next.push_back(move(r));}
  active=move(next);
 }
}
int solve(const string&out){map<V,uint64_t> patterns;
 for(const auto&c:src){guard();if(c.empty()) {proof.push_back({});writeproof(out);return 20;}if(c.size()>6)continue;V x;unsigned mask=0;bool bad=false;for(size_t i=0;i<c.size();i++){int v=abs(c[i]);if(!x.empty()&&x.back()==v){bad=true;break;}x.push_back(v);if(c[i]<0)mask|=1u<<i;}if(!bad)patterns[x]|=1ULL<<mask;}
 for(auto&[x,p]:patterns){guard();for(int b=0;b<2;b++){uint64_t need=0;for(unsigned mask=0;mask<(1u<<x.size());mask++)if(parity(mask)!=b)need|=1ULL<<mask;if((p&need)==need){rows.push_back({x,b});seen[x]|=1<<b;detected++;}}}
 if(rows.empty())return 0;
 // Only seed known clauses on candidate-sized CNFs; otherwise leave to base.
 for(auto&c:src){guard();known.insert(c);} vector<pair<int,Row>> basis;
 // Cheap local relational closure: join two rows only if their symmetric
 // difference shrinks both inputs, with bounded variable incidence.
 map<int,vector<size_t>> index;for(size_t i=0;i<rows.size();i++)for(int v:rows[i].x)index[v].push_back(i);
 for(size_t i=0;i<rows.size()&&i<20000;i++){
  guard();Row a=rows[i];set<size_t> candidates;for(int v:a.x){auto& ix=index[v];if(ix.size()>128)continue;for(size_t j:ix)if(j<i)candidates.insert(j);}
  for(size_t j:candidates){Row b=rows[j],q=sumrow(a,b);if(q.x.size()>=min(a.x.size(),b.x.size()))continue;size_t before=rows.size();if(derive(a,b,q)&&rows.size()>before){for(int v:q.x)index[v].push_back(rows.size()-1);if(q.x.empty()&&q.b){writeproof(out);return 20;}}}
 }
 // Independent algebraic basis from the extracted + derived constraints.
 vector<Row> initial=rows;sparse(move(initial),basis);
 if(seen[V{}]&2){if(proof.empty()||!proof.back().empty())emit({});writeproof(out);return 20;}
 // Exchange newly derived unit clauses with original non-affine clauses via UP.
 V a(n+1,-1);bool change=true;while(change){guard();change=false;auto scan=[&](const vector<V>&cs){for(auto&c:cs){guard();int u=0,k=0;bool sat=false;for(int l:c){int v=a[abs(l)];if(v==(l>0)){sat=true;break;}if(v<0){u=l;k++;}}if(sat)continue;if(k==0)return false;if(k==1){a[abs(u)]=(u>0);change=true;}}return true;};if(!scan(src)||!scan(proof)){emit({});writeproof(out);return 20;}}
 V m=model(basis);if(!check(m)){for(int i=1;i<=n;i++)if(a[i]>=0)m[i]=a[i];}
 if(check(m)){ofstream o(out);o<<"v ";for(int i=1;i<=n;i++)o<<(m[i]?i:-i)<<' ';o<<"0\n";return 10;}return 0;}
int main(int argc,char**argv){if(argc!=4)return 2;deadline=Clock::now()+chrono::milliseconds(max(1,atoi(argv[3])));int s=0;try{if(readcnf(argv[1]))s=solve(argv[2]);}catch(Limit&){}catch(exception&e){cerr<<e.what()<<'\n';return 2;}cout<<"status="<<s<<" rows="<<detected<<" joins="<<joined<<" blocked="<<blocked<<" proof="<<proof.size()<<'\n';return s;}
