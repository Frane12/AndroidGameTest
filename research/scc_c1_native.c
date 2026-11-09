/* DRNAS SCC-C1: conservative SCC equivalence quotient on binary implication graph.
   C11 (gcc -std=c11). Transformation: x<->y or x<->!y if both
   literals belong to same SCC. No arbitrary implication or unit is substituted.
   Input DIMACS -> output DIMACS + signed 1-based mapping file. Fail closed.
   Pure 2-SAT contradictory SCC is independently checkable by reachability.
*/
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <limits.h>
#include <errno.h>
#include <time.h>
#include <ctype.h>

typedef struct {int to,next;} Edge;
typedef struct {int *items;size_t used,cap;} Ints;
static void fail(const char *msg){fprintf(stderr,"SCC_C1_FATAL %s\n",msg);exit(3);}
static void *allocn(size_t n,size_t sz){if(n && n>SIZE_MAX/sz)fail("overflow");void *p=calloc(n?n:1,sz);if(!p)fail("out_of_memory");return p;}
static void push(Ints *a,int x){if(a->used==a->cap){size_t cap=a->cap?a->cap*2:4096;if(cap<a->cap)fail("overflow");int *p=realloc(a->items,cap*sizeof(int));if(!p)fail("out_of_memory");a->items=p;a->cap=cap;}a->items[a->used++]=x;}
static double seconds(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))fail("clock");return t.tv_sec+t.tv_nsec/1e9;}
static int lit_id(int v){return 2*(abs(v)-1)+(v<0);}
static int cmpint(const void *a,const void *b){int x=*(const int *)a,y=*(const int *)b;return (x>y)-(x<y);}
static void add_edge(int a,int b,int *h,int *rh,Edge *e,Edge *re,int *used){int k=(*used)++;e[k]=(Edge){b,h[a]};h[a]=k;re[k]=(Edge){a,rh[b]};rh[b]=k;}
static void map_save(const char *path,int n,int newvars,int *map){FILE *f=fopen(path,"w");if(!f)fail("map_open");if(fprintf(f,"p map %d %d\n",n,newvars)<0)fail("map_write");for(int i=1;i<=n;i++)if(fprintf(f,"%d\n",map[i])<0)fail("map_write");if(fclose(f))fail("map_close");}
int main(int argc,char **argv){
 if(argc!=4){fprintf(stderr,"usage: drnas_scc INPUT.cnf OUTPUT.cnf MAP.txt\n");return 2;}
 double start=seconds();
 FILE *f=fopen(argv[1],"r");if(!f)fail("input_open");
 char *line=NULL;size_t ln=0;ssize_t nr;int n=-1,m=-1,header=0;
 Ints lits={0},offsets={0};push(&offsets,0);
 size_t binaries=0,units=0,empty=0;
 while((nr=getline(&line,&ln,f))>=0){
   (void)nr;char *s=line;while(isspace((unsigned char)*s))s++;
   if(!*s || *s=='c' || *s=='%')continue;
   if(!header){
     char extra;
     if(sscanf(s,"p cnf %d %d %c",&n,&m,&extra)!=2 || n<1 || n>200000 || m<0 || m>2000000)fail("bad_header_or_limit");
     header=1;continue;
   }
   while(*s){
     while(isspace((unsigned char)*s))s++;
     if(!*s)break;
     if(*s=='c'){break;}
     errno=0;char *end=NULL;long l=strtol(s,&end,10);
     if(end==s || errno || l < -n || l>n)fail("bad_literal");
     s=end;
     if(l==0){
        size_t len=lits.used-(size_t)offsets.items[offsets.used-1];
        if(len==0)empty++;else if(len==1)units++;else if(len==2)binaries++;
        if(lits.used>INT_MAX)fail("too_many_literals");
        push(&offsets,(int)lits.used);
        if(offsets.used>(size_t)m+1)fail("too_many_clauses");
     }else push(&lits,(int)l);
   }
 }
 free(line);fclose(f);
 if(!header || offsets.used!=(size_t)m+1 || (size_t)offsets.items[offsets.used-1]!=lits.used)fail("malformed_dimacs");
 if(units>INT_MAX || binaries > ((size_t)INT_MAX-units)/2)fail("too_many_edges");
 int nn=n*2,edgen=(int)(2*binaries+units);
 int *head=allocn(nn,sizeof(int)),*rhead=allocn(nn,sizeof(int));
 Edge *edges=allocn(edgen,sizeof(Edge)),*rev=allocn(edgen,sizeof(Edge));
 for(int i=0;i<nn;i++)head[i]=rhead[i]=-1;
 int k=0;
 for(int i=0;i<m;i++){
   int p=offsets.items[i],q=offsets.items[i+1];
   if(q-p==1){int a=lit_id(lits.items[p]);add_edge(a^1,a,head,rhead,edges,rev,&k);}
   if(q-p==2){int a=lit_id(lits.items[p]),b=lit_id(lits.items[p+1]);
     add_edge(a^1,b,head,rhead,edges,rev,&k);add_edge(b^1,a,head,rhead,edges,rev,&k);}
 }
 if(k!=edgen)fail("edge_count");
 unsigned char *vis=allocn(nn,sizeof(unsigned char));
 int *iter=allocn(nn,sizeof(int)),*stack=allocn(nn,sizeof(int)),*order=allocn(nn,sizeof(int)),*comp=allocn(nn,sizeof(int));
 for(int i=0;i<nn;i++)iter[i]=head[i];
 int olen=0;
 for(int root=0;root<nn;root++)if(!vis[root]){
   int top=0;stack[top++]=root;vis[root]=1;
   while(top){int v=stack[top-1],e=iter[v];
     while(e!=-1 && vis[edges[e].to])e=edges[e].next;
     iter[v]=e;
     if(e==-1){order[olen++]=v;top--;}
     else{iter[v]=edges[e].next;int u=edges[e].to;vis[u]=1;stack[top++]=u;}
   }
 }
 for(int i=0;i<nn;i++)comp[i]=-1;
 int comps=0;
 for(int t=olen-1;t>=0;t--){int root=order[t];if(comp[root]!=-1)continue;
   int top=0;stack[top++]=root;comp[root]=comps;
   while(top){int v=stack[--top];for(int e=rhead[v];e!=-1;e=rev[e].next){int u=rev[e].to;
     if(comp[u]==-1){comp[u]=comps;stack[top++]=u;}
   }}comps++;
 }
 int contradictory=(empty!=0);
 for(int i=0;i<n;i++)if(comp[2*i]==comp[2*i+1])contradictory=1;
 int *rmap=allocn(comps,sizeof(int));int *map=allocn(n+1,sizeof(int));
 int newvars=0;
 for(int i=1;i<=n;i++){
    int a=comp[lit_id(i)],b=comp[lit_id(-i)];
    if(contradictory){map[i]=i;continue;}
    if(!rmap[a] && !rmap[b]){newvars++;rmap[a]=newvars;rmap[b]=-newvars;}
    if(rmap[a]!=-rmap[b])fail("complement_scc_invariant");
    map[i]=rmap[a];
 }
 if(contradictory){
    FILE *out=fopen(argv[2],"w");if(!out)fail("output_open");
    if(fputs("p cnf 1 1\n0\n",out)==EOF)fail("output_write");
    if(fclose(out))fail("output_close");
    map_save(argv[3],n,n,map);
    printf("SCC_C1_FINAL {\"status\":\"UNSAT\",\"orig_vars\":%d,\"orig_clauses\":%d,\"binary_clauses\":%zu,\"new_vars\":%d,\"merged_vars\":0,\"elapsed_s\":%.6f}\n",n,m,binaries,n,seconds()-start);
    return 0;
 }
 if(newvars==n){
    /* Fast no-change mode: caller uses original CNF; no map/output is required. */
    printf("SCC_C1_FINAL {\"status\":\"NO_CHANGE\",\"orig_vars\":%d,\"orig_clauses\":%d,\"binary_clauses\":%zu,\"new_vars\":%d,\"merged_vars\":0,\"elapsed_s\":%.6f}\n",n,m,binaries,newvars,seconds()-start);
    return 0;
 }
 FILE *tmp=tmpfile();if(!tmp)fail("tmpfile");
 int *scratch=NULL;size_t sc_cap=0;int kept=0,tauts=0,removed=0;
 for(int i=0;i<m;i++){
   int p=offsets.items[i],q=offsets.items[i+1],len=q-p;
   if((size_t)len>sc_cap){int *t=realloc(scratch,(size_t)len*sizeof(int));if(!t)fail("scratch_alloc");scratch=t;sc_cap=len;}
   for(int z=0;z<len;z++){int l=lits.items[p+z];scratch[z]=l>0?map[l]:-map[-l];}
   qsort(scratch,len,sizeof(int),cmpint);
   int uniq=0,taut=0;
   for(int z=0;z<len;z++){
      if(uniq && scratch[z]==scratch[uniq-1])continue;
      scratch[uniq++]=scratch[z];
   }
   for(int z=0;z<uniq;z++){
      int other=-scratch[z];
      if(bsearch(&other,scratch,(size_t)uniq,sizeof(int),cmpint)){taut=1;break;}
   }
   if(taut){tauts++;continue;}
   for(int z=0;z<uniq;z++)if(fprintf(tmp,"%d ",scratch[z])<0)fail("tmp_write");
   if(fputs("0\n",tmp)==EOF)fail("tmp_write");
   kept++;removed+=len-uniq;
 }
 FILE *out=fopen(argv[2],"w");if(!out)fail("output_open");
 if(fprintf(out,"p cnf %d %d\n",newvars,kept)<0)fail("output_header");
 rewind(tmp);char buffer[65536];size_t nr2;
 while((nr2=fread(buffer,1,sizeof(buffer),tmp))>0)if(fwrite(buffer,1,nr2,out)!=nr2)fail("output_copy");
 if(ferror(tmp)||fclose(tmp)||fclose(out))fail("output_close");
 map_save(argv[3],n,newvars,map);
 printf("SCC_C1_FINAL {\"status\":\"REDUCED\",\"orig_vars\":%d,\"orig_clauses\":%d,\"binary_clauses\":%zu,\"new_vars\":%d,\"new_clauses\":%d,\"merged_vars\":%d,\"tautologies_removed\":%d,\"duplicate_literals_removed\":%d,\"elapsed_s\":%.6f}\n",n,m,binaries,newvars,kept,n-newvars,tauts,removed,seconds()-start);
 free(head);free(rhead);free(edges);free(rev);free(vis);free(iter);free(stack);free(order);free(comp);free(rmap);free(map);free(lits.items);free(offsets.items);free(scratch);
 return 0;
}
