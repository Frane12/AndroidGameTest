# DRNAS SAT — independent parity proof for 10 external Dubois formulas
Original CNFs pinned at fc0e735aff48989326f256121b5ed6fc585858c3; all raw and normalized SHA256 values match the V15.3.1 measured manifest.

For these examples named dubois(k), n = 3k variables; m = 8k clauses;
there are exactly 2k independent-*looking* XOR3 constraint rows but
rank(A) = 2k−1 and rank([A|b]) = 2k. Their combined equations yield
**0=1 in GF(2)**, a checkable UNSAT certificate.
Every quadruple of CNF clauses was checked against the corresponding
XOR3 truth table over all eight assignments.

| Formula | Vars | Clauses | XOR equations | rank A | rank [A|b] | Certificate equations |
|---|---:|---:|---:|---:|---:|---:|
| dubois22.cnf | 66 | 176 | 44 | 43 | 44 | 44 |
| dubois24.cnf | 72 | 192 | 48 | 47 | 48 | 48 |
| dubois25.cnf | 75 | 200 | 50 | 49 | 50 | 50 |
| dubois26.cnf | 78 | 208 | 52 | 51 | 52 | 52 |
| dubois27.cnf | 81 | 216 | 54 | 53 | 54 | 54 |
| dubois28.cnf | 84 | 224 | 56 | 55 | 56 | 56 |
| dubois29.cnf | 87 | 232 | 58 | 57 | 58 | 58 |
| dubois30.cnf | 90 | 240 | 60 | 59 | 60 | 60 |
| dubois50.cnf | 150 | 400 | 100 | 99 | 100 | 100 |
| dubois21.cnf | 63 | 168 | 42 | 41 | 42 | 42 |

**Scope:** This demonstrates the known hidden parity structure of this selected benchmark family; it is not a new mathematical theorem or general SAT breakthrough.
The certificate is independently reconstructible from public original clauses and does not rely on trusting solver status.
