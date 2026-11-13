import ast,itertools,json,pathlib,random,subprocess,tempfile,time
module=ast.parse(open('research/drnas_xor_component_study.py').read());fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='verify')
ns={'json':json,'time':time};exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'verify','exec'),ns)
r=random.Random(6719)
with tempfile.TemporaryDirectory() as td:
 for sample in range(60):
  n=r.randint(2,6);clauses=[]
  for _ in range(r.randint(1,7)):
   vs=r.sample(range(1,n+1),r.randint(2,min(4,n)));rhs=r.randrange(2)
   for bits in range(1<<len(vs)):
    if bits.bit_count()%2!=rhs:clauses.append([-v if bits>>j&1 else v for j,v in enumerate(vs)])
  for _ in range(r.randint(0,2)):
   v=r.randint(1,n);clauses.append([v if r.randrange(2) else -v])
  cnf=pathlib.Path(td)/'f.cnf';cert=pathlib.Path(td)/'proof'
  cnf.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
  got=json.loads(subprocess.check_output(['./compiled/xor_component_study',str(cnf),str(cert)],text=True));ns['verify'](cnf,cert)
  models=[x for x in itertools.product((False,True),repeat=n) if all(any(x[abs(lit)-1]==(lit>0) for lit in c) for c in clauses)]
  for line in cert.read_text().splitlines():
   rec=json.loads(line)
   if rec['type']=='unit':assert all(m[abs(rec['lit'])-1]==(rec['lit']>0) for m in models)
   elif rec['type']=='contradiction':assert not models
print('60 randomized formulas: proofs verified and checked by exhaustive assignments')
