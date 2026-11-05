/* DRNAS SAT R32b research-only native GF(2) shadow, v1.
 * Included ONLY by pinned upstream src/parse.c; search.c uses extern.
 * Captures the original DIMACS before Kissat's own preprocessing; never
 * injects clauses, literals, decisions, phases, restarts or solver settings.
 * Fixed budgets make out-of-scope formulas explicitly abstain.
 */
#ifndef DRNAS_R32B_SHADOW_H
#define DRNAS_R32B_SHADOW_H
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#define R32B_MAXVAR 2048
#define R32B_MAXCLAUSE 20000
#define R32B_MAXLITS 210000
#define R32B_MAXRECORD 22000
#define R32B_MAXEQ 1600
#define R32B_WORDS ((R32B_MAXVAR+63)/64)
#define R32B_MAXWIDTH 6

typedef struct { unsigned start, len; } r32b_cnf_clause;
typedef struct {
  unsigned char k,mask;
  unsigned short v[6];
} r32b_pattern;
typedef struct {
  unsigned char k,rhs;
  unsigned short v[6];
} r32b_eq;
typedef struct {
  unsigned short k;
  unsigned short id[2];
} r32b_occ;
static int r32b_active=-1, r32b_guard=0, r32b_looked=0;
static unsigned r32b_varmax=0, r32b_nclause=0, r32b_nlit=0;
static unsigned r32b_clause_start=0, r32b_too_wide=0;
static int r32b_literals[R32B_MAXLITS];
static r32b_cnf_clause r32b_clauses[R32B_MAXCLAUSE];
static r32b_pattern r32b_patterns[R32B_MAXRECORD];
static unsigned r32b_npattern=0, r32b_nresolved=0;
static r32b_eq r32b_eqs[R32B_MAXEQ];
static unsigned r32b_neq=0;
static unsigned char r32b_var_in_gf[R32B_MAXVAR+1];
static uint64_t r32b_basis[R32B_MAXEQ][R32B_WORDS];
static unsigned char r32b_basis_rhs[R32B_MAXEQ];
static unsigned short r32b_basis_pivot[R32B_MAXVAR+1];
static const char *r32b_guard_name(void) {
  if (r32b_guard==1) return "var_cap";
  if (r32b_guard==2) return "clause_cap";
  if (r32b_guard==3) return "literal_cap";
  if (r32b_guard==4) return "clause_width_cap";
  if (r32b_guard==5) return "record_cap";
  if (r32b_guard==6) return "equation_cap";
  return "none";
}
static double r32b_clock_us(void) {
  return 1e6 * (double)clock() / (double)CLOCKS_PER_SEC;
}
void r32b_capture_original_literal (int lit) {
  if (r32b_active<0) {
    const char *mode=getenv("R32B_MODE");
    r32b_active=(mode && !strcmp(mode,"shadow")) ? 1 : 0;
  }
  if (!r32b_active || r32b_guard) return;
  if (lit) {
    const unsigned var=(unsigned)(lit>0 ? lit:-lit);
    if (var>R32B_MAXVAR) {r32b_guard=1;return;}
    if (var>r32b_varmax) r32b_varmax=var;
    if (r32b_nlit>=R32B_MAXLITS) {r32b_guard=3;return;}
    if (r32b_nlit-r32b_clause_start>=256) {r32b_guard=4;return;}
    r32b_literals[r32b_nlit++]=lit;
  } else {
    if (r32b_nclause>=R32B_MAXCLAUSE) {r32b_guard=2;return;}
    r32b_clauses[r32b_nclause].start=r32b_clause_start;
    r32b_clauses[r32b_nclause].len=r32b_nlit-r32b_clause_start;
    ++r32b_nclause;
    r32b_clause_start=r32b_nlit;
  }
}
static int r32b_cmp_pattern(const void *aa,const void *bb){
  const r32b_pattern *a=(const r32b_pattern*)aa,*b=(const r32b_pattern*)bb;
  if (a->k!=b->k)return (int)a->k-(int)b->k;
  for(unsigned i=0;i<a->k;i++)if(a->v[i]!=b->v[i])
    return (int)a->v[i]-(int)b->v[i];
  return (int)a->mask-(int)b->mask;
}
static int r32b_same_support(const r32b_pattern *a,const r32b_pattern *b){
  if(a->k!=b->k)return 0;
  for(unsigned i=0;i<a->k;i++)if(a->v[i]!=b->v[i])return 0;
  return 1;
}
static int r32b_add_pattern (const int *lits,unsigned len) {
  if(len<2 || len>R32B_MAXWIDTH)return 0;
  if(r32b_npattern>=R32B_MAXRECORD){r32b_guard=5;return 0;}
  unsigned short vars[6];unsigned char neg[6];
  for(unsigned i=0;i<len;i++){
    int x=lits[i];unsigned v=(unsigned)(x>0?x:-x);
    if(!v || v>R32B_MAXVAR)return 0;
    vars[i]=(unsigned short)v;neg[i]=(unsigned char)(x<0);
  }
  for(unsigned i=1;i<len;i++){
    unsigned short v=vars[i];unsigned char s=neg[i];unsigned j=i;
    while(j && vars[j-1]>v){vars[j]=vars[j-1];neg[j]=neg[j-1];--j;}
    vars[j]=v;neg[j]=s;
  }
  for(unsigned i=1;i<len;i++)if(vars[i-1]==vars[i])return 0;
  r32b_pattern *p=&r32b_patterns[r32b_npattern++];
  memset(p,0,sizeof(*p));p->k=(unsigned char)len;
  for(unsigned i=0;i<len;i++){p->v[i]=vars[i];p->mask |= (neg[i]<<i);}
  return 1;
}
static void r32b_add_equation(const r32b_pattern *p,int rhs) {
  if(r32b_neq>=R32B_MAXEQ){r32b_guard=6;return;}
  r32b_eq *eq=&r32b_eqs[r32b_neq++];
  memset(eq,0,sizeof(*eq));
  eq->k=p->k;eq->rhs=(unsigned char)rhs;
  for(unsigned j=0;j<p->k;j++){
    eq->v[j]=p->v[j];
    r32b_var_in_gf[p->v[j]]=1;
  }
}
/* Clause-set soundness: a recognized XOR requires ALL forbidden
 * assignments, each as a complete matching support-width clause.
 * Hidden candidates are single-positive/single-negative resolvents
 * of original CNF clauses. Every resolvent is an original consequence.
 */
