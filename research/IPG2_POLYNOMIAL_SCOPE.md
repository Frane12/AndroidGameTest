# DRNAS IPG2-POLY — carefully bounded polynomial classes (2026-11-16)

## Two separate mathematical results, NOT a general P=NP algorithm

**A. Complete polynomial algorithm for PCMAX with <=2 distinct job durations.**
Input is an explicit scheduling instance (jobs p_j>0, m identical machines,
deadline T>=0); NOT an arbitrary original CNF encoding. Let a and b be its
two durations and A, B their counts. Let F_k(i) be the maximum number
of type-b jobs fitting in the first k machines with exactly i type-a jobs.
With F_0(0)=0 and F_0(i>0)=-infinity, use the recurrence

 F_(k+1)(i)=max_{u: 0<=u<=i, a*u<=T} [ F_k(i-u)+floor((T-a*u)/b) ]

Cap values at B. The schedule is feasible iff F_m(A)>=B.
Each transition allocates exactly u indistinguishable a-jobs to a machine
and fills its remaining space with as many b-jobs as possible; completeness
follows from all a-job count allocations being enumerated.

By merging indistinguishable jobs and capping m at the number of jobs n,
time is O(min(m,n)*A^2) integer arithmetic and memory O(A), where A
is chosen as the less frequent job type. The integers have input-bounded
bit lengths. This is genuinely polynomial in binary input size for this
restricted class, not a general PCMAX solution or a new complexity theorem.
Independent verifier: research/ipg2_dp_checker.py.

**B. Polynomial sufficient UNSAT detector for cubic three-edge-coloring CNFs
when the number of perfect matchings is at most a FIXED constant K=8.**

Reconstruct a 3-regular graph from ORIGINAL CNF clauses: for each job
exactly one of three colors is selected (ALO and all AMO clauses), and
source binary mutex clauses forbid equal colors on incident jobs.
The 3-job mutex triangles are required to form the precise 3-regular
line-graph incidence pattern. Any satisfying assignment of this CNF
would induce a 3-edge-coloring of that graph.

In a cubic graph, every color class of a 3-edge-coloring is a perfect
matching. Removing such a matching leaves a two-regular graph whose
cycles must all be EVEN so that the remaining two colors can alternate.
Therefore if EVERY perfect matching leaves an odd cycle, the
source CNF must be UNSAT.

Use an Edmonds blossom oracle O(V^3) at every branch of a
self-reduction that enumerates distinct perfect matchings. If more
than K are found, return UNKNOWN immediately. Since K is constant,
only polynomially many oracle branches are visited before completion
or cutoff, yielding polynomial worst-case detection on this restricted
CNF family. The proof certificate includes all matchings and a
concrete odd cycle for each. The independent checker redoes the
bounded perfect-matching enumeration and checks source clauses and
all parity witnesses. It never trusts a list of matchings alone.

For the Petersen graph there are six perfect matchings, and each
leaves two odd 5-cycles: this detects the class-2 obstruction.
References: Combinatorica 2024, Proposition 2.1 on six Petersen
perfect matchings; NetworkX blossom maximum matching documentation.

## Relationship to our previous original PCMAX example

The graph-edge-coloring CNF is a DIFFERENT representation of the
underlying Petersen scheduling obstruction than the earlier
45-variable/300-clause weighted-bin-packing CNF.
The polynomial graph certificate directly proves UNSAT only for
the source graph-edge-coloring encoding. The old 300-clause CNF
must NOT be marked verified by IPG2; its valid proof comes from
the previous IPG1 exact source-bound checker (exponential).

Arithmetic equivalence of the *underlying instances*: set p_e=3^u+3^v
for each edge e=(u,v), and T=sum_(v=0..9) 3^v. For the cubic graph
the total weight is 3T, hence every machine must have load exactly T.
The base-3 digits of that load force exactly one incident edge per
vertex on every machine (inductively no carries), which is precisely
the three-edge-coloring condition. This mathematical equivalence
does not itself supply a polynomial source-bound verifier for the
older 300-clause CNF. Bridging those proofs is a separate research task.

## Test discipline

Test 2 vs 3 machines on the identical jobs and deadlines, verify
small cases against an exact independent oracle, large cases
against an independent DP verifier, check genuine source CNF
Petersen/K3,3 graph encodings, reject forged/incomplete certificates,
and explicitly test that the original 300-clause CNF is unsupported
by the new polynomial graph source decoder.

This is a research prototype in Python, not yet an integrated
C++ DRNAS target. Do not replace the current IPG1/BDD/MG7 C++
solver or promote to main without broader source-frozen tests.

## Reproduce

 python3 research/ipg2_poly_benchmark.py

Requires NetworkX 3.4.2 for a polynomial maximum matching oracle.
All generated source bytes and certificate JSON files are archived
in the corresponding GitHub Actions artifact.
