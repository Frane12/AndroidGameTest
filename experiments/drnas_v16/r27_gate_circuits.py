#!/usr/bin/env python3
"""R27c: independently verify each 3-binary + 1-quaternary XOR bridge.

For each original GBD polynomial CNF, reconstruct all exact XOR blocks and
test whether each boundary variable's four residual clauses encode a complete
3-input AND / OR gate (possibly negated inputs). Every gate's 16-state Boolean
truth table is checked against its four ORIGINAL clauses.
No intervention, new learnt clause, or solver result is produced.
"""
import argparse, json, sys
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parent))
from r27_xor_residual_links import clauses, signature, first_pass, sha256

def evaluate(v, values):
    return (v>0)==values[abs(v)]

def classify(x, clauses4):
    b=[c for c in clauses4 if len(c)==2]
    w=[c for c in clauses4 if len(c)==4]
    if len(clauses4)!=4 or len(b)!=3 or len(w)!=1:
        return None
    bin_x=[]
    other=[]
    for cl in b:
        xs=[z for z in cl if abs(z)==x]
        if len(xs)!=1:return None
        bin_x.append(xs[0])
        others=[z for z in cl if abs(z)!=x]
        if len(others)!=1:return None
        other.extend(others)
    long_x=[z for z in w[0] if abs(z)==x]
    long_others=[z for z in w[0] if abs(z)!=x]
    if(len(long_x)!=1 or len(long_others)!=3 or len(set(map(abs,other)))!=3
       or len(set(bin_x))!=1 or long_x[0]!=-bin_x[0]
       or sorted(long_others)!=sorted(-z for z in other)):
        return None
    gate_type="AND" if bin_x[0]<0 else "OR"
    vars_=[x]+[abs(z) for z in other]
    # The four clauses must be equivalent, for ALL 16 assignments, to the
    # gate relation (not only equisatisfiable).
    for mask in range(16):
        values={v:bool(mask>>i&1) for i,v in enumerate(vars_)}
        cnf=all(any(evaluate(lit,values) for lit in cl) for cl in clauses4)
        in_value=[evaluate(z,values) for z in other]
        expected=(all(in_value) if gate_type=="AND"
                  else any(not z for z in in_value))
        relation=values[x]==expected
        if cnf!=relation:
            raise RuntimeError("Independent 16-state gate equivalence failed")
    return gate_type, tuple(other)

def inspect(path):
    n, count, widths, groups, _, _, _ = first_pass(path)
    xorvars=set(v for sup in groups for v in sup)
    by_output=defaultdict(list)
    other_residual=0
    other_motifs=Counter()
    for _,cl in clauses(path):
        sig=signature(cl)
        if sig is not None and sig[0] in groups:
            continue
        outputs={abs(z) for z in cl if abs(z) in xorvars}
        if len(outputs)==1 and len(outputs)<len({abs(z) for z in cl}):
            out=next(iter(outputs))
            by_output[out].append(cl)
        else:
            other_residual+=1
            other_motifs[(len(cl),len(outputs))]+=1
    gates={}
    failed=[]
    for x,source_clauses in by_output.items():
        result=classify(x,source_clauses)
        if result is None:
            failed.append((x,len(source_clauses)))
        else:
            gates[x]=result
    per_gate_input_fanout=Counter()
    number_of_negative_inputs=Counter()
    for x,(gate, inputs) in gates.items():
        per_gate_input_fanout.update(abs(z) for z in inputs)
        number_of_negative_inputs[sum(z<0 for z in inputs)]+=1
    eq_gate_output_count=Counter()
    gate_xor_degree=Counter()
    for support in groups:
        for v in support:
            if v in gates:
                gate_xor_degree[v]+=1
        eq_gate_output_count[sum(v in gates for v in support)]+=1
    output_types=Counter(g for g,inputs in gates.values())
    result=dict(xor_blocks=len(groups),xor_variables=len(xorvars),
        residual_output_variables=len(by_output),
        detected_complete_3input_gates=len(gates),
        gate_types=dict(output_types),
        gate_verification="16-state Boolean equivalence for every recognized gate",
        unclassified_output_variables=len(failed),
        unclassified_examples=failed[:12],
        residual_clauses_outside_one_xor_var=other_residual,
        other_residual_motifs={str(k):v for k,v in other_motifs.items()},
        all_interface_bridges_certified=(len(gates)==len(by_output) and
                                         other_residual==0),
        total_gate_clauses=sum(len(by_output[x]) for x in gates),
        external_gate_input_variables=len(per_gate_input_fanout),
        external_gate_input_fanout_hist=dict(Counter(per_gate_input_fanout.values())),
        signed_input_negative_count_hist=dict(number_of_negative_inputs),
        xor_blocks_by_number_of_gate_outputs=dict(eq_gate_output_count),
        xor_degree_on_gate_outputs=dict(Counter(gate_xor_degree.values())),
        gate_input_top_hubs=[{"variable":v,"gate_fanout":c}
            for v,c in per_gate_input_fanout.most_common(10)],
        sha256=sha256(path),source_file=Path(path).name,
        disclaimer="Conjunctive AND/OR gates are a discovered exact CNF encoding motif; "
                   "they do not establish cause of CaDiCaL-vs-Kissat runtime gap")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    root=Path(a.input)
    manifest=json.loads((root/"manifest.json").read_text())
    rows=[row for row in manifest["cases"] if
          row["family"]=="polynomial_gbd_original"]
    assert len(rows)==10
    results=[]
    for row in rows:
        file=root/row["path"]
        assert sha256(file)==row["sha256"]
        res=inspect(file)
        res["id"]=row["id"]
        results.append(res)
        print("R27C_GATE",json.dumps({
            "id":res["id"],
            "and_or":res["gate_types"],
            "certified":res["detected_complete_3input_gates"],
            "failures":res["unclassified_output_variables"],
            "all":res["all_interface_bridges_certified"],
            "gate_outputs_per_xor":res["xor_blocks_by_number_of_gate_outputs"]
        },sort_keys=True),flush=True)
    out=dict(protocol="DRNAS-R27C-CERTIFIED-XOR-AND-OR-MOTIFS-20261103-v1",
             method="full CNF exact parity + independent 16-state gate truth table",
             cases=results,
             every_interface_full_gate=all(x["all_interface_bridges_certified"] for x in results),
             total_gates=sum(x["detected_complete_3input_gates"] for x in results),
             total_and=sum(x["gate_types"].get("AND",0) for x in results),
             total_or=sum(x["gate_types"].get("OR",0) for x in results))
    Path(a.out).write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("R27C_FINAL",json.dumps({k:v for k,v in out.items() if k!="cases"},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