static void r32b_discover(void) {
  if (r32b_looked++ || r32b_guard || !r32b_active)return;
  static unsigned short pos[R32B_MAXVAR+1],neg[R32B_MAXVAR+1];
  static unsigned short pc[R32B_MAXVAR+1],nc[R32B_MAXVAR+1];
  memset(pos,0,sizeof(pos));memset(neg,0,sizeof(neg));
  memset(pc,0,sizeof(pc));memset(nc,0,sizeof(nc));
  for(unsigned ci=0;ci<r32b_nclause && !r32b_guard;ci++){
    const r32b_cnf_clause *cl=&r32b_clauses[ci];
    const int *vs=r32b_literals+cl->start;
    if(cl->len==1) {
      if(r32b_neq>=R32B_MAXEQ){r32b_guard=6;break;}
      const unsigned v=(unsigned)(vs[0]>0?vs[0]:-vs[0]);
      r32b_eq *e=&r32b_eqs[r32b_neq++];
      memset(e,0,sizeof(*e));e->k=1;e->v[0]=(unsigned short)v;
      e->rhs=(unsigned char)(vs[0]>0);r32b_var_in_gf[v]=1;
    }
    if(cl->len>=2 && cl->len<=6)r32b_add_pattern(vs,cl->len);
    for(unsigned j=0;j<cl->len;j++){
      unsigned v=(unsigned)(vs[j]>0?vs[j]:-vs[j]);
      if(v>R32B_MAXVAR){r32b_guard=1;break;}
      if(vs[j]>0){if(pc[v]<2){pc[v]++;pos[v]=(unsigned short)(ci+1);}}
      else{if(nc[v]<2){nc[v]++;neg[v]=(unsigned short)(ci+1);}}
    }
  }
  for(unsigned v=1;v<=r32b_varmax && !r32b_guard;v++){
    if(pc[v]!=1 || nc[v]!=1)continue;
    const r32b_cnf_clause *a=&r32b_clauses[pos[v]-1], *b=&r32b_clauses[neg[v]-1];
    if(!((a->len==2 && b->len>=2 && b->len<=6) ||
         (b->len==2 && a->len>=2 && a->len<=6)))continue;
    int tmp[12];unsigned k=0,taut=0;
    const r32b_cnf_clause *parents[2]={a,b};
    for(unsigned i=0;i<2;i++)for(unsigned j=0;j<parents[i]->len;j++){
      const int x=r32b_literals[parents[i]->start+j];
      if((unsigned)(x>0?x:-x)==v)continue;
      unsigned skip=0;
      for(unsigned h=0;h<k;h++){
        if(tmp[h]==x) {skip=1;break;}
        if(tmp[h]==-x) {taut=1;break;}
      }
      if(taut)break;
      if(!skip && k<12)tmp[k++]=x;
    }
    if(!taut && k>=2 && k<=6) {
      if(r32b_add_pattern(tmp,k))r32b_nresolved++;
    }
  }
  if(r32b_guard)return;
  qsort(r32b_patterns,r32b_npattern,sizeof(r32b_pattern),r32b_cmp_pattern);
  for(unsigned i=0;i<r32b_npattern && !r32b_guard;){
    unsigned j=i+1;uint64_t mask=1ULL<<r32b_patterns[i].mask;
    while(j<r32b_npattern && r32b_same_support(r32b_patterns+i,r32b_patterns+j)){
      mask|=1ULL<<r32b_patterns[j].mask;
      j++;
    }
    unsigned k=r32b_patterns[i].k;
    for(unsigned rhs=0;rhs<=1;rhs++){
      uint64_t required=0;
      for(unsigned m=0;m<(1u<<k);m++)
        if((__builtin_popcount(m)&1)!=(int)rhs)required|=1ULL<<m;
      if((mask&required)==required)r32b_add_equation(r32b_patterns+i,rhs);
    }
    i=j;
  }
}
static int r32b_reduce_bcp(signed char *assignment) {
  for(unsigned it=0;it<=r32b_varmax && !r32b_guard;it++){
    unsigned changed=0;
    for(unsigned ci=0;ci<r32b_nclause;ci++){
      const r32b_cnf_clause *cl=&r32b_clauses[ci];
      int unit=0,found=0;unsigned unseen=0;
      for(unsigned j=0;j<cl->len;j++){
        int lit=r32b_literals[cl->start+j];
        int val=assignment[lit>0?lit:-lit];
        if(val && ((lit>0)==(val>0))){found=1;break;}
        if(!val){unit=lit;unseen++;}
      }
      if(found)continue;
      if(!unseen)return 1;
      if(unseen==1){
        unsigned v=(unsigned)(unit>0?unit:-unit);
        signed char val=unit>0 ? 1:-1;
        if(assignment[v] && assignment[v]!=val)return 1;
        if(!assignment[v]){assignment[v]=val;changed++;}
      }
    }
    if(!changed)return 0;
  }
  return 2;
}
static void r32b_xor(uint64_t *a,const uint64_t *b,unsigned nwords) {
  for(unsigned k=0;k<nwords;k++)a[k]^=b[k];
}
static int r32b_lowest(uint64_t *a,unsigned nwords) {
  for(unsigned i=0;i<nwords;i++)if(a[i])
    return (int)(i*64+__builtin_ctzll(a[i])+1);
  return 0;
}
typedef struct {
 unsigned rank, extra, contradiction, bcp_units, original_assigned;
 int sample[12];unsigned nsample;
} r32b_gap;
static r32b_gap r32b_compute(const int *trail,unsigned trail_len){
  r32b_gap result;memset(&result,0,sizeof(result));
  static signed char assign[R32B_MAXVAR+1];
  memset(assign,0,sizeof(assign));
  for(unsigned i=0;i<trail_len;i++){
    int lit=trail[i];unsigned v=(unsigned)(lit>0?lit:-lit);
    if(!v || v>r32b_varmax || (assign[v] && assign[v]!=(lit>0?1:-1))) {
      result.contradiction=3;return result;
    }
    assign[v]=lit>0?1:-1;
  }
  result.original_assigned=trail_len;
  int bcp_conflict=r32b_reduce_bcp(assign);
  if(bcp_conflict){result.contradiction=2;return result;}
  for(unsigned v=1;v<=r32b_varmax;v++)result.bcp_units+=!!assign[v];
  memset(r32b_basis_pivot,0,sizeof(r32b_basis_pivot));
  const unsigned words=(r32b_varmax+63)/64;
  unsigned rows_used=0;
  for(unsigned e=0;e<r32b_neq;e++){
    uint64_t row[R32B_WORDS]={0};
    unsigned rhs=r32b_eqs[e].rhs;
    for(unsigned k=0;k<r32b_eqs[e].k;k++){
      unsigned v=r32b_eqs[e].v[k];
      if(assign[v])rhs^=(unsigned)(assign[v]>0);
      else row[(v-1)>>6]^=1ULL<<((v-1)&63);
    }
    int pivot;
    while((pivot=r32b_lowest(row,words)) && r32b_basis_pivot[pivot]){
      const unsigned b=r32b_basis_pivot[pivot]-1;
      r32b_xor(row,r32b_basis[b],words);
      rhs^=r32b_basis_rhs[b];
    }
    if(!pivot){
      if(rhs){result.contradiction=1;return result;}
    } else {
      if(rows_used>=R32B_MAXEQ){result.contradiction=4;return result;}
      memcpy(r32b_basis[rows_used],row,words*sizeof(uint64_t));
      r32b_basis_rhs[rows_used]=(unsigned char)rhs;
      r32b_basis_pivot[pivot]=(unsigned short)(++rows_used);
    }
  }
  result.rank=rows_used;
  /* Reverse-pivot elimination: each row remains a sound GF2 consequence. */
  for(int p=(int)r32b_varmax;p>=1;p--){
    unsigned source=r32b_basis_pivot[p];
    if(!source)continue;
    const uint64_t *br=r32b_basis[source-1];
    const unsigned word=(unsigned)(p-1)>>6;
    const uint64_t bit=1ULL<<((p-1)&63);
    for(int q=p-1;q>=1;q--)if(r32b_basis_pivot[q]){
      const unsigned idx=r32b_basis_pivot[q]-1;
      if(r32b_basis[idx][word]&bit){
        r32b_xor(r32b_basis[idx],br,words);
        r32b_basis_rhs[idx]^=r32b_basis_rhs[source-1];
      }
    }
  }
  for(unsigned row=0;row<rows_used;row++){
    unsigned pop=0;
    for(unsigned k=0;k<words;k++)pop+=__builtin_popcountll(r32b_basis[row][k]);
    if(pop==1){
      const int v=r32b_lowest(r32b_basis[row],words);
      if(v && !assign[v]){
        result.extra++;
        if(result.nsample<12)
          result.sample[result.nsample++]=r32b_basis_rhs[row]?v:-v;
      }
    }
  }
  return result;
}
void r32b_shadow_native_probe(const int *trail,unsigned n,unsigned mark) {
  if(!r32b_active)return;
  const double start=r32b_clock_us();
  if(!r32b_looked)r32b_discover();
  if(r32b_guard){
    printf("c R32B_PROBE mark=%u signal=INPUT_GUARD reason=%s"
           " vars=%u clauses=%u literals=%u elapsed_us=%.0f\n",
           mark,r32b_guard_name(),r32b_varmax,r32b_nclause,r32b_nlit,
           r32b_clock_us()-start);
    fflush(stdout);return;
  }
  if(n>1024){
    printf("c R32B_PROBE mark=%u signal=TRAIL_GUARD reason=trail_cap"
           " assignments=%u equations=%u elapsed_us=%.0f\n",
           mark,n,r32b_neq,r32b_clock_us()-start);
    fflush(stdout);return;
  }
  r32b_gap gap=r32b_compute(trail,n);
  const char *signal=gap.contradiction==1?"GF2_UNSAT":
      gap.contradiction==2?"ORIGINAL_BCP_CONFLICT":
      gap.contradiction==3?"TRAIL_INVALID":
      gap.contradiction==4?"ELIMINATION_CAP":
      gap.extra?"CONSISTENT_GAP":"CONSISTENT_NO_GAP";
  printf("c R32B_PROBE mark=%u signal=%s"
         " clauses=%u vars=%u equations=%u resolved=%u"
         " trail_assigned=%u bcp_assigned=%u rank=%u extra=%u"
         " probe_us=%.0f samples=",
         mark,signal,r32b_nclause,r32b_varmax,
         r32b_neq,r32b_nresolved,gap.original_assigned,
         gap.bcp_units,gap.rank,gap.contradiction?0:gap.extra,
         r32b_clock_us()-start);
  if(!gap.contradiction)for(unsigned i=0;i<gap.nsample;i++)
    printf("%s%d",i?",":"",gap.sample[i]);
  putchar('\n');fflush(stdout);
}
#endif
