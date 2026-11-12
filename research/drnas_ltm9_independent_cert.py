#!/usr/bin/env python3
"""Independent source-CNF checker for LTM9 counting certificates.

Does not use the LTM9 detector or generator. Every certificate row must
be an ORIGINAL positive CNF clause; every pair of rows, in every column,
must be incompatible via an ORIGINAL binary negative clause. With R>K
such rows and K columns, SAT is impossible by pigeonhole counting.

This verifies a mathematical certificate, NOT an LRAT/DRAT proof.
"""
import pathlib
import re
import tempfile

class CertificateError(ValueError):
    pass

def parse_dimacs(path):
    n=None
    expected=None
    count=0
    current=[]
    clauses=[]
    positive=set()
    negative_binary=set()
    with open(path,encoding="ascii",errors="replace") as f:
        for raw in f:
            row=raw.strip()
            if not row or row.startswith(("c","%")):
                continue
            if row.startswith("p "):
                parts=row.split()
                if n is not None or len(parts)!=4 or parts[1]!="cnf":
                    raise CertificateError("bad/duplicate DIMACS header")
                n=int(parts[2]);expected=int(parts[3])
                if n<0 or expected<0:raise CertificateError("negative DIMACS counts")
                continue
            if n is None:raise CertificateError("clauses before DIMACS header")
            for tok in row.split():
                try:lit=int(tok)
                except ValueError as e:raise CertificateError("noninteger literal") from e
                if lit!=0:
                    if abs(lit)>n:raise CertificateError("literal outside original n")
                    current.append(lit)
                else:
                    c=tuple(current);current=[]
                    clauses.append(c);count+=1
                    if c and all(v>0 for v in c) and len(set(c))==len(c):
                        positive.add(tuple(sorted(c)))
                    if len(c)==2 and c[0]<0 and c[1]<0 and c[0]!=c[1]:
                        negative_binary.add(tuple(sorted((-c[0],-c[1]))))
    if n is None or count!=expected or current:
        raise CertificateError("incomplete DIMACS source")
    return dict(n=n,clauses=clauses,positive=positive,negative_binary=negative_binary)

def certificate_from_stdout(stdout):
    header=[]
    rows=[]
    for line in stdout.splitlines():
        if line.startswith("c LTM9_PHP_CERT "):
            m=re.fullmatch(r"c LTM9_PHP_CERT rows=(\d+) cols=(\d+)",line.strip())
            if m is None:raise CertificateError("malformed certificate header")
            header.append((int(m[1]),int(m[2])))
        elif line.startswith("c LTM9_PHP_ROW"):
            toks=line.split()[2:]
            if not toks or toks[-1]!="0":raise CertificateError("unterminated certificate row")
            try:row=[int(v) for v in toks[:-1]]
            except ValueError as e:raise CertificateError("bad certificate integer") from e
            rows.append(row)
    if not header and not rows:return None
    if len(header)!=1:raise CertificateError("multiple/missing certificate headers")
    return dict(rows_expected=header[0][0],cols_expected=header[0][1],rows=rows)

def verify_php_certificate(source, certificate):
    if certificate is None:raise CertificateError("missing PHP certificate")
    n=source["n"]
    rows=certificate["rows"]
    k=certificate["cols_expected"]
    R=certificate["rows_expected"]
    if not 2<=k<=32 or R<=k or R!=len(rows) or R>33:
        raise CertificateError("invalid row/column cardinality")
    used=set()
    for row in rows:
        if len(row)!=k or any(v<=0 or v>n for v in row):
            raise CertificateError("invalid positive choice row")
        if len(set(row))!=k or any(v in used for v in row):
            raise CertificateError("repeated choice variable")
        if tuple(sorted(row)) not in source["positive"]:
            raise CertificateError("positive row absent from original CNF")
        used.update(row)
    checked=0
    for i in range(R):
        for j in range(i+1,R):
            for column in range(k):
                a=rows[i][column]
                b=rows[j][column]
                if tuple(sorted((a,b))) not in source["negative_binary"]:
                    raise CertificateError(f"missing original negative exclusion: {a} {b}")
                checked+=1
    return dict(proved=True,rows=R,cols=k,
                source_choice_rows=R,original_negative_exclusions_checked=checked,
                proof="counting-on-original-CNF",lrat=False)

def selftest():
    def php(k,R):
        cs=[]
        for i in range(R):
            cs.append([i*k+j+1 for j in range(k)])
        for i in range(R):
            for q in range(i+1,R):
                for j in range(k):
                    cs.append([-(i*k+j+1),-(q*k+j+1)])
        return k*R,cs
    def save(path,n,clauses):
        path.write_text(f"p cnf {n} {len(clauses)}\n"+
                        "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    n,cs=php(2,3)
    c=dict(rows_expected=3,cols_expected=2,rows=[[1,2],[3,4],[5,6]])
    with tempfile.TemporaryDirectory() as td:
        path=pathlib.Path(td)/"test.cnf"
        save(path,n,cs)
        s=parse_dimacs(path)
        assert verify_php_certificate(s,c)["original_negative_exclusions_checked"]==6
        out="c LTM9_PHP_CERT rows=3 cols=2\n"+"".join(
            "c LTM9_PHP_ROW "+" ".join(map(str,row))+" 0\n" for row in c["rows"])
        assert verify_php_certificate(s,certificate_from_stdout(out))["proved"]
        altered=[row[:] for row in cs]
        altered.remove([-1,-3])
        save(path,n,altered)
        for bad_source,bad_cert in (
            (parse_dimacs(path),c),
            (s,dict(c,rows=[[1,2],[3,4],[3,6]])),
            (s,dict(c,rows=[[1,2],[3,4],[5,7]])),
            (s,dict(c,rows=[[1,2],[3,4]])),
            (s,dict(c,rows=[[1,2],[3,4],[6,5]]))
        ):
            try:verify_php_certificate(bad_source,bad_cert)
            except CertificateError:pass
            else:raise AssertionError("incorrect certificate accepted")
    print("LTM9_INDEPENDENT_CERT_SELFTEST_PASS valid=1 adversarial_rejects=5",flush=True)

if __name__=="__main__":
    selftest()
