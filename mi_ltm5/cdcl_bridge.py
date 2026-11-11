"""LTM5 certified graph reduction feeding the native CDCL CNF reader.

Every added clause is a logical consequence of two COMPLETE source-XOR
encodings. No learned motifs, guesses, or conditional trail conclusions
are transferred as global facts. Original SHA/CNF remain untouched.
"""
from itertools import combinations
from mi_ltm4.graph_shadow import source_rows
from mi_ltm5.dynamic_graph import row_from_source,combine,audit

def derived_clauses(clauses,*,max_sources=96,max_pairs=2048,max_added=64):
 sources=source_rows(clauses,max_groups=30000)
 stats=dict(source_rows=len(sources),pairs=0,proof_checked=0,
            derived_units=0,derived_binary=0,added=0,gate="inactive")
 if len(sources)>max_sources: return [],stats
 existing={tuple(sorted(c)) for c in clauses}
 out=set()
 for i,j in combinations(range(len(sources)),2):
  if stats["pairs"]>=max_pairs or len(out)>=max_added:break
  a,b=row_from_source(sources,i),row_from_source(sources,j)
  if not (a.variables & b.variables):continue
  stats["pairs"]+=1
  d=combine(a,b)
  if not audit(d,sources):raise AssertionError("LTM5 invalid provenance")
  stats["proof_checked"]+=1
  vs=sorted(d.variables)
  if len(vs)>2:continue
  if len(vs)==0:
   if d.rhs:out.add(tuple())
   continue
  for mask in range(1<<len(vs)):
   if mask.bit_count()%2==d.rhs:continue
   clause=tuple(-v if mask>>k&1 else v for k,v in enumerate(vs))
   key=tuple(sorted(clause))
   if key not in existing:out.add(key)
  stats["derived_units" if len(vs)==1 else "derived_binary"]+=1
 result=sorted(out)[:max_added]
 stats["added"]=len(result)
 stats["gate"]="active" if result else "no_novel_clauses"
 return result,stats

def write_derived(original,output):
 raw=original.read_bytes()
 lines=raw.decode().splitlines()
 header=next((i for i,line in enumerate(lines) if line.startswith("p cnf ")),None)
 if header is None:raise ValueError("missing DIMACS header")
 fields=lines[header].split()
 n=int(fields[2]);declared=int(fields[3])
 clauses=[];current=[]
 for line in lines[header+1:]:
  if line.startswith(("c","%")):continue
  for t in line.split():
   lit=int(t)
   if lit:
    if abs(lit)>n:raise ValueError("variable outside DIMACS header")
    current.append(lit)
   else:
    clauses.append(tuple(current));current=[]
 if current or len(clauses)!=declared:raise ValueError("incomplete CNF")
 additions,stats=derived_clauses(clauses)
 # Preserve the source body verbatim; only modify count and append proved clauses.
 lines[header]=f"p cnf {n} {declared+len(additions)}"
 output.write_text("\n".join(lines)+"\n"+"".join(" ".join(map(str,c))+" 0\n" for c in additions))
 return stats
