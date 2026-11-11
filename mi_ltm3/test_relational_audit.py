import copy
import random
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import experiment
import runtime
from design import make_case,opportunity_key,xor_cnf,dimacs
from relational_probe import close_relations,probe_relations
from probe import probe_cnf


class RelationAuditTests(unittest.TestCase):
    def test_three_row_cycle_requires_multistep_closure(self):
        cs=xor_cnf((1,2),0)+xor_cnf((2,3),0)+xor_cnf((1,3),1)
        old=probe_cnf(dimacs(3,cs))
        self.assertFalse(any(c['kind']=='conflict' for c in old['consequences']))
        new=probe_relations(dimacs(3,cs),budget_s=1)
        experiment.independently_audit_inferences(cs,new)
        conflict=next(c for c in new['consequences'] if c['kind']=='conflict')
        self.assertEqual(len(conflict['source_equations']),3)
        self.assertGreaterEqual(conflict['derivation_depth'],2)

    def test_transitive_relation_and_parent_cancellation(self):
        cs=xor_cnf((1,2),0)+xor_cnf((2,3),1)+xor_cnf((3,4),0)
        report=probe_cnf(dimacs(4,cs))
        report['consequences'],_=close_relations(report['xor_equations'])
        experiment.independently_audit_inferences(cs,report)
        row=next(c for c in report['consequences'] if c['variables']==[1,4])
        self.assertEqual(row['rhs'],1)
        self.assertEqual(len(row['source_equations']),3)
        # Sets compose by XOR: a repeated parent cancels rather than duplicates.
        for c in report['consequences']:
            self.assertEqual(len(c['source_equations']),len(set(c['source_equations'])))
        efficient=probe_relations(dimacs(4,cs),budget_s=1)
        self.assertFalse(efficient['consequences'])
        self.assertEqual(efficient['relational_closure']['stop_reason'],'binary_components')

    def test_incomplete_source_cannot_become_fact(self):
        cs=xor_cnf((1,2,3),0)[:-1]+xor_cnf((2,3,4),1)
        report=probe_relations(dimacs(4,cs),budget_s=1)
        self.assertEqual(len(report['xor_equations']),1)
        self.assertFalse(report['consequences'])

    def test_budget_and_expired_deadline(self):
        eqs=[dict(variables=[i,i+1],rhs=i%2) for i in range(1,30)]
        for pairs,derived,depth in [(0,64,4),(5,2,2),(100,0,4),(100,64,0)]:
            cs,st=close_relations(eqs,max_pairs=pairs,max_derived=derived,max_depth=depth)
            self.assertLessEqual(st['pairs_examined'],pairs)
            self.assertLessEqual(st['derived_rows'],derived)
            self.assertLessEqual(st['max_depth'],depth)
        cs,st=close_relations(eqs,deadline=time.perf_counter()-1)
        self.assertEqual(st['stop_reason'],'time_budget')
        self.assertFalse(cs)

    def test_200_random_small_cnf_independent_truth_and_provenance(self):
        rng=random.Random(813025)
        for _ in range(200):
            n=6;cs=[]
            for _ in range(rng.randrange(1,10)):
                vs=rng.sample(range(1,n+1),rng.choice((2,3)))
                block=xor_cnf(vs,rng.randrange(2))
                if rng.randrange(4)==0:block.pop()
                cs+=block
            report=probe_relations(dimacs(n,cs),budget_s=1)
            experiment.independently_audit_inferences(cs,report)
            models=[bits for bits in range(1<<n) if all(
                any(bool(bits>>(abs(l)-1)&1)==(l>0) for l in c) for c in cs)]
            for con in report['consequences']:
                self.assertTrue(all(sum((b>>(v-1))&1 for v in con['variables'])%2==con['rhs'] for b in models))

    def test_late_valid_sat_not_credited(self):
        case=make_case('random3_planted',0,generation=123)
        case['split']='train';case['feature_key']=opportunity_key(case['clauses'],case['n'])
        model='v '+' '.join(str(v if b else -v) for v,b in case['planted'].items())+' 0\n'
        with tempfile.TemporaryDirectory() as td:
            def late(*args):
                time.sleep(.03)
                return 10,model,.03
            with patch.object(experiment,'CAP_S',.02),patch.object(experiment,'solve',side_effect=late),patch.object(experiment,'OUT',Path(td)):
                row=experiment.run_arm(case,'BASE',0,None,Path(td))
            self.assertFalse(row['solved'])
            self.assertFalse(row['verified'])
            self.assertTrue(row['trial_audited'])
            self.assertEqual(row['status'],'UNKNOWN')
            self.assertEqual(row['candidate_status'],'SAT_ORIGINAL_VERIFIED')
            self.assertEqual(row['par2_s'],.04)

    def test_empty_policy_never_scans_features(self):
        case=make_case('random3_planted',0,generation=123)
        case['split']='holdout';case['feature_key']=opportunity_key(case['clauses'],case['n'])
        model='v '+' '.join(str(v if b else -v) for v,b in case['planted'].items())+' 0\n'
        policy=dict(positive_classes={},feature_classes={})
        with tempfile.TemporaryDirectory() as td:
            with patch.object(experiment,'solve',return_value=(10,model,.001)),patch.object(experiment,'opportunity_key',side_effect=AssertionError('unnecessary feature scan')),patch.object(experiment,'OUT',Path(td)):
                row=experiment.run_arm(case,'LTM_GATE',0,policy,Path(td))
        self.assertTrue(row['solved'])
        self.assertFalse(row['feature_computed'])
        self.assertEqual(row['reason'],'empty_policy_fast_fallback')

    def test_subprocess_timeout_has_no_two_second_grace(self):
        with patch.object(runtime.subprocess,'run',side_effect=runtime.subprocess.TimeoutExpired(['fake'],.02)) as run:
            rc,out,elapsed=runtime.solve_deadline(Path('fake.cnf'),1,.02)
        self.assertEqual(rc,0)
        self.assertEqual(run.call_args.kwargs['timeout'],.02)

    def test_tampered_provenance_fails_closed(self):
        cs=xor_cnf((1,2),0)+xor_cnf((2,3),0)+xor_cnf((1,3),1)
        report=probe_relations(dimacs(3,cs),budget_s=1)
        report=copy.deepcopy(report)
        report['consequences'][-1]['source_equations']=[0]
        with self.assertRaises(AssertionError):
            experiment.independently_audit_inferences(cs,report)


if __name__=='__main__':unittest.main()
