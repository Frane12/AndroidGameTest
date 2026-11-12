#!/usr/bin/env python3
"""Independent CNF-local checker for LTM9B's graph-injection proof.
Validates an explicit certificate against exact original CNF clauses.
Never calls or imports the C++ detector.
"""
import re

def verify(clauses, stdout):
    rowprefix='c LTM9B_PHP_ROW '
    certprefix='c LTM9B_PHP_CERT '
    rows=[]; headers=[]
    for line in stdout.splitlines():
        if line.startswith(rowprefix):
            try: lits=[int(x) for x in line[len(rowprefix):].split()]
            except ValueError as exc: raise ValueError('noninteger proof row') from exc
            if not lits or lits[-1]!=0 or 0 in lits[:-1]:
                raise ValueError('missing row terminator')
            rows.append(lits[:-1])
        elif line.startswith(certprefix):
            m=re.fullmatch(r'c LTM9B_PHP_CERT rows=(\d+) cols=(\d+)',line)
            if not m: raise ValueError('malformed certificate header')
            headers.append((int(m[1]),int(m[2])))
    if not rows and not headers:return False
    if len(headers)!=1:raise ValueError('missing or repeated certificate header')
    count,k=headers[0]
    if count!=len(rows) or count<=k or not (2<=k<=32):
        raise ValueError('pigeonhole count invalid')
    positive_clauses={frozenset(c) for c in clauses if all(l>0 for l in c)}
    forbidden={frozenset(c) for c in clauses if len(c)==2 and all(l<0 for l in c)}
    used=set()
    for row in rows:
        if len(row)!=k or any(v<=0 for v in row) or len(set(row))!=k:
            raise ValueError('invalid positive row')
        if frozenset(row) not in positive_clauses:
            raise ValueError('positive row not in original CNF')
        if used.intersection(row):
            raise ValueError('overlapping rows')
        used.update(row)
    for i in range(count):
        for j in range(i+1,count):
            for col in range(k):
                if frozenset((-rows[i][col],-rows[j][col])) not in forbidden:
                    raise ValueError('missing negative exclusion clause')
    return True

def selftest():
    def php(k,r):
        def v(p,c):return p*k+c+1
        positives=[[v(p,c) for c in range(k)] for p in range(r)]
        negatives=[[-v(p,c),-v(q,c)] for c in range(k) for p in range(r) for q in range(p+1,r)]
        return positives,negatives
    pos,neg=php(3,4)
    out=''.join('c LTM9B_PHP_ROW '+' '.join(map(str,row))+' 0\n' for row in pos)
    out+='c LTM9B_PHP_CERT rows=4 cols=3\ns UNSATISFIABLE\n'
    assert verify(pos+neg,out)
    for damaged in (pos+neg[:-1],pos[:-1]+neg):
        try: verify(damaged,out)
        except ValueError: pass
        else: raise AssertionError('invalid certificate accepted')
    try: verify(pos+neg,out.replace('rows=4','rows=3'))
    except ValueError: pass
    else: raise AssertionError('invalid header accepted')
    assert not verify(pos+neg,'s UNSATISFIABLE\n')
    print('LTM9B_INDEPENDENT_CHECKER_SELFTEST_PASS good=1 bad=3')
if __name__=='__main__': selftest()
